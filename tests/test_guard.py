import json
from decimal import Decimal as D

import pytest

from agentguard.audit import AuditLog, verify
from agentguard.cli import demo
from agentguard.guard import AccountState, MarketState, OrderIntent, evaluate
from agentguard.indexer import Indexer
from agentguard.policy import Policy
from agentguard.service import GuardService, StaticState

MKT = MarketState(oracle_prices={"BTC-USD": D("90000"), "ETH-USD": D("3000")},
                  active=frozenset({"BTC-USD", "ETH-USD"}))


def acct(**kw):
    base = dict(equity=D("2000"), free_collateral=D("1500"), positions={}, day_start_equity=D("2000"))
    base.update(kw)
    return AccountState(**base)


def intent(**kw):
    base = dict(market="ETH-USD", side="BUY", size="0.2", price="3000")
    base.update(kw)
    return OrderIntent.from_dict(base)


POL = Policy()


def test_small_order_allowed():
    d = evaluate(intent(), acct(), MKT, POL)
    assert d.allowed, d.reasons
    assert d.order["market"] == "ETH-USD" and "builder_code" not in d.order


def test_builder_code_attached_when_configured():
    pol = Policy(builder_address="dydx1builder", builder_fee_ppm=300)
    d = evaluate(intent(), acct(), MKT, pol)
    assert d.order["builder_code"] == {"builder_address": "dydx1builder", "fee_ppm": 300}


@pytest.mark.parametrize("ppm", [-1, 10_001])
def test_builder_fee_cap(ppm):
    with pytest.raises(ValueError):
        Policy(builder_address="dydx1x", builder_fee_ppm=ppm)


def test_builder_fee_needs_address():
    with pytest.raises(ValueError):
        Policy(builder_fee_ppm=100)


def test_market_not_allowed():
    d = evaluate(intent(market="DOGE-USD"), acct(), MarketState({"DOGE-USD": D("0.2")}), POL)
    assert not d.allowed and any("allowed list" in r for r in d.reasons)


def test_order_notional_cap():
    d = evaluate(intent(size="0.5"), acct(), MKT, POL)  # 1500 > 1000
    assert not d.allowed and any("order notional" in r for r in d.reasons)


def test_position_cap_counts_existing_position():
    d = evaluate(intent(market="BTC-USD", size="0.01", price="90000"), acct(positions={"BTC-USD": D("0.05")}), MKT, POL)
    assert not d.allowed and any("position notional" in r for r in d.reasons)  # 0.06*90000=5400


def test_leverage_cap():
    pol = Policy(max_leverage=D("1"), max_order_notional_usd=D("5000"), max_position_notional_usd=D("9000"))
    d = evaluate(intent(size="0.8"), acct(equity=D("2000")), MKT, pol)  # 2400/2000 = 1.2x
    assert not d.allowed and any("leverage" in r for r in d.reasons)


def test_price_deviation():
    d = evaluate(intent(price="2900"), acct(), MKT, POL)  # 333 bps
    assert not d.allowed and any("bps from oracle" in r for r in d.reasons)


def test_market_buy_sized_at_worst_price():
    d = evaluate(intent(order_type="MARKET", price=None, size="0.2"), acct(), MKT, POL)
    # 3000 oracle + 200 bps default slippage = 3060 worst price; 0.2 * 3060 = 612
    assert d.allowed and d.checks["order_notional_usd"] == "612.00"
    assert d.order["price"] == "3060.00" and d.checks["worst_price_slippage_bps"] == "200.0"


def test_market_order_under_cap_at_oracle_but_over_at_worst_price_is_rejected():
    d = evaluate(intent(order_type="MARKET", price=None, size="0.33"), acct(), MKT, POL)  # 990 at oracle, 1009.80 worst
    assert not d.allowed and any("order notional 1009.80" in r for r in d.reasons)


def test_market_sell_worst_price_is_below_oracle():
    a = acct(positions={"ETH-USD": D("0.5")})
    d = evaluate(intent(order_type="MARKET", side="SELL", price=None, size="0.2"), a, MKT, POL)
    assert d.allowed and d.order["price"] == "2940.00"
    assert d.checks["order_notional_usd"] == "600.00"  # capped at the higher of worst price and oracle


def test_market_order_protection_price_within_slippage_allowed():
    d = evaluate(intent(order_type="MARKET", price="3050", size="0.2"), acct(), MKT, POL)  # 166.7 bps
    assert d.allowed and d.order["price"] == "3050"


def test_market_order_protection_price_beyond_slippage_rejected():
    d = evaluate(intent(order_type="MARKET", price="3100", size="0.2"), acct(), MKT, POL)  # 333.3 bps
    assert not d.allowed and any("bps through oracle" in r for r in d.reasons)


def test_market_slippage_policy_from_json():
    pol = Policy.from_dict({"max_market_slippage_bps": 50})
    d = evaluate(intent(order_type="MARKET", price=None, size="0.2"), acct(), MKT, pol)
    assert D(d.order["price"]) == D("3015")


@pytest.mark.parametrize("bps", [0, 10_000])
def test_market_slippage_bounds(bps):
    with pytest.raises(ValueError):
        Policy(max_market_slippage_bps=bps)


def test_limit_needs_price():
    d = evaluate(intent(price=None), acct(), MKT, POL)
    assert not d.allowed


def test_daily_loss_blocks_new_risk_but_allows_closing():
    a = acct(equity=D("1700"), day_start_equity=D("2000"), positions={"ETH-USD": D("0.3")})
    assert not evaluate(intent(), a, MKT, POL).allowed
    close = evaluate(intent(side="SELL", size="0.3", price="3000"), a, MKT, POL)
    assert close.allowed and close.order["reduce_only"] is True


