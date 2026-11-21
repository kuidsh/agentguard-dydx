"""Create a TESTNET-ONLY dYdX wallet. Run this yourself (the AI assistant must never see the phrase).

The recovery phrase is written to .env (git-ignored) and is never printed. Only the public address is shown.
    python scripts/create_testnet_wallet.py
"""
import hashlib
import os
import sys
from pathlib import Path

import bech32
from bip_utils import Bip39MnemonicGenerator, Bip39WordsNum, Bip39SeedGenerator, Bip44, Bip44Coins
from Crypto.Hash import RIPEMD160

ENV = Path(".env")


def main() -> int:
    if ENV.exists() and "DYDX_TESTNET_MNEMONIC" in ENV.read_text():
        print("DYDX_TESTNET_MNEMONIC already in .env; refusing to overwrite. Delete that line first if intended.")
        return 1
    phrase = str(Bip39MnemonicGenerator().FromWordsNumber(Bip39WordsNum.WORDS_NUM_24))
    pub = Bip44.FromSeed(Bip39SeedGenerator(phrase).Generate(), Bip44Coins.COSMOS).DeriveDefaultPath().PublicKey().RawCompressed().ToBytes()
    addr = bech32.bech32_encode("dydx", bech32.convertbits(RIPEMD160.new(hashlib.sha256(pub).digest()).digest(), 8, 5))
    fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(f"\nDYDX_TESTNET_MNEMONIC={phrase}\nAGENTGUARD_ADDRESS={addr}\n")
    print(f"Testnet address: {addr}\nRecovery phrase saved to {ENV} (not shown). Back it up only if you ever fund it, which you should not.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
