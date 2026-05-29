from . import config, portfolio_db
from .coingecko_client import fetch_market_coins_by_ids


def calculate_portfolio():
    positions = portfolio_db.get_active_positions()
    cash_balance = portfolio_db.get_cash_balance()

    slugs = [p["coin_id"] for p in positions]
    prices = {}
    if slugs:
        try:
            market_data = fetch_market_coins_by_ids(slugs, changes="1h,24h,7d")
            if market_data:
                for c in market_data:
                    prices[c["id"]] = c
        except Exception:
            pass

    total_value = 0.0
    total_cost_basis = 0.0
    total_realized_pnl = 0.0
    total_weighted = 0.0
    total_alloc = 0.0
    best_change = -999
    worst_change = 999
    best_token = None
    worst_token = None
    tokens = []

    total_alloc_sum = sum(p.get("cost_basis_usd", 0) or 0 for p in positions)
    if total_alloc_sum <= 0:
        total_alloc_sum = 1

    for pos in positions:
        sym = pos["symbol"]
        slug = pos["coin_id"]
        qty = pos["quantity"]
        cost_basis = pos["cost_basis_usd"] or 0
        realized_pnl = pos.get("realized_pnl_usd", 0) or 0
        avg_entry = pos.get("avg_entry_price", 0) or 0

        data = prices.get(slug, {})
        price = data.get("current_price", 0) or 0
        change_1h = data.get("price_change_percentage_1h_in_currency")
        change_24h = data.get("price_change_percentage_24h")
        change_7d = data.get("price_change_percentage_7d_in_currency")

        position_value = qty * price if qty > 0 else 0

        pnl_pct = None
        pnl_usd = None
        if avg_entry > 0 and qty > 0:
            pnl_pct = ((price - avg_entry) / avg_entry) * 100
            pnl_usd = (price - avg_entry) * qty

        alloc_pct = (cost_basis / total_alloc_sum) * 100 if total_alloc_sum > 0 else 0

        tokens.append({
            "slug": slug,
            "symbol": sym,
            "name": pos.get("name", ""),
            "price": price,
            "change_1h": change_1h,
            "change_24h": change_24h,
            "change_7d": change_7d,
            "quantity": qty,
            "position_value": position_value,
            "entry_price": avg_entry,
            "cost_basis": cost_basis,
            "pnl_pct": pnl_pct,
            "pnl_usd": pnl_usd,
            "realized_pnl": realized_pnl,
            "allocation": round(alloc_pct, 2),
        })

        total_value += position_value
        total_cost_basis += cost_basis
        total_realized_pnl += realized_pnl

        if change_24h is not None:
            total_weighted += change_24h * qty
            total_alloc += qty
            if change_24h > best_change:
                best_change = change_24h
                best_token = sym
            if change_24h < worst_change:
                worst_change = change_24h
                worst_token = sym

    total_value_with_cash = total_value + cash_balance
    unrealized_pnl = total_value - total_cost_basis
    total_pnl = unrealized_pnl + total_realized_pnl

    if total_cost_basis > 0:
        total_pnl_pct = ((total_value + cash_balance - total_cost_basis) / total_cost_basis) * 100
    else:
        total_pnl_pct = 0.0

    result = {
        "total_invested": total_cost_basis,
        "total_value": total_value,
        "total_value_with_cash": total_value_with_cash,
        "cash_balance": cash_balance,
        "total_pnl_usd": total_pnl,
        "total_pnl_pct": round(total_pnl_pct, 2),
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": total_realized_pnl,
        "weighted_24h_change": round(total_weighted / total_alloc, 2) if total_alloc > 0 else 0,
        "best_token": best_token,
        "worst_token": worst_token,
        "tokens": tokens,
    }
    return result
