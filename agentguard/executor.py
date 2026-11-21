"""Order submission behind the guard.

v0.1 ships two submitters:
  DryRunSubmitter      - records the order, sends nothing (default)
  DydxTestnetSubmitter - places the order on dYdX TESTNET via the official
                         dydx-v4-client (optional dependency). Mainnet is refused.
The signing key comes only from the DYDX_TESTNET_MNEMONIC env var set by the
operator; agentguard never stores, logs or returns it.
"""
from __future__ import annotations

import os
import random
import time
from typing import Protocol


class Submitter(Protocol):
    name: str

    def submit(self, order: dict) -> dict: ...


class DryRunSubmitter:
    name = "dry-run"

    def __init__(self):
        self.sent: list[dict] = []

    def submit(self, order: dict) -> dict:
        self.sent.append(order)
        return {"status": "DRY_RUN", "client_id": random.randint(1, 2**31 - 1), "ts": time.time()}


def confirm_fill(fetch, base: str, address: str, subaccount: int, client_id: int,
                 timeout: float = 12.0, interval: float = 2.0, sleep=time.sleep) -> dict:
    """Poll the Indexer until the order with `client_id` shows up, and summarize what really happened.

    status: FILLED | PARTIALLY_FILLED | RESTING (on the book, unmatched) | NOT_FILLED (dropped, or canceled with no fill)
    The chain accepting a transaction (code 0) does not mean the order matched; this does.
    """
    waited = 0.0
    while True:
        orders = fetch(f"{base}/orders?address={address}&subaccountNumber={subaccount}")
        order = next((o for o in orders if str(o.get("clientId")) == str(client_id)), None)
        if order is not None and (order.get("status") != "OPEN" or waited >= timeout):
            break
        if order is None and waited >= timeout:
            return {"status": "NOT_FILLED", "filled": "0", "builder_fee_usd": "0"}
        sleep(interval)
        waited += interval
    size, filled = float(order["size"]), float(order.get("totalFilled") or 0)
    fees = fetch(f"{base}/fills?address={address}&subaccountNumber={subaccount}").get("fills", [])
    mine = [f for f in fees if f.get("orderId") == order.get("id")]
    status = "FILLED" if filled >= size else ("PARTIALLY_FILLED" if filled > 0 else "NOT_FILLED")
    if status == "NOT_FILLED" and order.get("status") == "OPEN":
        status = "RESTING"  # on the book, unmatched so far (stateful limit order)
    return {"status": status, "filled": str(filled), "requested": str(size), "order_status": order.get("status"),
            "builder_fee_usd": f"{sum(float(f.get('builderFee') or 0) for f in mine):.6f}"}


def exact_size(size: str) -> float:
    """dydx-v4-client floors size to the step in float math, so 0.0003 can become 2999999.99 quantums and
    round DOWN a whole step. Nudge by 1e-9 relative (far below any step) so the intended size is kept."""
    from decimal import Decimal
    return float(Decimal(size) * Decimal("1.000000001"))


