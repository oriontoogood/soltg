# ─────────────────────────────────────────────
#  PNL — Fetches trade history and generates
#  styled PNL image (Top Gains or Top Losses)
# ─────────────────────────────────────────────
import httpx
import io
from datetime import datetime
from config import HELIUS_API_KEY


def fmt_num(n):
    try:
        n = float(n)
        if n >= 1_000_000:
            return str(round(n / 1_000_000, 2)) + "M"
        elif n >= 1_000:
            return str(round(n / 1_000, 2)) + "K"
        else:
            return str(round(n, 4))
    except Exception:
        return str(n)


# ── Fetch swap transactions from Helius ───────
async def get_swap_transactions(pubkey, limit=100):
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.helius.xyz/v0/addresses/" + pubkey + "/transactions",
                params={"api-key": HELIUS_API_KEY, "limit": limit, "type": "SWAP"},
            )
            if resp.status_code != 200:
                return []
            return resp.json()
    except Exception:
        return []


# ── Get token symbol from mint ────────────────
async def get_token_symbol(mint):
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://api.dexscreener.com/latest/dex/tokens/" + mint
            )
            data  = resp.json()
            pairs = data.get("pairs", [])
            if pairs:
                base = pairs[0].get("baseToken", {})
                return base.get("symbol", mint[:6])
    except Exception:
        pass
    return mint[:6]


# ── Calculate PNL per token ───────────────────
async def calculate_pnl(pubkey):
    txns = await get_swap_transactions(pubkey)
    if not txns:
        return None

    trades = {}

    for tx in txns:
        try:
            events     = tx.get("events", {})
            swap       = events.get("swap", {})
            if not swap:
                continue
            token_in   = (swap.get("tokenInputs")  or [{}])[0]
            token_out  = (swap.get("tokenOutputs") or [{}])[0]
            native_in  = swap.get("nativeInput")  or {}
            native_out = swap.get("nativeOutput") or {}

            # BUY: paid SOL, received token
            if native_in and token_out:
                mint      = token_out.get("mint", "")
                amount    = float(token_out.get("tokenAmount", 0))
                sol_spent = float(native_in.get("amount", 0)) / 1e9
                if mint not in trades:
                    trades[mint] = {"bought": 0, "sold": 0, "sol_in": 0, "sol_out": 0}
                trades[mint]["bought"]  += amount
                trades[mint]["sol_in"]  += sol_spent

            # SELL: paid token, received SOL
            elif token_in and native_out:
                mint    = token_in.get("mint", "")
                amount  = float(token_in.get("tokenAmount", 0))
                sol_got = float(native_out.get("amount", 0)) / 1e9
                if mint not in trades:
                    trades[mint] = {"bought": 0, "sold": 0, "sol_in": 0, "sol_out": 0}
                trades[mint]["sold"]    += amount
                trades[mint]["sol_out"] += sol_got

        except Exception:
            continue

    if not trades:
        return None

    results    = []
    total_pnl  = 0.0
    total_wins = 0
    total_loss = 0

    for mint, data in trades.items():
        pnl = data["sol_out"] - data["sol_in"]
        total_pnl += pnl
        if pnl > 0:
            total_wins += 1
        else:
            total_loss += 1
        results.append({
            "mint":    mint,
            "symbol":  mint[:6],
            "sol_in":  round(data["sol_in"],  4),
            "sol_out": round(data["sol_out"], 4),
            "pnl":     round(pnl, 4),
            "win":     pnl > 0,
        })

    return {
        "trades":     results,
        "total_pnl":  round(total_pnl, 4),
        "total_wins": total_wins,
        "total_loss": total_loss,
    }


