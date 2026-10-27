# ─────────────────────────────────────────────
#  DATABASE — all tables for every feature
# ─────────────────────────────────────────────
import sqlite3
import os
import json
from config import DB_FILE


def _conn():
    return sqlite3.connect(DB_FILE)


def _ensure_column(conn, table, column, coltype):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    c = _conn()

    c.execute(
        "CREATE TABLE IF NOT EXISTS messages ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "timestamp TEXT NOT NULL,"
        "chat_id INTEGER NOT NULL,"
        "user_id INTEGER,"
        "username TEXT,"
        "full_name TEXT,"
        "message_id INTEGER,"
        "text TEXT,"
        "media_type TEXT,"
        "media_path TEXT)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS user_filters ("
        "user_id INTEGER PRIMARY KEY,"
        "username TEXT,"
        "list_type TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS wallets ("
        "user_id INTEGER PRIMARY KEY,"
        "pubkey TEXT NOT NULL,"
        "balance REAL DEFAULT 0,"
        "encrypted_secret TEXT)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS multi_wallets ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER NOT NULL,"
        "wallet_index INTEGER NOT NULL,"
        "pubkey TEXT NOT NULL,"
        "encrypted_secret TEXT NOT NULL,"
        "label TEXT,"
        "is_active INTEGER DEFAULT 0,"
        "created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        "UNIQUE(user_id, wallet_index))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS user_settings ("
        "user_id INTEGER PRIMARY KEY,"
        "slippage_buy_bps INTEGER DEFAULT 100,"
        "slippage_sell_bps INTEGER DEFAULT 100,"
        "tip_enabled INTEGER DEFAULT 0,"
        "tip_lamports INTEGER DEFAULT 1000000,"
        "priority_fee_enabled INTEGER DEFAULT 0,"
        "priority_fee_microlamports INTEGER DEFAULT 100000,"
        "anti_mev_buy_sell INTEGER DEFAULT 0,"
        "anti_mev_sniper INTEGER DEFAULT 0,"
        "custom_buy_buttons TEXT DEFAULT '[0.01,0.05,0.1]',"
        "custom_sell_buttons TEXT DEFAULT '[25,50,100]',"
        "num_wallets_display INTEGER DEFAULT 3,"
        "auto_buy_enabled INTEGER DEFAULT 0,"
        "auto_buy_sol REAL DEFAULT 0,"
        "auto_buy_wallets TEXT DEFAULT '[]',"
        "ca_sell_enabled INTEGER DEFAULT 0,"
        "ca_sell_percent INTEGER DEFAULT 100,"
        "ca_sell_wallets TEXT DEFAULT '[]')"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS orders ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER NOT NULL,"
        "order_type TEXT NOT NULL,"
        "token_address TEXT NOT NULL,"
        "token_name TEXT,"
        "wallet_pubkey TEXT NOT NULL,"
        "params TEXT NOT NULL,"
        "status TEXT DEFAULT 'active',"
        "created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        "expires_at TEXT,"
        "last_run_at TEXT)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS copy_targets ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER NOT NULL,"
        "source_wallet_pubkey TEXT NOT NULL,"
        "target_label TEXT,"
        "target_wallet TEXT NOT NULL,"
        "copy_buy_enabled INTEGER DEFAULT 1,"
        "copy_buy_sol REAL DEFAULT 0.1,"
        "copy_sell_enabled INTEGER DEFAULT 1,"
        "copy_sell_percent INTEGER DEFAULT 100,"
        "active INTEGER DEFAULT 1,"
        "last_seen_signature TEXT,"
        "created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        "UNIQUE(user_id, target_wallet))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS snipers ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER NOT NULL,"
        "sniper_type TEXT NOT NULL,"
        "token_address TEXT,"
        "token_symbol TEXT,"
        "dev_wallet TEXT,"
        "wallet_pubkey TEXT NOT NULL,"
        "params TEXT NOT NULL,"
        "status TEXT DEFAULT 'watching',"
        "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS pnl_trackers ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER NOT NULL,"
        "token_address TEXT NOT NULL,"
        "token_name TEXT,"
        "message_id INTEGER,"
        "chat_id INTEGER,"
        "entry_price REAL DEFAULT 0,"
        "entry_lamports INTEGER DEFAULT 0,"
        "created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        "UNIQUE(user_id, token_address))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS cashback ("
        "user_id INTEGER PRIMARY KEY,"
        "total_earned_usd REAL DEFAULT 0,"
        "claimed_usd REAL DEFAULT 0,"
        "last_claim_at TEXT)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS referrals ("
        "user_id INTEGER PRIMARY KEY,"
        "referred_by INTEGER,"
        "referred_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        "total_earned_usd REAL DEFAULT 0)"
    )
    c.commit()
    c.close()


