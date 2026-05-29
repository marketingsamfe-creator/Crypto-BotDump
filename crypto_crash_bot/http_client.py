import time
import requests
from .logger import logger
from . import config

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

API_LATENCY = {}
API_CALLS = {}


def _record_latency(api_name, duration_ms, status, endpoint=""):
    if api_name not in API_LATENCY:
        API_LATENCY[api_name] = {"count": 0, "total_ms": 0, "max_ms": 0, "errors": 0}
    API_LATENCY[api_name]["count"] += 1
    API_LATENCY[api_name]["total_ms"] += duration_ms
    API_LATENCY[api_name]["max_ms"] = max(API_LATENCY[api_name]["max_ms"], duration_ms)
    if status >= 400 or status == 0:
        API_LATENCY[api_name]["errors"] += 1
    API_CALLS.setdefault(api_name, 0)
    API_CALLS[api_name] += 1
    slow_threshold = getattr(config, "SLOW_API_THRESHOLD_MS", 2000)
    if duration_ms > slow_threshold:
        logger.warning(f"SLOW_API api={api_name} duration_ms={duration_ms:.0f} endpoint={endpoint}")


def get_latency_stats():
    result = {}
    for name, data in API_LATENCY.items():
        avg = data["total_ms"] / data["count"] if data["count"] > 0 else 0
        result[name] = {
            "avg_ms": round(avg, 1),
            "max_ms": round(data["max_ms"], 1),
            "count": data["count"],
            "errors": data["errors"],
        }
    return result


def request(method, url, api_name="unknown", **kwargs):
    connect_timeout = getattr(config, "HTTP_CONNECT_TIMEOUT_SECONDS", 3)
    read_timeout = getattr(config, "HTTP_READ_TIMEOUT_SECONDS", 7)
    kwargs.setdefault("timeout", (connect_timeout, read_timeout))
    max_retries = getattr(config, "HTTP_MAX_RETRIES", 2)

    start = time.time()
    for attempt in range(max_retries + 1):
        try:
            resp = session.request(method, url, **kwargs)
            duration_ms = (time.time() - start) * 1000
            _record_latency(api_name, duration_ms, resp.status_code, url)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                logger.warning(f"Rate limited on {api_name}, waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                backoff = 2 ** attempt
                logger.warning(f"Timeout {api_name}, retry {attempt+1} in {backoff}s")
                time.sleep(backoff)
                continue
            duration_ms = (time.time() - start) * 1000
            _record_latency(api_name, duration_ms, 0, url)
            logger.error(f"Timeout {api_name} after {max_retries+1} attempts")
            return None
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (502, 503, 504) and attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            duration_ms = (time.time() - start) * 1000
            _record_latency(api_name, duration_ms, status, url)
            logger.error(f"HTTP {status} on {api_name}: {url[:80]}")
            return None
        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            duration_ms = (time.time() - start) * 1000
            _record_latency(api_name, duration_ms, 0, url)
            logger.error(f"Connection error on {api_name}: {e}")
            return None
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            _record_latency(api_name, duration_ms, 0, url)
            logger.error(f"Error on {api_name}: {e}")
            return None
    return None


def get(url, api_name="unknown", **kwargs):
    return request("GET", url, api_name, **kwargs)


def post(url, api_name="unknown", **kwargs):
    return request("POST", url, api_name, **kwargs)
