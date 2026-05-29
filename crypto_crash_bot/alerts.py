import time
from datetime import datetime
from . import config, storage
from .logger import logger


def is_excluded(coin):
    symbol = (coin.get("symbol") or "").lower()
    slug = coin.get("id", "").lower()
    if symbol in config.STABLECOINS:
        return True
    if symbol in config.WRAPPED_EXCLUDE:
        return True
    if slug in config.ALWAYS_EXCLUDED:
        return True
    return False


def passes_filters(coin):
    volume = coin.get("total_volume") or 0
    market_cap = coin.get("market_cap") or 0
    if volume < config.MIN_VOLUME_USD:
        return False
    if market_cap < config.MIN_MARKET_CAP_USD:
        return False
    if is_excluded(coin):
        return False
    return True


def save_price_snapshots(coins):
    now = time.time()
    snapshots = storage.load_snapshots()
    for coin in coins:
        slug = coin["id"]
        price = coin.get("current_price")
        if price is None:
            continue
        if slug not in snapshots:
            snapshots[slug] = []
        snapshots[slug].append({
            "ts": now,
            "price": price,
            "volume": coin.get("total_volume") or 0,
            "market_cap": coin.get("market_cap") or 0,
        })
        if len(snapshots[slug]) > config.MAX_SNAPSHOTS_PER_COIN:
            snapshots[slug] = snapshots[slug][-config.MAX_SNAPSHOTS_PER_COIN:]

    cutoff = now - config.SNAPSHOT_CLEANUP_AGE
    for slug in list(snapshots.keys()):
        snapshots[slug] = [s for s in snapshots[slug] if s["ts"] > cutoff]
        if not snapshots[slug]:
            del snapshots[slug]

    storage.save_snapshots(snapshots)
    return snapshots


def get_price_change(snapshots, slug, current_price, window_seconds):
    entries = snapshots.get(slug, [])
    if not entries:
        return None

    target_ts = time.time() - window_seconds
    best = None
    for entry in entries:
        diff = abs(entry["ts"] - target_ts)
        if best is None or diff < best["diff"]:
            best = {"diff": diff, "price": entry["price"]}

    if best is None or best["price"] == 0:
        return None

    return ((current_price - best["price"]) / best["price"]) * 100


def calculate_all_changes(snapshots, slug, current_price):
    changes = {}
    for window in config.ALERT_WINDOWS:
        seconds = config.WINDOW_SECONDS[window]
        change = get_price_change(snapshots, slug, current_price, seconds)
        if change is not None:
            changes[window] = round(change, 2)
    return changes


def determine_severity(change_pct):
    for level, threshold in sorted(
            config.DROP_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
        if change_pct <= threshold:
            return level
    return None


def should_alert(alerted_data, slug, window, severity):
    now = datetime.utcnow()
    coin_entry = alerted_data.get(slug, {})
    window_entry = coin_entry.get(window, {})

    if not window_entry:
        return True

    last_severity = window_entry.get("severity")
    last_time_str = window_entry.get("last_alert_at")

    if not last_time_str:
        return True

    try:
        last_time = datetime.fromisoformat(last_time_str)
    except (ValueError, TypeError):
        return True

    severity_order = list(config.DROP_THRESHOLDS.keys())
    last_idx = severity_order.index(last_severity) if last_severity in severity_order else -1
    current_idx = severity_order.index(severity) if severity in severity_order else -1

    if current_idx > last_idx:
        return True

    elapsed = (now - last_time).total_seconds() / 60
    if elapsed >= config.COOLDOWN_MINUTES:
        return True

    return False


def mark_alerted(alerted_data, slug, window, severity):
    now = datetime.utcnow().isoformat()
    if slug not in alerted_data:
        alerted_data[slug] = {}
    alerted_data[slug][window] = {
        "severity": severity,
        "last_alert_at": now,
    }
    return alerted_data


def check_alerts(coins, snapshots):
    alerted_data = storage.load_alerted()
    alerts = []

    for coin in coins:
        slug = coin["id"]
        current_price = coin.get("current_price")
        if current_price is None:
            continue

        if not passes_filters(coin):
            continue

        changes = calculate_all_changes(snapshots, slug, current_price)
        if not changes:
            continue

        for window in config.ALERT_WINDOWS:
            change = changes.get(window)
            if change is None:
                continue
            if change >= 0:
                continue

            severity = determine_severity(change)
            if severity is None:
                continue

            if should_alert(alerted_data, slug, window, severity):
                alerts.append({
                    "coin": coin,
                    "window": window,
                    "severity": severity,
                    "change_pct": change,
                    "all_changes": changes,
                })
                alerted_data = mark_alerted(alerted_data, slug, window, severity)

    storage.save_alerted(alerted_data)
    return alerts


def get_recent_alerts(limit=10):
    alerted = storage.load_alerted()
    recent = []
    for slug, windows in alerted.items():
        for window, info in windows.items():
            if isinstance(info, dict):
                last = info.get("last_alert_at")
                sev = info.get("severity", "unknown")
                if last:
                    recent.append({
                        "slug": slug,
                        "window": window,
                        "severity": sev,
                        "time": last,
                    })
    recent.sort(key=lambda x: x.get("time", ""), reverse=True)
    return recent[:limit]
