"""Deposit testnet USDC from the wallet's bank balance into trading subaccount 0 (TESTNET only).

The dYdX faucet credits the *bank* balance; trading needs the USDC inside a subaccount.
    python scripts/deposit_to_subaccount.py 1000        # amount in USDC
Reads DYDX_TESTNET_MNEMONIC / AGENTGUARD_ADDRESS from .env; never prints the phrase.
"""
import asyncio
import os
import sys
from decimal import Decimal

from agentguard.mcp_server import load_env_file


async def main(amount_usdc: Decimal) -> None:
    from v4_proto.dydxprotocol.subaccounts.subaccount_pb2 import SubaccountId
    from dydx_v4_client.network import TESTNET
    from dydx_v4_client.node.client import NodeClient
    from dydx_v4_client.wallet import Wallet

    addr = os.environ["AGENTGUARD_ADDRESS"]
    node = await NodeClient.connect(TESTNET.node)
    wallet = await Wallet.from_mnemonic(node, os.environ["DYDX_TESTNET_MNEMONIC"], addr)
    if wallet.address != addr:
        raise SystemExit("DYDX_TESTNET_MNEMONIC does not match AGENTGUARD_ADDRESS")
    quantums = int(amount_usdc * 10**6)  # USDC has 6 decimals; asset_id 0 = USDC
    resp = await node.deposit(wallet, addr, SubaccountId(owner=addr, number=0), 0, quantums)
    tx = resp.tx_response
    print("deposit", amount_usdc, "USDC -> code", tx.code, "tx", tx.txhash, tx.raw_log[:200])


if __name__ == "__main__":
    load_env_file()
    asyncio.run(main(Decimal(sys.argv[1]) if len(sys.argv) > 1 else Decimal("1000")))
