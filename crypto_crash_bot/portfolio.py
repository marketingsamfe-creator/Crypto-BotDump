from . import config, storage
from .coingecko_client import fetch_market_coins_by_ids


def fetch_prices():
    slugs = [p["slug"] for p in config.PORTFOLIO]
    data = fetch_market_coins_by_ids(slugs, changes="1h,24h,7d")
    if not data:
        return {}
    return {c["id"]: c for c in data}


def calculate_portfolio():
    prices = fetch_prices()
    pdata = storage.load_portfolio_data()
    total_invested = pdata.get("total_invested", 0)
    entry_prices = pdata.get("entry_prices", {})
    quantities = pdata.get("quantities", {})

    result = {
        "timestamp": None,
        "total_invested": total_invested,
        "total_value": 0.0,
        "total_pnl_usd": 0.0,
        "total_pnl_pct": 0.0,
        "weighted_24h_change": 0.0,
        "best_token": None,
        "worst_token": None,
        "tokens": [],
    }

    total_weighted = 0.0
    total_alloc = 0.0
    best_change = -999
    worst_change = 999

    for coin in config.PORTFOLIO:
        data = prices.get(coin["slug"])
        if not data:
            continue

        price = data.get("current_price", 0)
        change_1h = data.get("price_change_percentage_1h_in_currency")
        change_24h = data.get("price_change_percentage_24h")
        change_7d = data.get("price_change_percentage_7d_in_currency")
        sym = coin["symbol"]
        entry = entry_prices.get(sym)
        qty = quantities.get(sym, 0)
        alloc = coin["alloc"]

        position_value = qty * price if qty > 0 else 0
        pnl_pct = None
        pnl_usd = None

        if entry and entry > 0:
            pnl_pct = ((price - entry) / entry) * 100
            if qty > 0:
                pnl_usd = (price - entry) * qty

        token_info = {
            "slug": coin["slug"],
            "symbol": sym,
            "name": coin["name"],
            "price": price,
            "change_1h": change_1h,
            "change_24h": change_24h,
            "change_7d": change_7d,
            "quantity": qty,
            "position_value": position_value,
            "entry_price": entry,
            "pnl_pct": pnl_pct,
            "pnl_usd": pnl_usd,
            "allocation": alloc,
        }
        result["tokens"].append(token_info)
        result["total_value"] += position_value

        if pnl_usd is not None:
            result["total_pnl_usd"] += pnl_usd

        if change_24h is not None:
            total_weighted += change_24h * alloc
            total_alloc += alloc
            if change_24h > best_change:
                best_change = change_24h
                result["best_token"] = sym
            if change_24h < worst_change:
                worst_change = change_24h
                result["worst_token"] = sym

    if total_alloc > 0:
        result["weighted_24h_change"] = round(total_weighted / total_alloc, 2)

    if total_invested > 0:
        result["total_pnl_pct"] = round(
            (result["total_pnl_usd"] / total_invested) * 100, 2
        )

    return result
