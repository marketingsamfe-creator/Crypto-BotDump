from datetime import datetime
from ..logger import logger
from . import trending, dex_client, scoring, database


def run_scan():
    logger.info("Starting social scan...")
    database.init_db()
    results = []

    gecko_trending = trending.fetch_trending()
    if not gecko_trending:
        logger.warning("No trending data from CoinGecko")
        return []

    top_slugs = [t["slug"] for t in gecko_trending[:20]]
    prices = trending.fetch_simple_price(top_slugs)

    for item in gecko_trending[:20]:
        slug = item["slug"]
        symbol = item["symbol"]
        name = item["name"]
        gecko_score = item.get("score", 0) or 0

        entry = {
            "slug": slug,
            "symbol": symbol,
            "name": name,
            "gecko_score": 15 - gecko_score,
            "source": "coingecko_trending",
            "risk_flags": scoring.detect_risks(name, symbol),
            "is_portfolio": scoring.is_portfolio_coin(slug),
        }

        price_data = prices.get(slug, {})
        entry["price"] = price_data.get("usd")
        entry["volume_24h"] = price_data.get("usd_24h_vol")
        entry["price_change_24h"] = price_data.get("usd_24h_change")

        pair = dex_client.search_pairs(symbol)
        best = dex_client.get_best_pair(pair, symbol)
        if best:
            dex_info = dex_client.extract_market_data(best)
            entry["dex_data"] = dex_info
            entry["price"] = entry["price"] or dex_info.get("price")
            entry["price_change_1h"] = dex_info.get("price_change_1h")
            entry["price_change_24h"] = entry["price_change_24h"] or dex_info.get("price_change_24h")
            entry["volume_24h"] = entry["volume_24h"] or dex_info.get("volume_24h")
            entry["liquidity"] = dex_info.get("liquidity")
            entry["fdv"] = dex_info.get("fdv")
            entry["chain"] = dex_info.get("chain")
            entry["pair_address"] = dex_info.get("pair_address")
            entry["dex_url"] = dex_info.get("dex_url")
        else:
            entry["dex_data"] = {}

        vol_real = entry.get("volume_24h")
        liq_real = entry.get("liquidity")
        volume_score = scoring.calculate_volume_score(vol_real, liq_real)

        logger.info(
            f"HYPE_DEBUG token={slug} source={'dexscreener' if entry.get('dex_data') else 'coingecko'} "
            f"volume_h24={vol_real} liquidity={liq_real} "
            f"volume_score={volume_score} social_score={score}"
        )

        score = scoring.calculate_score(entry)
        category = scoring.classify(
            score, entry.get("price_change_1h"),
            entry.get("price_change_24h"), entry.get("risk_flags", [])
        )
        narratives = scoring.detect_narrative(name, symbol)

        result = {
            "slug": slug,
            "symbol": symbol,
            "name": name,
            "score": score,
            "volume_score": volume_score,
            "category": category,
            "narrative": ", ".join(narratives) if narratives else "General",
            "source": "coingecko_trending",
            "price": entry.get("price"),
            "price_change_1h": entry.get("price_change_1h"),
            "price_change_24h": entry.get("price_change_24h"),
            "volume_24h": vol_real,
            "volume_1h": (entry.get("dex_data") or {}).get("volume_1h"),
            "volume_change_24h": None,
            "liquidity": liq_real,
            "fdv": entry.get("fdv"),
            "chain": entry.get("chain"),
            "pair_address": entry.get("pair_address"),
            "dex_url": entry.get("dex_url"),
            "gecko_score": gecko_score,
            "risk_flags": entry.get("risk_flags", []),
            "raw_data": {},
        }
        results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)
    database.save_trend_scores(results)
    database.set_scan_timestamp(datetime.utcnow().isoformat())

    logger.info(f"Social scan complete: {len(results)} results")
    return results


def get_trends(limit=15, min_score=0):
    return database.get_latest_scores(limit=limit, min_score=min_score)


def get_early(limit=15, min_score=70):
    high = database.get_latest_scores(limit=limit, min_score=85)
    early = database.get_latest_scores(limit=limit, min_score=min_score)
    high_cats = {"high_priority", "early_signal"}
    combined = [r for r in high if r.get("category") in high_cats]
    combined += [r for r in early if r.get("category") in high_cats and r["slug"] not in {c["slug"] for c in combined}]
    combined.sort(key=lambda x: x["score"], reverse=True)
    return combined[:limit]


def get_hype(limit=10):
    all_scores = database.get_latest_scores(limit=50)
    hype = [r for r in all_scores if r.get("category") == "moderate_noise"]
    return hype[:limit]


def get_risk(limit=10):
    all_scores = database.get_latest_scores(limit=50)
    risks = [r for r in all_scores if r.get("category") == "risk"]
    return risks[:limit]
