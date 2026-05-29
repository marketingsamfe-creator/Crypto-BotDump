import re
from .. import config
from ..logger import logger

NARRATIVE_KEYWORDS = {
    "AI": r"\b(ai|artificial.intelligence|gpt|llm|neural|agent|autonomous)\b",
    "RWA": r"\b(rwa|real.world.asset|tokenized.asset|treasury)\b",
    "DePIN": r"\b(depin|physical.infrastructure|iot|sensor|mesh)\b",
    "Bitcoin L2": r"\b(bitcoin.l2|btc.l2|bitcoin.layer|stacks|rootstock)\b",
    "Ordinals": r"\b(ordinal|brc-20|brc20|inscription)\b",
    "Solana": r"\b(solana|sol|spl)\b",
    "Base": r"\b(base|coinbase.l2)\b",
    "Gaming": r"\b(gaming|gamefi|game.fi|metaverse|p2e|play.to.earn)\b",
    "Memes": r"\b(meme|pepe|doge|shib|cat|dog|floki|woof)\b",
    "Restaking": r"\b(restaking|liquid.staking|lst|lrt|eigen)\b",
    "DeFi": r"\b(defi|lending|yield|swap|dex|liquidity|protocol)\b",
    "Infra": r"\b(infrastructure|oracle|bridge|cross.chain|interop)\b",
}

RISK_KEYWORDS = [
    "hack", "exploit", "rug", "scam", "honeypot", "delist",
    "unlock", "withdrawal paused", "bridge hacked", "contract issue",
    "insider selling", "liquidity removed", "fake airdrop",
]


def detect_narrative(name, symbol):
    text = f"{name} {symbol}".lower()
    detected = []
    for label, pattern in NARRATIVE_KEYWORDS.items():
        if re.search(pattern, text, re.IGNORECASE):
            detected.append(label)
    return detected[:2]


def detect_risks(name, symbol):
    text = f"{name} {symbol}".lower()
    found = []
    for kw in RISK_KEYWORDS:
        if kw in text:
            found.append(kw)
    return found


def is_portfolio_coin(slug):
    return any(p["slug"] == slug for p in config.PORTFOLIO)


def calculate_score(data):
    gecko_score = data.get("gecko_score", 0)
    dex_data = data.get("dex_data", {})
    price_change_1h = dex_data.get("price_change_1h")
    price_change_24h = dex_data.get("price_change_24h")
    volume_24h = dex_data.get("volume_24h")
    liquidity = dex_data.get("liquidity")
    fdv = dex_data.get("fdv")
    risk_flags = data.get("risk_flags", [])

    base_score = 0

    social_momentum = min(gecko_score * 7, 25)
    base_score += social_momentum

    if volume_24h and liquidity and liquidity > 0:
        vol_liq_ratio = volume_24h / liquidity
        if vol_liq_ratio > 0.5 and vol_liq_ratio < 10:
            base_score += 15
        elif vol_liq_ratio >= 10:
            base_score += 10
        elif vol_liq_ratio > 0:
            base_score += 5

        if volume_24h >= config.MIN_VOLUME_USD:
            base_score += 10

    if liquidity:
        if liquidity >= 1_000_000:
            base_score += 15
        elif liquidity >= 500_000:
            base_score += 10
        elif liquidity >= 100_000:
            base_score += 5

    if price_change_1h is not None:
        if -3 <= price_change_1h <= 10:
            base_score += 15
        elif 10 < price_change_1h <= 25:
            base_score += 10
        elif price_change_1h > 25:
            base_score += 3

    if price_change_24h is not None:
        if -5 <= price_change_24h <= 15:
            base_score += 5
        elif 15 < price_change_24h <= 60:
            base_score += 3
        elif price_change_24h > 80:
            base_score -= 5

    if fdv and fdv > 0:
        if fdv >= 50_000_000:
            base_score += 5
        elif fdv >= 10_000_000:
            base_score += 3

    if data.get("is_portfolio"):
        base_score += 10

    if risk_flags:
        base_score -= min(len(risk_flags) * 15, 30)

    return max(0, min(100, base_score))


def calculate_volume_score(volume_24h, liquidity):
    if volume_24h is None or volume_24h <= 0:
        return 0
    vol = float(volume_24h)
    liq = float(liquidity) if liquidity and liquidity > 0 else 0
    base = 0
    if vol >= 1_000_000:
        base += 4
    elif vol >= 100_000:
        base += 2
    elif vol >= 10_000:
        base += 1
    if liq > 0:
        ratio = vol / liq
        if ratio >= 2:
            base += 3
        elif ratio >= 1:
            base += 2
        elif ratio >= 0.5:
            base += 1
        if liq >= 500_000:
            base += 2
        elif liq >= 100_000:
            base += 1
    return min(base, 10)


def classify(score, price_change_1h, price_change_24h, risk_flags):
    if risk_flags:
        return "risk"

    has_price = price_change_1h is not None or price_change_24h is not None
    price_1h = price_change_1h or 0
    price_24h = price_change_24h or 0

    if score >= 85:
        if price_24h > 60 or price_1h > 20:
            return "pump_in_progress"
        return "high_priority"

    if score >= 70:
        if price_1h > 15 or price_24h > 40:
            return "strong_trend"
        return "early_signal"

    if score >= 55:
        return "moderate_noise"

    return "low_signal"


CATEGORY_LABELS = {
    "high_priority": ("High Priority Research", "\U0001f9e0"),
    "early_signal": ("Early Signal", "\U0001f7e2"),
    "strong_trend": ("Strong Trend", "\U0001f525"),
    "pump_in_progress": ("Pump in Progress", "\U0001f680"),
    "moderate_noise": ("Moderate Noise", "\u26aa"),
    "risk": ("Risk Signal", "\U0001f9e8"),
    "low_signal": ("Low Signal", "\u26aa"),
}
