# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
import os

# Telegram
BOT_TOKEN       = "8983317940:AAEzFhYAx89t21hhuwRiITGGwCWNbIhAyEA"
FORWARD_CHAT_ID = "-1004354117607"

# User filtering
ALLOWED_USERS = []
BLOCKED_USERS = []

# File paths
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_FILE   = os.path.join(BASE_DIR, "data", "messages.db")
LOG_FILE  = os.path.join(BASE_DIR, "data", "messages.log")
MEDIA_DIR = os.path.join(BASE_DIR, "media")

# Solana RPC (Helius) — mainnet
HELIUS_API_KEY = "e0133e22-1e34-4a35-8597-b0949596972e"
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
HELIUS_WS_URL  = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# Devnet testing — uncomment to test safely
# HELIUS_RPC_URL = "https://api.devnet.solana.com"
# HELIUS_WS_URL  = "wss://api.devnet.solana.com"

# Jupiter
JUPITER_API_KEY   = ""
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL  = "https://quote-api.jup.ag/v6/swap"

# Jito (for Anti-MEV / snipers — used in later phases)
JITO_BLOCK_ENGINE = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"

# Wallet encryption
# Generate ONCE with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste the result. NEVER change after creating wallets.
ENCRYPTION_KEY = ""

# Constants
SOL_MINT             = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL     = 1_000_000_000
DEFAULT_SLIPPAGE_BPS = 100
DEFAULT_PRIORITY_FEE = 100_000
DEFAULT_TIP_LAMPORTS = 1_000_000
RENT_EXEMPT_MIN_SOL  = 0.00204