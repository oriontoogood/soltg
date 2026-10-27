# ─────────────────────────────────────────────
#  TRENDING — Fetches trending tokens from
#  DexScreener, PumpFun and other DEXes
# ─────────────────────────────────────────────
import httpx


def fmt_num(n):
    try:
        n = float(n)
        if n >= 1_000_000_000:
            return "$" + str(round(n / 1_000_000_000, 2)) + "B"
        elif n >= 1_000_000:
            return "$" + str(round(n / 1_000_000, 2)) + "M"
        elif n >= 1_000:
            return "$" + str(round(n / 1_000, 2)) + "K"
        else:
            return "$" + str(round(n, 4))
    except Exception:
        return str(n)


def change_emoji(val):
    try:
        v = float(val)
        if v > 0:
            return "📈 +" + str(round(v, 2)) + "%"
        else:
            return "📉 " + str(round(v, 2)) + "%"
    except Exception:
        return str(val) + "%"


# ── DexScreener trending ──────────────────────
async def get_dexscreener_trending():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://api.dexscreener.com/token-boosts/top/v1")
            data = resp.json()
            tokens = []
            seen   = set()
            for item in data[:20]:
                addr = item.get("tokenAddress", "")
                if addr in seen:
                    continue
                seen.add(addr)
                tokens.append({
                    "name":    item.get("description", "Unknown")[:20],
                    "address": addr,
                    "chain":   item.get("chainId", "solana"),
                    "url":     item.get("url", ""),
                    "boosts":  item.get("totalAmount", 0),
                })
            return tokens[:10]
    except Exception:
        return []


# ── DexScreener Solana trending ───────────────
async def get_solana_trending():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.dexscreener.com/latest/dex/search",
                params={"q": "SOL"},
            )
            data  = resp.json()
            pairs = data.get("pairs", [])
            # Filter Solana pairs and sort by volume
            sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
            sol_pairs = sorted(sol_pairs, key=lambda x: float(x.get("volume", {}).get("h24", 0) or 0), reverse=True)
            tokens = []
            seen   = set()
            for p in sol_pairs[:20]:
                base = p.get("baseToken", {})
                name = base.get("name", "Unknown")
                addr = base.get("address", "")
                if addr in seen or not addr:
                    continue
                seen.add(addr)
                tokens.append({
                    "name":       name[:15],
                    "symbol":     base.get("symbol", "???"),
                    "address":    addr,
                    "price":      p.get("priceUsd", "0"),
                    "volume_24h": p.get("volume", {}).get("h24", 0),
                    "change_24h": p.get("priceChange", {}).get("h24", 0),
                    "mcap":       p.get("marketCap", 0),
                    "liquidity":  p.get("liquidity", {}).get("usd", 0),
                    "dex":        p.get("dexId", "").capitalize(),
                })
            return tokens[:10]
    except Exception:
        return []


# ── PumpFun trending ──────────────────────────
async def get_pumpfun_trending():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://frontend-api.pump.fun/coins",
                params={"offset": 0, "limit": 10, "sort": "last_trade_timestamp", "order": "DESC", "includeNsfw": "false"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            data   = resp.json()
            tokens = []
            for coin in data[:10]:
                tokens.append({
                    "name":    coin.get("name", "Unknown")[:15],
                    "symbol":  coin.get("symbol", "???"),
                    "address": coin.get("mint", ""),
                    "mcap":    coin.get("usd_market_cap", 0),
                    "replies": coin.get("reply_count", 0),
                })
            return tokens
    except Exception:
        return []


# ── Format trending message ───────────────────
async def get_trending_message():
    solana   = await get_solana_trending()
    pumpfun  = await get_pumpfun_trending()
    boosted  = await get_dexscreener_trending()

    lines = ["🔥 Trending Tokens\n"]

    # Solana DEX trending
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚡ Top Solana Tokens (DexScreener)")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if solana:
        for i, t in enumerate(solana[:5], 1):
            lines.append(
                str(i) + ". " + t["name"] + " (" + t["symbol"] + ")\n"
                "   Price: $" + str(round(float(t["price"] or 0), 6)) + "\n"
                "   Vol 24h: " + fmt_num(t["volume_24h"]) + "  " + change_emoji(t["change_24h"]) + "\n"
                "   MCap: " + fmt_num(t["mcap"]) + " | " + t["dex"] + "\n"
                "   `" + t["address"] + "`"
            )
    else:
        lines.append("Could not fetch Solana trending data.")

    # PumpFun trending
    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("🎯 Trending on Pump.fun")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if pumpfun:
        for i, t in enumerate(pumpfun[:5], 1):
            lines.append(
                str(i) + ". " + t["name"] + " (" + t["symbol"] + ")\n"
                "   MCap: " + fmt_num(t["mcap"]) + "\n"
                "   Replies: " + str(t["replies"]) + "\n"
                "   `" + t["address"] + "`"
            )
    else:
        lines.append("Could not fetch Pump.fun trending data.")

    # Boosted tokens
    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("🚀 Top Boosted Tokens (DexScreener)")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if boosted:
        for i, t in enumerate(boosted[:5], 1):
            lines.append(
                str(i) + ". " + (t["name"] or "Unknown") + "\n"
                "   Chain: " + t["chain"] + "\n"
                "   Boosts: " + str(t["boosts"]) + "\n"
                "   `" + t["address"] + "`"
            )
    else:
        lines.append("Could not fetch boosted tokens data.")

    return "\n".join(lines)