# ── Messages ──────────────────────────────────
def save_message(timestamp, chat_id, user_id, username, full_name, message_id, text, media_type, media_path=None):
    c = _conn()
    c.execute(
        "INSERT INTO messages (timestamp, chat_id, user_id, username, full_name, message_id, text, media_type, media_path)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (timestamp, chat_id, user_id, username, full_name, message_id, text, media_type, media_path),
    )
    c.commit(); c.close()


def get_stats():
    c = _conn()
    total = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    by_type = c.execute("SELECT media_type, COUNT(*) FROM messages GROUP BY media_type ORDER BY COUNT(*) DESC").fetchall()
    unique_users = c.execute("SELECT COUNT(DISTINCT user_id) FROM messages").fetchone()[0]
    today = c.execute("SELECT COUNT(*) FROM messages WHERE DATE(timestamp) = DATE('now')").fetchone()[0]
    c.close()
    return {"total": total, "by_type": by_type, "unique_users": unique_users, "today": today}


# ── User filters ──────────────────────────────
def get_filter_lists():
    c = _conn()
    rows = c.execute("SELECT user_id, list_type FROM user_filters").fetchall()
    c.close()
    return rows


def add_user_filter(user_id, username, list_type):
    c = _conn()
    c.execute("INSERT OR REPLACE INTO user_filters (user_id, username, list_type) VALUES (?, ?, ?)", (user_id, username, list_type))
    c.commit(); c.close()


def remove_user_filter(user_id):
    c = _conn()
    c.execute("DELETE FROM user_filters WHERE user_id = ?", (user_id,))
    c.commit(); c.close()


# ── Legacy single wallet ──────────────────────
def save_wallet(user_id, pubkey, balance):
    c = _conn()
    c.execute("INSERT OR REPLACE INTO wallets (user_id, pubkey, balance) VALUES (?, ?, ?)", (user_id, pubkey, balance))
    c.commit(); c.close()


def save_wallet_with_secret(user_id, pubkey, encrypted_secret, balance=0):
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO wallets (user_id, pubkey, balance, encrypted_secret) VALUES (?, ?, ?, ?)",
        (user_id, pubkey, balance, encrypted_secret),
    )
    c.commit(); c.close()


def get_wallet(user_id):
    c = _conn()
    row = c.execute("SELECT pubkey, balance FROM wallets WHERE user_id = ?", (user_id,)).fetchone()
    c.close()
    return {"pubkey": row[0], "balance": row[1]} if row else None


def get_wallet_secret(user_id):
    c = _conn()
    row = c.execute("SELECT encrypted_secret FROM wallets WHERE user_id = ?", (user_id,)).fetchone()
    c.close()
    return row[0] if row and row[0] else None


# ── Multi-wallet ──────────────────────────────
def mw_save(user_id, index, pubkey, encrypted_secret, label=None):
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO multi_wallets (user_id, wallet_index, pubkey, encrypted_secret, label)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, index, pubkey, encrypted_secret, label),
    )
    c.commit(); c.close()


