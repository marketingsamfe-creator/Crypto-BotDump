import sqlite3
import os
import json
import shutil
from datetime import datetime
from .logger import logger

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "portfolio.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coin_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT DEFAULT '',
            quantity REAL DEFAULT 0,
            avg_entry_price REAL DEFAULT 0,
            cost_basis_usd REAL DEFAULT 0,
            realized_pnl_usd REAL DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS portfolio_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coin_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            type TEXT NOT NULL,
            quantity REAL,
            price_usd REAL,
            total_usd REAL,
            fee_usd REAL DEFAULT 0,
            realized_pnl_usd REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS cash_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            amount_usd REAL NOT NULL,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS portfolio_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_positions_active ON portfolio_positions(active);
        CREATE INDEX IF NOT EXISTS idx_positions_symbol ON portfolio_positions(symbol);
        CREATE INDEX IF NOT EXISTS idx_transactions_coin ON portfolio_transactions(coin_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_created ON portfolio_transactions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cash_created ON cash_movements(created_at DESC);
    """)
    conn.commit()
    conn.close()


def migrate_from_json():
    from . import storage as json_store
    pdata = json_store.load_portfolio_data()
    if not pdata or not pdata.get("entry_prices"):
        logger.info("No JSON portfolio data to migrate")
        return

    conn = _conn()
    existing = conn.execute("SELECT COUNT(*) FROM portfolio_positions").fetchone()[0]
    if existing > 0:
        logger.info("Portfolio already migrated, skipping")
        conn.close()
        return

    entries = pdata.get("entry_prices", {})
    qtys = pdata.get("quantities", {})
    invested = pdata.get("total_invested", 0)
    now = datetime.utcnow().isoformat()

    for sym, price in entries.items():
        qty = qtys.get(sym, 0)
        cost_basis = qty * price
        conn.execute("""
            INSERT INTO portfolio_positions
                (coin_id, symbol, name, quantity, avg_entry_price, cost_basis_usd,
                 realized_pnl_usd, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?, ?)
        """, (sym.lower(), sym, "", qty, price, cost_basis, now, now))

    if invested > 0:
        conn.execute("""
            INSERT INTO cash_movements (type, amount_usd, notes, created_at)
            VALUES (?, ?, ?, ?)
        """, ("deposit", invested, "Migrated from JSON portfolio", now))

    conn.execute("REPLACE INTO portfolio_state (key, value) VALUES (?, ?)",
                 ("migrated_from_json", "true"))
    conn.execute("REPLACE INTO portfolio_state (key, value) VALUES (?, ?)",
                 ("migrated_at", now))
    conn.commit()
    conn.close()

    backup_path = os.path.join(DATA_DIR, "portfolio_data.json.bak")
    json_path = os.path.join(DATA_DIR, "portfolio_data.json")
    if os.path.exists(json_path) and not os.path.exists(backup_path):
        shutil.copy2(json_path, backup_path)
        logger.info(f"Backed up portfolio_data.json to portfolio_data.json.bak")

    logger.info(f"Migration complete: {len(entries)} positions migrated")


# --- Positions ---

def get_active_positions():
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM portfolio_positions WHERE active = 1 ORDER BY symbol"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_positions(include_inactive=False):
    conn = _conn()
    if include_inactive:
        rows = conn.execute(
            "SELECT * FROM portfolio_positions ORDER BY active DESC, symbol"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM portfolio_positions WHERE active = 1 ORDER BY symbol"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_position(symbol):
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM portfolio_positions WHERE symbol = ? AND active = 1",
        (symbol.upper(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_position_by_coin_id(coin_id):
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM portfolio_positions WHERE coin_id = ? AND active = 1",
        (coin_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_position(coin_id, symbol, name=""):
    conn = _conn()
    existing = conn.execute(
        "SELECT * FROM portfolio_positions WHERE coin_id = ? AND active = 1",
        (coin_id,)
    ).fetchone()
    if existing:
        conn.close()
        return dict(existing)
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO portfolio_positions
            (coin_id, symbol, name, quantity, avg_entry_price, cost_basis_usd,
             realized_pnl_usd, active, created_at, updated_at)
        VALUES (?, ?, ?, 0, 0, 0, 0, 1, ?, ?)
    """, (coin_id, symbol.upper(), name, now, now))
    conn.commit()
    row = conn.execute(
        "SELECT * FROM portfolio_positions WHERE coin_id = ?", (coin_id,)
    ).fetchone()
    conn.close()
    return dict(row)


