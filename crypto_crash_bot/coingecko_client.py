import time
import requests
from .logger import logger
from . import config

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

_api_calls_hour = 0
_api_calls_day = 0
_api_reset_hour = time.time()
_api_reset_day = time.time()
_last_rate_limit = 0


def _track_call():
    global _api_calls_hour, _api_calls_day, _api_reset_hour, _api_reset_day
    now = time.time()
    if now - _api_reset_hour >= 3600:
        _api_calls_hour = 0
        _api_reset_hour = now
    if now - _api_reset_day >= 86400:
        _api_calls_day = 0
        _api_reset_day = now
    _api_calls_hour += 1
    _api_calls_day += 1


def get_api_stats():
    return {
        "calls_hour": _api_calls_hour,
        "calls_day": _api_calls_day,
    }


def _request(method, url, **kwargs):
    global _last_rate_limit
    now = time.time()

    if now - _last_rate_limit < 60:
        wait = 60 - (now - _last_rate_limit)
        logger.info(f"Cooling down from rate limit, waiting {wait:.0f}s")
        time.sleep(wait)

    kwargs.setdefault("timeout", 30)

    for attempt in range(3):
        try:
            resp = session.request(method, url, **kwargs)
            _track_call()

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                logger.warning(f"Rate limited. Retry-After: {retry_after}s")
                _last_rate_limit = time.time()
                time.sleep(retry_after)
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.Timeout:
            if attempt < 2:
                backoff = 2 ** attempt
                logger.warning(f"Timeout, retry {attempt + 1} in {backoff}s")
                time.sleep(backoff)
                continue
            raise

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            if status == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                _last_rate_limit = time.time()
                time.sleep(retry_after)
                continue
            if status in (502, 503, 504) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise

        except requests.exceptions.ConnectionError as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise

    return None


def fetch_market_coins(page=1, per_page=250):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": config.VS_CURRENCY,
        "order": "volume_desc",
        "per_page": per_page,
        "page": page,
        "price_change_percentage": "24h",
        "sparkline": "false",
    }
    return _request("GET", url, params=params)


def fetch_coin_detail(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false",
    }
    return _request("GET", url, params=params)


def fetch_simple_price(ids):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ids,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    return _request("GET", url, params=params)


_coins_list_cache = None
_coins_list_ts = 0


def fetch_coins_list(force=False):
    global _coins_list_cache, _coins_list_ts
    now = time.time()
    if not force and _coins_list_cache and now - _coins_list_ts < 3600:
        return _coins_list_cache

    url = "https://api.coingecko.com/api/v3/coins/list"
    data = _request("GET", url)
    if data:
        _coins_list_cache = data
        _coins_list_ts = now
    return _coins_list_cache or []


def search_coins(query):
    query = query.lower().strip()
    coins = fetch_coins_list()
    if not coins:
        return []

    matches = []
    for coin in coins:
        if (coin["symbol"].lower() == query or
                query in coin["id"] or
                query in coin["name"].lower()):
            matches.append(coin)
            if len(matches) >= 5:
                break

    if not matches:
        for coin in coins:
            if query in coin["symbol"].lower():
                matches.append(coin)
                if len(matches) >= 5:
                    break

    return matches


def fetch_market_coins_by_ids(ids, changes="1h,24h,7d"):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": config.VS_CURRENCY,
        "ids": ",".join(ids),
        "order": "market_cap_desc",
        "per_page": len(ids),
        "page": 1,
        "price_change_percentage": changes,
        "sparkline": "false",
    }
    return _request("GET", url, params=params)


def fetch_all_market_coins():
    all_coins = []
    for page in range(1, config.MAX_PAGES + 1):
        data = fetch_market_coins(page=page)
        if not data:
            break
        all_coins.extend(data)
        if len(data) < 250:
            break
        time.sleep(1.5)
    return all_coins
