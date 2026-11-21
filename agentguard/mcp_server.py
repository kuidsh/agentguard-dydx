"""MCP server: the only trading surface the AI agent sees.

Tools exposed to the agent: get_policy, check_order, place_order, get_status, audit_tail.
The kill switch is deliberately NOT an agent tool: the operator flips it with the CLI
(`agentguard kill on|off`), which writes a flag file the server reads on every call.

Run:  AGENTGUARD_POLICY=examples/policy.json agentguard-mcp            (dry-run, testnet data)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .audit import AuditLog
from .indexer import TESTNET_INDEXER, Indexer
from .policy import Policy
from .service import GuardService, StateSource

KILL_FILE = Path(os.environ.get("AGENTGUARD_KILL_FILE", ".agentguard/KILL"))


class IndexerState(StateSource):
    def __init__(self, idx: Indexer, address: str, subaccount: int, markets):
        self.idx, self.address, self.subaccount, self.markets = idx, address, subaccount, markets
        self.day_start: Decimal | None = None
        self._since: str | None = None   # transfers after this timestamp are netted out of today's PnL
        self._day = None

    def snapshot(self, orders_last_minute: int, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        if self.day_start is None or self._day != now.date():  # equity at 00:00 UTC from /historical-pnl
            self._day = now.date()
            base = self.idx.day_start(self.address, self.subaccount, now)
            self.day_start, self._since = base if base else (None, None)
        net = (self.idx.net_transfers_since(self.address, self.subaccount, self._since)
               if self._since else Decimal(0))
        acct = self.idx.account_state(self.address, self.subaccount, self.day_start, orders_last_minute, net)
        if self.day_start is None:  # no history yet (new account): today's baseline is this first snapshot
            self.day_start = acct.equity
            self._since = now.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return acct, self.idx.market_state(self.markets)


def load_env_file(path: str | None = None) -> None:
    """Load KEY=VALUE lines from .env into os.environ (existing variables win). Values are never printed."""
    f = Path(path or os.environ.get("AGENTGUARD_ENV", ".env"))
    if not f.is_file():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def build_service() -> GuardService:
    load_env_file()
    pol = Policy.load(os.environ.get("AGENTGUARD_POLICY", "examples/policy.json"))
    if pol.network != "testnet":
        raise SystemExit("v0.1 runs on testnet only")
    idx = Indexer(os.environ.get("AGENTGUARD_INDEXER", TESTNET_INDEXER))
    state = IndexerState(idx, os.environ["AGENTGUARD_ADDRESS"], int(os.environ.get("AGENTGUARD_SUBACCOUNT", "0")),
                         set(pol.allowed_markets))
    submitter = None  # dry-run unless the operator opts in
    if os.environ.get("AGENTGUARD_SUBMITTER") == "dydx-testnet":
        from .executor import DydxTestnetSubmitter
        submitter = DydxTestnetSubmitter(address=os.environ["AGENTGUARD_ADDRESS"],
                                         subaccount=int(os.environ.get("AGENTGUARD_SUBACCOUNT", "0")))
    return GuardService(pol, state, AuditLog(os.environ.get("AGENTGUARD_AUDIT", ".agentguard/audit.jsonl")),
                        submitter=submitter)


def main() -> None:  # pragma: no cover
    svc = build_service()
    mcp = FastMCP("agentguard-dydx")

    def sync_kill():
        on = KILL_FILE.exists()
        if on != svc.kill_switch:
            svc.set_kill_switch(on, who="operator-file", reason=KILL_FILE.read_text()[:200] if on else "")

    @mcp.tool()
    def get_policy() -> dict:
        """Return the risk policy the operator set. Orders outside it are rejected."""
        return svc.policy.to_dict()

    @mcp.tool()
    def check_order(market: str, side: str, size: str, order_type: str = "LIMIT",
                    price: str | None = None, reduce_only: bool = False) -> dict:
        """Dry check: would this order pass the policy? Returns reasons and computed exposure. Sends nothing."""
        sync_kill()
        return svc.check(dict(market=market, side=side, size=size, order_type=order_type,
                              price=price, reduce_only=reduce_only))

    @mcp.tool()
    def place_order(market: str, side: str, size: str, order_type: str = "LIMIT",
                    price: str | None = None, reduce_only: bool = False, note: str = "") -> dict:
        """Place an order through the guard. Rejected orders are logged with reasons. `note` should say why."""
        sync_kill()
        return svc.place(dict(market=market, side=side, size=size, order_type=order_type,
                              price=price, reduce_only=reduce_only, client_note=note))

    @mcp.tool()
    def get_status() -> dict:
        """Equity, today's PnL, positions, rate-limit usage and kill-switch state."""
        sync_kill()
        return svc.status()

    @mcp.tool()
    def audit_tail(n: int = 10) -> list:
        """Last n audit records (hash-chained)."""
        return svc.audit.tail(min(max(n, 1), 100))

    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
