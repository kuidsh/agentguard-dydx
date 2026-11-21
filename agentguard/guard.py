"""Pre-trade checks. Pure functions: same inputs, same decision, easy to test and audit."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .policy import Policy

D0 = Decimal(0)


@dataclass(frozen=True)
class OrderIntent:
    market: str
    side: str                    # BUY | SELL
    size: Decimal                # base units, > 0
    order_type: str = "LIMIT"
    price: Optional[Decimal] = None   # required for LIMIT
    reduce_only: bool = False
    client_note: str = ""        # free text from the agent, logged verbatim

    @staticmethod
    def from_dict(d: dict) -> "OrderIntent":
        return OrderIntent(
            market=str(d["market"]).upper(), side=str(d["side"]).upper(), size=Decimal(str(d["size"])),
            order_type=str(d.get("order_type", "LIMIT")).upper(),
            price=Decimal(str(d["price"])) if d.get("price") is not None else None,
            reduce_only=bool(d.get("reduce_only", False)), client_note=str(d.get("client_note", ""))[:500])


@dataclass(frozen=True)
class AccountState:
    equity: Decimal
    free_collateral: Decimal
    positions: dict              # market -> signed size (long > 0)
    day_start_equity: Decimal    # equity at the 00:00 UTC baseline snapshot
    orders_last_minute: int = 0
    net_transfers_today: Decimal = D0   # deposits/transfers in minus withdrawals/out since that baseline


@dataclass(frozen=True)
class MarketState:
    oracle_prices: dict          # market -> Decimal
    active: frozenset = frozenset()


@dataclass
class Decision:
    allowed: bool
    reasons: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    order: Optional[dict] = None


def _signed(side: str, size: Decimal) -> Decimal:
    return size if side == "BUY" else -size


def pnl_today(acct: AccountState) -> Decimal:
    """Trading PnL since the day-start baseline. Deposits are subtracted so they can't hide a loss,
    and withdrawals are added back so they don't count as one."""
    return acct.equity - acct.day_start_equity - acct.net_transfers_today


def worst_price(intent: OrderIntent, oracle: Decimal, pol: Policy) -> Decimal:
    """Worst execution price of a MARKET order: the agent's protection price if it sent one,
    otherwise oracle +/- the policy's max slippage. The submitter uses it as the order's limit."""
    if intent.price is not None:
        return intent.price
    s = Decimal(pol.max_market_slippage_bps) / 10_000
    return oracle * (1 + s) if intent.side == "BUY" else oracle * (1 - s)


