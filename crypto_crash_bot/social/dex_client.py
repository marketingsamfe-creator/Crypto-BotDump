import requests
from ..logger import logger

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})


def search_pairs(query):
    url = f"https://api.dexscreener.com/latest/dex/search"
    try:
        resp = session.get(url, params={"q": query}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("pairs", [])
    except Exception as e:
        logger.error(f"DexScreener search error: {e}")
        return []


def get_best_pair(pairs, symbol):
    if not pairs:
        return None
    symbol = symbol.lower()
    candidates = []
    for p in pairs:
        base = (p.get("baseToken") or {}).get("symbol", "").lower()
        quote = (p.get("quoteToken") or {}).get("symbol", "").lower()
        if base == symbol.lower() and quote == "usd":
            candidates.append(p)
    if not candidates:
        for p in pairs:
            base = (p.get("baseToken") or {}).get("symbol", "").lower()
            if base == symbol.lower():
                candidates.append(p)
    if not candidates:
        candidates = pairs
    candidates.sort(key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
    return candidates[0] if candidates else None


def extract_market_data(pair):
    if not pair:
        return {}
    base = pair.get("baseToken", {})
    return {
        "price": pair.get("priceUsd"),
        "price_change_5m": pair.get("priceChange", {}).get("m5"),
        "price_change_1h": pair.get("priceChange", {}).get("h1"),
        "price_change_6h": pair.get("priceChange", {}).get("h6"),
        "price_change_24h": pair.get("priceChange", {}).get("h24"),
        "volume_24h": pair.get("volume", {}).get("h24"),
        "volume_1h": pair.get("volume", {}).get("h1"),
        "liquidity": pair.get("liquidity", {}).get("usd"),
        "fdv": pair.get("fdv"),
        "chain": pair.get("chainId"),
        "dex": pair.get("dexId"),
        "pair_address": pair.get("pairAddress"),
        "dex_url": pair.get("url"),
        "pair_created_at": pair.get("pairCreatedAt"),
        "base_symbol": base.get("symbol"),
        "base_name": base.get("name"),
        "base_address": base.get("address"),
    }