class DydxTestnetSubmitter:  # pragma: no cover - needs network + optional dependency
    """Places orders on dYdX testnet (stateful limit orders by default, expiring after 60s; market intents are
    limit orders at the guard's worst acceptable price, `max_market_slippage_bps` across the oracle).
    The result includes `fill`: what the Indexer says actually happened (FILLED / PARTIALLY_FILLED / NOT_FILLED)."""
    name = "dydx-testnet"
    GOOD_FOR_BLOCKS = 20
    STATEFUL = True          # short-term orders were accepted by the node but silently never matched on testnet
    GOOD_FOR_SECONDS = 60    # stateful orders expire after this long if unmatched
    MARKET_SLIPPAGE = 0.02

    def __init__(self, network: str = "testnet", address: str | None = None, subaccount: int = 0):
        if network != "testnet":
            raise RuntimeError("v0.1 refuses mainnet. Use testnet until the operator signs off on a mainnet release.")
        if not os.environ.get("DYDX_TESTNET_MNEMONIC"):
            raise RuntimeError("set DYDX_TESTNET_MNEMONIC (a TESTNET-only wallet) to enable testnet submission")
        self.address, self.subaccount = address, subaccount

    async def _submit(self, order: dict) -> dict:
        from v4_proto.dydxprotocol.clob.order_pb2 import Order
        from dydx_v4_client import MAX_CLIENT_ID, OrderFlags
        from dydx_v4_client.indexer.rest.constants import OrderType
        from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
        from dydx_v4_client.network import TESTNET
        from dydx_v4_client.node.client import NodeClient
        from dydx_v4_client.node.market import Market
        from dydx_v4_client.wallet import Wallet

        mnemonic = os.environ["DYDX_TESTNET_MNEMONIC"]  # never logged or returned
        node = await NodeClient.connect(TESTNET.node)
        indexer = IndexerClient(TESTNET.rest_indexer)
        meta = (await indexer.markets.get_perpetual_markets(order["market"]))["markets"][order["market"]]
        wallet = await Wallet.from_mnemonic(node, mnemonic, self.address)
        if wallet.address != self.address:
            raise RuntimeError("DYDX_TESTNET_MNEMONIC does not match AGENTGUARD_ADDRESS")
        market = Market(meta)
        buy = order["side"] == "BUY"
        is_market = order["type"] == "MARKET"
        oracle = float(meta["oraclePrice"])
        if order["price"] is not None:
            # for MARKET intents this is the guard's worst acceptable price, so the chain enforces it
            price = float(order["price"])
        elif is_market:  # only reached if a caller bypasses the guard's order dict
            price = oracle * (1 + self.MARKET_SLIPPAGE if buy else 1 - self.MARKET_SLIPPAGE)
        else:
            raise ValueError("limit order without a price")
        client_id = random.randint(0, MAX_CLIENT_ID)
        flags = OrderFlags.LONG_TERM if self.STATEFUL else OrderFlags.SHORT_TERM
        oid = market.order_id(self.address, self.subaccount, client_id, flags)
        height = await node.latest_block_height()
        expiry = ({"good_til_block_time": int(time.time()) + self.GOOD_FOR_SECONDS} if self.STATEFUL
                  else {"good_til_block": height + self.GOOD_FOR_BLOCKS})
        # Stateful orders cannot be IOC/market: a "market" intent becomes a limit priced across the book.
        otype = OrderType.LIMIT if (self.STATEFUL or not is_market) else OrderType.MARKET
        bc = order.get("builder_code") or {}
        o = market.order(
            oid, otype,
            Order.Side.SIDE_BUY if buy else Order.Side.SIDE_SELL,
            size=exact_size(order["size"]), price=price,
            time_in_force=Order.TimeInForce.TIME_IN_FORCE_UNSPECIFIED,
            reduce_only=bool(order["reduce_only"]),
            **expiry,
            builder_address=bc.get("builder_address"), fee_ppm=bc.get("fee_ppm"))
        resp = await node.place_order(wallet, o)
        tx = resp.tx_response
        out = {"status": "SUBMITTED" if tx.code == 0 else "REJECTED_BY_CHAIN", "client_id": client_id,
               "tx_hash": tx.txhash, "code": tx.code, "raw_log": tx.raw_log[:200], "ts": time.time()}
        if tx.code == 0:  # accepted by the node != matched: report the real outcome from the Indexer
            from .indexer import TESTNET_INDEXER, http_fetch
            try:
                out["fill"] = confirm_fill(http_fetch, TESTNET_INDEXER, self.address, self.subaccount, client_id)
            except Exception as e:  # never fail the order report because the confirmation lookup failed
                out["fill"] = {"status": "UNKNOWN", "error": str(e)[:120]}
        return out

    def submit(self, order: dict) -> dict:
        import asyncio
        return asyncio.run(self._submit(order))
