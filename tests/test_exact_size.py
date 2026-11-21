import pytest

from agentguard.executor import exact_size

pytest.importorskip("dydx_v4_client")
from dydx_v4_client.node.market import Market  # noqa: E402

BTC = {"atomicResolution": -10, "stepBaseQuantums": 1000000, "subticksPerTick": 100000,
       "quantumConversionExponent": -8, "clobPairId": "0"}


@pytest.mark.parametrize("size,quantums", [("0.0003", 3_000_000), ("0.001", 10_000_000), ("0.0007", 7_000_000), ("0.0001", 1_000_000)])
def test_size_not_rounded_down_a_step(size, quantums):
    assert Market(BTC).calculate_quantums(exact_size(size)) == quantums


def test_plain_float_would_lose_a_step():
    assert Market(BTC).calculate_quantums(float("0.0003")) == 2_000_000  # the library bug exact_size works around
