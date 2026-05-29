import requests
from ..logger import logger

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_trending():
    url = "https://api.coingecko.com/api/v3/search/trending"
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        coins = data.get("coins", [])
        result = []
        for entry in coins:
            item = entry.get("item", {})
            result.append({
                "slug": item.get("id"),
                "symbol": (item.get("symbol") or "").upper(),
                "name": item.get("name"),
                "market_cap_rank": item.get("market_cap_rank"),
                "score": item.get("score", 0),
                "price_btc": item.get("price_btc"),
            })
        logger.info(f"Trending: {len(result)} coins")
        return result
    except Exception as e:
        logger.error(f"Trending error: {e}")
        return []


def fetch_simple_price(slugs):
    if not slugs:
        return {}
    ids = ",".join(slugs[:50])
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ids,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
        "include_market_cap": "true",
    }
    try:
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Simple price error: {e}")
        return {}


def search_coin_by_symbol(symbol):
    url = "https://api.coingecko.com/api/v3/coins/list"
    try:
        resp = session.get(url, timeout=30)
        coins = resp.json()
        s = symbol.lower().strip()
        matches = [c for c in coins if c["symbol"].lower() == s]
        if matches:
            return matches[0]
        matches = [c for c in coins if s in c["id"] or s in c["name"].lower()]
        return matches[0] if matches else None
    except Exception as e:
        logger.error(f"Search error: {e}")
        return None
