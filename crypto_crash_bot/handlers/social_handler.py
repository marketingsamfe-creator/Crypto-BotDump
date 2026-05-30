from typing import Optional
from .. import config
from .. import coingecko_client
from ..social import scanner as social_scanner
from ..social.formatter import format_trends_list, format_early_list, format_hype_list
from ..logger import logger
from ..utils.calculations import hype_score, opportunity_score
from ..utils.formatters import format_usd, format_pnl_percent


def handle_trends(args: list) -> str:
    try:
        results = social_scanner.get_trends(limit=10)
        if results:
            return format_trends_list(results)
        return "No trending data available."
    except Exception as e:
        logger.error(f"Trends error: {e}")
        return "Error fetching trends."


def handle_early(args: list) -> str:
    try:
        results = social_scanner.get_trends(limit=10, min_score=70)
        if results:
            return format_early_list(results)
        return "No early signals found."
    except Exception as e:
        logger.error(f"Early signals error: {e}")
        return "Error fetching early signals."


def handle_hype(args: list) -> str:
    try:
        results = social_scanner.get_trends(limit=10, min_score=55)
        if results:
            return format_hype_list(results)
        return "No hype tokens found."
    except Exception as e:
        logger.error(f"Hype error: {e}")
        return "Error fetching hype data."


def handle_top_trending(args: list) -> str:
    try:
        trending = coingecko_client.get_trending()
        if not trending:
            return "No trending data available."
        lines = ["\U0001f525 Top Trending Tokens", ""]
        for i, coin in enumerate(trending[:10], 1):
            item = coin.get("item", coin)
            sym = item.get("symbol", "?").upper()
            name = item.get("name", "?")
            score = item.get("score", item.get("gecko_score", 0))
            price = item.get("price", item.get("data", {}).get("price", 0))
            lines.append(f"{i}. {name} ({sym})")
            if price:
                lines.append(f"   Price: {format_usd(price)}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Top trending error: {e}")
        return "Error fetching trending data."


def handle_hype_analysis(args: list) -> str:
    try:
        results = social_scanner.get_trends(limit=20)
        if not results:
            return "No data for hype analysis."
        scored = []
        for t in results:
            m_score = t.get("mentions_score", t.get("score", 0))
            e_score = t.get("engagement_score", m_score)
            s_score = t.get("sentiment_score", 50)
            v_score = t.get("volume_score", 0)
            h = hype_score(m_score, e_score, s_score, v_score)
            o = opportunity_score(
                social_mentions_growth=m_score,
                positive_sentiment=s_score,
                liquidity_score=min(t.get("liquidity", 0) / 100000, 100) if t.get("liquidity") else 0,
                low_market_cap_score=max(0, 100 - (t.get("fdv", 0) / 1000000) * 10) if t.get("fdv") else 50,
            )
            scored.append((t, h, o))
        scored.sort(key=lambda x: x[2], reverse=True)
        lines = ["\U0001f4a5 Early Hype Tokens", ""]
        for i, (t, h, o) in enumerate(scored[:10], 1):
            sym = t.get("symbol", t.get("name", "?")).upper()
            name = t.get("name", sym)
            lines.append(f"{i}. {name} ({sym})")
            lines.append(f"   Hype Score: {h:.1f}/100 | Opportunity: {o:.1f}/100")
            volume = t.get("volume_24h", t.get("volume_usd", 0))
            liq = t.get("liquidity", 0)
            if volume:
                lines.append(f"   Volume: {format_usd(volume)}")
            if liq:
                lines.append(f"   Liquidity: {format_usd(liq)}")
            lines.append("")
        return "\n".join(lines) if len(lines) > 2 else "No hype tokens found."
    except Exception as e:
        logger.error(f"Hype analysis error: {e}")
        return "Error analyzing hype tokens."
