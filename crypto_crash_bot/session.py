import time
import re
from decimal import Decimal, InvalidOperation
from .logger import logger
from . import config

SESSION_TTL = 900

_sessions = {}
CMD_LATENCY = {}


def _now():
    return time.time()


def _session_key(user_id, chat_id=None):
    if chat_id:
        return f"{chat_id}:{user_id}"
    return str(user_id)


def get_session(user_id, chat_id=None):
    cleanup()
    key = _session_key(user_id, chat_id)
    s = _sessions.get(key)
    if s and _now() > s.get("expires_at", 0):
        logger.info(f"Session expired: user={user_id} key={key}")
        del _sessions[key]
        return None
    return s


def create_session(user_id, flow, data=None, step=None, chat_id=None):
    key = _session_key(user_id, chat_id)
    existing = _sessions.get(key)
    if existing:
        cancel_session(user_id, chat_id)
    now = _now()
    _sessions[key] = {
        "user_id": user_id,
        "chat_id": chat_id,
        "flow": flow,
        "step": step,
        "data": data or {},
        "created_at": now,
        "expires_at": now + SESSION_TTL,
    }
    logger.info(f"SESSION_START user={user_id} chat={chat_id} flow={flow} step={step}")
    return _sessions[key]


def set_step(user_id, step, chat_id=None):
    key = _session_key(user_id, chat_id)
    s = _sessions.get(key)
    if s:
        old = s.get("step")
        s["step"] = step
        s["expires_at"] = _now() + SESSION_TTL
        logger.info(f"SESSION_TRANSITION flow={s['flow']} from={old} to={step}")
        return True
    return False


def set_data(user_id, key, value, chat_id=None):
    key_s = _session_key(user_id, chat_id)
    s = _sessions.get(key_s)
    if s:
        s["data"][key] = value
        s["expires_at"] = _now() + SESSION_TTL
        return True
    return False


def get_data(user_id, key, default=None, chat_id=None):
    key_s = _session_key(user_id, chat_id)
    s = _sessions.get(key_s)
    if s:
        return s["data"].get(key, default)
    return default


def update_data(user_id, updates, chat_id=None):
    key_s = _session_key(user_id, chat_id)
    s = _sessions.get(key_s)
    if s:
        s["data"].update(updates)
        s["expires_at"] = _now() + SESSION_TTL
        return True
    return False


def cancel_session(user_id, chat_id=None):
    key = _session_key(user_id, chat_id)
    if key in _sessions:
        s = _sessions[key]
        logger.info(f"SESSION_CLEAR user={user_id} flow={s.get('flow')} reason=cancelled")
        del _sessions[key]
        return True
    return False


def complete_session(user_id, chat_id=None):
    key = _session_key(user_id, chat_id)
    if key in _sessions:
        s = _sessions[key]
        logger.info(f"SESSION_COMPLETE user={user_id} flow={s.get('flow')} data={s.get('data')}")
        del _sessions[key]
        return True
    return False


def has_active_session(user_id, chat_id=None):
    key = _session_key(user_id, chat_id)
    s = _sessions.get(key)
    return s is not None and _now() <= s.get("expires_at", 0)


def cleanup():
    now = _now()
    expired = []
    for key, s in list(_sessions.items()):
        if now > s.get("expires_at", 0):
            expired.append(key)
    for key in expired:
        logger.info(f"Session expired: key={key}")
        del _sessions[key]
    return len(expired)


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
