from datetime import datetime
from . import config
from .alerts import determine_severity

SEP = "\n" + "─" * 35 + "\n"


def _fmt_price(val, decimals=8):
    if val is None or val == 0:
        return "$0.00"
    if val >= 1:
        return f"${val:,.2f}"
    if val >= 0.01:
        return f"${val:,.4f}"
    return f"${val:,.8f}"


def _fmt_change(val, suffix="%", always_sign=True):
    if val is None:
        return "N/A"
    if always_sign and val > 0:
        return f"+{val:.2f}{suffix}"
    return f"{val:.2f}{suffix}"


def format_usd(value):
    if value is None:
        return "N/A"
    if not isinstance(value, (int, float)):
        return "N/A"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:,.2f}"


def _fmt_pnl(val):
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}${val:,.2f}"


def _change_emoji(val):
    if val is None:
        return "⚪"
    if val > 0:
        return "🟢"
    if val < 0:
        return "🔴"
    return "⚪"


def _severity_emoji(sev):
    emojis = {
        "dump": "⚠️",
        "dump_severe": "🚨",
        "dump_extreme": "🩸",
    }
    return emojis.get(sev, "⚠️")


def _severity_label(sev):
    return config.SEVERITY_LABELS.get(sev, "⚠️ Alert")


def split_long_message(text, max_len=4000):
    parts = []
    while len(text) > max_len:
        split_at = text.rfind("\n\n", 0, max_len)
        if split_at == -1:
            split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].strip()
    if text:
        parts.append(text)
    return parts


def format_dump_alert(alert):
    coin = alert["coin"]
    slug = coin["id"]
    name = coin.get("name", slug)
    symbol = (coin.get("symbol") or "").upper()
    price = coin.get("current_price")
    volume = coin.get("total_volume") or 0
    mcap = coin.get("market_cap") or 0
    rank = coin.get("market_cap_rank")

    sev = alert["severity"]
    window = alert["window"]
    change_pct = alert["change_pct"]
    all_changes = alert.get("all_changes", {})

    emoji = _severity_emoji(sev)
    label = _severity_label(sev)

    lines = [
        f"{emoji} <b>{label}</b>",
        "",
        f"<b>Token:</b> {symbol} — {name}",
        f"<b>Price:</b> {_fmt_price(price)}",
        f"<b>Trigger:</b> {_fmt_change(change_pct)} in {window}",
        "",
        "<b>Changes:</b>",
    ]

    for w in config.ALERT_WINDOWS:
        ch = all_changes.get(w)
        if ch is not None:
            e = _change_emoji(ch)
            lines.append(f"  {w}: {e} {_fmt_change(ch)}")

    lines.extend([
        "",
        "<b>Market:</b>",
        f"  Volume 24h: {_fmt_price(volume)}",
        f"  Market Cap: {_fmt_price(mcap)}",
    ])
    if rank:
        lines.append(f"  Rank: #{rank}")

    lines.extend([
        "",
        f"🔗 <a href='https://www.coingecko.com/en/coins/{slug}'>View on CoinGecko</a>",
        f"🕐 Detected: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "⚠️ Not financial advice. Verify liquidity, news and exchange spreads before acting.",
    ])

    return "\n".join(lines)


