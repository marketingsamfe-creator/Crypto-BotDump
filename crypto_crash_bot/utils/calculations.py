from typing import Optional


def current_value(amount: float, current_price: float) -> float:
    return amount * current_price


def invested_value(amount: float, buy_price: float) -> float:
    return amount * buy_price


def unrealized_pnl(amount: float, current_price: float, buy_price: float) -> float:
    return (amount * current_price) - (amount * buy_price)


def unrealized_pnl_percent(current_price: float, buy_price: float) -> Optional[float]:
    if buy_price and buy_price > 0:
        return ((current_price - buy_price) / buy_price) * 100
    return None


def portfolio_total_value(positions: list) -> float:
    return sum(p.get("current_value", 0) for p in positions)


def portfolio_total_invested(positions: list) -> float:
    return sum(p.get("invested_value", 0) for p in positions)


def portfolio_total_pnl(total_value: float, total_invested: float) -> float:
    return total_value - total_invested


def portfolio_total_pnl_percent(total_pnl: float, total_invested: float) -> Optional[float]:
    if total_invested and total_invested > 0:
        return (total_pnl / total_invested) * 100
    return None


def price_change_percent(current_price: float, old_price: float) -> Optional[float]:
    if old_price and old_price > 0:
        return ((current_price - old_price) / old_price) * 100
    return None


def hype_score(
    mentions_score: float = 0,
    engagement_score: float = 0,
    sentiment_score: float = 0,
    volume_growth_score: float = 0,
) -> float:
    return (
        mentions_score * 0.4 +
        engagement_score * 0.3 +
        sentiment_score * 0.2 +
        volume_growth_score * 0.1
    )


def opportunity_score(
    social_mentions_growth: float = 0,
    positive_sentiment: float = 0,
    liquidity_score: float = 0,
    low_market_cap_score: float = 0,
) -> float:
    return (
        social_mentions_growth * 0.45 +
        positive_sentiment * 0.25 +
        liquidity_score * 0.15 +
        low_market_cap_score * 0.15
    )


def format_usd(value: float) -> str:
    if value is None:
        return "$0.00"
    if abs(value) >= 1:
        return f"${value:,.2f}"
    if abs(value) >= 0.01:
        return f"${value:,.4f}"
    return f"${value:.8f}"


def format_pnl(pnl_value: float) -> str:
    sign = "+" if pnl_value >= 0 else ""
    return f"{sign}{format_usd(pnl_value)}"


def format_pnl_percent(pct: Optional[float]) -> str:
    if pct is None:
        return "N/A"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"
