import time
from typing import Optional
from .. import config
from .. import portfolio_db
from .. import trading_ui
from .. import coingecko_client
from ..logger import logger
from ..database import models as db_models
from ..utils.formatters import format_hourly_report, format_usd
from ..utils.calculations import (
    current_value, invested_value, unrealized_pnl, unrealized_pnl_percent,
    portfolio_total_value, portfolio_total_invested, portfolio_total_pnl,
    portfolio_total_pnl_percent,
)
from ..handlers.portfolio_handler import handle_portfolio
from ..social import scanner as social_scanner

TELEGRAM_ID = config.TELEGRAM_CHAT_ID
_last_report_time = 0
REPORT_INTERVAL = 3600


def get_hourly_report() -> Optional[str]:
    try:
        losers = coingecko_client.get_losers(limit=10)
        gainers = coingecko_client.get_gainers(limit=10)
    except Exception as e:
        logger.warning(f"Hourly report data error: {e}")
        losers = []
        gainers = []
    trending = []
    try:
        from ..social.trending import get_trending
        trending_data = get_trending()
        if trending_data:
            for t in trending_data[:5]:
                item = t.get("item", t)
                trending.append({"name": item.get("name", "?"), "symbol": item.get("symbol", "?")})
    except Exception as e:
        logger.warning(f"Trending error: {e}")
    hype_tokens = []
    try:
        hype = social_scanner.get_trends(limit=5, min_score=55)
        if hype:
            for h in hype:
                hype_tokens.append({
                    "name": h.get("name", "?"),
                    "symbol": h.get("symbol", "?"),
                    "score": h.get("score", 0),
                })
    except Exception as e:
        logger.warning(f"Hype error: {e}")
    portfolio_summary = None
    try:
        portfolio_summary = handle_portfolio([])
    except Exception as e:
        logger.warning(f"Portfolio summary error: {e}")
    return format_hourly_report(
        losers=losers,
        gainers=gainers,
        trending=trending,
        hype_tokens=hype_tokens,
        portfolio_summary=portfolio_summary,
    )


def should_send_report() -> bool:
    global _last_report_time
    now = time.time()
    if now - _last_report_time < REPORT_INTERVAL:
        return False
    user_id = db_models.register_user(TELEGRAM_ID)
    settings = db_models.get_user_settings(user_id)
    if not settings.get("hourly_report_enabled"):
        return False
    _last_report_time = now
    return True


def reset_report_timer():
    global _last_report_time
    _last_report_time = time.time()