def mw_list(user_id):
    c = _conn()
    rows = c.execute(
        "SELECT wallet_index, pubkey, label, is_active FROM multi_wallets WHERE user_id = ? ORDER BY wallet_index",
        (user_id,),
    ).fetchall()
    c.close()
    return [{"index": r[0], "pubkey": r[1], "label": r[2], "active": bool(r[3])} for r in rows]


def mw_get(user_id, index):
    c = _conn()
    row = c.execute(
        "SELECT pubkey, encrypted_secret, label FROM multi_wallets WHERE user_id = ? AND wallet_index = ?",
        (user_id, index),
    ).fetchone()
    c.close()
    return {"pubkey": row[0], "encrypted_secret": row[1], "label": row[2]} if row else None


def mw_delete(user_id, index):
    c = _conn()
    c.execute("DELETE FROM multi_wallets WHERE user_id = ? AND wallet_index = ?", (user_id, index))
    c.commit(); c.close()


def mw_next_index(user_id):
    c = _conn()
    row = c.execute("SELECT MAX(wallet_index) FROM multi_wallets WHERE user_id = ?", (user_id,)).fetchone()
    c.close()
    return (row[0] or 0) + 1


def mw_set_active(user_id, index):
    c = _conn()
    c.execute("UPDATE multi_wallets SET is_active = 0 WHERE user_id = ?", (user_id,))
    c.execute("UPDATE multi_wallets SET is_active = 1 WHERE user_id = ? AND wallet_index = ?", (user_id, index))
    c.commit(); c.close()


def mw_active(user_id):
    c = _conn()
    row = c.execute(
        "SELECT wallet_index, pubkey, encrypted_secret FROM multi_wallets WHERE user_id = ? AND is_active = 1",
        (user_id,),
    ).fetchone()
    if not row:
        row = c.execute(
            "SELECT wallet_index, pubkey, encrypted_secret FROM multi_wallets WHERE user_id = ? ORDER BY wallet_index LIMIT 1",
            (user_id,),
        ).fetchone()
    c.close()
    return {"index": row[0], "pubkey": row[1], "encrypted_secret": row[2]} if row else None


def get_any_active_wallet(user_id):
    """
    Return the active wallet regardless of single or multi-wallet mode.
    Returns dict: {pubkey, encrypted_secret, source} or None.
    """
    mw = mw_active(user_id)
    if mw and mw.get("encrypted_secret"):
        return {
            "pubkey": mw["pubkey"],
            "encrypted_secret": mw["encrypted_secret"],
            "source": "multi",
            "index": mw.get("index"),
        }
    single_enc = get_wallet_secret(user_id)
    single_w = get_wallet(user_id)
    if single_enc and single_w:
        return {
            "pubkey": single_w["pubkey"],
            "encrypted_secret": single_enc,
            "source": "single",
        }
    if single_w:
        return {
            "pubkey": single_w["pubkey"],
            "encrypted_secret": None,
            "source": "single_no_secret",
        }
    return None


# ── Settings ──────────────────────────────────
def settings_get(user_id):
    c = _conn()
    c.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
    c.commit()
    row = c.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    cols = [d[0] for d in c.execute("SELECT * FROM user_settings LIMIT 0").description]
    c.close()
    return dict(zip(cols, row))


def settings_set(user_id, **kwargs):
    if not kwargs:
        return
    c = _conn()
    c.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
    for k, v in kwargs.items():
        c.execute(f"UPDATE user_settings SET {k} = ? WHERE user_id = ?", (v, user_id))
    c.commit(); c.close()


# ── Orders ────────────────────────────────────
def order_create(user_id, order_type, token_address, token_name, wallet_pubkey, params, expires_at=None):
    c = _conn()
    cur = c.execute(
        "INSERT INTO orders (user_id, order_type, token_address, token_name, wallet_pubkey, params, expires_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, order_type, token_address, token_name, wallet_pubkey, json.dumps(params), expires_at),
    )
    oid = cur.lastrowid
    c.commit(); c.close()
    return oid


