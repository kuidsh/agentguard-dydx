"""Save real testnet Indexer responses to tests/fixtures (public data; address is redacted to a placeholder)."""
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = "https://indexer.v4testnet.dydx.exchange/v4"
OUT = Path("tests/fixtures")


def get(path: str):
    req = urllib.request.Request(BASE + path, headers={"Accept": "application/json", "User-Agent": "agentguard-fixtures"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def main(addr: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mk = get("/perpetualMarkets")
    mk["markets"] = {k: v for k, v in mk["markets"].items() if k in ("BTC-USD", "ETH-USD")}
    items = {"perpetualMarkets.json": mk,
             "subaccount.json": get(f"/addresses/{addr}/subaccountNumber/0"),
             "historical-pnl.json": get(f"/historical-pnl?address={addr}&subaccountNumber=0")}
    for name, data in items.items():
        txt = json.dumps(data, indent=2).replace(addr, "dydx1testaddressredacted")
        (OUT / name).write_text(txt)
        print("saved", name)


if __name__ == "__main__":
    a = os.environ.get("AGENTGUARD_ADDRESS") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not a:
        sys.exit("set AGENTGUARD_ADDRESS")
    main(a)
