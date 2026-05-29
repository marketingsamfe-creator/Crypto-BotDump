import time
from .logger import logger


class TTLCache:
    def __init__(self, name="cache"):
        self._data = {}
        self._name = name
        self._hits = 0
        self._misses = 0

    def get(self, key):
        entry = self._data.get(key)
        if entry and time.time() < entry["expires"]:
            self._hits += 1
            return entry["value"]
        if entry:
            del self._data[key]
        self._misses += 1
        return None

    def set(self, key, value, ttl=60):
        self._data[key] = {
            "value": value,
            "expires": time.time() + ttl,
            "created": time.time(),
        }

    def get_or_fetch(self, key, ttl, fetch_func):
        cached = self.get(key)
        if cached is not None:
            return cached
        value = fetch_func()
        if value is not None:
            self.set(key, value, ttl)
        return value

    def clear(self):
        self._data.clear()

    def remove(self, key):
        self._data.pop(key, None)

    def stats(self):
        now = time.time()
        valid = sum(1 for v in self._data.values() if now < v["expires"])
        total_calls = self._hits + self._misses
        hit_rate = (self._hits / total_calls * 100) if total_calls > 0 else 0
        return {
            "name": self._name,
            "total": len(self._data),
            "valid": valid,
            "expired": len(self._data) - valid,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 1),
        }


price_cache = TTLCache("price")
market_cache = TTLCache("market")
portfolio_cache = TTLCache("portfolio")
social_cache = TTLCache("social")
detail_cache = TTLCache("detail")
dex_cache = TTLCache("dex")
dumps_cache = TTLCache("dumps")
token_resolve_cache = TTLCache("token_resolve")


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

def get_dumps_cache():
    return dumps_cache

def get_token_resolve_cache():
    return token_resolve_cache

def clear_all():
    for c in [price_cache, market_cache, portfolio_cache, social_cache,
              detail_cache, dex_cache, dumps_cache, token_resolve_cache]:
        c.clear()
    logger.info("All caches cleared")

def get_all_stats():
    return [price_cache.stats(), market_cache.stats(), portfolio_cache.stats(),
            social_cache.stats(), detail_cache.stats(), dex_cache.stats(),
            dumps_cache.stats(), token_resolve_cache.stats()]

def get_global_hit_rate():
    total_hits = sum(c._hits for c in [price_cache, market_cache, portfolio_cache,
                                        social_cache, detail_cache, dex_cache,
                                        dumps_cache, token_resolve_cache])
    total_misses = sum(c._misses for c in [price_cache, market_cache, portfolio_cache,
                                           social_cache, detail_cache, dex_cache,
                                           dumps_cache, token_resolve_cache])
    total = total_hits + total_misses
    return round(total_hits / total * 100, 1) if total > 0 else 0
