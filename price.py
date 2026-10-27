# ─────────────────────────────────────────────
#  PRICE — SOL + token prices (multi-source, cached)
# ─────────────────────────────────────────────
import aiohttp
import time
import logging
from config import SOL_MINT, JUPITER_API_KEY

logger = logging.getLogger(__name__)

_sol_price_cache = {"price": None, "ts": 0.0}
SOL_PRICE_TTL = 30

_token_price_cache = {}
TOKEN_PRICE_TTL = 20


async def _jup_v3():
    if not JUPITER_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.jup.ag/price/v3?ids={SOL_MINT}",
                headers={"x-api-key": JUPITER_API_KEY},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    p = d.get(SOL_MINT, {}).get("usdPrice")
                    if p:
                        return float(p)
    except Exception:
        pass
    return None


async def _jup_v2():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.jup.ag/price/v2?ids={SOL_MINT}",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    p = d.get("data", {}).get(SOL_MINT, {}).get("price")
                    if p:
                        return float(p)
    except Exception:
        pass
    return None


async def _binance():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    p = d.get("price")
                    if p:
                        return float(p)
    except Exception:
        pass
    return None


async def _coingecko():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    p = d.get("solana", {}).get("usd")
                    if p:
                        return float(p)
    except Exception:
        pass
    return None


async def _okx():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://www.okx.com/api/v5/market/ticker?instId=SOL-USDT",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    arr = d.get("data", [])
                    if arr and arr[0].get("last"):
                        return float(arr[0]["last"])
    except Exception:
        pass
    return None


async def get_sol_price_usd():
    now = time.time()
    if _sol_price_cache["price"] and (now - _sol_price_cache["ts"]) < SOL_PRICE_TTL:
        return _sol_price_cache["price"]
    for f in (_jup_v3, _jup_v2, _binance, _coingecko, _okx):
        p = await f()
        if p:
            _sol_price_cache["price"] = p
            _sol_price_cache["ts"] = now
            return p
    return _sol_price_cache["price"]


async def get_token_price_usd(mint):
    now = time.time()
    cached = _token_price_cache.get(mint)
    if cached and (now - cached["ts"]) < TOKEN_PRICE_TTL:
        return cached["price"]
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{mint}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    pairs = d.get("pairs", [])
                    if pairs:
                        pair = sorted(
                            pairs,
                            key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0),
                            reverse=True,
                        )[0]
                        price = float(pair.get("priceUsd") or 0)
                        _token_price_cache[mint] = {"price": price, "ts": now}
                        return price
    except Exception as exc:
        logger.warning("Token price fetch failed for %s: %s", mint[:8], exc)
    return None


async def get_token_info(mint):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{mint}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    pairs = d.get("pairs", [])
                    if not pairs:
                        return None
                    pair = sorted(
                        pairs,
                        key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0),
                        reverse=True,
                    )[0]
                    base = pair.get("baseToken", {})
                    return {
                        "name": base.get("name", "Unknown"),
                        "symbol": base.get("symbol", "???"),
                        "price_usd": float(pair.get("priceUsd") or 0),
                        "liquidity": float(pair.get("liquidity", {}).get("usd", 0) or 0),
                        "mcap": float(pair.get("marketCap") or 0),
                        "dex": pair.get("dexId", ""),
                    }
    except Exception:
        pass
    return None