def format_portfolio_report(result):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "📊 <b>Portfolio Snapshot</b>",
        f"🕒 {timestamp}",
        "",
    ]

    if result["total_value"] > 0:
        lines.append(f"💰 <b>Positions Value:</b> {format_usd(result['total_value'])}")
    cash = result.get("cash_balance", 0)
    lines.append(f"💵 <b>Cash:</b> {format_usd(cash)}")
    lines.append(f"💎 <b>Total Value:</b> {format_usd(result.get('total_value_with_cash', result['total_value'] + cash))}")

    if result["total_invested"] > 0:
        lines.append(f"💸 <b>Cost Basis:</b> {format_usd(result['total_invested'])}")

    unrealized = result.get("unrealized_pnl", 0)
    realized = result.get("realized_pnl", 0)
    total_pnl_usd = result["total_pnl_usd"]

    if unrealized != 0:
        e = "📈" if unrealized > 0 else "📉"
        lines.append(f"{e} <b>Unrealized P&L:</b> {_fmt_pnl(unrealized)}")
    if realized != 0:
        e = "📈" if realized > 0 else "📉"
        lines.append(f"{e} <b>Realized P&L:</b> {_fmt_pnl(realized)}")
    if total_pnl_usd != 0:
        pnl_emoji = "📈" if total_pnl_usd > 0 else "📉"
        lines.append(
            f"{pnl_emoji} <b>Total P&L:</b> {_fmt_pnl(total_pnl_usd)} "
            f"({_fmt_change(result['total_pnl_pct'])})"
        )

    w24h = result.get("weighted_24h_change")
    if w24h is not None:
        e = _change_emoji(w24h)
        lines.append(f"{e} <b>24h Change:</b> {_fmt_change(w24h)}")

    lines.append(SEP)

    for token in result["tokens"]:
        e = _change_emoji(token["change_24h"])
        lines.append(
            f"{e} <b>{token['symbol']} — {token['name']}</b>"
        )
        changes_line = f"   Price: {format_usd(token['price'])}"
        if token.get("change_1h") is not None:
            changes_line += f" | 1h: {_fmt_change(token['change_1h'])}"
        if token.get("change_24h") is not None:
            changes_line += f" | 24h: {_fmt_change(token['change_24h'])}"
        if token.get("change_7d") is not None:
            changes_line += f" | 7d: {_fmt_change(token['change_7d'])}"
        lines.append(changes_line)

        if token["quantity"] and token["quantity"] > 0:
            lines.append(
                f"   Position: {token['quantity']:.4f} {token['symbol']} "
                f"= {format_usd(token['position_value'])}"
            )

        if token["entry_price"] and token["entry_price"] > 0:
            lines.append(f"   Entry: {format_usd(token['entry_price'])}")
            lines.append(f"   Cost Basis: {format_usd(token.get('cost_basis', 0))}")

        if token["pnl_pct"] is not None:
            emoji_pnl = "🟢" if token["pnl_pct"] >= 0 else "🔴"
            pnl_str = f"   P&L: {emoji_pnl} {_fmt_change(token['pnl_pct'])}"
            if token["pnl_usd"] is not None:
                pnl_str += f" ({_fmt_pnl(token['pnl_usd'])})"
            lines.append(pnl_str)

        rp = token.get("realized_pnl", 0)
        if rp:
            e = "🟢" if rp >= 0 else "🔴"
            lines.append(f"   Realized P&L: {e} {_fmt_pnl(rp)}")

        lines.append(f"   Allocation: {token['allocation']}%")
        lines.append("")

    lines.append(SEP)
    lines.append("<b>Summary</b>")

    if result["best_token"]:
        lines.append(f"🟢 Best 24h: {result['best_token']}")
    if result["worst_token"]:
        lines.append(f"🔴 Worst 24h: {result['worst_token']}")

    lines.append(f"\n🕐 {timestamp}")

    return split_long_message("\n".join(lines))


def format_coin_detail(coin_data):
    md = coin_data.get("market_data", {})
    price = md.get("current_price", {}).get("usd", 0)
    cap = md.get("market_cap", {}).get("usd", 0)
    vol = md.get("total_volume", {}).get("usd", 0)
    rank = md.get("market_cap_rank", "N/A")
    high_24h = md.get("high_24h", {}).get("usd")
    low_24h = md.get("low_24h", {}).get("usd")

    ch1h = md.get("price_change_percentage_1h_in_currency", {}).get("usd")
    ch24h = md.get("price_change_percentage_24h")
    ch7d = md.get("price_change_percentage_7d")

    name = coin_data.get("name", "")
    symbol = (coin_data.get("symbol") or "").upper()
    slug = coin_data.get("id", "")

    def fmt(val):
        if val is None:
            return "N/A"
        e = "🟢" if val >= 0 else "🔴"
        return f"{e} {val:+.2f}%"

    lines = [
        f"<b>{name}</b> ({symbol})",
        "",
        f"💰 Price: {_fmt_price(price)}",
        f"🏆 Rank: #{rank}",
        f"📊 Market Cap: {_fmt_price(cap)}",
        f"📈 Vol 24h: {_fmt_price(vol)}",
    ]

    if high_24h:
        lines.append(f"📊 High 24h: {_fmt_price(high_24h)}")
    if low_24h:
        lines.append(f"📊 Low 24h: {_fmt_price(low_24h)}")

    lines.extend([
        "",
        f"1h: {fmt(ch1h)}",
        f"24h: {fmt(ch24h)}",
        f"7d: {fmt(ch7d)}",
        "",
        f"🔗 <a href='https://www.coingecko.com/en/coins/{slug}'>View on CoinGecko</a>",
    ])

    return "\n".join(lines)


