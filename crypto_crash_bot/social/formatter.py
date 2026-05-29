from datetime import datetime
from . import scoring
from .. import config

SEP = "\n" + "\u2500" * 35 + "\n"


def _fmt_price(val):
    if val is None or val == 0:
        return "$0.00"
    val = float(val)
    if val >= 1:
        return f"${val:,.2f}"
    if val >= 0.01:
        return f"${val:,.4f}"
    return f"${val:,.8f}"


def _fmt_change(val, always_sign=True):
    if val is None:
        return "N/A"
    val = float(val)
    if always_sign and val > 0:
        return f"+{val:.2f}%"
    return f"{val:.2f}%"


def _change_emoji(val):
    if val is None:
        return "\u26aa"
    if float(val) > 0:
        return "\U0001f7e2"
    if float(val) < 0:
        return "\U0001f534"
    return "\u26aa"


def _risk_emoji(flags):
    if flags:
        return "\U0001f9e8"
    return ""


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


def format_trends_list(results):
    if not results:
        return "No hay datos de tendencias. Espera al siguiente escaneo."

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"\U0001f4a1 <b>Top Opportunities</b>",
        f"\U0001f552 {now}\n",
    ]

    for i, r in enumerate(results[:15], 1):
        cat_info = scoring.CATEGORY_LABELS.get(
            r.get("category", "low_signal"),
            ("Unknown", "\u2753"),
        )
        emoji = cat_info[1]
        symbol = r.get("symbol", "?")
        name = r.get("name", "?")
        score = r.get("score", 0)
        narrative = r.get("narrative", "")
        price_change = r.get("price_change_24h")
        e = _change_emoji(price_change)

        lines.append(
            f"{i}. {emoji} <b>{symbol}</b> — {name}"
        )
        lines.append(
            f"   Score: <b>{score}/100</b> | 24h: {e} {_fmt_change(price_change)}"
        )
        if narrative and narrative != "General":
            lines.append(f"   Narrative: {narrative}")
        lines.append("")

    lines.append(SEP)
    lines.append("\U0001f449 Usa /early para se\u00f1ales tempranas")
    lines.append("\U0001f449 Usa /hype para ruido sin volumen")
    lines.append("\n\u26a0\ufe0f No es consejo financiero.")

    return split_long_message("\n".join(lines))


def format_early_list(results):
    if not results:
        return "\U0001f7e2 <b>Early Signals</b>\n\nNo hay se\u00f1ales tempranas en este momento."

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"\U0001f7e2 <b>Early Signals</b>",
        f"\U0001f552 {now}\n",
    ]

    for i, r in enumerate(results[:10], 1):
        cat_info = scoring.CATEGORY_LABELS.get(
            r.get("category", "low_signal"),
            ("Unknown", "\u2753"),
        )
        emoji = cat_info[1]
        label = cat_info[0]
        symbol = r.get("symbol", "?")
        score = r.get("score", 0)
        narrative = r.get("narrative", "")
        price = r.get("price")
        vol = r.get("volume_24h")
        liq = r.get("liquidity")
        ph = r.get("price_change_1h")
        p24 = r.get("price_change_24h")

        lines.append(f"{i}. {emoji} <b>{symbol}</b> — Score: <b>{score}/100</b>")
        lines.append(f"   Category: {label}")
        if price:
            lines.append(f"   Price: {_fmt_price(price)}")
        parts = []
        if ph is not None:
            parts.append(f"1h: {_fmt_change(ph)}")
        if p24 is not None:
            parts.append(f"24h: {_fmt_change(p24)}")
        if parts:
            lines.append(f"   Changes: {' | '.join(parts)}")
        if vol:
            lines.append(f"   Volume 24h: {_fmt_price(vol)}")
        if liq:
            lines.append(f"   Liquidity: {_fmt_price(liq)}")
        if narrative and narrative != "General":
            lines.append(f"   Narrative: {narrative}")
        lines.append("")

    lines.append("\u26a0\ufe0f No es consejo financiero.")
    return split_long_message("\n".join(lines))


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


def _build_hype_reason(r):
    score = r.get("score", 0) or 0
    vol = r.get("volume_24h")
    liq = r.get("liquidity")
    vol_score = r.get("volume_score")
    reasons = []
    if score >= 60:
        reasons.append(f"Social Score alto ({score}/100)")
    if vol_score is not None and vol_score <= 4:
        reasons.append(f"Volume Score bajo ({vol_score}/10)")
    if vol is None and liq is None:
        reasons.append("Sin datos de volumen real")
    if liq is not None and liq < 100_000:
        reasons.append("Liquidez muy baja")
    if vol is not None and liq is not None and liq > 0 and (vol / liq) < 0.5:
        reasons.append("Volumen bajo relativo a liquidez")
    return "; ".join(reasons) if reasons else "Ruido social sin confirmacion de mercado"


def format_hype_list(results):
    if not results:
        return "\u26aa <b>Hype Warning</b>\n\nNo hay tokens con ruido excesivo sin volumen."

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"\u26a0\ufe0f <b>Hype Without Volume</b>",
        f"\U0001f552 {now}",
        "",
        "Tokens con alta atencion social pero bajo volumen o liquidez.\n",
    ]

    for i, r in enumerate(results[:8], 1):
        symbol = r.get("symbol", "?")
        name = r.get("name", "")
        score = r.get("score", 0) or 0
        vol = r.get("volume_24h")
        liq = r.get("liquidity")
        vol_score = r.get("volume_score")
        ph = r.get("price_change_1h")
        p24 = r.get("price_change_24h")
        fdv = r.get("fdv")
        chain = r.get("chain", "")
        slug = r.get("slug", "")

        lines.append(
            f"{i}. <b>{symbol}</b> — {name}"
        )
        lines.append(f"   Social Score: {score}/100")
        if vol_score is not None:
            lines.append(f"   Volume Score: {vol_score}/10")
        else:
            lines.append(f"   Volume Score: N/A")
        lines.append(f"   Real Volume 24h: {format_usd(vol)}")
        if ph is not None:
            e = "\U0001f7e2" if ph >= 0 else "\U0001f534"
            lines.append(f"   1h: {e} {ph:+.2f}%")
        if p24 is not None:
            e = "\U0001f7e2" if p24 >= 0 else "\U0001f534"
            lines.append(f"   24h: {e} {p24:+.2f}%")
        lines.append(f"   Liquidity: {format_usd(liq)}")
        if chain:
            lines.append(f"   Chain: {chain}")
        if fdv:
            lines.append(f"   FDV: {format_usd(fdv)}")
        reason = _build_hype_reason(r)
        lines.append(f"   \u26a0\ufe0f {reason}")
        lines.append("")

    lines.append("\u26a0\ufe0f No es consejo financiero.")
    return "\n".join(lines)


def build_trend_buttons(slug):
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f4c8 DexScreener",
                 "url": f"https://dexscreener.com/search?q={slug}"},
                {"text": "\U0001f4a1 CoinGecko",
                 "url": f"https://www.coingecko.com/en/coins/{slug}"},
            ],
            [
                {"text": "\u2795 Watchlist",
                 "callback_data": f"watchlist:add:{slug}"},
            ],
        ]
    }
