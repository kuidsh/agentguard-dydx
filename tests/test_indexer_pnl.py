from datetime import datetime, timezone
from decimal import Decimal

from agentguard.indexer import Indexer


def test_day_start_equity_uses_midnight_utc_and_latest_row():
    seen = []

    def fetch(url):
        seen.append(url)
        return {"historicalPnl": [{"equity": "900", "createdAt": "2026-11-16T22:00:00.000Z"},
                                  {"equity": "1000", "createdAt": "2026-11-16T23:59:00.000Z"}]}

    idx = Indexer("http://x/v4", fetch)
    eq = idx.day_start_equity("dydx1abc", 0, now=datetime(2026, 11, 17, 15, 30, tzinfo=timezone.utc))
    assert eq == Decimal("1000")
    assert "createdBeforeOrAt=2026-11-17T00%3A00%3A00.000Z" in seen[0]


def test_day_start_equity_none_without_history():
    assert Indexer("http://x/v4", lambda u: {"historicalPnl": []}).day_start_equity("dydx1abc", 0) is None


def test_unfunded_subaccount_is_zero_equity_not_a_crash():
    import urllib.error

    def fetch(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    a = Indexer("http://x/v4", fetch).account_state("dydx1new", 0, None)
    assert a.equity == Decimal(0) and a.positions == {}


def test_day_start_equity_none_when_indexer_404s():
    import urllib.error

    def fetch(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    assert Indexer("http://x/v4", fetch).day_start_equity("dydx1new", 0) is None


# --- daily-loss baseline net of deposits/withdrawals (row shape checked against testnet /transfers) ---

def _transfers(*rows):
    return lambda url: {"transfers": [dict(zip(("type", "size", "createdAt"), r)) for r in rows]}


def test_day_start_returns_snapshot_time():
    rows = {"historicalPnl": [{"equity": "1000", "createdAt": "2026-11-17T00:00:00.000Z"}]}
    base = Indexer("http://x/v4", lambda u: rows).day_start("dydx1abc", 0)
    assert base == (Decimal("1000"), "2026-11-17T00:00:00.000Z")


def test_net_transfers_counts_only_after_baseline_with_signs():
    idx = Indexer("http://x/v4", _transfers(
        ("DEPOSIT", "1000", "2026-11-17T09:00:00.000Z"),
        ("WITHDRAWAL", "200", "2026-11-17T08:00:00.000Z"),
        ("TRANSFER_IN", "50", "2026-11-17T07:00:00.000Z"),
        ("TRANSFER_OUT", "25", "2026-11-17T06:00:00.000Z"),
        ("DEPOSIT", "5000", "2026-11-16T23:00:00.000Z")))   # before the baseline: already in day-start equity
    assert idx.net_transfers_since("dydx1abc", 0, "2026-11-17T00:00:00.000Z") == Decimal("825")


def test_net_transfers_none_and_404_are_zero():
    import urllib.error

    def fetch(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    assert Indexer("http://x/v4", lambda u: {"transfers": []}).net_transfers_since("a", 0, "2026") == 0
    assert Indexer("http://x/v4", fetch).net_transfers_since("a", 0, "2026") == 0


def test_net_transfers_fails_closed_on_unknown_type():
    import pytest
    idx = Indexer("http://x/v4", _transfers(("AIRDROP", "10", "2026-11-17T09:00:00.000Z")))
    with pytest.raises(RuntimeError, match="unknown transfer type"):
        idx.net_transfers_since("a", 0, "2026-11-17T00:00:00.000Z")


def test_net_transfers_fails_closed_on_full_page():
    import pytest
    idx = Indexer("http://x/v4", _transfers(*[("DEPOSIT", "1", "2026-11-17T09:00:00.000Z")] * 3))
    with pytest.raises(RuntimeError, match="refusing to guess"):
        idx.net_transfers_since("a", 0, "2026-11-17T00:00:00.000Z", limit=3)


def _fake_indexer(history, transfers, equity):
    def fetch(url):
        if "/historical-pnl" in url:
            return {"historicalPnl": history}
        if "/transfers" in url:
            return {"transfers": transfers}
        if "/perpetualMarkets" in url:
            return {"markets": {}}
        return {"subaccount": {"equity": equity, "freeCollateral": equity}}
    return Indexer("http://x/v4", fetch)


def test_indexer_state_deposit_after_midnight_does_not_hide_loss():
    from agentguard.guard import pnl_today
    from agentguard.mcp_server import IndexerState
    idx = _fake_indexer([{"equity": "2000", "createdAt": "2026-11-17T00:00:00.000Z"}],
                        [{"type": "DEPOSIT", "size": "1000", "createdAt": "2026-11-17T10:00:00.000Z"}], "2700")
    acct, _ = IndexerState(idx, "dydx1abc", 0, None).snapshot(0, now=datetime(2026, 11, 17, 15, tzinfo=timezone.utc))
    assert pnl_today(acct) == Decimal("-300")


def test_indexer_state_new_account_ignores_transfers_before_first_snapshot():
    from agentguard.guard import pnl_today
    from agentguard.mcp_server import IndexerState
    # no history; the account was funded at 01:00 and the guard starts at 15:00
    idx = _fake_indexer([], [{"type": "DEPOSIT", "size": "1000", "createdAt": "2026-11-17T01:00:00.000Z"}], "1000")
    st = IndexerState(idx, "dydx1abc", 0, None)
    acct, _ = st.snapshot(0, now=datetime(2026, 11, 17, 15, tzinfo=timezone.utc))
    assert pnl_today(acct) == 0
    acct, _ = st.snapshot(0, now=datetime(2026, 11, 17, 16, tzinfo=timezone.utc))
    assert pnl_today(acct) == 0  # the 01:00 deposit is before the 15:00 baseline