# ── Generate PNL image ────────────────────────
async def generate_pnl_image(pubkey, balance, mode="gains"):
    try:
        from PIL import Image, ImageDraw, ImageFont

        pnl_data = await calculate_pnl(pubkey)

        W, H = 920, 640
        img  = Image.new("RGB", (W, H), color="#0d0f1a")
        draw = ImageDraw.Draw(img)

        # Background
        for y in range(H):
            shade = int(13 + (y / H) * 10)
            draw.line([(0, y), (W, y)], fill=(shade, shade + 2, shade + 22))

        # Load fonts
        try:
            fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
            fm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
            fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
        except Exception:
            fb = fm = fs = ImageFont.load_default()

        # Header
        draw.rectangle([0, 0, W, 75], fill="#111827")
        draw.text((30, 18), "Meta Solana Bot", font=fb, fill="#5b8af7")
        title = "Top Gains 📈" if mode == "gains" else "Top Losses 📉"
        draw.text((W - 220, 22), title, font=fm, fill="#22c55e" if mode == "gains" else "#ef4444")

        # Wallet + date
        short = pubkey[:8] + "..." + pubkey[-8:]
        draw.text((30, 88),  "Wallet: " + short, font=fs, fill="#94a3b8")
        draw.text((30, 108), "Date: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), font=fs, fill="#64748b")
        draw.text((W - 240, 90), "Balance: " + str(round(balance, 4)) + " SOL", font=fs, fill="#5b8af7")

        if not pnl_data:
            draw.text((W // 2 - 180, H // 2), "No trade history found for this wallet.", font=fm, fill="#64748b")
        else:
            total     = pnl_data["total_pnl"]
            wins      = pnl_data["total_wins"]
            losses    = pnl_data["total_loss"]
            all_trades = pnl_data["trades"]

            # Sort by mode
            if mode == "gains":
                sorted_trades = sorted([t for t in all_trades if t["win"]], key=lambda x: x["pnl"], reverse=True)
                accent = "#22c55e"
            else:
                sorted_trades = sorted([t for t in all_trades if not t["win"]], key=lambda x: x["pnl"])
                accent = "#ef4444"

            top_trades = sorted_trades[:8]

            # Summary box
            sign = "+" if total >= 0 else ""
            col  = "#22c55e" if total >= 0 else "#ef4444"
            draw.rectangle([30, 132, W - 30, 192], fill="#1a1d2e", outline=col, width=2)
            draw.text((50, 145),  "Total PNL:", font=fm, fill="#94a3b8")
            draw.text((220, 142), sign + str(total) + " SOL", font=fb, fill=col)
            draw.text((520, 148), "Wins: " + str(wins), font=fm, fill="#22c55e")
            draw.text((680, 148), "Losses: " + str(losses), font=fm, fill="#ef4444")

            # Divider
            draw.rectangle([30, 200, W - 30, 202], fill=accent)

            # Table header
            draw.rectangle([30, 210, W - 30, 238], fill="#1e2235")
            draw.text((45,  215), "#",       font=fs, fill="#64748b")
            draw.text((80,  215), "Token",   font=fs, fill="#64748b")
            draw.text((280, 215), "SOL In",  font=fs, fill="#64748b")
            draw.text((420, 215), "SOL Out", font=fs, fill="#64748b")
            draw.text((570, 215), "PNL",     font=fs, fill="#64748b")
            draw.text((730, 215), "Result",  font=fs, fill="#64748b")

            # Trade rows
            if not top_trades:
                draw.text((30, 260), "No " + ("gains" if mode == "gains" else "losses") + " found.", font=fm, fill="#64748b")
            else:
                y = 246
                for idx, t in enumerate(top_trades, 1):
                    bg = "#111827" if idx % 2 == 0 else "#0f172a"
                    draw.rectangle([30, y, W - 30, y + 34], fill=bg)
                    pnl_c  = "#22c55e" if t["win"] else "#ef4444"
                    sign_t = "+" if t["win"] else ""
                    result = "WIN" if t["win"] else "LOSS"
                    draw.text((45,  y + 9), str(idx),                       font=fs, fill="#64748b")
                    draw.text((80,  y + 9), t["symbol"][:12],               font=fs, fill="#e2e8f0")
                    draw.text((280, y + 9), str(t["sol_in"]),                font=fs, fill="#94a3b8")
                    draw.text((420, y + 9), str(t["sol_out"]),               font=fs, fill="#94a3b8")
                    draw.text((570, y + 9), sign_t + str(t["pnl"]) + " SOL", font=fs, fill=pnl_c)
                    draw.text((730, y + 9), result,                          font=fs, fill=pnl_c)
                    y += 36

        # Footer
        draw.rectangle([0, H - 38, W, H], fill="#111827")
        draw.text((30,      H - 26), "Powered by Meta Solana Bot", font=fs, fill="#334155")
        draw.text((W - 220, H - 26), "Helius + DexScreener",       font=fs, fill="#5b8af7")

        buf = io.BytesIO()
        img.save(buf, format="PNG", quality=95)
        buf.seek(0)
        return buf, pnl_data

    except Exception as exc:
        return None, None
