from typing import Optional, List
from .. import config
from .. import portfolio_db
from .. import trading_ui
from ..logger import logger
from ..database import models as db_models
from ..utils.calculations import (
    current_value, invested_value, unrealized_pnl, unrealized_pnl_percent,
    portfolio_total_value, portfolio_total_invested, portfolio_total_pnl,
    portfolio_total_pnl_percent,
)
from ..utils.formatters import format_portfolio_summary, format_token_position
from ..utils.validators import parse_portfolio_line
from ..formatter import format_usd
from ..cache import get_price_cache

TELEGRAM_ID = config.TELEGRAM_CHAT_ID

PRICE_CACHE_TTL = 60


def _fetch_prices_batch(slugs: list) -> dict:
    if not slugs:
        return {}
    from ..coingecko_client import fetch_market_coins_by_ids
    cache = get_price_cache()
    result = {}
    uncached = []
    for slug in slugs:
        cached = cache.get(f"price:{slug}")
        if cached:
            result[slug] = cached
        else:
            uncached.append(slug)
    if uncached:
        try:
            market_data = fetch_market_coins_by_ids(uncached, changes="1h,24h,7d")
            if market_data:
                for c in market_data:
                    cid = c["id"]
                    result[cid] = c
                    cache.set(f"price:{cid}", c, ttl=PRICE_CACHE_TTL)
        except Exception as e:
            logger.warning(f"Batch price fetch error: {e}")
    return result


def _resolve_coin_id(symbol: str) -> str:
    try:
        tok = trading_ui.resolve_token(symbol)
        if tok and tok.get("slug"):
            slug = tok["slug"]
            logger.info(f"RESOLVE symbol={symbol} -> slug={slug}")
            return slug
    except Exception as e:
        logger.warning(f"RESOLVE error for {symbol}: {e}")
    fallback = symbol.lower()
    logger.info(f"RESOLVE symbol={symbol} -> fallback={fallback}")
    return fallback


def handle_portfolio(args: list) -> str:
    positions = portfolio_db.get_active_positions(is_test=config.TEST_MODE)
    if not positions:
        return "Your portfolio is empty. Add tokens with /portfolio_add."
    logger.info(f"PORTFOLIO_SUMMARY: user={TELEGRAM_ID}, positions_found={len(positions)}")
    slugs = [p["coin_id"] for p in positions if p["coin_id"]]
    prices = _fetch_prices_batch(slugs)
    pos_list = []
    for pos in positions:
        sym = pos["symbol"]
        slug = pos["coin_id"]
        qty = pos["quantity"]
        buy_px = pos["avg_entry_price"]
        price_data = prices.get(slug, {})
        current_px = price_data.get("current_price")
        if current_px is None:
            logger.warning(f"PORTFOLIO_PRICE_MISSING: symbol={sym}, slug={slug}")
            pos_list.append({
                "symbol": sym,
                "current_value": 0,
                "invested_value": invested_value(qty, buy_px),
                "pnl": 0,
                "pnl_pct": None,
                "price_unavailable": True,
            })
            continue
        current_px = float(current_px)
        cv = current_value(qty, current_px)
        inv = invested_value(qty, buy_px)
        pnl = unrealized_pnl(qty, current_px, buy_px)
        pnl_pct = unrealized_pnl_percent(current_px, buy_px)
        logger.info(f"PORTFOLIO_TOKEN: symbol={sym}, qty={qty}, buy={buy_px}, current={current_px}, pnl={pnl}")
        pos_list.append({
            "symbol": sym,
            "current_value": cv,
            "invested_value": inv,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        })
    tv = portfolio_total_value(pos_list)
    ti = portfolio_total_invested(pos_list)
    tp = portfolio_total_pnl(tv, ti)
    tpp = portfolio_total_pnl_percent(tp, ti)
    profit_count = sum(1 for p in pos_list if p.get("pnl", 0) > 0)
    loss_count = sum(1 for p in pos_list if p.get("pnl", 0) < 0)
    unavailable = sum(1 for p in pos_list if p.get("price_unavailable"))
    valid = [p for p in pos_list if not p.get("price_unavailable")]
    best = max(valid, key=lambda p: p.get("pnl_pct") or -999) if valid else None
    worst = min(valid, key=lambda p: p.get("pnl_pct") or 999) if valid else None
    msg = format_portfolio_summary(
        total_value=tv, total_invested=ti, total_pnl=tp, total_pnl_pct=tpp,
        tokens_in_profit=profit_count, tokens_in_loss=loss_count,
        best_performer=(best["symbol"], best["pnl_pct"]) if best else None,
        worst_performer=(worst["symbol"], worst["pnl_pct"]) if worst else None,
    )
    if unavailable:
        msg += f"\n\n\u26a0\ufe0f Price unavailable for {unavailable} token(s)"
    return msg


