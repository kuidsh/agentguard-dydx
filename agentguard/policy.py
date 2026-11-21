"""Risk policy for an AI agent trading on dYdX v4.

A policy is plain JSON so a human (not the agent) owns it. The agent can read it
but never change it through the guard's tools.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path

ORDER_TYPES = {"LIMIT", "MARKET", "STOP_LIMIT", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"}


@dataclass(frozen=True)
class Policy:
    allowed_markets: tuple[str, ...] = ("BTC-USD", "ETH-USD")
    allowed_order_types: tuple[str, ...] = ("LIMIT", "MARKET")
    max_order_notional_usd: Decimal = Decimal("1000")
    max_position_notional_usd: Decimal = Decimal("5000")   # per market, after the order
    max_gross_notional_usd: Decimal = Decimal("10000")     # all markets, after the order
    max_leverage: Decimal = Decimal("3")                   # gross notional / equity
    max_daily_loss_usd: Decimal = Decimal("250")           # realized + unrealized since UTC midnight
    max_orders_per_minute: int = 10
    max_price_deviation_bps: int = 100                     # limit price vs oracle
    max_market_slippage_bps: int = 200                     # MARKET orders: worst fill price vs oracle
    min_free_collateral_usd: Decimal = Decimal("50")
    reduce_only_after_loss_limit: bool = True              # after the loss limit, only allow closing
    network: str = "testnet"
    builder_address: str | None = None
    builder_fee_ppm: int = 0                               # 0 = no builder fee; max 10_000 (1%)
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.network not in ("testnet", "mainnet"):
            raise ValueError("network must be testnet or mainnet")
        bad = set(self.allowed_order_types) - ORDER_TYPES
        if bad:
            raise ValueError(f"unknown order types: {sorted(bad)}")
        if not 0 <= self.builder_fee_ppm <= 10_000:
            raise ValueError("builder_fee_ppm must be in [0, 10000] (dYdX cap is 1%)")
        if not 0 < self.max_market_slippage_bps < 10_000:
            raise ValueError("max_market_slippage_bps must be in (0, 10000)")
        if self.builder_fee_ppm and not self.builder_address:
            raise ValueError("builder_fee_ppm set but builder_address missing")
        for name in ("max_order_notional_usd", "max_position_notional_usd", "max_gross_notional_usd",
                     "max_leverage", "max_daily_loss_usd"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")

    @staticmethod
    def from_dict(d: dict) -> "Policy":
        dec = {"max_order_notional_usd", "max_position_notional_usd", "max_gross_notional_usd",
               "max_leverage", "max_daily_loss_usd", "min_free_collateral_usd"}
        tup = {"allowed_markets", "allowed_order_types"}
        kw = {}
        for k, v in d.items():
            if k in dec:
                kw[k] = Decimal(str(v))
            elif k in tup:
                kw[k] = tuple(v)
            else:
                kw[k] = v
        return Policy(**kw)

    @staticmethod
    def load(path: str | Path) -> "Policy":
        return Policy.from_dict(json.loads(Path(path).read_text()))

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: (str(v) if isinstance(v, Decimal) else list(v) if isinstance(v, tuple) else v)
                for k, v in d.items()}