def format_top_list(coins):
    lines = ["<b>🏆 Top 10 by Market Cap</b>\n"]
    for i, c in enumerate(coins, 1):
        ch = c.get("price_change_percentage_24h")
        e = _change_emoji(ch)
        ch_s = _fmt_change(ch) if ch is not None else "N/A"
        lines.append(
            f"{i}. <b>{c['name']}</b> ({c['symbol'].upper()})"
        )
        lines.append(f"   {_fmt_price(c['current_price'])} | {e} {ch_s}")
    return "\n".join(lines)


def format_gainers_losers(gainers, losers):
    lines = []

    lines.append("<b>🟢 Top 10 Gainers (24h)</b>\n")
    for i, c in enumerate(gainers, 1):
        ch = c["price_change_percentage_24h"]
        lines.append(
            f"{i}. <b>{c['name']}</b> ({c['symbol'].upper()})"
        )
        lines.append(f"   <b>+{ch:.2f}%</b> | {_fmt_price(c['current_price'])}")
    lines.append("")

    lines.append("─" * 35)
    lines.append("")

    lines.append("<b>🔴 Top 10 Losers (24h)</b>\n")
    for i, c in enumerate(losers, 1):
        ch = c["price_change_percentage_24h"]
        lines.append(
            f"{i}. <b>{c['name']}</b> ({c['symbol'].upper()})"
        )
        lines.append(f"   <b>{ch:.2f}%</b> | {_fmt_price(c['current_price'])}")

    return split_long_message("\n".join(lines))


