from typing import Optional
from .calculations import format_usd, format_pnl_percent

SEPARATOR = "\n" + "\u2501" * 20 + "\n"


def format_portfolio_summary(
    total_value: float,
    total_invested: float,
    total_pnl: float,
    total_pnl_pct: Optional[float],
    tokens_in_profit: int = 0,
    tokens_in_loss: int = 0,
    best_performer: Optional[tuple] = None,
    worst_performer: Optional[tuple] = None,
    portfolio_name: str = "My Portfolio",
) -> str:
    lines = [
        f"\U0001f4ca Portfolio: {portfolio_name}",
        "",
        f"\U0001f4b0 Current Value: {format_usd(total_value)}",
        f"\U0001f4b5 Total Invested: {format_usd(total_invested)}",
    ]
    if total_pnl >= 0:
        lines.append(f"\U0001f4c8 Unrealized PNL: +{format_usd(total_pnl)}")
    else:
        lines.append(f"\U0001f4c9 Unrealized PNL: {format_usd(total_pnl)}")
    lines.append(f"\U0001f4ca Total Performance: {format_pnl_percent(total_pnl_pct)}")
    lines.append("")
    lines.append(f"\U0001f7e2 Tokens in Profit: {tokens_in_profit}")
    lines.append(f"\U0001f534 Tokens in Loss: {tokens_in_loss}")
    if best_performer:
        sym, pct = best_performer
        lines.append(f"\nBest Performer: {sym} {format_pnl_percent(pct)}")
    if worst_performer:
        sym, pct = worst_performer
        lines.append(f"Worst Performer: {sym} {format_pnl_percent(pct)}")
    return "\n".join(lines)


def format_token_position(
    symbol: str,
    name: str,
    amount: float,
    buy_price: float,
    current_price: float,
    current_value: float,
    invested: float,
    pnl: float,
    pnl_pct: Optional[float],
    changes: Optional[dict] = None,
) -> str:
    lines = [
        f"\U0001fa99 {name} ({symbol})",
        f"Amount: {amount:.6f}",
        f"Buy Price: {format_usd(buy_price)}",
        f"Current Price: {format_usd(current_price)}",
        f"Current Value: {format_usd(current_value)}",
        f"Invested: {format_usd(invested)}",
    ]
    if pnl >= 0:
        lines.append(f"PNL: +{format_usd(pnl)}")
    else:
        lines.append(f"PNL: {format_usd(pnl)}")
    lines.append(f"PNL %: {format_pnl_percent(pnl_pct)}")
    if changes:
        lines.append("")
        lines.append("Price Change:")
        for period, pct in sorted(changes.items()):
            if pct is not None:
                lines.append(f"  {period}: {format_pnl_percent(pct)}")
    return "\n".join(lines)


def format_token_report(
    name: str,
    symbol: str,
    contract: str = "",
    network: str = "",
    price: Optional[float] = None,
    market_cap: Optional[float] = None,
    fdv: Optional[float] = None,
    volume_24h: Optional[float] = None,
    liquidity: Optional[float] = None,
    price_changes: Optional[dict] = None,
    holders: Optional[int] = None,
    dex_pairs: int = 0,
    risk_notes: Optional[list] = None,
    links: Optional[dict] = None,
) -> str:
    lines = [
        f"\U0001f50d Token Report: {name} ({symbol})",
        "",
    ]
    if contract:
        lines.append(f"Contract: {contract[:42]}{'...' if len(contract) > 42 else ''}")
    if network:
        lines.append(f"Network: {network}")
    if price is not None:
        lines.append(f"Price: {format_usd(price)}")
    if market_cap is not None:
        lines.append(f"Market Cap: {format_usd(market_cap)}")
    if fdv is not None:
        lines.append(f"FDV: {format_usd(fdv)}")
    if volume_24h is not None:
        lines.append(f"24h Volume: {format_usd(volume_24h)}")
    if liquidity is not None:
        lines.append(f"Liquidity: {format_usd(liquidity)}")
    if holders is not None:
        lines.append(f"Holders: {holders:,}")
    if dex_pairs:
        lines.append(f"DEX Pairs: {dex_pairs}")
    if price_changes:
        lines.append("")
        lines.append("Price Change:")
        for period, pct in sorted(price_changes.items()):
            if pct is not None:
                lines.append(f"  {period}: {format_pnl_percent(pct)}")
    if risk_notes:
        lines.append("")
        lines.append("\u26a0\ufe0f Risk Notes:")
        for note in risk_notes:
            lines.append(f"  \u2022 {note}")
    if links:
        lines.append("")
        for label, url in links.items():
            if url:
                lines.append(f"\U0001f517 {label}: {url}")
    return "\n".join(lines)


def format_hourly_report(
    losers: list,
    gainers: list,
    trending: list,
    hype_tokens: list,
    portfolio_summary: Optional[str] = None,
) -> str:
    lines = ["\U0001f4ca Hourly Crypto Report", ""]

    if losers:
        lines.append("\U0001f4c9 Top 10 Losers:")
        for i, t in enumerate(losers[:10], 1):
            sym = t.get("symbol", t.get("name", "?"))
            pct = t.get("price_change_24h", t.get("change", 0))
            lines.append(f"  {i}. {sym} {format_pnl_percent(pct)}")
        lines.append("")

    if gainers:
        lines.append("\U0001f4c8 Top 10 Gainers:")
        for i, t in enumerate(gainers[:10], 1):
            sym = t.get("symbol", t.get("name", "?"))
            pct = t.get("price_change_24h", t.get("change", 0))
            lines.append(f"  {i}. {sym} {format_pnl_percent(pct)}")
        lines.append("")

    if trending:
        lines.append("\U0001f525 Trending:")
        for i, t in enumerate(trending[:5], 1):
            sym = t.get("symbol", t.get("name", "?"))
            lines.append(f"  {i}. {sym}")
        lines.append("")

    if hype_tokens:
        lines.append("\U0001f4a5 Social Hype:")
        for i, t in enumerate(hype_tokens[:5], 1):
            sym = t.get("symbol", t.get("name", "?"))
            mentions = t.get("mentions_growth", t.get("score", 0))
            lines.append(f"  {i}. {sym} (Score: {mentions})")
        lines.append("")

    if portfolio_summary:
        lines.append(portfolio_summary)

    return "\n".join(lines) if len(lines) > 2 else "No data available for hourly report."
