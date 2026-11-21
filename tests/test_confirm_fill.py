from agentguard.executor import confirm_fill

B = "http://x/v4"


def mk(orders, fills):
    def fetch(url):
        return orders if "/orders" in url else {"fills": fills}
    return fetch


def run(orders, fills, cid=7):
    return confirm_fill(mk(orders, fills), B, "dydx1a", 0, cid, timeout=4, interval=2, sleep=lambda s: None)


def test_partial_fill_reports_builder_fee():
    o = [{"clientId": "7", "id": "o1", "status": "CANCELED", "size": "0.001", "totalFilled": "0.0005"}]
    f = [{"orderId": "o1", "builderFee": "0.004"}, {"orderId": "o1", "builderFee": "0.005"}, {"orderId": "other", "builderFee": "9"}]
    r = run(o, f)
    assert r["status"] == "PARTIALLY_FILLED" and r["builder_fee_usd"] == "0.009000"


def test_full_fill():
    o = [{"clientId": "7", "id": "o1", "status": "FILLED", "size": "0.001", "totalFilled": "0.001"}]
    assert run(o, [])["status"] == "FILLED"


def test_dropped_order_is_not_filled():
    assert run([], [])["status"] == "NOT_FILLED"


def test_canceled_with_zero_fill_is_not_filled():
    o = [{"clientId": "7", "id": "o1", "status": "CANCELED", "size": "0.001", "totalFilled": "0"}]
    assert run(o, [])["status"] == "NOT_FILLED"


def test_open_unmatched_order_is_resting_not_dropped():
    o = [{"clientId": "7", "id": "o1", "status": "OPEN", "size": "0.001", "totalFilled": "0"}]
    assert run(o, [])["status"] == "RESTING"
