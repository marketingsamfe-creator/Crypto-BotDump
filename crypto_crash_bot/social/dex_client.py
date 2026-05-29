import requests
import re
import time
from ..logger import logger
from .. import cache

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

DEXSEARCHER_API = "https://api.dexscreener.com/latest/dex"
PREFERRED_QUOTES = {"USDC", "USDT", "WETH", "WBNB", "SOL", "ETH", "BNB"}

SOLANA_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
EVM_ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
TRON_ADDR_RE = re.compile(r"^T[a-zA-Z0-9]{33}$")


def _request(url, params=None, retries=2):
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            logger.error(f"DexScreener timeout: {url}")
            return None
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                time.sleep(5)
                continue
            logger.error(f"DexScreener HTTP {e.response.status_code if e.response else '?'}: {url}")
            return None
        except Exception as e:
            logger.error(f"DexScreener error: {e}")
            return None
    return None


def extract_pair_data(pair):
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    vol = pair.get("volume") or {}
    liq = pair.get("liquidity") or {}
    pch = pair.get("priceChange") or {}
    txns = pair.get("txns") or {}
    return {
        "chain_id": pair.get("chainId"),
        "dex_id": pair.get("dexId"),
        "url": pair.get("url"),
        "pair_address": pair.get("pairAddress"),
        "pair_created_at": pair.get("pairCreatedAt"),
        "base_address": base.get("address"),
        "base_name": base.get("name"),
        "base_symbol": base.get("symbol"),
        "quote_address": quote.get("address"),
        "quote_name": quote.get("name"),
        "quote_symbol": quote.get("symbol"),
        "price_usd": pair.get("priceUsd"),
        "price_native": pair.get("priceNative"),
        "liquidity_usd": liq.get("usd"),
        "liquidity_base": liq.get("base"),
        "liquidity_quote": liq.get("quote"),
        "fdv": pair.get("fdv"),
        "market_cap": pair.get("marketCap"),
        "volume_m5": vol.get("m5"),
        "volume_h1": vol.get("h1"),
        "volume_h6": vol.get("h6"),
        "volume_h24": vol.get("h24"),
        "price_change_m5": pch.get("m5"),
        "price_change_h1": pch.get("h1"),
        "price_change_h6": pch.get("h6"),
        "price_change_h24": pch.get("h24"),
        "txns_m5": txns.get("m5"),
        "txns_h1": txns.get("h1"),
        "txns_h6": txns.get("h6"),
        "txns_h24": txns.get("h24"),
        "source": "dexscreener",
    }


def search_pairs(query):
    cached = cache.get_dex_cache().get(f"search:{query}")
    if cached:
        return cached
    data = _request(f"{DEXSEARCHER_API}/search", params={"q": query})
    pairs = data.get("pairs", []) if data else []
    extracted = [extract_pair_data(p) for p in pairs] if pairs else []
    cache.get_dex_cache().set(f"search:{query}", extracted, ttl=60)
    logger.info(f"DEX_SEARCH query={query} status=ok pairs_count={len(extracted)}")
    return extracted


def get_token_pairs(chain_id, token_address):
    cached = cache.get_dex_cache().get(f"pairs:{chain_id}:{token_address}")
    if cached:
        return cached
    data = _request(f"{DEXSEARCHER_API}/tokens/{token_address}")
    pairs = data.get("pairs", []) if data else []
    extracted = [extract_pair_data(p) for p in pairs] if pairs else []
    cache.get_dex_cache().set(f"pairs:{chain_id}:{token_address}", extracted, ttl=60)
    logger.info(f"DEX_TOKEN_PAIRS chain={chain_id} token={token_address[:12]} status=ok pairs_count={len(extracted)}")
    return extracted


def score_pair(pair, query_lower=None, base_address_lower=None):
    score = 0
    liq = pair.get("liquidity_usd") or 0
    vol = pair.get("volume_h24") or 0
    price = pair.get("price_usd")

    if price is None or price == 0:
        score -= 500

    if pair.get("base_address") and base_address_lower:
        if pair["base_address"].lower() == base_address_lower:
            score += 300

    if pair.get("pair_address") and query_lower:
        if pair["pair_address"].lower() == query_lower:
            score += 250

    quote = pair.get("quote_symbol", "").upper()
    if quote in PREFERRED_QUOTES:
        score += 100

    if liq:
        score += min(float(liq) / 1000, 200)
    if vol:
        score += min(float(vol) / 10000, 150)
    if not liq or float(liq) <= 0:
        score -= 100
    if not vol or float(vol) <= 0:
        score -= 50

    return score


def get_best_pair(pairs, query=""):
    if not pairs:
        return None
    q_lower = query.lower().strip() if query else ""
    ba_lower = None
    if q_lower.startswith("0x") or len(q_lower) >= 30:
        ba_lower = q_lower
    scored = [(score_pair(p, q_lower, ba_lower), p) for p in pairs]
    scored.sort(key=lambda x: x[0], reverse=True)
    logger.info(f"BEST_PAIR selected={scored[0][1].get('base_symbol','?')} score={scored[0][0]} pairs_evaluated={len(scored)}")
    return scored[0][1]


def get_best_pair_for_token(query):
    pairs = search_pairs(query)
    if not pairs:
        return None, []
    best = get_best_pair(pairs, query)
    return best, pairs


def detect_address_family(text):
    t = text.strip()
    if EVM_ADDR_RE.match(t):
        return "evm_contract"
    if t.startswith("0x"):
        if len(t) == 42:
            try:
                int(t[2:], 16)
                return "evm_contract"
            except ValueError:
                pass
        return "possible_contract_or_token_address"
    if TRON_ADDR_RE.match(t):
        return "tron_address"
    if SOLANA_ADDR_RE.match(t):
        return "solana_address"
    if re.match(r"^[a-zA-Z0-9_-]{2,48}$", t):
        if re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", t):
            return "coingecko_id_or_slug"
        return "symbol_or_name"
    return "unknown"