def handle_portfolio_summary(args: list) -> str:
    return handle_portfolio(args)


def handle_portfolio_add(args: list) -> str:
    if len(args) < 3:
        return (
            "Usage:\n"
            "/portfolio_add <symbol> <quantity> <price>\n"
            "Example:\n"
            "/portfolio_add BTC 0.05 62000\n\n"
            "Advanced:\n"
            "/portfolio_add <network> <contract> <symbol> <qty> <price>\n"
            "Example:\n"
            "/portfolio_add ethereum 0x... PEPE 15000000 0.0000082"
        )
    if len(args) >= 5:
        network = args[0].lower()
        contract = args[1]
        symbol = args[2].upper()
        qty = float(args[3].replace(",", ""))
        price = float(args[4].replace(",", ""))
    elif len(args) >= 3:
        symbol = args[0].upper()
        qty = float(args[1].replace(",", ""))
        price = float(args[2].replace(",", ""))
        network = ""
        contract = ""
    else:
        return "Invalid arguments. See /portfolio_add for usage."
    if qty <= 0 or price <= 0:
        return "Quantity and price must be positive."
    user_id = db_models.register_user(TELEGRAM_ID)
    portfolio_id = db_models.get_or_create_portfolio(user_id)
    coin_id = _resolve_coin_id(symbol)
    token_name = symbol
    try:
        tok = trading_ui.resolve_token(symbol)
        if tok:
            token_name = tok.get("name", symbol)
            if not network:
                network = tok.get("chain_id", "")
            if not contract:
                contract = tok.get("contract_address", "")
    except Exception:
        pass
    test_flag = 1 if config.TEST_MODE else 0
    existing = portfolio_db.get_position(symbol=symbol, is_test=test_flag)
    if existing:
        return f"Token {symbol} already exists in portfolio. Use /editposition to modify."
    portfolio_db.add_position(coin_id, symbol, token_name, is_test=test_flag)
    pos = portfolio_db.get_position(symbol=symbol, is_test=test_flag)
    if pos:
        portfolio_db.edit_position(symbol, qty, price)
        portfolio_db.add_transaction(
            coin_id, symbol, "buy", qty, price, qty * price,
            notes=f"Added via /portfolio_add", is_test=test_flag
        )
    db_models.add_portfolio_token(portfolio_id, symbol, qty, price, token_name, contract, network)
    logger.info(f"PORTFOLIO_ADD: symbol={symbol}, qty={qty}, price={price}, coin_id={coin_id}")
    return (
        f"\u2705 Added {symbol}\n"
        f"Quantity: {qty:.6f}\n"
        f"Price: {format_usd(price)}\n"
        f"Total: {format_usd(qty * price)}"
    )


def handle_portfolio_remove(args: list) -> str:
    if not args:
        return "Usage: /portfolio_remove <symbol>\nExample: /portfolio_remove TAO"
    symbol = args[0].upper()
    test_flag = 1 if config.TEST_MODE else 0
    pos = portfolio_db.get_position(symbol=symbol, is_test=test_flag)
    if not pos:
        return f"Token {symbol} not found in portfolio."
    deleted = portfolio_db.hard_delete_position(symbol=symbol, is_test=test_flag)
    portfolio_db.add_transaction(
        pos["coin_id"], symbol, "remove",
        0, 0, 0, notes="Removed via /portfolio_remove", is_test=test_flag
    )
    logger.info(f"PORTFOLIO_REMOVE: symbol={symbol}, deleted={deleted}")
    return f"\u2705 Removed {symbol} from portfolio."


