# ─────────────────────────────────────────────
#  WALLET — verification, generation, encryption, balance
# ─────────────────────────────────────────────
import httpx
import base58
import hashlib
import hmac
import struct
from config import HELIUS_RPC_URL, ENCRYPTION_KEY


def is_valid_private_key(key_str):
    try:
        decoded = base58.b58decode(key_str.strip())
        return len(decoded) == 64
    except Exception:
        return False


def is_valid_mnemonic(phrase):
    return len(phrase.strip().split()) in [12, 18, 24]


def get_pubkey_from_private_key(key_str):
    try:
        from nacl.signing import SigningKey
        decoded = base58.b58decode(key_str.strip())
        signing_key = SigningKey(decoded[:32])
        return base58.b58encode(bytes(signing_key.verify_key)).decode("utf-8")
    except Exception:
        return None


def get_pubkey_from_mnemonic(phrase):
    try:
        from mnemonic import Mnemonic
        from nacl.signing import SigningKey
        mnemo = Mnemonic("english")
        seed = mnemo.to_seed(phrase.strip(), passphrase="")
        path = [44 + 0x80000000, 501 + 0x80000000, 0 + 0x80000000, 0 + 0x80000000]
        il = seed[:32]
        for index in path:
            data = b"\x00" + il + struct.pack(">I", index)
            h = hmac.new(b"ed25519 seed", data, hashlib.sha512).digest()
            il = h[:32]
        signing_key = SigningKey(il)
        return base58.b58encode(bytes(signing_key.verify_key)).decode("utf-8")
    except Exception:
        return None


def get_keypair_from_mnemonic(phrase):
    """Derive BOTH pubkey and 64-byte base58 private key from a mnemonic."""
    try:
        from mnemonic import Mnemonic
        from nacl.signing import SigningKey
        mnemo = Mnemonic("english")
        seed = mnemo.to_seed(phrase.strip(), passphrase="")
        path = [44 + 0x80000000, 501 + 0x80000000, 0 + 0x80000000, 0 + 0x80000000]
        il = seed[:32]
        for index in path:
            data = b"\x00" + il + struct.pack(">I", index)
            h = hmac.new(b"ed25519 seed", data, hashlib.sha512).digest()
            il = h[:32]
        signing_key = SigningKey(il)
        verify_key = signing_key.verify_key
        secret_bytes = bytes(signing_key) + bytes(verify_key)
        return {
            "pubkey":     base58.b58encode(bytes(verify_key)).decode("utf-8"),
            "secret_b58": base58.b58encode(secret_bytes).decode("utf-8"),
        }
    except Exception:
        return None


async def get_sol_balance(pubkey):
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [pubkey]}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(HELIUS_RPC_URL, json=payload)
            data = resp.json()
            return data["result"]["value"] / 1_000_000_000
    except Exception:
        return None


async def get_sol_price_usd():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "solana", "vs_currencies": "usd"},
            )
            return resp.json()["solana"]["usd"]
    except Exception:
        return None


async def verify_wallet(user_input):
    """
    Returns dict with:
      valid, pubkey, balance, usd, input_type, secret_b58, message
    Both private-key AND mnemonic imports now return secret_b58 so the bot
    can encrypt and store it, enabling buy/sell.
    """
    user_input = user_input.strip()
    pubkey = None
    input_type = None
    secret_out = None

    if is_valid_private_key(user_input):
        input_type = "private_key"
        pubkey = get_pubkey_from_private_key(user_input)
        if pubkey:
            secret_out = user_input

    elif is_valid_mnemonic(user_input):
        input_type = "mnemonic"
        derived = get_keypair_from_mnemonic(user_input)
        if derived:
            pubkey = derived["pubkey"]
            secret_out = derived["secret_b58"]

    else:
        return {
            "valid": False,
            "message": (
                "Invalid wallet input.\n\n"
                "Please send a valid:\n"
                "- Private key (base58 encoded)\n"
                "- Seed phrase (12, 18, or 24 words)"
            ),
        }

    if not pubkey:
        return {"valid": False, "message": "Could not derive wallet address. Please check your input and try again."}

    balance = await get_sol_balance(pubkey)
    if balance is None:
        return {"valid": False, "message": "Wallet found but could not fetch balance. Please try again."}

    price = await get_sol_price_usd()
    usd_val = round(balance * price, 2) if price else 0.00

    return {
        "valid": True,
        "pubkey": pubkey,
        "balance": round(balance, 4),
        "usd": usd_val,
        "input_type": input_type,
        "secret_b58": secret_out,
        "message": (
            "Wallet connected successfully!\n\n"
            "Solana: " + pubkey + "\n\n"
            "Bal: " + str(round(balance, 4)) + " SOL - $" + str(usd_val)
        ),
    }


def generate_solana_wallet():
    try:
        from nacl.signing import SigningKey
        signing_key = SigningKey.generate()
        secret_bytes = bytes(signing_key) + bytes(signing_key.verify_key)
        return {
            "pubkey": base58.b58encode(bytes(signing_key.verify_key)).decode("utf-8"),
            "secret_b58": base58.b58encode(secret_bytes).decode("utf-8"),
        }
    except Exception:
        return None


def encrypt_secret(secret_b58):
    try:
        from cryptography.fernet import Fernet
        if not ENCRYPTION_KEY or not secret_b58:
            return ""
        return Fernet(ENCRYPTION_KEY.encode()).encrypt(secret_b58.encode()).decode()
    except Exception:
        return ""


def decrypt_secret(encrypted):
    try:
        from cryptography.fernet import Fernet
        if not ENCRYPTION_KEY or not encrypted:
            return ""
        return Fernet(ENCRYPTION_KEY.encode()).decrypt(encrypted.encode()).decode()
    except Exception:
        return ""