def test_deposit_cannot_hide_a_daily_loss():
    # lost 300 trading, then deposited 1000: equity is up 700 but the loss limit must still trip
    a = acct(equity=D("2700"), day_start_equity=D("2000"), net_transfers_today=D("1000"))
    d = evaluate(intent(), a, MKT, POL)
    assert not d.allowed and d.checks["pnl_today_usd"] == "-300"
    assert any("daily loss limit" in r for r in d.reasons)


def test_withdrawal_is_not_a_daily_loss():
    # withdrew 1000, no trading loss: equity is down 1000 but PnL today is 0
    a = acct(equity=D("1000"), day_start_equity=D("2000"), net_transfers_today=D("-1000"))
    d = evaluate(intent(), a, MKT, POL)
    assert d.allowed, d.reasons
    assert d.checks["pnl_today_usd"] == "0"


def test_status_reports_pnl_net_of_transfers(tmp_path):
    a = acct(equity=D("2700"), day_start_equity=D("2000"), net_transfers_today=D("1000"))
    svc = GuardService(POL, StaticState(a, MKT), AuditLog(tmp_path / "a.jsonl"))
    s = svc.status()
    assert s["pnl_today"] == "-300" and s["net_transfers_today"] == "1000"


def test_reduce_only_must_reduce():
    d = evaluate(intent(reduce_only=True), acct(), MKT, POL)
    assert not d.allowed


def test_flip_is_not_a_reduction():
    a = acct(positions={"ETH-USD": D("0.1")})
    d = evaluate(intent(side="SELL", size="0.2", price="3000", reduce_only=True), a, MKT, POL)
    assert not d.allowed


def test_missing_oracle_refuses():
    d = evaluate(intent(), acct(), MarketState({}), POL)
    assert not d.allowed and "oracle" in d.reasons[0]


def test_kill_switch_blocks_everything():
    d = evaluate(intent(), acct(), MKT, POL, kill_switch=True)
    assert not d.allowed and "kill switch" in d.reasons[0]


def test_rate_limit_in_service(tmp_path):
    t = [1000.0]
    pol = Policy(max_orders_per_minute=2)
    svc = GuardService(pol, StaticState(acct(), MKT), AuditLog(tmp_path / "a.jsonl"), clock=lambda: t[0])
    small = dict(market="ETH-USD", side="BUY", size="0.01", price="3000")
    assert svc.place(small)["allowed"]
    assert svc.place(small)["allowed"]
    assert not svc.place(small)["allowed"]
    t[0] += 61
    assert svc.place(small)["allowed"]


def test_audit_chain_detects_tampering(tmp_path):
    p = tmp_path / "audit.jsonl"
    log = AuditLog(p)
    for i in range(5):
        log.append("evt", {"i": i})
    assert verify(p) == (True, 5, "chain intact")
    lines = p.read_text().splitlines()
    rec = json.loads(lines[2]); rec["data"]["i"] = 99
    lines[2] = json.dumps(rec, sort_keys=True)
    p.write_text("\n".join(lines) + "\n")
    ok, n, msg = verify(p)
    assert not ok and n == 3 and "modified" in msg


def test_audit_chain_detects_deletion(tmp_path):
    p = tmp_path / "audit.jsonl"
    log = AuditLog(p)
    for i in range(4):
        log.append("evt", {"i": i})
    lines = p.read_text().splitlines()
    del lines[1]
    p.write_text("\n".join(lines) + "\n")
    assert not verify(p)[0]


def test_audit_resumes_chain_after_restart(tmp_path):
    p = tmp_path / "audit.jsonl"
    AuditLog(p).append("a", {})
    AuditLog(p).append("b", {})
    assert verify(p)[0]


def test_service_logs_rejections_with_reasons(tmp_path):
    p = tmp_path / "a.jsonl"
    svc = GuardService(POL, StaticState(acct(), MKT), AuditLog(p))
    svc.place(dict(market="DOGE-USD", side="BUY", size="1", price="1"))
    events = [r["event"] for r in AuditLog(p).records()]
    assert events == ["service_start", "order_requested", "order_rejected"]


def test_malformed_input_is_denied_not_crashed(tmp_path):
    svc = GuardService(POL, StaticState(acct(), MKT), AuditLog(tmp_path / "a.jsonl"))
    res = svc.place({"market": "ETH-USD"})
    assert not res["allowed"] and res["reasons"][0].startswith("error")


def test_indexer_parsing():
    def fetch(url):
        if url.endswith("/perpetualMarkets"):
            return {"markets": {"BTC-USD": {"oraclePrice": "90000", "status": "ACTIVE"},
                                "OLD-USD": {"oraclePrice": "1", "status": "FINAL_SETTLEMENT"}}}
        return {"subaccount": {"equity": "2000.5", "freeCollateral": "1500",
                               "openPerpetualPositions": {"BTC-USD": {"size": "0.01", "side": "SHORT"}}}}
    idx = Indexer("https://x/v4", fetch=fetch)
    m = idx.market_state()
    assert m.oracle_prices["BTC-USD"] == D("90000") and "OLD-USD" not in m.active
    a = idx.account_state("dydx1abc", 0, None)
    assert a.positions["BTC-USD"] == D("-0.01") and a.day_start_equity == D("2000.5")


def test_policy_roundtrip(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(Policy(builder_address="dydx1b", builder_fee_ppm=200).to_dict()))
    assert Policy.load(p).builder_fee_ppm == 200


def test_demo_runs(tmp_path):
    out = demo(str(tmp_path / "demo.jsonl"))
    assert [r["allowed"] for r in out] == [True, False, False, False, False]
    assert verify(tmp_path / "demo.jsonl")[0]
