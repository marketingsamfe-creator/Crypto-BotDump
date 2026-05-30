from typing import Optional
from ..http_client import http_get
from ..logger import logger


GECKO_TERMINAL_BASE = "https://api.geckoterminal.com/api/v2"


def search_pairs(query: str) -> list:
    try:
        url = f"{GECKO_TERMINAL_BASE}/search/pairs?query={query}"
        data = http_get(url, cache_ttl=120)
        if data and "data" in data:
            return data["data"]
        return []
    except Exception as e:
        logger.warning(f"GeckoTerminal search error: {e}")
        return []


def get_token_info(network: str, address: str) -> Optional[dict]:
    try:
        url = f"{GECKO_TERMINAL_BASE}/networks/{network}/tokens/{address}"
        data = http_get(url, cache_ttl=60)
        if data and "data" in data:
            attrs = data["data"].get("attributes", {})
            return {
                "name": attrs.get("name", ""),
                "symbol": attrs.get("symbol", ""),
                "address": address,
                "network": network,
                "price": attrs.get("price_usd"),
                "volume_24h": attrs.get("volume_usd", {}).get("h24"),
                "liquidity": attrs.get("reserve_in_usd"),
                "fdv": attrs.get("fdv_usd"),
                "price_change_1h": _get_change(attrs, "h1"),
                "price_change_24h": _get_change(attrs, "h24"),
                "source": "geckoterminal",
            }
        return None
    except Exception as e:
        logger.warning(f"GeckoTerminal token error: {e}")
        return None


def get_token_pairs(network: str, address: str) -> list:
    try:
        url = f"{GECKO_TERMINAL_BASE}/networks/{network}/tokens/{address}/pools"
        data = http_get(url, cache_ttl=60)
        if data and "data" in data:
            return data["data"]
        return []
    except Exception as e:
        logger.warning(f"GeckoTerminal pairs error: {e}")
        return []


def _get_change(attrs: dict, period: str) -> Optional[float]:
    changes = attrs.get("price_change_percentage", {})
    if changes and period in changes:
        return changes[period]
    return None


NETWORK_MAP = {
    "ethereum": "eth",
    "eth": "eth",
    "solana": "solana",
    "bsc": "bsc",
    "binance": "bsc",
    "polygon": "polygon",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "avalanche": "avax",
    "base": "base",
    "tron": "tron",
}


def resolve_network(name: str) -> str:
    name = name.lower().strip()
    return NETWORK_MAP.get(name, name)
