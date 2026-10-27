# ─────────────────────────────────────────────
#  JUPITER — swap execution
# ─────────────────────────────────────────────
import httpx
import base64
import asyncio
import logging
from config import (
    JUPITER_QUOTE_URL, JUPITER_SWAP_URL, HELIUS_RPC_URL,
    SOL_MINT, DEFAULT_SLIPPAGE_BPS, DEFAULT_PRIORITY_FEE,
)

logger = logging.getLogger(__name__)


async def get_quote(input_mint, output_mint, amount_lamports, slippage_bps=DEFAULT_SLIPPAGE_BPS):
    try:
        params = {
            "inputMint":  input_mint,
            "outputMint": output_mint,
            "amount":     str(int(amount_lamports)),
            "slippageBps": str(int(slippage_bps)),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(JUPITER_QUOTE_URL, params=params)
            if resp.status_code != 200:
                return None
            return resp.json()
    except Exception as exc:
        logger.warning("Jupiter quote failed: %s", exc)
        return None


async def build_swap_tx(quote, user_pubkey, jito_tip_lamports=0):
    try:
        payload = {
            "quoteResponse": quote,
            "userPublicKey": user_pubkey,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        }
        if jito_tip_lamports > 0:
            payload["prioritizationFeeLamports"] = {"jitoTipLamports": jito_tip_lamports}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(JUPITER_SWAP_URL, json=payload)
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("swapTransaction")
    except Exception as exc:
        logger.warning("Jupiter swap build failed: %s", exc)
        return None


async def send_transaction(signed_b64):
    try:
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
            "params": [signed_b64, {"encoding": "base64", "skipPreflight": False, "maxRetries": 3}],
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(HELIUS_RPC_URL, json=payload)
            data = resp.json()
            return data.get("result")
    except Exception as exc:
        logger.warning("Send tx failed: %s", exc)
        return None


async def confirm_transaction(signature, timeout_sec=45):
    elapsed = 0
    while elapsed < timeout_sec:
        try:
            payload = {
                "jsonrpc": "2.0", "id": 1, "method": "getSignatureStatuses",
                "params": [[signature], {"searchTransactionHistory": True}],
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(HELIUS_RPC_URL, json=payload)
                data = resp.json()
                arr = data.get("result", {}).get("value", [])
                if arr and arr[0]:
                    if arr[0].get("err"):
                        return False
                    if arr[0].get("confirmationStatus") in ("confirmed", "finalized"):
                        return True
        except Exception:
            pass
        await asyncio.sleep(2)
        elapsed += 2
    return False


async def execute_swap(secret_b58, input_mint, output_mint, amount_lamports,
                       slippage_bps=DEFAULT_SLIPPAGE_BPS, jito_tip_lamports=0):
    """
    Full pipeline. Returns dict:
      {success, signature, error, in_amount, out_amount}
    """
    from solders.keypair import Keypair
    from solders.transaction import VersionedTransaction
    import base58

    try:
        secret_bytes = base58.b58decode(secret_b58)
        keypair = Keypair.from_bytes(secret_bytes)
        pubkey = str(keypair.pubkey())

        quote = await get_quote(input_mint, output_mint, amount_lamports, slippage_bps)
        if not quote:
            return {"success": False, "error": "Could not get swap quote."}

        swap_b64 = await build_swap_tx(quote, pubkey, jito_tip_lamports)
        if not swap_b64:
            return {"success": False, "error": "Could not build swap transaction."}

        raw = base64.b64decode(swap_b64)
        unsigned = VersionedTransaction.from_bytes(raw)
        signed = VersionedTransaction(unsigned.message, [keypair])
        signed_b64 = base64.b64encode(bytes(signed)).decode()

        signature = await send_transaction(signed_b64)
        if not signature:
            return {"success": False, "error": "Failed to submit transaction."}

        confirmed = await confirm_transaction(signature)
        if not confirmed:
            return {"success": False, "signature": signature,
                    "error": "Submitted but not confirmed. Check Solscan."}

        return {
            "success": True,
            "signature": signature,
            "in_amount": quote.get("inAmount"),
            "out_amount": quote.get("outAmount"),
        }
    except Exception as exc:
        logger.exception("Swap failed")
        return {"success": False, "error": str(exc)}