def order_list(user_id, order_type=None, status="active"):
    c = _conn()
    if order_type:
        rows = c.execute(
            "SELECT * FROM orders WHERE user_id = ? AND order_type = ? AND status = ?",
            (user_id, order_type, status),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM orders WHERE user_id = ? AND status = ?",
            (user_id, status),
        ).fetchall()
    cols = [d[0] for d in c.execute("SELECT * FROM orders LIMIT 0").description]
    c.close()
    return [dict(zip(cols, r)) for r in rows]


def order_update(order_id, **kwargs):
    if not kwargs:
        return
    c = _conn()
    for k, v in kwargs.items():
        c.execute(f"UPDATE orders SET {k} = ? WHERE id = ?", (v, order_id))
    c.commit(); c.close()


def order_delete(order_id):
    c = _conn()
    c.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    c.commit(); c.close()


def order_active_all():
    c = _conn()
    rows = c.execute("SELECT * FROM orders WHERE status = 'active'").fetchall()
    cols = [d[0] for d in c.execute("SELECT * FROM orders LIMIT 0").description]
    c.close()
    return [dict(zip(cols, r)) for r in rows]


# ── Copy targets ──────────────────────────────
def copy_create(user_id, source_wallet, label, target_wallet, buy_sol, sell_percent):
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO copy_targets"
        " (user_id, source_wallet_pubkey, target_label, target_wallet, copy_buy_sol, copy_sell_percent)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, source_wallet, label, target_wallet, buy_sol, sell_percent),
    )
    c.commit(); c.close()


def copy_list(user_id):
    c = _conn()
    rows = c.execute(
        "SELECT id, source_wallet_pubkey, target_label, target_wallet, copy_buy_enabled, copy_buy_sol, copy_sell_enabled, copy_sell_percent, active"
        " FROM copy_targets WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    c.close()
    return [dict(zip(
        ["id", "source_wallet_pubkey", "target_label", "target_wallet",
         "copy_buy_enabled", "copy_buy_sol", "copy_sell_enabled", "copy_sell_percent", "active"],
        r,
    )) for r in rows]


def copy_delete(user_id, target_id):
    c = _conn()
    c.execute("DELETE FROM copy_targets WHERE id = ? AND user_id = ?", (target_id, user_id))
    c.commit(); c.close()


def copy_active_all():
    c = _conn()
    rows = c.execute("SELECT * FROM copy_targets WHERE active = 1").fetchall()
    cols = [d[0] for d in c.execute("SELECT * FROM copy_targets LIMIT 0").description]
    c.close()
    return [dict(zip(cols, r)) for r in rows]


def copy_set_last_seen(target_id, signature):
    c = _conn()
    c.execute("UPDATE copy_targets SET last_seen_signature = ? WHERE id = ?", (signature, target_id))
    c.commit(); c.close()


# ── PNL Trackers ──────────────────────────────
def pnl_tracker_upsert(user_id, token_address, token_name, chat_id, message_id, entry_price, entry_lamports):
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO pnl_trackers"
        " (user_id, token_address, token_name, chat_id, message_id, entry_price, entry_lamports)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, token_address, token_name, chat_id, message_id, entry_price, entry_lamports),
    )
    c.commit(); c.close()


def pnl_trackers_all():
    c = _conn()
    rows = c.execute("SELECT * FROM pnl_trackers").fetchall()
    cols = [d[0] for d in c.execute("SELECT * FROM pnl_trackers LIMIT 0").description]
    c.close()
    return [dict(zip(cols, r)) for r in rows]


def pnl_tracker_delete(tracker_id):
    c = _conn()
    c.execute("DELETE FROM pnl_trackers WHERE id = ?", (tracker_id,))
    c.commit(); c.close()