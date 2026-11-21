"""Request free testnet USDC + native token from dYdX's faucet for AGENTGUARD_ADDRESS (public, no key needed)."""
import asyncio
import os
import sys

import httpx

from dydx_v4_client.faucet_client import FaucetClient
from dydx_v4_client.network import TESTNET_FAUCET


async def main(addr: str, amount: float) -> None:
    f = FaucetClient(TESTNET_FAUCET)
    for name, make in (("USDC", lambda: f.fill(addr, 0, amount)), ("native", lambda: f.fill_native(addr))):
        try:
            r = await make()
            print(name, r.status_code, "accepted (delivery is asynchronous). USDC lands in the BANK balance; run scripts/deposit_to_subaccount.py to move it into subaccount 0")
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            print(name, code, "rate limited, try after the reset in the Reset response header" if code == 429 else e.response.text[:200])


if __name__ == "__main__":
    addr = os.environ.get("AGENTGUARD_ADDRESS") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not addr.startswith("dydx1"):
        sys.exit("set AGENTGUARD_ADDRESS or pass the address")
    asyncio.run(main(addr, float(sys.argv[2]) if len(sys.argv) > 2 else 1000))
