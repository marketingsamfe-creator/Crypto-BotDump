import sqlite3
import os
from datetime import datetime
from typing import Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "crypto_bot.db")


def get_connection() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database():
    conn = get_connection()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT UNIQUE NOT NULL,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT DEFAULT 'My Portfolio',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS portfolio_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            token_name TEXT DEFAULT '',
            symbol TEXT NOT NULL,
            contract_address TEXT DEFAULT '',
            network TEXT DEFAULT '',
            amount REAL DEFAULT 0,
            buy_price REAL DEFAULT 0,
            buy_date TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
        );

        CREATE TABLE IF NOT EXISTS token_price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id TEXT NOT NULL,
            symbol TEXT DEFAULT '',
            contract_address TEXT DEFAULT '',
            network TEXT DEFAULT '',
            price REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_token_id ON token_price_snapshots(token_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON token_price_snapshots(created_at);
        CREATE INDEX IF NOT EXISTS idx_snapshots_contract ON token_price_snapshots(contract_address, network);

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_id TEXT DEFAULT '',
            symbol TEXT DEFAULT '',
            contract_address TEXT DEFAULT '',
            network TEXT DEFAULT '',
            alert_type TEXT NOT NULL,
            target_value REAL DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            dump_alerts_enabled INTEGER DEFAULT 1,
            hourly_report_enabled INTEGER DEFAULT 0,
            default_currency TEXT DEFAULT 'usd',
            timezone TEXT DEFAULT 'UTC',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS watched_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_id TEXT DEFAULT '',
            symbol TEXT DEFAULT '',
            contract_address TEXT DEFAULT '',
            network TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_watched_user ON watched_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id);
        CREATE INDEX IF NOT EXISTS idx_portfolio_tokens_portfolio ON portfolio_tokens(portfolio_id);
        CREATE INDEX IF NOT EXISTS idx_portfolio_tokens_symbol ON portfolio_tokens(symbol);
        """)
        conn.commit()
    finally:
        conn.close()


def register_user(telegram_id: str, username: str = "", first_name: str = "") -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        return row["id"] if row else 0
    finally:
        conn.close()


def get_or_create_portfolio(user_id: int, name: str = "My Portfolio") -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM portfolios WHERE user_id = ? ORDER BY id LIMIT 1",
            (user_id,)
        ).fetchone()
        if row:
            return row["id"]
        cur = conn.execute(
            "INSERT INTO portfolios (user_id, name) VALUES (?, ?)",
            (user_id, name)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def add_portfolio_token(
    portfolio_id: int,
    symbol: str,
    amount: float,
    buy_price: float,
    token_name: str = "",
    contract_address: str = "",
    network: str = "",
    buy_date: str = "",
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO portfolio_tokens
               (portfolio_id, token_name, symbol, contract_address, network, amount, buy_price, buy_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (portfolio_id, token_name, symbol.upper(), contract_address, network, amount, buy_price, buy_date)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_portfolio_tokens(portfolio_id: int) -> list:
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT * FROM portfolio_tokens WHERE portfolio_id = ? ORDER BY symbol",
            (portfolio_id,)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def remove_portfolio_token(token_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM portfolio_tokens WHERE id = ?", (token_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_user_settings(user_id: int) -> dict:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)",
            (user_id,)
        )
        conn.commit()
        return {"dump_alerts_enabled": 1, "hourly_report_enabled": 0, "default_currency": "usd", "timezone": "UTC"}
    finally:
        conn.close()


def update_user_setting(user_id: int, key: str, value) -> bool:
    allowed = {"dump_alerts_enabled", "hourly_report_enabled", "default_currency", "timezone"}
    if key not in allowed:
        return False
    conn = get_connection()
    try:
        conn.execute(
            f"INSERT INTO user_settings (user_id, {key}) VALUES (?, ?) "
            f"ON CONFLICT(user_id) DO UPDATE SET {key}=excluded.{key}, updated_at=datetime('now')",
            (user_id, int(value) if isinstance(value, bool) else value)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def add_price_snapshot(token_id: str, price: float, symbol: str = "", contract_address: str = "", network: str = ""):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO token_price_snapshots
               (token_id, symbol, contract_address, network, price)
               VALUES (?, ?, ?, ?, ?)""",
            (token_id, symbol, contract_address, network, price)
        )
        conn.commit()
    finally:
        conn.close()


def get_price_snapshots(token_id: str, hours: int = 24) -> list:
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT * FROM token_price_snapshots WHERE token_id = ? AND created_at >= datetime('now', ? || ' hours') ORDER BY created_at DESC",
            (token_id, f"-{hours}")
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_price_change(token_id: str, hours: int) -> Optional[float]:
    conn = get_connection()
    try:
        current = conn.execute(
            "SELECT price FROM token_price_snapshots WHERE token_id = ? ORDER BY created_at DESC LIMIT 1",
            (token_id,)
        ).fetchone()
        old = conn.execute(
            "SELECT price FROM token_price_snapshots WHERE token_id = ? AND created_at <= datetime('now', ? || ' hours') ORDER BY created_at DESC LIMIT 1",
            (token_id, f"-{hours}")
        ).fetchone()
        if current and old and old["price"] > 0:
            return ((current["price"] - old["price"]) / old["price"]) * 100
        return None
    finally:
        conn.close()


def get_watched_tokens(user_id: int) -> list:
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT * FROM watched_tokens WHERE user_id = ? ORDER BY symbol",
            (user_id,)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def add_watched_token(user_id: int, token_id: str, symbol: str = "", contract_address: str = "", network: str = ""):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO watched_tokens (user_id, token_id, symbol, contract_address, network) VALUES (?, ?, ?, ?, ?)",
            (user_id, token_id, symbol, contract_address, network)
        )
        conn.commit()
    finally:
        conn.close()


def remove_watched_token(user_id: int, token_id: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM watched_tokens WHERE user_id = ? AND token_id = ?",
            (user_id, token_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_all_tracked_token_ids() -> list:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT token_id FROM ("
            "  SELECT token_id FROM portfolio_tokens WHERE token_id != '' "
            "  UNION "
            "  SELECT token_id FROM watched_tokens WHERE token_id != ''"
            ")"
        ).fetchall()
        return [r["token_id"] for r in rows]
    finally:
        conn.close()