def format_status(stats):
    lines = [
        "<b>🤖 Bot Status</b>",
        "",
        "━━━━━━━━━━━━━━",
        "<b>Monitor:</b>",
        f"• Crash check: every {config.MONITOR_INTERVAL}s",
        f"• Portfolio report: every {config.PORTFOLIO_INTERVAL}s",
        f"• Poll interval: {config.POLL_INTERVAL}s",
        "",
        "<b>Filters:</b>",
        f"• Min volume: ${config.MIN_VOLUME_USD:,.0f}",
        f"• Min market cap: ${config.MIN_MARKET_CAP_USD:,.0f}",
        f"• Cooldown: {config.COOLDOWN_MINUTES} min",
        "",
        "<b>Alerts:</b>",
    ]
    for level, threshold in sorted(
        config.DROP_THRESHOLDS.items(), key=lambda x: x[1]
    ):
        label = config.SEVERITY_LABELS.get(level, level)
        lines.append(f"  • {label}: {threshold}%")
    lines.append("")
    lines.append("<b>API Usage:</b>")
    if stats:
        lines.append(f"  • Calls (hour): {stats.get('calls_hour', '?')}")
        lines.append(f"  • Calls (day): {stats.get('calls_day', '?')}")
    lines.append("")
    lines.append(f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    return "\n".join(lines)


def format_help():
    return (
        "<b>🤖 Comandos Disponibles</b>\n\n"
        "━━━━━━━━━━━━━━\n"
        "<b>Portafolio</b>\n"
        "• /portafolio — Resumen completo del portafolio\n"
        "• /buy &lt;sym&gt; &lt;qty&gt; &lt;price&gt; [fee] — Comprar\n"
        "• /sell &lt;sym&gt; &lt;qty&gt; &lt;price&gt; [fee] — Vender parcial\n"
        "• /sellall &lt;sym&gt; &lt;price&gt; [fee] — Vender todo\n"
        "• /position &lt;sym&gt; — Detalle de posicion\n"
        "• /transactions &lt;sym&gt; — Historial de operaciones\n"
        "• /addtoken &lt;sym&gt; &lt;coin_id&gt; — Agregar token\n"
        "• /removetoken &lt;sym&gt; — Archivar token\n"
        "• /cash — Efectivo disponible\n"
        "• /deposit &lt;amount&gt; [note] — Depositar efectivo\n"
        "• /withdraw &lt;amount&gt; [note] — Retirar efectivo\n"
        "• /portfolioedit — Menu de edicion\n\n"
        "<b>Busqueda</b>\n"
        "• /precio &lt;coin&gt; — Precio, cambios 1h/24h/7d\n"
        "• /search &lt;texto&gt; — Buscar token por nombre\n\n"
        "<b>Mercado</b>\n"
        "• /top — Top 10 por market cap\n"
        "• /gainers — Top 10 ganadores 24h\n"
        "• /losers — Top 10 perdedores 24h\n\n"
        "<b>Alertas</b>\n"
        "• /alerts — Ultimas alertas registradas\n"
        "• /watchlist — Tokens bajo vigilancia\n"
        "• /addwatch &lt;coin_id&gt; — Agregar a watchlist\n"
        "• /removewatch &lt;coin_id&gt; — Quitar de watchlist\n\n"
        "<b>Tendencias</b>\n"
        "• /trends — Top oportunidades por Opportunity Score\n"
        "• /early — Senales tempranas\n"
        "• /hype — Tokens con ruido sin volumen\n\n"
        "<b>Sistema</b>\n"
        "• /status — Estado del bot\n"
        "• /help — Esta ayuda"
    )


def format_watchlist(watchlist):
    if not watchlist:
        return "📋 <b>Watchlist</b>\n\nNo hay tokens en la watchlist.\nUsa /addwatch &lt;coin_id&gt; para agregar."

    lines = ["📋 <b>Watchlist</b>\n"]
    for slug, info in watchlist.items():
        symbol = info.get("symbol", slug)
        thresholds = info.get("alert_thresholds", {})
        lines.append(f"• <b>{symbol}</b> ({slug})")
        if thresholds:
            parts = [f"{w}: {t}%" for w, t in thresholds.items()]
            lines.append(f"  Thresholds: {', '.join(parts)}")
    return "\n".join(lines)


def format_alerts_list(alerts):
    if not alerts:
        return "🚨 <b>Recent Alerts</b>\n\nNo hay alertas recientes."

    lines = ["🚨 <b>Recent Alerts</b>\n"]
    for a in alerts:
        slug = a.get("slug", "?")
        sev = a.get("severity", "?")
        window = a.get("window", "?")
        time_str = a.get("time", "?")[:19]
        label = config.SEVERITY_LABELS.get(sev, sev)
        lines.append(f"• <b>{slug}</b> — {label} ({window})")
        lines.append(f"  {time_str}")
    return "\n".join(lines)


def format_error(msg):
    return f"❌ {msg}"


def format_api_error(source="CoinGecko"):
    return (
        f"\u26a0\ufe0f Error al consultar {source}.\n"
        "La API puede estar temporalmente caída o con limite de requests.\n"
        "Intenta de nuevo en unos minutos."
    )


def format_usage_error(cmd, required, examples):
    lines = [
        f"\u26a0\ufe0f <b>Uso incorrecto</b>",
        f"<b>{cmd}</b> requiere los siguientes argumentos:",
    ]
    if required:
        for r in required:
            lines.append(f"  \u2022 <code>{r}</code> (obligatorio)")
    lines.append("")
    if examples:
        lines.append("<b>Ejemplos:</b>")
        for ex in examples:
            lines.append(f"  <code>{ex}</code>")
    return "\n".join(lines)


def format_not_found(query):
    return (
        f"No se encontr\u00f3 <b>{query}</b>.\n"
        "Verifica el nombre o ID del token. Usa /search para buscar."
    )