def archive_position(symbol):
    conn = _conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE portfolio_positions SET active = 0, updated_at = ? WHERE symbol = ?",
        (now, symbol.upper())
    )
    conn.commit()
    conn.close()


def update_position_after_buy(symbol, qty_bought, price_usd, fee_usd=0):
    pos = get_position(symbol.upper())
    conn = _conn()
    now = datetime.utcnow().isoformat()
    if not pos:
        return None
    old_qty = pos["quantity"]
    old_cost = pos["cost_basis_usd"]
    total_cost = qty_bought * price_usd + fee_usd
    new_qty = old_qty + qty_bought
    new_cost_basis = old_cost + total_cost
    new_avg = new_cost_basis / new_qty if new_qty > 0 else 0
    conn.execute("""
        UPDATE portfolio_positions
        SET quantity = ?, avg_entry_price = ?, cost_basis_usd = ?, updated_at = ?
        WHERE id = ?
    """, (new_qty, new_avg, new_cost_basis, now, pos["id"]))
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM portfolio_positions WHERE id = ?", (pos["id"],)
    ).fetchone()
    conn.close()
    return dict(updated)


def update_position_after_sell(symbol, qty_sold, price_usd, fee_usd=0):
    pos = get_position(symbol.upper())
    if not pos:
        return None
    conn = _conn()
    now = datetime.utcnow().isoformat()
    old_qty = pos["quantity"]
    if qty_sold > old_qty:
        conn.close()
        return None
    proceeds = qty_sold * price_usd
    cost_removed = pos["avg_entry_price"] * qty_sold
    realized_pnl = proceeds - cost_removed - fee_usd
    new_qty = old_qty - qty_sold
    new_cost_basis = pos["avg_entry_price"] * new_qty
    new_realized = pos["realized_pnl_usd"] + realized_pnl
    conn.execute("""
        UPDATE portfolio_positions
        SET quantity = ?, cost_basis_usd = ?, realized_pnl_usd = ?,
            active = ?, updated_at = ?
        WHERE id = ?
    """, (new_qty, new_cost_basis, new_realized,
          1 if new_qty > 0 else 0, now, pos["id"]))
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM portfolio_positions WHERE id = ?", (pos["id"],)
    ).fetchone()
    conn.close()
    return dict(updated), realized_pnl, proceeds


def edit_position(symbol, new_qty, new_avg_price):
    pos = get_position(symbol.upper())
    if not pos:
        return None
    conn = _conn()
    now = datetime.utcnow().isoformat()
    new_cost = new_qty * new_avg_price
    conn.execute("""
        UPDATE portfolio_positions
        SET quantity = ?, avg_entry_price = ?, cost_basis_usd = ?, updated_at = ?
        WHERE id = ?
    """, (new_qty, new_avg_price, new_cost, now, pos["id"]))
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM portfolio_positions WHERE id = ?", (pos["id"],)
    ).fetchone()
    conn.close()
    return dict(updated)


# --- Transactions ---

def add_transaction(coin_id, symbol, ttype, quantity, price_usd, total_usd,
                    fee_usd=0, realized_pnl_usd=0, notes=""):
    conn = _conn()
    conn.execute("""
        INSERT INTO portfolio_transactions
            (coin_id, symbol, type, quantity, price_usd, total_usd,
             fee_usd, realized_pnl_usd, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (coin_id, symbol.upper(), ttype, quantity, price_usd, total_usd,
          fee_usd, realized_pnl_usd, notes))
    conn.commit()
    conn.close()


def get_transactions(symbol=None, limit=20):
    conn = _conn()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM portfolio_transactions WHERE symbol = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (symbol.upper(), limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM portfolio_transactions ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Cash ---

def get_cash_balance():
    conn = _conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_usd), 0) as balance FROM cash_movements "
        "WHERE type IN ('deposit','sell','buy','withdraw','fee','adjustment')"
    ).fetchone()
    conn.close()
    return row["balance"] if row else 0


def add_cash_movement(mtype, amount_usd, notes=""):
    conn = _conn()
    conn.execute(
        "INSERT INTO cash_movements (type, amount_usd, notes) VALUES (?, ?, ?)",
        (mtype, amount_usd, notes)
    )
    conn.commit()
    conn.close()


def set_cash_balance(target_usd):
    current = get_cash_balance()
    diff = target_usd - current
    if abs(diff) < 0.01:
        return current
    add_cash_movement("adjustment", diff,
                      f"Manual cash adjustment to ${target_usd:,.2f}")
    return target_usd


def get_cash_history(limit=20):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM cash_movements ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