def handle_portfolio_clear(args: list) -> str:
    test_flag = 1 if config.TEST_MODE else 0
    positions = portfolio_db.get_active_positions(is_test=test_flag)
    if not positions:
        return "Portfolio is already empty."
    count = 0
    for pos in positions:
        deleted = portfolio_db.hard_delete_position(symbol=pos["symbol"], is_test=test_flag)
        count += deleted
    logger.info(f"PORTFOLIO_CLEAR: deleted {count} tokens")
    return f"\u2705 Cleared {count} token(s) from portfolio."


def handle_portfolio_help(args: list) -> str:
    return (
        "\U0001f4da Portfolio Commands\n\n"
        "/portfolio - Show portfolio summary\n"
        "/portfolio_summary - Detailed portfolio report\n"
        "/portfolio_add <sym> <qty> <price> - Add token\n"
        "/portfolio_add <network> <contract> <sym> <qty> <price> - Add token with details\n"
        "/portfolio_remove <sym> - Remove token\n"
        "/portfolio_clear - Clear all tokens\n"
        "/portfolio_import <url> - Import from CG/CMC\n"
        "/portfolio_import - Paste token list\n\n"
        "Examples:\n"
        "/portfolio_add BTC 0.05 62000\n"
        "/portfolio_add ethereum 0x... PEPE 15000000 0.0000082"
    )


def handle_portfolio_import(args: list) -> Optional[str]:
    if not args:
        return (
            "\U0001f4e5 Import Portfolio\n\n"
            "Send a CoinGecko or CoinMarketCap portfolio URL, or paste holdings:\n\n"
            "BTC, 0.05, 62000\n"
            "ETH, 1.2, 3100\n"
            "PEPE, 15000000, 0.0000082\n\n"
            "Or send a CG/CMC portfolio link."
        )
    text = " ".join(args)
    from ..telegram_bot import _fetch_portfolio_from_url
    cg_match = __import__("re").search(r"coingecko\.com/.+portfolio", text, __import__("re").IGNORECASE)
    cmc_match = __import__("re").search(r"coinmarketcap", text, __import__("re").IGNORECASE)
    if cg_match or cmc_match:
        result = _fetch_portfolio_from_url(text)
        if result:
            from ..telegram_bot import _apply_portfolio
            _apply_portfolio(result)
            return f"\u2705 Imported {len(result)} tokens from URL."
        return "\u274c Could not parse portfolio from URL."
    lines = text.strip().split("\n")
    entries = []
    errors = []
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        parsed = parse_portfolio_line(line)
        if parsed:
            sym, qty, price = parsed
            entries.append({"symbol": sym, "quantity": qty, "price": price})
        else:
            errors.append(f"Line {i}: could not parse")
    if not entries:
        return "\u274c No valid entries found."
    for entry in entries:
        test_flag = 1 if config.TEST_MODE else 0
        coin_id = entry["symbol"].lower()
        sym = entry["symbol"]
        qty = entry["quantity"]
        price = entry["price"]
        existing = portfolio_db.get_position(symbol=sym, is_test=test_flag)
        if existing:
            portfolio_db.edit_position(sym, qty, price)
            portfolio_db.add_transaction(
                coin_id, sym, "import_adjustment", qty, price, qty * price,
                notes="Portfolio import", is_test=test_flag
            )
        else:
            portfolio_db.add_position(coin_id, sym, sym, is_test=test_flag)
            pos = portfolio_db.get_position(symbol=sym, is_test=test_flag)
            if pos:
                portfolio_db.edit_position(sym, qty, price)
                portfolio_db.add_transaction(
                    coin_id, sym, "import", qty, price, qty * price,
                    notes="Portfolio import", is_test=test_flag
                )
    msg = f"\u2705 Imported {len(entries)} token(s)."
    if errors:
        msg += f"\nErrors: {'; '.join(errors[:3])}"
    return msg