def evaluate(intent: OrderIntent, acct: AccountState, mkt: MarketState, pol: Policy,
             kill_switch: bool = False) -> Decision:
    r: list[str] = []
    c: dict = {}

    if kill_switch:
        r.append("kill switch is on: all new orders are blocked")
    if intent.side not in ("BUY", "SELL"):
        r.append(f"side must be BUY or SELL, got {intent.side}")
    if intent.size <= 0:
        r.append("size must be > 0")
    if intent.market not in pol.allowed_markets:
        r.append(f"market {intent.market} is not in the allowed list")
    if mkt.active and intent.market not in mkt.active:
        r.append(f"market {intent.market} is not active")
    if intent.order_type not in pol.allowed_order_types:
        r.append(f"order type {intent.order_type} is not allowed")
    if intent.order_type == "LIMIT" and intent.price is None:
        r.append("LIMIT orders need a price")

    oracle = mkt.oracle_prices.get(intent.market)
    if oracle is None or oracle <= 0:
        r.append(f"no oracle price for {intent.market}; refusing to size the order")
        return Decision(False, r, c)

    is_market = intent.order_type == "MARKET"
    worst = None
    if is_market:
        # size and cap a market order at the worst price it could fill at, not at the oracle
        worst = worst_price(intent, oracle, pol)
        adverse = (worst - oracle) if intent.side == "BUY" else (oracle - worst)
        slip_bps = (adverse / oracle * 10_000).quantize(Decimal("0.1"))
        c["worst_price"], c["worst_price_slippage_bps"] = str(worst), str(slip_bps)
        if worst <= 0:
            r.append("market order worst price must be > 0")
        elif slip_bps > pol.max_market_slippage_bps:
            r.append(f"market order worst price {worst} is {slip_bps} bps through oracle "
                     f"(max {pol.max_market_slippage_bps})")
        ref_price = max(worst, oracle)
    else:
        ref_price = intent.price if intent.price is not None else oracle
    notional = (intent.size * ref_price).quantize(Decimal("0.01"))
    c["order_notional_usd"] = str(notional)

    # limit price sanity vs oracle
    if intent.price is not None and not is_market:
        dev_bps = (abs(intent.price - oracle) / oracle * 10_000).quantize(Decimal("0.1"))
        c["price_deviation_bps"] = str(dev_bps)
        if dev_bps > pol.max_price_deviation_bps:
            r.append(f"limit price is {dev_bps} bps from oracle (max {pol.max_price_deviation_bps})")

    cur = Decimal(acct.positions.get(intent.market, 0))
    new = cur + _signed(intent.side, intent.size)
    reduces = abs(new) < abs(cur) and (cur * new) >= 0
    c["position_before"], c["position_after"] = str(cur), str(new)
    c["reduces_exposure"] = reduces

    if intent.reduce_only and not reduces:
        r.append("reduce_only order would not reduce the position")

    # daily loss
    pnl = pnl_today(acct)
    c["pnl_today_usd"] = str(pnl)
    c["net_transfers_today_usd"] = str(acct.net_transfers_today)
    loss_hit = pnl <= -pol.max_daily_loss_usd
    if loss_hit and not (pol.reduce_only_after_loss_limit and reduces):
        r.append(f"daily loss limit reached ({pnl} <= -{pol.max_daily_loss_usd}); only closing orders allowed")

    if not reduces:
        if notional > pol.max_order_notional_usd:
            r.append(f"order notional {notional} > max {pol.max_order_notional_usd}")
        pos_notional = abs(new) * oracle
        c["position_notional_after_usd"] = str(pos_notional.quantize(Decimal('0.01')))
        if pos_notional > pol.max_position_notional_usd:
            r.append(f"position notional after order {pos_notional:.2f} > max {pol.max_position_notional_usd}")
        gross = sum((abs(Decimal(s)) * mkt.oracle_prices.get(m, D0) for m, s in acct.positions.items()
                     if m != intent.market), D0) + pos_notional
        c["gross_notional_after_usd"] = str(gross.quantize(Decimal('0.01')))
        if gross > pol.max_gross_notional_usd:
            r.append(f"gross notional after order {gross:.2f} > max {pol.max_gross_notional_usd}")
        if acct.equity <= 0:
            r.append("equity is zero or negative")
        else:
            lev = (gross / acct.equity).quantize(Decimal("0.01"))
            c["leverage_after"] = str(lev)
            if lev > pol.max_leverage:
                r.append(f"leverage after order {lev}x > max {pol.max_leverage}x")
        if acct.free_collateral < pol.min_free_collateral_usd:
            r.append(f"free collateral {acct.free_collateral} < min {pol.min_free_collateral_usd}")

    if acct.orders_last_minute >= pol.max_orders_per_minute:
        r.append(f"rate limit: {acct.orders_last_minute} orders in the last minute (max {pol.max_orders_per_minute})")

    order = None
    if not r:
        order = {"market": intent.market, "side": intent.side, "size": str(intent.size),
                 "type": intent.order_type,
                 "price": str(worst) if worst is not None else (str(intent.price) if intent.price is not None else None),
                 "reduce_only": intent.reduce_only or (loss_hit and reduces)}
        if pol.builder_fee_ppm:
            order["builder_code"] = {"builder_address": pol.builder_address, "fee_ppm": pol.builder_fee_ppm}
    return Decision(not r, r, c, order)
