import sqlite3
import os
import json
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "social_data.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trend_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL,
            symbol TEXT,
            name TEXT,
            score INTEGER,
            category TEXT,
            narrative TEXT,
            source TEXT,
            price REAL,
            price_change_1h REAL,
            price_change_24h REAL,
            volume_24h REAL,
            volume_change_24h REAL,
            liquidity REAL,
            fdv REAL,
            chain TEXT,
            pair_address TEXT,
            dex_url TEXT,
            gecko_score INTEGER,
            risk_flags TEXT,
            raw_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scanning_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_trend_scores_score ON trend_scores(score DESC);
        CREATE INDEX IF NOT EXISTS idx_trend_scores_created ON trend_scores(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_trend_scores_slug ON trend_scores(slug);
    """)
    conn.commit()
    conn.close()


def save_trend_scores(scores):
    conn = _get_conn()
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    conn.execute("DELETE FROM trend_scores WHERE created_at < ?", (cutoff,))
    for s in scores:
        conn.execute("""
            INSERT INTO trend_scores
                (slug, symbol, name, score, category, narrative, source,
                 price, price_change_1h, price_change_24h,
                 volume_24h, volume_change_24h, liquidity, fdv,
                 chain, pair_address, dex_url, gecko_score,
                 risk_flags, raw_data)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            s.get("slug"), s.get("symbol"), s.get("name"),
            s.get("score"), s.get("category"), s.get("narrative"),
            s.get("source"), s.get("price"),
            s.get("price_change_1h"), s.get("price_change_24h"),
            s.get("volume_24h"), s.get("volume_change_24h"),
            s.get("liquidity"), s.get("fdv"),
            s.get("chain"), s.get("pair_address"),
            s.get("dex_url"), s.get("gecko_score"),
            json.dumps(s.get("risk_flags", [])),
            json.dumps(s.get("raw_data", {})),
        ))
    conn.commit()
    conn.close()


def get_latest_scores(limit=30, min_score=0, category=None):
    conn = _get_conn()
    query = """
        SELECT * FROM trend_scores
        WHERE created_at = (SELECT MAX(created_at) FROM trend_scores)
        AND score >= ?
    """
    params = [min_score]
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY score DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_scan_timestamp():
    conn = _get_conn()
    row = conn.execute("SELECT value FROM scanning_state WHERE key='last_scan'").fetchone()
    conn.close()
    return row["value"] if row else None


def set_scan_timestamp(ts):
    conn = _get_conn()
    conn.execute("REPLACE INTO scanning_state (key, value) VALUES ('last_scan', ?)", (ts,))
    conn.commit()
    conn.close()
