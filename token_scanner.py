# ─────────────────────────────────────────────
#  TOKEN SCANNER — Full token analysis
#  Uses DexScreener + Helius API
# ─────────────────────────────────────────────
import httpx
from config import HELIUS_RPC_URL, HELIUS_API_KEY


# ── Fetch token data from DexScreener ─────────
async def get_dexscreener_data(token_address):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.dexscreener.com/latest/dex/tokens/" + token_address
            )
            data = resp.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return None
            # Get the most liquid pair
            pair = sorted(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)[0]
            return pair
    except Exception:
        return None


# ── Fetch token metadata from Helius ──────────
async def get_helius_metadata(token_address):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                HELIUS_RPC_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getAsset",
                    "params": {"id": token_address},
                },
            )
            data = resp.json()
            return data.get("result", {})
    except Exception:
        return {}


# ── Check token safety ────────────────────────
async def check_token_safety(token_address, pair_data, metadata):
    risks = []
    safe  = []

    # Check liquidity
    liquidity = float(pair_data.get("liquidity", {}).get("usd", 0) or 0)
    if liquidity < 10000:
        risks.append("Low liquidity (under $10,000) — high risk")
    else:
        safe.append("Liquidity is healthy")

    # Check market cap
    mcap = float(pair_data.get("marketCap", 0) or 0)
    if mcap < 50000:
        risks.append("Very low market cap — high risk")

    # Check if token is freezable
    content = metadata.get("content", {})
    interfaces = metadata.get("interface", "")
    if "freeze" in str(metadata).lower():
        risks.append("Token has freeze authority — owner can freeze wallets")
    else:
        safe.append("No freeze authority detected")

    # Check price change
    price_change = pair_data.get("priceChange", {})
    h24 = float(price_change.get("h24", 0) or 0)
    if h24 < -50:
        risks.append("Price dropped over 50% in 24h — possible rug pull")
    elif h24 > 100:
        risks.append("Price pumped over 100% in 24h — possible pump and dump")

    # Check volume
    volume = float(pair_data.get("volume", {}).get("h24", 0) or 0)
    if volume < 1000:
        risks.append("Very low 24h volume — low activity")
    else:
        safe.append("Good trading volume")

    # Check age
    created = pair_data.get("pairCreatedAt", 0)
    if created:
        import time
        age_hours = (time.time() * 1000 - created) / (1000 * 3600)
        if age_hours < 24:
            risks.append("Token is less than 24 hours old — very new and risky")
        elif age_hours < 168:
            risks.append("Token is less than 1 week old — proceed with caution")
        else:
            safe.append("Token is more than 1 week old")

    if not risks:
        verdict = "SAFE"
        verdict_emoji = "✅"
    elif len(risks) >= 3:
        verdict = "HIGH RISK"
        verdict_emoji = "🔴"
    else:
        verdict = "MODERATE RISK"
        verdict_emoji = "🟡"

    return {
        "verdict":       verdict,
        "verdict_emoji": verdict_emoji,
        "risks":         risks,
        "safe":          safe,
    }


# ── Format number nicely ──────────────────────
def fmt_number(n):
    try:
        n = float(n)
        if n >= 1_000_000_000:
            return str(round(n / 1_000_000_000, 2)) + "B"
        elif n >= 1_000_000:
            return str(round(n / 1_000_000, 2)) + "M"
        elif n >= 1_000:
            return str(round(n / 1_000, 2)) + "K"
        else:
            return str(round(n, 6))
    except Exception:
        return str(n)


# ── Main scan function ────────────────────────
async def scan_token(token_address):
    token_address = token_address.strip()

    # Fetch data
    pair     = await get_dexscreener_data(token_address)
    metadata = await get_helius_metadata(token_address)

    if not pair:
        return {
            "success": False,
            "message": (
                "Token not found.\n\n"
                "Please make sure you entered a valid Solana token contract address.\n"
                "Example: So11111111111111111111111111111111111111112"
            ),
        }

    # Extract data
    base_token   = pair.get("baseToken", {})
    name         = base_token.get("name", "Unknown")
    symbol       = base_token.get("symbol", "???")
    price_usd    = pair.get("priceUsd", "0")
    price_sol    = pair.get("priceNative", "0")
    mcap         = pair.get("marketCap", 0)
    liquidity    = pair.get("liquidity", {}).get("usd", 0)
    volume_24h   = pair.get("volume", {}).get("h24", 0)
    volume_6h    = pair.get("volume", {}).get("h6", 0)
    volume_1h    = pair.get("volume", {}).get("h1", 0)
    price_change = pair.get("priceChange", {})
    h24_change   = price_change.get("h24", 0)
    h6_change    = price_change.get("h6", 0)
    h1_change    = price_change.get("h1", 0)
    dex          = pair.get("dexId", "unknown").capitalize()
    pair_address = pair.get("pairAddress", "")
    buys_24h     = pair.get("txns", {}).get("h24", {}).get("buys", 0)
    sells_24h    = pair.get("txns", {}).get("h24", {}).get("sells", 0)

    # Safety check
    safety = await check_token_safety(token_address, pair, metadata)

    # Format price change with emoji
    def change_emoji(val):
        try:
            v = float(val)
            return ("📈 +" if v > 0 else "📉 ") + str(round(v, 2)) + "%"
        except Exception:
            return str(val) + "%"

    # Build message
    lines = [
        "Token Analysis",
        "",
        "Name: " + name + " (" + symbol + ")",
        "Contract: `" + token_address + "`",
        "DEX: " + dex,
        "",
        "Price",
        "USD: `$" + str(round(float(price_usd or 0), 8)) + "`",
        "SOL: `" + str(round(float(price_sol or 0), 8)) + " SOL`",
        "",
        "Market Data",
        "Market Cap: `$" + fmt_number(mcap) + "`",
        "Liquidity: `$" + fmt_number(liquidity) + "`",
        "Volume 1h: `$" + fmt_number(volume_1h) + "`",
        "Volume 6h: `$" + fmt_number(volume_6h) + "`",
        "Volume 24h: `$" + fmt_number(volume_24h) + "`",
        "",
        "Price Change",
        "1h:  " + change_emoji(h1_change),
        "6h:  " + change_emoji(h6_change),
        "24h: " + change_emoji(h24_change),
        "",
        "Transactions (24h)",
        "Buys: " + str(buys_24h) + " | Sells: " + str(sells_24h),
        "",
        "Safety Check " + safety["verdict_emoji"] + " " + safety["verdict"],
    ]

    if safety["risks"]:
        lines.append("")
        lines.append("Risks:")
        for r in safety["risks"]:
            lines.append("  🔴 " + r)

    if safety["safe"]:
        lines.append("")
        lines.append("Positives:")
        for s in safety["safe"]:
            lines.append("  ✅ " + s)

    return {
        "success":       True,
        "message":       "\n".join(lines),
        "token_address": token_address,
        "symbol":        symbol,
        "name":          name,
        "safety":        safety["verdict"],
    }
