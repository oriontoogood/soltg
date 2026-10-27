# ─────────────────────────────────────────────
#  TRANSFERS — native SOL transfers
# ─────────────────────────────────────────────
import base64
import base58
import logging
from config import HELIUS_RPC_URL, LAMPORTS_PER_SOL, RENT_EXEMPT_MIN_SOL

logger = logging.getLogger(__name__)


async def send_sol(secret_b58, to_pubkey, lamports):
    """Send native SOL. Returns {success, signature, error}."""
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.system_program import transfer, TransferParams
    from solders.transaction import Transaction
    from solders.hash import Hash
    import httpx

    try:
        keypair = Keypair.from_bytes(base58.b58decode(secret_b58))
        recipient = Pubkey.from_string(to_pubkey)

        # Fetch recent blockhash
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(HELIUS_RPC_URL, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getLatestBlockhash",
                "params": [{"commitment": "finalized"}],
            })
            bh = resp.json()["result"]["value"]["blockhash"]

        ix = transfer(TransferParams(
            from_pubkey=keypair.pubkey(),
            to_pubkey=recipient,
            lamports=int(lamports),
        ))
        tx = Transaction.new_signed_with_payer(
            [ix], keypair.pubkey(), [keypair], Hash.from_string(bh)
        )
        signed_b64 = base64.b64encode(bytes(tx)).decode()

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(HELIUS_RPC_URL, json={
                "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
                "params": [signed_b64, {"encoding": "base64"}],
            })
            data = resp.json()
            sig = data.get("result")
            if not sig:
                return {"success": False, "error": str(data.get("error", "unknown"))}

        return {"success": True, "signature": sig}
    except Exception as exc:
        logger.exception("SOL transfer failed")
        return {"success": False, "error": str(exc)}


def lamports_to_sol(lamports):
    return lamports / LAMPORTS_PER_SOL


def sol_to_lamports(sol):
    return int(sol * LAMPORTS_PER_SOL)