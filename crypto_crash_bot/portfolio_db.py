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


def _build_token_key(source, chain_id, contract_address):
    if source == "coingecko":
        return f"coingecko:{chain_id}"
    return f"{source}:{chain_id}:{contract_address}" if contract_address else f"{source}:{chain_id}"


def init_db():
    conn = _conn()
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-8000")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coin_id TEXT NOT NULL DEFAULT '',
            symbol TEXT NOT NULL,
            name TEXT DEFAULT '',
            token_key TEXT DEFAULT '',
            source TEXT DEFAULT '',
            chain_id TEXT DEFAULT '',
            contract_address TEXT DEFAULT '',
            pair_address TEXT DEFAULT '',
            dex_id TEXT DEFAULT '',
            quantity REAL DEFAULT 0,
            avg_entry_price REAL DEFAULT 0,
            cost_basis_usd REAL DEFAULT 0,
            realized_pnl_usd REAL DEFAULT 0,
            is_test INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS portfolio_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coin_id TEXT NOT NULL DEFAULT '',
            symbol TEXT NOT NULL,
            token_key TEXT DEFAULT '',
            source TEXT DEFAULT '',
            chain_id TEXT DEFAULT '',
            contract_address TEXT DEFAULT '',
            pair_address TEXT DEFAULT '',
            dex_id TEXT DEFAULT '',
            type TEXT NOT NULL,
            quantity REAL,
            price_usd REAL,
            total_usd REAL,
            fee_usd REAL DEFAULT 0,
            realized_pnl_usd REAL DEFAULT 0,
            is_test INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS cash_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            amount_usd REAL NOT NULL,
            is_test INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS portfolio_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_positions_active ON portfolio_positions(active);
        CREATE INDEX IF NOT EXISTS idx_positions_symbol ON portfolio_positions(symbol);
        CREATE INDEX IF NOT EXISTS idx_positions_token_key ON portfolio_positions(token_key);
        CREATE INDEX IF NOT EXISTS idx_transactions_coin ON portfolio_transactions(coin_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_token_key ON portfolio_transactions(token_key);
        CREATE INDEX IF NOT EXISTS idx_transactions_created ON portfolio_transactions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cash_created ON cash_movements(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_positions_is_test ON portfolio_positions(is_test);
        CREATE INDEX IF NOT EXISTS idx_positions_updated ON portfolio_positions(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_transactions_is_test ON portfolio_transactions(is_test);
        CREATE INDEX IF NOT EXISTS idx_transactions_type ON portfolio_transactions(type);
    """)
    conn.commit()

    existing = conn.execute("PRAGMA table_info(portfolio_positions)").fetchall()
    existing_cols = {r["name"] for r in existing}
    migrations = []
    for col, typ in [("token_key", "TEXT DEFAULT ''"), ("source", "TEXT DEFAULT ''"),
                     ("chain_id", "TEXT DEFAULT ''"), ("contract_address", "TEXT DEFAULT ''"),
                     ("pair_address", "TEXT DEFAULT ''"), ("dex_id", "TEXT DEFAULT ''"),
                     ("is_test", "INTEGER DEFAULT 0")]:
        if col not in existing_cols:
            migrations.append(f"ALTER TABLE portfolio_positions ADD COLUMN {col} {typ}")
    existing_t = conn.execute("PRAGMA table_info(portfolio_transactions)").fetchall()
    existing_tcols = {r["name"] for r in existing_t}
    for col, typ in [("token_key", "TEXT DEFAULT ''"), ("source", "TEXT DEFAULT ''"),
                     ("chain_id", "TEXT DEFAULT ''"), ("contract_address", "TEXT DEFAULT ''"),
                     ("pair_address", "TEXT DEFAULT ''"), ("dex_id", "TEXT DEFAULT ''"),
                     ("is_test", "INTEGER DEFAULT 0")]:
        if col not in existing_tcols:
            migrations.append(f"ALTER TABLE portfolio_transactions ADD COLUMN {col} {typ}")
    existing_c = conn.execute("PRAGMA table_info(cash_movements)").fetchall()
    existing_ccols = {r["name"] for r in existing_c}
    if "is_test" not in existing_ccols:
        migrations.append("ALTER TABLE cash_movements ADD COLUMN is_test INTEGER DEFAULT 0")
    for m in migrations:
        conn.execute(m)
    if migrations:
        conn.commit()
        logger.info(f"Applied {len(migrations)} portfolio schema migrations")
    conn.close()


def migrate_from_json():
    from . import config as cfg
    from . import storage as json_store

    conn = _conn()
    existing = conn.execute("SELECT COUNT(*) FROM portfolio_positions").fetchone()[0]
    if existing > 0:
        logger.info("Portfolio already migrated, skipping")
        conn.close()
        return

    pdata = json_store.load_portfolio_data()
    entries = pdata.get("entry_prices", {}) if pdata else {}
    qtys = pdata.get("quantities", {}) if pdata else {}
    invested = pdata.get("total_invested", 0) if pdata else 0
    now = datetime.utcnow().isoformat()
    migrated_count = 0

    if entries:
        for sym, price in entries.items():
            qty = qtys.get(sym, 0)
            cost_basis = qty * price
            conn.execute("""
                INSERT INTO portfolio_positions
                    (coin_id, symbol, name, quantity, avg_entry_price, cost_basis_usd,
                     realized_pnl_usd, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?, ?)
            """, (sym.lower(), sym, "", qty, price, cost_basis, now, now))
            migrated_count += 1
        logger.info(f"Migrated {migrated_count} positions from portfolio_data.json")
    else:
        entries_from_config = getattr(cfg, "PORTFOLIO", [])
        for coin_def in entries_from_config:
            slug = coin_def["slug"]
            symbol = coin_def["symbol"]
            name = coin_def["name"]
            conn.execute("""
                INSERT INTO portfolio_positions
                    (coin_id, symbol, name, quantity, avg_entry_price, cost_basis_usd,
                     realized_pnl_usd, active, created_at, updated_at)
                VALUES (?, ?, ?, 0, 0, 0, 0, 1, ?, ?)
            """, (slug, symbol, name, now, now))
            migrated_count += 1
        logger.info(f"Bootstrapped {migrated_count} positions from config.PORTFOLIO")

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
    logger.info(f"Migration complete: {migrated_count} positions")


def _row_to_dict(row):
    if row is None:
        return None
    return dict(row)


# --- Positions ---

def get_all_positions(is_test=0):
    return get_active_positions(is_test)


def hard_delete_position(symbol=None, token_key=None, is_test=0):
    conn = _conn()
    if token_key:
        deleted = conn.execute(
            "DELETE FROM portfolio_positions WHERE token_key = ? AND is_test = ?",
            (token_key, is_test)
        ).rowcount
    elif symbol:
        deleted = conn.execute(
            "DELETE FROM portfolio_positions WHERE symbol = ? AND is_test = ?",
            (symbol.upper(), is_test)
        ).rowcount
    else:
        deleted = 0
    conn.commit()
    conn.close()
    return deleted


def get_active_positions(is_test=0):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM portfolio_positions WHERE active = 1 AND is_test = ? ORDER BY symbol",
        (is_test,)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_position(symbol=None, token_key=None, is_test=0):
    conn = _conn()
    if token_key:
        row = conn.execute(
            "SELECT * FROM portfolio_positions WHERE token_key = ? AND active = 1 AND is_test = ?",
            (token_key, is_test)
        ).fetchone()
    elif symbol:
        row = conn.execute(
            "SELECT * FROM portfolio_positions WHERE symbol = ? AND active = 1 AND is_test = ?",
            (symbol.upper(), is_test)
        ).fetchone()
    else:
        row = None
    conn.close()
    return _row_to_dict(row)


def add_position(coin_id, symbol, name="", token_key="", source="", chain_id="",
                 contract_address="", pair_address="", dex_id="", is_test=0):
    conn = _conn()
    if token_key:
        existing = conn.execute(
            "SELECT * FROM portfolio_positions WHERE token_key = ? AND active = 1 AND is_test = ?",
            (token_key, is_test)
        ).fetchone()
        if existing:
            conn.close()
            return _row_to_dict(existing)
    else:
        existing = conn.execute(
            "SELECT * FROM portfolio_positions WHERE coin_id = ? AND active = 1 AND is_test = ?",
            (coin_id, is_test)
        ).fetchone()
        if existing:
            conn.close()
            return _row_to_dict(existing)
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO portfolio_positions
            (coin_id, symbol, name, token_key, source, chain_id, contract_address,
             pair_address, dex_id, quantity, avg_entry_price, cost_basis_usd,
             realized_pnl_usd, is_test, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?, 1, ?, ?)
    """, (coin_id, symbol.upper(), name, token_key, source, chain_id,
          contract_address, pair_address, dex_id, is_test, now, now))
    conn.commit()
    if token_key:
        row = conn.execute(
            "SELECT * FROM portfolio_positions WHERE token_key = ?", (token_key,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM portfolio_positions WHERE coin_id = ?", (coin_id,)
        ).fetchone()
    conn.close()
    return _row_to_dict(row)


def archive_position(symbol=None, token_key=None, is_test=0):
    conn = _conn()
    now = datetime.utcnow().isoformat()
    if token_key:
        conn.execute(
            "UPDATE portfolio_positions SET active = 0, updated_at = ? WHERE token_key = ? AND is_test = ?",
            (now, token_key, is_test)
        )
    else:
        conn.execute(
            "UPDATE portfolio_positions SET active = 0, updated_at = ? WHERE symbol = ? AND is_test = ?",
            (now, symbol.upper(), is_test)
        )
    conn.commit()
    conn.close()


def update_position_after_buy(symbol, qty_bought, price_usd, fee_usd=0, token_key=None, is_test=0):
    pos = get_position(symbol=symbol, token_key=token_key, is_test=is_test)
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
    return _row_to_dict(updated)


def update_position_after_sell(symbol, qty_sold, price_usd, fee_usd=0, token_key=None, is_test=0):
    pos = get_position(symbol=symbol, token_key=token_key, is_test=is_test)
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
    return _row_to_dict(updated), realized_pnl, proceeds


def edit_position(symbol, new_qty, new_avg_price, token_key=None):
    pos = get_position(symbol=symbol, token_key=token_key)
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
    return _row_to_dict(updated)


# --- Transactions ---

def add_transaction(coin_id, symbol, ttype, quantity, price_usd, total_usd,
                    fee_usd=0, realized_pnl_usd=0, notes="",
                    token_key="", source="", chain_id="", contract_address="",
                    pair_address="", dex_id="", is_test=0):
    conn = _conn()
    conn.execute("""
        INSERT INTO portfolio_transactions
            (coin_id, symbol, token_key, source, chain_id, contract_address,
             pair_address, dex_id, type, quantity, price_usd, total_usd,
             fee_usd, realized_pnl_usd, is_test, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (coin_id, symbol.upper(), token_key, source, chain_id, contract_address,
          pair_address, dex_id, ttype, quantity, price_usd, total_usd,
          fee_usd, realized_pnl_usd, is_test, notes))
    conn.commit()
    conn.close()


def get_transactions(symbol=None, token_key=None, limit=20, is_test=0):
    conn = _conn()
    if token_key:
        rows = conn.execute(
            "SELECT * FROM portfolio_transactions WHERE token_key = ? AND is_test = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (token_key, is_test, limit)
        ).fetchall()
    elif symbol:
        rows = conn.execute(
            "SELECT * FROM portfolio_transactions WHERE symbol = ? AND is_test = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (symbol.upper(), is_test, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM portfolio_transactions WHERE is_test = ? ORDER BY created_at DESC LIMIT ?",
            (is_test, limit)
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


# --- Cash ---

def get_cash_balance(is_test=0):
    conn = _conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_usd), 0) as balance FROM cash_movements "
        "WHERE is_test = ? AND type IN ('deposit','sell','buy','withdraw','fee','adjustment')",
        (is_test,)
    ).fetchone()
    conn.close()
    return row["balance"] if row else 0


def add_cash_movement(mtype, amount_usd, notes="", is_test=0):
    conn = _conn()
    conn.execute(
        "INSERT INTO cash_movements (type, amount_usd, is_test, notes) VALUES (?, ?, ?, ?)",
        (mtype, amount_usd, is_test, notes)
    )
    conn.commit()
    conn.close()


def set_cash_balance(target_usd, is_test=0):
    current = get_cash_balance(is_test)
    diff = target_usd - current
    if abs(diff) < 0.01:
        return current
    add_cash_movement("adjustment", diff,
                      f"Manual cash adjustment to ${target_usd:,.2f}", is_test)
    return target_usd


def get_cash_history(limit=20, is_test=0):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM cash_movements WHERE is_test = ? ORDER BY created_at DESC LIMIT ?",
        (is_test, limit)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


# --- Test data management ---

def clear_test_data():
    conn = _conn()
    conn.execute("DELETE FROM portfolio_positions WHERE is_test = 1")
    conn.execute("DELETE FROM portfolio_transactions WHERE is_test = 1")
    conn.execute("DELETE FROM cash_movements WHERE is_test = 1")
    conn.commit()
    conn.close()
    logger.info("Test data cleared")


def get_test_positions_count():
    conn = _conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM portfolio_positions WHERE is_test = 1"
    ).fetchone()[0]
    conn.close()
    return count
