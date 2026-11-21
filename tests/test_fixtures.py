"""Assert the field names agentguard and the submitter depend on exist in REAL testnet Indexer responses."""
import json
from decimal import Decimal
from pathlib import Path

from agentguard.indexer import Indexer

FX = Path(__file__).parent / "fixtures"
SUBMITTER_FIELDS = {"clobPairId", "atomicResolution", "quantumConversionExponent",
                    "stepBaseQuantums", "subticksPerTick", "oraclePrice", "status"}


def load(name):
    return json.loads((FX / name).read_text())


def test_perpetual_markets_have_fields_the_code_uses():
    for tkr, m in load("perpetualMarkets.json")["markets"].items():
        assert SUBMITTER_FIELDS <= m.keys(), tkr


def test_market_state_parses_real_response():
    ms = Indexer("http://x/v4", lambda u: load("perpetualMarkets.json")).market_state()
    assert {"BTC-USD", "ETH-USD"} <= ms.active
    assert ms.oracle_prices["BTC-USD"] > Decimal(0)


def test_subaccount_and_pnl_fixtures_if_captured():
    for name, key in (("subaccount.json", "subaccount"), ("historical-pnl.json", "historicalPnl")):
        if (FX / name).exists():
            assert key in load(name), name
