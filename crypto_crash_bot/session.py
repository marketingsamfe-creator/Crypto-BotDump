import time
from datetime import datetime
from .logger import logger

SESSION_TTL = 900

_sessions = {}


def _now():
    return time.time()


def get_session(user_id):
    cleanup()
    return _sessions.get(str(user_id))


def create_session(user_id, flow, data=None):
    sid = str(user_id)
    existing = _sessions.get(sid)
    if existing:
        cancel_session(user_id)
    now = _now()
    _sessions[sid] = {
        "user_id": user_id,
        "flow": flow,
        "step": None,
        "data": data or {},
        "created_at": now,
        "expires_at": now + SESSION_TTL,
    }
    logger.info(f"Session created: user={user_id} flow={flow}")
    return _sessions[sid]


def set_step(user_id, step):
    s = _sessions.get(str(user_id))
    if s:
        s["step"] = step
        s["expires_at"] = _now() + SESSION_TTL


def set_data(user_id, key, value):
    s = _sessions.get(str(user_id))
    if s:
        s["data"][key] = value
        s["expires_at"] = _now() + SESSION_TTL


def get_data(user_id, key, default=None):
    s = _sessions.get(str(user_id))
    if s:
        return s["data"].get(key, default)
    return default


def cancel_session(user_id):
    sid = str(user_id)
    if sid in _sessions:
        logger.info(f"Session cancelled: user={user_id}")
        del _sessions[sid]


def has_active_session(user_id):
    s = _sessions.get(str(user_id))
    return s is not None


def cleanup():
    now = _now()
    expired = [sid for sid, s in list(_sessions.items()) if now > s["expires_at"]]
    for sid in expired:
        logger.info(f"Session expired: user={sid}")
        del _sessions[sid]
