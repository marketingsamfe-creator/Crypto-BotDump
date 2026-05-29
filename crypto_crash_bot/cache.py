import time
from .logger import logger


class TTLCache:
    def __init__(self):
        self._data = {}

    def get(self, key):
        entry = self._data.get(key)
        if entry and time.time() < entry["expires"]:
            return entry["value"]
        if entry:
            del self._data[key]
        return None

    def set(self, key, value, ttl=60):
        self._data[key] = {
            "value": value,
            "expires": time.time() + ttl,
            "created": time.time(),
        }

    def clear(self):
        self._data.clear()

    def remove(self, key):
        self._data.pop(key, None)

    def stats(self):
        now = time.time()
        valid = sum(1 for v in self._data.values() if now < v["expires"])
        return {
            "total": len(self._data),
            "valid": valid,
            "expired": len(self._data) - valid,
        }


price_cache = TTLCache()
market_cache = TTLCache()
portfolio_cache = TTLCache()
social_cache = TTLCache()
detail_cache = TTLCache()
dex_cache = TTLCache()


def get_price_cache():
    return price_cache

def get_market_cache():
    return market_cache

def get_portfolio_cache():
    return portfolio_cache

def get_social_cache():
    return social_cache

def get_detail_cache():
    return detail_cache

def get_dex_cache():
    return dex_cache

def clear_all():
    price_cache.clear()
    market_cache.clear()
    portfolio_cache.clear()
    social_cache.clear()
    detail_cache.clear()
    dex_cache.clear()
    logger.info("All caches cleared")
