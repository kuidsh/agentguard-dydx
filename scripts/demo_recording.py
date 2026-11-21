"""Script for the 2-minute screen recording of agentguard.

  python scripts/demo_recording.py --rehearse   # dry-run: live testnet prices, simulated $2,000 account, sends nothing
  python scripts/demo_recording.py              # LIVE testnet: needs a funded wallet + AGENTGUARD_SUBMITTER=dydx-testnet

Four beats (about 2 minutes with the built-in pauses):
  1) an in-policy order is allowed (live mode: placed on testnet with the builder code)
  2) an oversized order is rejected, with reasons
  3) operator kill switch on -> the same small order is blocked
  4) the hash-chained audit log verifies
"""
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from agentguard import mcp_server
from agentguard.audit import AuditLog, verify
from agentguard.executor import DryRunSubmitter
from agentguard.guard import AccountState
from agentguard.indexer import TESTNET_INDEXER, Indexer
from agentguard.policy import Policy
from agentguard.service import GuardService, StaticState

REHEARSE = "--rehearse" in sys.argv
PAUSE = 0 if "--fast" in sys.argv else 3


def build():
    if not REHEARSE:
        return mcp_server.build_service(), os.environ.get("AGENTGUARD_AUDIT", ".agentguard/audit.jsonl")
    mcp_server.load_env_file()
    pol = Policy.load(os.environ.get("AGENTGUARD_POLICY", "examples/policy.json"))
    mkt = Indexer(TESTNET_INDEXER).market_state(set(pol.allowed_markets))
    acct = AccountState(equity=Decimal("2000"), free_collateral=Decimal("1500"), positions={},
                        day_start_equity=Decimal("2000"))
    path = ".agentguard/rehearsal.jsonl"
    Path(path).unlink(missing_ok=True)
    return GuardService(pol, StaticState(acct, mkt), AuditLog(path), submitter=DryRunSubmitter()), path


def show(res):
    verdict = "ALLOWED" if res["allowed"] else "REJECTED"
    print(f"  -> {verdict}")
    for r in res["reasons"]:
        print(f"     reason: {r}")
    if res.get("submission"):
        sub = res["submission"]
        print("     submission:", json.dumps({k: v for k, v in sub.items() if k not in ("raw_log", "fill", "ts")}))
        if sub.get("fill"):
            print("     on-chain result:", json.dumps(sub["fill"]))
    if res.get("order") and res["order"].get("builder_code"):
        print("     builder code:", res["order"]["builder_code"])


def beat(title):
    print(f"\n=== {title}")
    time.sleep(PAUSE)


svc, audit_path = build()
print(f"agentguard demo | mode: {'REHEARSAL (dry-run, nothing sent)' if REHEARSE else 'LIVE TESTNET'} | "
      f"submitter: {svc.submitter.name}")

beat("1. Agent places a small BTC order (inside policy)")
show(svc.place(dict(market="BTC-USD", side="BUY", size="0.001", order_type="MARKET", client_note="demo entry")))
time.sleep(PAUSE)

beat("2. Agent tries an oversized order (5 BTC) -> must be rejected")
show(svc.place(dict(market="BTC-USD", side="BUY", size="5", order_type="MARKET", client_note="demo oversized")))
time.sleep(PAUSE)

beat("3. Operator flips the kill switch (what `agentguard kill on` does) -> everything blocked")
svc.set_kill_switch(True, who="operator", reason="demo")
show(svc.place(dict(market="BTC-USD", side="BUY", size="0.001", order_type="MARKET", client_note="after kill")))
svc.set_kill_switch(False, who="operator", reason="demo over")
time.sleep(PAUSE)

beat("4. Audit log: every request, rejection and submission, hash-chained")
ok, n, msg = verify(audit_path)
print(f"  verify {audit_path}: {'OK' if ok else 'BROKEN'}, {n} records, {msg}")
