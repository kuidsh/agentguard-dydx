"""Read-only dYdX v4 Indexer client: account and market state for the guard.

Endpoints (docs.dydx.xyz/indexer-client/http):
  GET /addresses/{address}/subaccountNumber/{n}
  GET /perpetualMarkets[?market=BTC-USD]
  GET /historical-pnl, GET /transfers   (daily-loss baseline, net of deposits/withdrawals)
Response field names (equity, freeCollateral, openPerpetualPositions, oraclePrice,
status) are parsed defensively; confirm against a live testnet response.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from .guard import AccountState, MarketState

TESTNET_INDEXER = "https://indexer.v4testnet.dydx.exchange/v4"
_TS = "%Y-%m-%dT%H:%M:%S.000Z"
# /transfers `type` is relative to the queried subaccount (checked against testnet, 2026-11-20)
TRANSFER_SIGN = {"DEPOSIT": 1, "TRANSFER_IN": 1, "WITHDRAWAL": -1, "TRANSFER_OUT": -1}

Fetch = Callable[[str], dict]


def http_fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "agentguard/0.1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


class Indexer:
    def __init__(self, base_url: str = TESTNET_INDEXER, fetch: Fetch = http_fetch):
        self.base = base_url.rstrip("/")
        self.fetch = fetch

    def market_state(self, markets=None) -> MarketState:
        data = self.fetch(f"{self.base}/perpetualMarkets")
        prices, active = {}, set()
        for tkr, m in (data.get("markets") or {}).items():
            if markets and tkr not in markets:
                continue
            if m.get("oraclePrice") not in (None, ""):
                prices[tkr] = Decimal(str(m["oraclePrice"]))
            if str(m.get("status", "ACTIVE")).upper() == "ACTIVE":
                active.add(tkr)
        return MarketState(oracle_prices=prices, active=frozenset(active))

    def day_start_equity(self, address: str, subaccount: int, now: datetime | None = None) -> Decimal | None:
        """Equity at the last snapshot at or before 00:00 UTC today, from /historical-pnl; None if no history."""
        base = self.day_start(address, subaccount, now)
        return base[0] if base else None

    def day_start(self, address: str, subaccount: int,
                  now: datetime | None = None) -> tuple[Decimal, str] | None:
        """(equity, createdAt) of the last /historical-pnl snapshot at or before 00:00 UTC; None if no history.
        createdAt is where deposits/withdrawals start counting against today's PnL."""
        now = now or datetime.now(timezone.utc)
        midnight = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        q = urllib.parse.urlencode({"address": address, "subaccountNumber": subaccount,
                                    "createdBeforeOrAt": midnight.strftime(_TS)})
        try:
            rows = self.fetch(f"{self.base}/historical-pnl?{q}").get("historicalPnl") or []
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            rows = []  # unknown/unfunded subaccount has no history
        if not rows:
            return None
        latest = max(rows, key=lambda r: r.get("createdAt", ""))
        return Decimal(str(latest["equity"])), str(latest.get("createdAt") or midnight.strftime(_TS))

    def net_transfers_since(self, address: str, subaccount: int, since: str, limit: int = 100) -> Decimal:
        """USDC deposited or transferred in, minus withdrawn or transferred out, after `since` (ISO, UTC).
        Fails closed (raises) on an unknown transfer type or a full page, rather than under-counting."""
        q = urllib.parse.urlencode({"address": address, "subaccountNumber": subaccount, "limit": limit})
        try:
            rows = self.fetch(f"{self.base}/transfers?{q}").get("transfers") or []
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            rows = []
        recent = [t for t in rows if str(t.get("createdAt", "")) > since]
        if len(rows) >= limit and len(recent) == len(rows):
            raise RuntimeError(f"{limit}+ transfers since {since}; refusing to guess the daily-loss baseline")
        net = Decimal(0)
        for t in recent:
            sign = TRANSFER_SIGN.get(str(t.get("type", "")).upper())
            if sign is None:
                raise RuntimeError(f"unknown transfer type {t.get('type')!r}; refusing to guess the daily-loss baseline")
            net += sign * Decimal(str(t["size"]))
        return net

    def account_state(self, address: str, subaccount: int, day_start_equity: Decimal | None,
                      orders_last_minute: int = 0, net_transfers_today: Decimal = Decimal(0)) -> AccountState:
        try:
            data = self.fetch(f"{self.base}/addresses/{address}/subaccountNumber/{subaccount}")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            data = {"subaccount": {}}  # unfunded/new subaccount: zero equity, so the guard rejects opening orders
        sub = data.get("subaccount", data)
        equity = Decimal(str(sub.get("equity", "0")))
        free = Decimal(str(sub.get("freeCollateral", "0")))
        pos = {}
        for tkr, p in (sub.get("openPerpetualPositions") or {}).items():
            size = Decimal(str(p.get("size", "0")))
            if str(p.get("side", "")).upper() == "SHORT" and size > 0:
                size = -size
            pos[tkr] = size
        if day_start_equity is None:  # no baseline: today starts now, so earlier transfers don't count
            day_start_equity, net_transfers_today = equity, Decimal(0)
        return AccountState(equity=equity, free_collateral=free, positions=pos,
                            day_start_equity=day_start_equity, orders_last_minute=orders_last_minute,
                            net_transfers_today=net_transfers_today)
