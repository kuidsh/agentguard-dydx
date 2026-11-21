"""Operator CLI (the human side).

  agentguard kill on --reason "volatility"    # block all new orders now
  agentguard kill off
  agentguard verify .agentguard/audit.jsonl    # check the hash chain
  agentguard demo                              # offline walkthrough with example state
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from .audit import AuditLog, verify
from .guard import AccountState, MarketState
from .mcp_server import KILL_FILE
from .policy import Policy
from .service import GuardService, StaticState


def demo(audit_path: str) -> list[dict]:
    pol = Policy(builder_address="dydx1examplebuilderaddressxxxxxxxxxxxxxxxxxxx", builder_fee_ppm=300)
    state = StaticState(
        AccountState(equity=Decimal("2000"), free_collateral=Decimal("1500"),
                     positions={"BTC-USD": Decimal("0.01")}, day_start_equity=Decimal("2100")),
        MarketState(oracle_prices={"BTC-USD": Decimal("90000"), "ETH-USD": Decimal("3000")},
                    active=frozenset({"BTC-USD", "ETH-USD"})))
    svc = GuardService(pol, state, AuditLog(audit_path))
    steps = [
        ("Small ETH buy near oracle", dict(market="ETH-USD", side="BUY", size="0.2", price="3005", client_note="trend entry")),
        ("Oversized BTC buy", dict(market="BTC-USD", side="BUY", size="0.05", price="90100")),
        ("Unlisted market", dict(market="DOGE-USD", side="BUY", size="100", price="0.2")),
        ("Limit far from oracle", dict(market="ETH-USD", side="SELL", size="0.1", price="2800")),
    ]
    out = []
    for label, intent in steps:
        res = svc.place(intent)
        if res["allowed"]:
            state.apply_fill(res["order"])
        out.append({"step": label, **res})
    svc.set_kill_switch(True, who="operator", reason="demo")
    out.append({"step": "Any order with kill switch on", **svc.place(dict(market="ETH-USD", side="BUY", size="0.01", price="3000"))})
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="agentguard")
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kill")
    k.add_argument("state", choices=["on", "off"])
    k.add_argument("--reason", default="")
    v = sub.add_parser("verify")
    v.add_argument("path")
    d = sub.add_parser("demo")
    d.add_argument("--audit", default=".agentguard/demo-audit.jsonl")
    p = sub.add_parser("policy-check")
    p.add_argument("path")
    a = ap.parse_args(argv)

    if a.cmd == "kill":
        KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
        if a.state == "on":
            KILL_FILE.write_text(a.reason or "manual")
        elif KILL_FILE.exists():
            KILL_FILE.unlink()
        print(f"kill switch {a.state}")
    elif a.cmd == "verify":
        ok, n, msg = verify(a.path)
        print(f"{'OK' if ok else 'BROKEN'}: {n} records, {msg}")
        raise SystemExit(0 if ok else 1)
    elif a.cmd == "policy-check":
        print(json.dumps(Policy.load(a.path).to_dict(), indent=2))
    else:
        Path(a.audit).unlink(missing_ok=True)
        for r in demo(a.audit):
            print(f"- {r['step']}: {'ALLOWED' if r['allowed'] else 'REJECTED'} {'; '.join(r['reasons'])}")


if __name__ == "__main__":
    main()
