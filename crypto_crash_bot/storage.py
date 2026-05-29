import json
import os
import tempfile
import shutil
from .logger import logger

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)

FILES = {
    "portfolio": "portfolio_data.json",
    "alerted": "alerted_coins.json",
    "snapshots": "price_snapshots.json",
    "settings": "settings.json",
}

def _path(key):
    return os.path.join(DATA_DIR, FILES[key])

def load_json(key, default=None):
    path = _path(key)
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Corrupted JSON {key}: {e}. Using default.")
        return default if default is not None else {}

def save_json(key, data):
    path = _path(key)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        shutil.move(tmp, path)
    except OSError as e:
        logger.error(f"Failed to save {key}: {e}")

def load_portfolio_data():
    return load_json("portfolio")

def save_portfolio_data(data):
    save_json("portfolio", data)

def load_alerted():
    return load_json("alerted")

def save_alerted(data):
    save_json("alerted", data)

def load_snapshots():
    return load_json("snapshots", {})

def save_snapshots(data):
    save_json("snapshots", data)

def load_settings():
    return load_json("settings")

def save_settings(data):
    save_json("settings", data)
