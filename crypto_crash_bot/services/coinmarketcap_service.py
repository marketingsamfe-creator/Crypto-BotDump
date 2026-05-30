import time
from typing import Optional
from .. import config
from ..http_client import http_get
from ..logger import logger


CMC_BASE = "https://pro-api.coinmarketcap.com/v1"
CMC_FREE_BASE = "https://web-api.coinmarketcap.com/v1"


def _headers() -> dict:
    api_key = config.COINMARKETCAP_API_KEY
    if api_key:
        return {"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"}
    return {"Accept": "application/json"}


def _use_pro() -> bool:
    return bool(config.COINMARKETCAP_API_KEY)


def search_token(query: str) -> Optional[dict]:
    try:
        if _use_pro():
            url = f"{CMC_BASE}/cryptocurrency/listings/latest?limit=5000"
            data = http_get(url, headers=_headers(), cache_ttl=300)
            if data and "data" in data:
                for coin in data["data"]:
                    name = coin.get("name", "").lower()
                    sym = coin.get("symbol", "").lower()
                    if query.lower() in (name, sym) or query.lower() in name or query.lower() in sym:
                        return {
                            "id": str(coin["id"]),
                            "name": coin.get("name", ""),
                            "symbol": coin.get("symbol", ""),
                            "slug": coin.get("slug", ""),
                            "price": (coin.get("quote", {}).get("USD", {}) or {}).get("price"),
                            "market_cap": (coin.get("quote", {}).get("USD", {}) or {}).get("market_cap"),
                            "volume_24h": (coin.get("quote", {}).get("USD", {}) or {}).get("volume_24h"),
                            "percent_change_1h": (coin.get("quote", {}).get("USD", {}) or {}).get("percent_change_1h"),
                            "percent_change_24h": (coin.get("quote", {}).get("USD", {}) or {}).get("percent_change_24h"),
                            "source": "coinmarketcap",
                        }
        return _search_free(query)
    except Exception as e:
        logger.warning(f"CMC search error: {e}")
        try:
            return _search_free(query)
        except Exception:
            return None


def _search_free(query: str) -> Optional[dict]:
    url = f"{CMC_FREE_BASE}/cryptocurrency/map?limit=5000"
    data = http_get(url, headers=_headers(), cache_ttl=300)
    if not data or "data" not in data:
        return None
    for coin in data["data"]:
        name = coin.get("name", "").lower()
        sym = coin.get("symbol", "").lower()
        if query.lower() in (name, sym):
            return {
                "id": str(coin["id"]),
                "name": coin.get("name", ""),
                "symbol": coin.get("symbol", ""),
                "slug": coin.get("slug", ""),
                "source": "coinmarketcap",
            }
    return None


def get_price(symbol: str) -> Optional[float]:
    try:
        if _use_pro():
            url = f"{CMC_BASE}/cryptocurrency/quotes/latest?symbol={symbol}"
            data = http_get(url, headers=_headers(), cache_ttl=60)
            if data and "data" in data:
                coin_data = data["data"].get(symbol.upper(), {})
                return (coin_data.get("quote", {}).get("USD", {}) or {}).get("price")
        return None
    except Exception as e:
        logger.warning(f"CMC get_price error: {e}")
        return None


def get_id_map() -> list:
    try:
        url = f"{CMC_FREE_BASE}/cryptocurrency/map?limit=10000"
        data = http_get(url, headers=_headers(), cache_ttl=86400)
        if data and "data" in data:
            return data["data"]
        return []
    except Exception as e:
        logger.warning(f"CMC id_map error: {e}")
        return []
