"""The guarded service: policy + state + guard + audit + submitter, with a kill switch.

Every request is logged before and after the decision, including rejected ones,
so a reviewer can replay exactly what the agent asked for and why it was blocked.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict
from decimal import Decimal

from .audit import AuditLog
from .executor import DryRunSubmitter, Submitter
from .guard import AccountState, MarketState, OrderIntent, evaluate, pnl_today
from .policy import Policy


class StateSource:
    """Anything that returns (AccountState, MarketState). The Indexer adapter or a test fake."""

    def snapshot(self, orders_last_minute: int) -> tuple[AccountState, MarketState]:  # pragma: no cover
        raise NotImplementedError


class GuardService:
    def __init__(self, policy: Policy, state: StateSource, audit: AuditLog,
                 submitter: Submitter | None = None, clock=time.time):
        self.policy = policy
        self.state = state
        self.audit = audit
        self.submitter = submitter or DryRunSubmitter()
        self.kill_switch = False
        self._clock = clock
        self._recent: deque = deque()
        self.audit.append("service_start", {"policy": policy.to_dict(), "submitter": self.submitter.name})

    def _rate(self) -> int:
        now = self._clock()
        while self._recent and now - self._recent[0] > 60:
            self._recent.popleft()
        return len(self._recent)

    def check(self, intent_dict: dict) -> dict:
        intent = OrderIntent.from_dict(intent_dict)
        acct, mkt = self.state.snapshot(self._rate())
        d = evaluate(intent, acct, mkt, self.policy, self.kill_switch)
        return {"allowed": d.allowed, "reasons": d.reasons, "checks": d.checks, "order": d.order}

    def place(self, intent_dict: dict) -> dict:
        self.audit.append("order_requested", {"intent": intent_dict})
        try:
            result = self.check(intent_dict)
        except Exception as e:  # malformed input or state failure: deny and log
            result = {"allowed": False, "reasons": [f"error: {e}"], "checks": {}, "order": None}
        if not result["allowed"]:
            self.audit.append("order_rejected", result)
            return result
        self._recent.append(self._clock())
        sub = self.submitter.submit(result["order"])
        self.audit.append("order_submitted", {"order": result["order"], "checks": result["checks"], "submitter": sub})
        return dict(result, submission=sub)

    def set_kill_switch(self, on: bool, who: str, reason: str = "") -> dict:
        self.kill_switch = bool(on)
        self.audit.append("kill_switch", {"on": self.kill_switch, "by": who, "reason": reason})
        return {"kill_switch": self.kill_switch}

    def status(self) -> dict:
        acct, mkt = self.state.snapshot(self._rate())
        return {"kill_switch": self.kill_switch, "network": self.policy.network,
                "submitter": self.submitter.name,
                "equity": str(acct.equity), "pnl_today": str(pnl_today(acct)),
                "net_transfers_today": str(acct.net_transfers_today),
                "positions": {k: str(v) for k, v in acct.positions.items()},
                "orders_last_minute": self._rate(),
                "builder_fee_ppm": self.policy.builder_fee_ppm}


class StaticState(StateSource):
    """Fixed state for demos and tests; positions update when orders are 'filled' in dry-run."""

    def __init__(self, acct: AccountState, mkt: MarketState):
        self.acct, self.mkt = acct, mkt

    def snapshot(self, orders_last_minute: int):
        a = AccountState(**{**asdict(self.acct), "orders_last_minute": orders_last_minute})
        return a, self.mkt

    def apply_fill(self, order: dict):
        size = Decimal(order["size"]) * (1 if order["side"] == "BUY" else -1)
        pos = dict(self.acct.positions)
        pos[order["market"]] = Decimal(pos.get(order["market"], 0)) + size
        self.acct = AccountState(**{**asdict(self.acct), "positions": pos})
