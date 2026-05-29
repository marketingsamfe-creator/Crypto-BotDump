import time
import json
import re
import os
import sqlite3
from decimal import Decimal, InvalidOperation
from datetime import datetime
from .logger import logger

SESSION_TTL = 900
SLOW_THRESHOLD = 3000

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "portfolio.db")

CMD_LATENCY = {}


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_user_sessions_table():
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_key TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            flow TEXT NOT NULL,
            step TEXT NOT NULL DEFAULT '',
            data_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_expires
        ON user_sessions(expires_at)
    """)
    conn.commit()
    conn.close()


def _now():
    return time.time()


def _format_ts(t=None):
    return datetime.utcfromtimestamp(t or _now()).isoformat()


def _session_key(chat_id, user_id):
    return f"{chat_id}:{user_id}"


def _get_session(chat_id, user_id):
    cleanup()
    key = _session_key(chat_id, user_id)
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM user_sessions WHERE session_key = ?", (key,)
    ).fetchone()
    conn.close()
    if row:
        expires = datetime.fromisoformat(row["expires_at"]).timestamp()
        if _now() > expires:
            logger.info(f"SESSION_EXPIRED key={key}")
            _clear_session(chat_id, user_id)
            return None
        return {
            "chat_id": row["chat_id"],
            "user_id": row["user_id"],
            "flow": row["flow"],
            "step": row["step"],
            "data": json.loads(row["data_json"]) if row["data_json"] else {},
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }
    return None


def _create_session(chat_id, user_id, flow, data=None, step=None):
    _clear_session(chat_id, user_id)
    key = _session_key(chat_id, user_id)
    now = _now()
    now_ts = _format_ts(now)
    expires_ts = _format_ts(now + SESSION_TTL)
    data_json = json.dumps(data or {})
    conn = _conn()
    conn.execute("""
        INSERT INTO user_sessions (session_key, chat_id, user_id, flow, step, data_json, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (key, chat_id, user_id, flow, step or "", data_json, now_ts, expires_ts))
    conn.commit()
    conn.close()
    logger.info(f"SESSION_CREATE key={key} flow={flow} step={step}")
    return _get_session(chat_id, user_id)


def _update_session(chat_id, user_id, updates):
    key = _session_key(chat_id, user_id)
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM user_sessions WHERE session_key = ?", (key,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    data = json.loads(row["data_json"]) if row["data_json"] else {}
    flow = updates.get("flow", row["flow"])
    step = updates.get("step", row["step"])
    if "data" in updates:
        data.update(updates["data"])
    data_json = json.dumps(data)
    expires_ts = _format_ts(_now() + SESSION_TTL)
    conn.execute("""
        UPDATE user_sessions SET flow=?, step=?, data_json=?, expires_at=?
        WHERE session_key=?
    """, (flow, step, data_json, expires_ts, key))
    conn.commit()
    conn.close()
    log_msg = f"SESSION_UPDATE key={key}"
    if "step" in updates:
        log_msg += f" step={updates['step']}"
    logger.info(log_msg)
    return True


def _set_step(chat_id, user_id, step):
    return _update_session(chat_id, user_id, {"step": step})


def _set_data(chat_id, user_id, key, value):
    return _update_session(chat_id, user_id, {"data": {key: value}})


def _update_data(chat_id, user_id, updates_dict):
    return _update_session(chat_id, user_id, {"data": updates_dict})


def _get_data(chat_id, user_id, key, default=None):
    s = _get_session(chat_id, user_id)
    if s:
        return s["data"].get(key, default)
    return default


def _clear_session(chat_id, user_id):
    key = _session_key(chat_id, user_id)
    conn = _conn()
    row = conn.execute(
        "SELECT flow FROM user_sessions WHERE session_key = ?", (key,)
    ).fetchone()
    flow = row["flow"] if row else "unknown"
    conn.execute("DELETE FROM user_sessions WHERE session_key = ?", (key,))
    conn.commit()
    conn.close()
    logger.info(f"SESSION_CLEAR key={key} flow={flow}")


def _has_active_session(chat_id, user_id):
    return _get_session(chat_id, user_id) is not None


def cleanup():
    conn = _conn()
    now_ts = _format_ts()
    deleted = conn.execute(
        "DELETE FROM user_sessions WHERE expires_at < ?", (now_ts,)
    ).rowcount
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"SESSION_CLEANUP deleted={deleted} expired sessions")
    return deleted


# ── Public API (old interface: chat_id-only, chat_id == user_id) ──

def _uid(cid):
    return int(cid) if not isinstance(cid, int) else cid


def get_session(chat_id):
    uid = _uid(chat_id)
    return _get_session(uid, uid)


def create_session(chat_id, flow, data=None, step=None):
    uid = _uid(chat_id)
    return _create_session(uid, uid, flow, data, step)


def set_step(chat_id, step):
    uid = _uid(chat_id)
    return _set_step(uid, uid, step)


def set_data(chat_id, key, value):
    uid = _uid(chat_id)
    return _set_data(uid, uid, key, value)


def update_data(chat_id, updates):
    uid = _uid(chat_id)
    return _update_data(uid, uid, updates)


def get_data(chat_id, key, default=None):
    uid = _uid(chat_id)
    return _get_data(uid, uid, key, default)


def cancel_session(chat_id):
    uid = _uid(chat_id)
    _clear_session(uid, uid)


def has_active_session(chat_id):
    uid = _uid(chat_id)
    return _has_active_session(uid, uid)


# ── New public API (explicit chat_id, user_id) ──
new_get_session = _get_session
new_create_session = _create_session
new_set_step = _set_step
new_set_data = _set_data
new_update_data = _update_data
new_get_data = _get_data
new_clear_session = _clear_session
new_has_active_session = _has_active_session


# ── Performance recording ──

def record_latency(command, duration_ms):
    if command not in CMD_LATENCY:
        CMD_LATENCY[command] = {"count": 0, "total_ms": 0, "max_ms": 0}
    CMD_LATENCY[command]["count"] += 1
    CMD_LATENCY[command]["total_ms"] += duration_ms
    CMD_LATENCY[command]["max_ms"] = max(CMD_LATENCY[command]["max_ms"], duration_ms)
    if duration_ms > SLOW_THRESHOLD:
        logger.warning(f"SLOW_COMMAND command={command} duration_ms={duration_ms:.0f}")
    logger.info(f"PERF command={command} total_ms={duration_ms:.0f}")


def get_command_stats():
    result = {}
    for cmd, data in CMD_LATENCY.items():
        avg = data["total_ms"] / data["count"] if data["count"] > 0 else 0
        result[cmd] = {
            "avg_ms": round(avg, 1),
            "max_ms": round(data["max_ms"], 1),
            "count": data["count"],
        }
    return result


def get_slowest_command():
    if not CMD_LATENCY:
        return "none", 0
    return max(CMD_LATENCY.items(), key=lambda x: x[1]["avg_ms"])


# ── Decimal parsing ──

DECIMAL_RE = re.compile(r"^[0-9]+([.,][0-9]+)?$")


def parse_positive_decimal(text):
    t = text.strip().replace(",", ".")
    if not DECIMAL_RE.match(t):
        return None
    try:
        val = Decimal(t)
        if val <= 0:
            return None
        return val
    except InvalidOperation:
        return None


def parse_non_negative_decimal(text):
    t = text.strip().replace(",", ".")
    if not DECIMAL_RE.match(t):
        return None
    try:
        val = Decimal(t)
        if val < 0:
            return None
        return val
    except InvalidOperation:
        return None


# Init table on import
_init_user_sessions_table()
