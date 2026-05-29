import re
import time
from datetime import datetime
from . import config, portfolio_db
from .logger import logger
from .coingecko_client import fetch_coin_detail, fetch_market_coins, search_coins, fetch_market_coins_by_ids
from .social.dex_client import search_pairs, extract_pair_data, get_best_pair, get_best_pair_for_token, detect_address_family
from .formatter import format_usd
from . import session as session_mgr

SOLANA_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
EVM_ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def detect_token_input_type(text):
    return detect_address_family(text)


def resolve_token(query):
    q = query.strip()
    if not q:
        return None
    family = detect_address_family(q)
    logger.info(f"TOKEN_RESOLVE input={q[:60]} type={family}")

    if family in ("evm_contract", "solana_address", "tron_address", "possible_contract_or_token_address"):
        best, all_pairs = get_best_pair_for_token(q)
        if best:
            result = _pair_to_token(best, q)
            result["all_pairs"] = all_pairs[:10]
            result["_family"] = family
            return result

    if family in ("coingecko_id_or_slug", "symbol_or_name"):
        q_lower = q.lower().strip()
        detail = None
        try:
            detail = fetch_coin_detail(q_lower)
        except Exception:
            pass
        if detail and detail.get("id"):
            coin_id = detail["id"]
        else:
            coin_data = search_coins(q_lower)
            coin = None
            if coin_data:
                for c in coin_data:
                    if c.get("symbol", "").lower() == q_lower:
                        coin = c; break
                    if c.get("id", "").lower() == q_lower:
                        coin = c; break
                if not coin:
                    coin = coin_data[0]
            if not coin:
                best, all_pairs = get_best_pair_for_token(q)
                if best:
                    result = _pair_to_token(best, q)
                    result["all_pairs"] = all_pairs[:10]
                    return result
                return None
            coin_id = coin["id"]
            try:
                detail = fetch_coin_detail(coin_id)
            except Exception:
                detail = None
        if not detail:
            best, all_pairs = get_best_pair_for_token(q)
            if best:
                result = _pair_to_token(best, q)
                result["all_pairs"] = all_pairs[:10]
                return result
            return None
        md = detail.get("market_data", {})
        result = {
            "slug": detail["id"],
            "symbol": detail.get("symbol", q_lower).upper(),
            "name": detail.get("name", q_lower),
            "source": "coingecko",
            "token_key": f"coingecko:{detail['id']}",
            "current_price": (md.get("current_price") or {}).get("usd"),
            "price_change_1h": (md.get("price_change_percentage_1h_in_currency") or {}).get("usd"),
            "price_change_24h": md.get("price_change_percentage_24h"),
            "price_change_7d": md.get("price_change_percentage_7d"),
            "volume_24h": (md.get("total_volume") or {}).get("usd"),
            "market_cap": (md.get("market_cap") or {}).get("usd"),
            "fdv": (md.get("fully_diluted_valuation") or {}).get("usd"),
        }
        try:
            csym = (detail.get("symbol") or q_lower).upper()
            pairs = search_pairs(csym)
            best = get_best_pair(pairs, csym)
            if best:
                result["liquidity_usd"] = best.get("liquidity_usd")
                result["chain_id"] = best.get("chain_id")
                result["dex_id"] = best.get("dex_id")
                result["dex_url"] = best.get("url")
                result["pair_address"] = best.get("pair_address")
                result["contract_address"] = best.get("base_address")
                result["current_price"] = result["current_price"] or best.get("price_usd")
                result["price_change_1h"] = result["price_change_1h"] or best.get("price_change_h1")
                result["volume_24h"] = result["volume_24h"] or best.get("volume_h24")
        except Exception:
            pass
        return result

    best, all_pairs = get_best_pair_for_token(q)
    if best:
        result = _pair_to_token(best, q)
        result["all_pairs"] = all_pairs[:10]
        return result

    return None


def resolve_token_debug(query):
    q = query.strip()
    q_lower = q.lower()
    family = detect_address_family(q)
    result = {
        "input": q,
        "family": family,
        "resolver_used": None,
        "matches": [],
        "selected": None,
    }
    if family in ("evm_contract", "solana_address", "tron_address", "possible_contract_or_token_address"):
        best, all_pairs = get_best_pair_for_token(q)
        result["resolver_used"] = "dexscreener_search"
        result["matches"] = [_pair_to_token(p, q) for p in all_pairs[:5]]
        if best:
            result["selected"] = _pair_to_token(best, q)
            result["selected"]["all_pairs_count"] = len(all_pairs)
        return result
    if family in ("coingecko_id_or_slug", "symbol_or_name"):
        detail = None
        try:
            detail = fetch_coin_detail(q_lower)
        except Exception:
            pass
        if detail and detail.get("id"):
            result["resolver_used"] = "coingecko_id"
            result["selected"] = {"symbol": detail.get("symbol","?").upper(), "name": detail.get("name",""), "id": detail["id"]}
            return result
        coin_data = search_coins(q_lower)
        if coin_data:
            result["resolver_used"] = "coingecko_search"
            result["matches"] = [{"symbol": c.get("symbol","?").upper(), "name": c.get("name",""), "id": c["id"]} for c in coin_data[:5]]
            return result
        best, all_pairs = get_best_pair_for_token(q)
        if best:
            result["resolver_used"] = "dexscreener_fallback"
            result["matches"] = [_pair_to_token(p, q) for p in all_pairs[:5]]
            result["selected"] = _pair_to_token(best, q)
            return result
    best, all_pairs = get_best_pair_for_token(q)
    if best:
        result["resolver_used"] = "dexscreener_last_resort"
        result["selected"] = _pair_to_token(best, q)
        result["matches_count"] = len(all_pairs)
        return result
    result["resolver_used"] = "none"
    return result


def _pair_to_token(pair, query=""):
    return {
        "slug": pair.get("base_address") or pair.get("pair_address") or query,
        "symbol": (pair.get("base_symbol") or "?").upper(),
        "name": pair.get("base_name") or (pair.get("base_symbol") or "?"),
        "source": "dexscreener",
        "token_key": portfolio_db._build_token_key("dexscreener", pair.get("chain_id","?"), pair.get("base_address","")),
        "chain_id": pair.get("chain_id"),
        "dex_id": pair.get("dex_id"),
        "contract_address": pair.get("base_address"),
        "pair_address": pair.get("pair_address"),
        "dex_url": pair.get("url"),
        "current_price": pair.get("price_usd"),
        "price_native": pair.get("price_native"),
        "liquidity_usd": pair.get("liquidity_usd"),
        "liquidity_base": pair.get("liquidity_base"),
        "liquidity_quote": pair.get("liquidity_quote"),
        "fdv": pair.get("fdv"),
        "market_cap": pair.get("market_cap"),
        "volume_24h": pair.get("volume_h24"),
        "volume_1h": pair.get("volume_h1"),
        "volume_6h": pair.get("volume_h6"),
        "volume_m5": pair.get("volume_m5"),
        "price_change_m5": pair.get("price_change_m5"),
        "price_change_1h": pair.get("price_change_h1"),
        "price_change_6h": pair.get("price_change_h6"),
        "price_change_24h": pair.get("price_change_h24"),
        "txns_m5": pair.get("txns_m5"),
        "txns_h1": pair.get("txns_h1"),
        "txns_h6": pair.get("txns_h6"),
        "txns_h24": pair.get("txns_h24"),
        "pair_created_at": pair.get("pair_created_at"),
    }


def build_token_card(sym, name, price, vol, mcap, liq, fdv, ch1h, ch24h, ch7d, slug, pair_addr, chain_id, dex_id, contract_addr, ch5m, ch6h):
    lines = [
        f"\U0001fa99 <b>{sym} \u2014 {name}</b>\n",
    ]
    if contract_addr:
        short = f"{contract_addr[:12]}...{contract_addr[-6:]}" if len(contract_addr) > 20 else contract_addr
        lines.append(f"<code>{short}</code>\n")
    lines.append("<b>Market</b>")
    lines.append(f"Price: {format_usd(price)}")
    if vol:
        lines.append(f"Volume 24h: {format_usd(vol)}")
    if mcap:
        lines.append(f"Market Cap: {format_usd(mcap)}")
    elif fdv:
        lines.append(f"FDV: {format_usd(fdv)}")
    if liq:
        lines.append(f"Liquidity: {format_usd(liq)}")
    if chain_id:
        lines.append(f"\n<b>DEX</b>")
        lines.append(f"Chain: {chain_id}")
        if dex_id:
            lines.append(f"DEX: {dex_id}")
        if pair_addr:
            lines.append(f"Pair: <code>{pair_addr[:12]}...{pair_addr[-6:]}</code>")

    changes = []
    if ch5m is not None:
        e = "\U0001f7e2" if ch5m >= 0 else "\U0001f534"
        changes.append(f"5m: {e} {ch5m:+.2f}%")
    if ch1h is not None:
        e = "\U0001f7e2" if ch1h >= 0 else "\U0001f534"
        changes.append(f"1h: {e} {ch1h:+.2f}%")
    if ch6h is not None:
        e = "\U0001f7e2" if ch6h >= 0 else "\U0001f534"
        changes.append(f"6h: {e} {ch6h:+.2f}%")
    if ch24h is not None:
        e = "\U0001f7e2" if ch24h >= 0 else "\U0001f534"
        changes.append(f"24h: {e} {ch24h:+.2f}%")
    if ch7d is not None:
        e = "\U0001f7e2" if ch7d >= 0 else "\U0001f534"
        changes.append(f"7d: {e} {ch7d:+.2f}%")
    if changes:
        lines.append("")
        lines.append("<b>Change</b>")
        lines.append(" | ".join(changes))

    pos = portfolio_db.get_position(symbol=sym) if sym else None
    cash = portfolio_db.get_cash_balance()
    lines.append("")
    lines.append("<b>Portfolio</b>")
    if pos and pos["quantity"] > 0:
        qty = pos["quantity"]
        avg = pos["avg_entry_price"]
        val = qty * price if price else 0
        lines.append(f"Balance: {qty:.4f} {sym}")
        lines.append(f"Value: {format_usd(val)}")
        lines.append(f"Avg Entry: {format_usd(avg)}")
        if price and avg > 0:
            upnl = (price - avg) * qty
            e = "\U0001f7e2" if upnl >= 0 else "\U0001f534"
            lines.append(f"Unrealized P&L: {e} {format_usd(upnl)}")
    else:
        lines.append("No position")
    lines.append(f"Cash: {format_usd(cash)}")
    lines.append("")
    lines.append(f"\U0001f552 {datetime.utcnow().strftime('%H:%M UTC')}")
    return "\n".join(lines)


def token_card_from_resolved(token, chat_id):
    return build_token_card(
        token.get("symbol", "?"), token.get("name", ""),
        token.get("current_price"), token.get("volume_24h"),
        token.get("market_cap"), token.get("liquidity_usd"),
        token.get("fdv"),
        token.get("price_change_1h"), token.get("price_change_24h"),
        token.get("price_change_7d"),
        token.get("slug", ""), token.get("pair_address", ""),
        token.get("chain_id", ""), token.get("dex_id", ""),
        token.get("contract_address", ""),
        token.get("price_change_m5"), token.get("price_change_6h"),
    )


def buy_flow_start_text():
    return (
        "\u2795 <b>Buy Token</b>\n\n"
        "Send token ID, symbol, name or contract address.\n\n"
        "Examples:\n"
        "\u2022 bittensor\n"
        "\u2022 TAO\n"
        "\u2022 0x...\n"
        "\u2022 DRLNhjM7jusYFPF1qade1dBD1qhgds7oAfdKs51Vpump"
    )


def buy_flow_start_buttons():
    return {
        "inline_keyboard": [
            [{"text": "\U0001f50e Search Token", "callback_data": "buy:search"}],
            [{"text": "\u2b50 Watchlist", "callback_data": "buy:watchlist"}],
            [{"text": "\U0001f7e2 Early Signals", "callback_data": "buy:early"}],
            [{"text": "\U0001f525 Trends", "callback_data": "buy:trends"}],
            [{"text": "\u274c Close", "callback_data": "flow:cancel"}],
        ]
    }


def buy_token_menu_buttons(slug, symbol, token_key=""):
    amounts = config.QUICK_BUY_AMOUNTS
    kb = []
    row = []
    for a in amounts:
        row.append({"text": f"Buy ${a}", "callback_data": f"buy:quick:{slug}:{symbol}:{a}"})
        if len(row) >= 2:
            kb.append(row); row = []
    if row:
        kb.append(row)
    kb.append([{"text": "\U0001f4b5 Buy Custom Amount", "callback_data": f"buy:custom:{slug}:{symbol}"}])
    kb.append([{"text": "\u270f\ufe0f Edit Price", "callback_data": f"buy:editprice:{slug}:{symbol}"}])
    kb.append([
        {"text": "\U0001f4ca Position", "callback_data": f"buy:pos:{slug}:{symbol}"},
        {"text": "\u2b50 Watchlist", "callback_data": f"watchlist:add:{slug}"},
    ])
    kb.append([
        {"text": "\U0001f504 Refresh", "callback_data": f"buy:refresh:{slug}:{symbol}"},
        {"text": "\u274c Close", "callback_data": "flow:cancel"},
    ])
    return {"inline_keyboard": kb}


def buy_price_buttons(slug, symbol):
    return {
        "inline_keyboard": [
            [{"text": "\u2705 Use Current Price", "callback_data": f"buy:usecurrent:{slug}:{symbol}"}],
            [{"text": "\u270f\ufe0f Enter Custom Price", "callback_data": f"buy:askprice:{slug}:{symbol}"}],
            [{"text": "\u274c Cancel", "callback_data": "flow:cancel"}],
        ]
    }


def buy_confirm_buttons(slug, symbol):
    return {
        "inline_keyboard": [
            [{"text": "\u2705 Confirm Buy", "callback_data": f"buy:confirm:{slug}:{symbol}"}],
            [{"text": "\u270f\ufe0f Edit Amount", "callback_data": f"buy:editamt:{slug}:{symbol}"}],
            [{"text": "\u270f\ufe0f Edit Price", "callback_data": f"buy:editprice:{slug}:{symbol}"}],
            [{"text": "\u270f\ufe0f Add/Edit Fee", "callback_data": f"buy:editfee:{slug}:{symbol}"}],
            [{"text": "\u274c Cancel", "callback_data": "flow:cancel"}],
        ]
    }


def build_buy_confirm_text(slug, symbol, data):
    qty = data.get("quantity", 0)
    price = data.get("price", 0)
    fee = data.get("fee", config.DEFAULT_FEE_USD)
    amount_usd = data.get("amount_usd", qty * price)
    total = amount_usd + fee
    name = data.get("name", symbol)
    contract = data.get("contract_address", "")

    pos = portfolio_db.get_position(symbol=symbol, token_key=data.get("token_key"))
    new_qty = (pos["quantity"] if pos else 0) + qty
    old_cost = pos["cost_basis_usd"] if pos else 0
    new_avg = (old_cost + total) / new_qty if new_qty > 0 else price

    lines = [
        f"\u2705 <b>Confirm Buy</b>\n\n"
        f"Token: {symbol} \u2014 {name}\n"
    ]
    if contract:
        short = f"{contract[:12]}...{contract[-6:]}" if len(contract) > 20 else contract
        lines.append(f"Contract: <code>{short}</code>\n")
    lines.append(f"Amount: {format_usd(amount_usd)}")
    lines.append(f"Price: {format_usd(price)}")
    lines.append(f"Estimated Qty: {qty:.6f} {symbol}")
    lines.append(f"Fee: {format_usd(fee)}\n")
    lines.append(f"<b>New Position</b>")
    lines.append(f"Total Qty: {new_qty:.6f}")
    lines.append(f"Avg Entry: {format_usd(new_avg)}")
    lines.append(f"Cost Basis: {format_usd(old_cost + total)}\n")
    lines.append(f"Confirm?")
    return "\n".join(lines)


def execute_buy(slug, symbol, data):
    qty = data.get("quantity", 0)
    price = data.get("price", 0)
    fee = data.get("fee", config.DEFAULT_FEE_USD)
    amount_usd = data.get("amount_usd", qty * price)
    total = amount_usd + fee
    coin_id = slug
    token_key = data.get("token_key", "")
    source = data.get("source", "dexscreener")
    chain_id = data.get("chain_id", "")
    contract_address = data.get("contract_address", "")
    pair_address = data.get("pair_address", "")
    dex_id = data.get("dex_id", "")
    is_test = 1 if config.TEST_MODE else 0

    pos = portfolio_db.get_position(symbol=symbol, token_key=token_key)
    if not pos:
        pos = portfolio_db.add_position(
            coin_id, symbol, data.get("name", symbol),
            token_key=token_key, source=source, chain_id=chain_id,
            contract_address=contract_address, pair_address=pair_address,
            dex_id=dex_id, is_test=is_test
        )

    updated = portfolio_db.update_position_after_buy(symbol, qty, price, fee, token_key=token_key, is_test=is_test)
    portfolio_db.add_transaction(
        coin_id, symbol, "buy", qty, price, total,
        fee_usd=fee, notes="Via buy flow",
        token_key=token_key, source=source, chain_id=chain_id,
        contract_address=contract_address, pair_address=pair_address,
        dex_id=dex_id, is_test=is_test
    )
    portfolio_db.add_cash_movement("buy", -total,
                                   f"Compra {qty:.6f} {symbol} @ {format_usd(price)}", is_test)

    session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)

    test_tag = " [TEST]" if is_test else ""
    return (
        f"\u2705 <b>Buy executed{test_tag}</b>\n\n"
        f"Token: {symbol}\n"
        f"Qty: {qty:.6f} {symbol}\n"
        f"Price: {format_usd(price)}\n"
        f"Fee: {format_usd(fee)}\n"
        f"Total: {format_usd(total)}\n\n"
        f"New qty: {updated['quantity']:.6f}\n"
        f"Avg entry: {format_usd(updated['avg_entry_price'])}"
    )


def sell_flow_start_text():
    return "\u2796 <b>Sell Token</b>\n\nSelect a position to sell:"


def sell_flow_position_buttons():
    is_test = 1 if config.TEST_MODE else 0
    positions = portfolio_db.get_active_positions(is_test=is_test)
    kb = []
    for p in positions:
        sym = p["symbol"]
        slug = p["token_key"] or p["coin_id"] or sym.lower()
        tk = p.get("token_key", "")
        kb.append([{"text": sym, "callback_data": f"sell:select:{slug}:{sym}"}])
    kb.append([{"text": "\u274c Close", "callback_data": "flow:cancel"}])
    return {"inline_keyboard": kb}


def sell_flow_position_text(slug, symbol):
    is_test = 1 if config.TEST_MODE else 0
    pos = portfolio_db.get_position(symbol=symbol, token_key=slug, is_test=is_test)
    if not pos:
        return None, None, None

    price = None
    try:
        detail = fetch_coin_detail(slug)
        md = detail.get("market_data", {})
        price = (md.get("current_price") or {}).get("usd")
    except Exception:
        try:
            pairs = search_pairs(symbol)
            best = get_best_pair(pairs, symbol)
            if best:
                price = best.get("price_usd")
        except Exception:
            pass

    qty = pos["quantity"]
    avg = pos["avg_entry_price"]
    val = qty * price if price else 0
    upnl = (price - avg) * qty if price and avg > 0 else 0
    upnl_pct = ((price - avg) / avg) * 100 if price and avg > 0 else 0
    rpnl = pos.get("realized_pnl_usd", 0) or 0

    lines = [f"\u2796 <b>Sell {symbol}</b>\n"]
    lines.append(f"Available: {qty:.4f} {symbol}")
    if price:
        lines.append(f"Current Price: {format_usd(price)}")
        lines.append(f"Current Value: {format_usd(val)}")
    lines.append(f"Avg Entry: {format_usd(avg)}")
    if price and avg > 0:
        e = "\U0001f7e2" if upnl >= 0 else "\U0001f534"
        lines.append(f"Unrealized P&L: {e} {format_usd(upnl)} ({upnl_pct:+.2f}%)")
    if rpnl:
        e = "\U0001f7e2" if rpnl >= 0 else "\U0001f534"
        lines.append(f"Realized P&L: {e} {format_usd(rpnl)}")
    lines.append(f"\nSelect amount to sell:")

    return "\n".join(lines), price, pos.get("token_key", slug)


def sell_pct_buttons(slug, symbol):
    return {
        "inline_keyboard": [
            [{"text": "Sell 25%", "callback_data": f"sell:pct:{slug}:{symbol}:25"},
             {"text": "Sell 50%", "callback_data": f"sell:pct:{slug}:{symbol}:50"}],
            [{"text": "Sell 75%", "callback_data": f"sell:pct:{slug}:{symbol}:75"},
             {"text": "Sell 100%", "callback_data": f"sell:pct:{slug}:{symbol}:100"}],
            [{"text": "\U0001f4b5 Sell Custom Qty", "callback_data": f"sell:custom:{slug}:{symbol}"}],
            [{"text": "\u270f\ufe0f Edit Price", "callback_data": f"sell:editprice:{slug}:{symbol}"}],
            [{"text": "\U0001f504 Refresh", "callback_data": f"sell:refresh:{slug}:{symbol}"},
             {"text": "\u274c Close", "callback_data": "flow:cancel"}],
        ]
    }


def sell_price_buttons(slug, symbol):
    return {
        "inline_keyboard": [
            [{"text": "\u2705 Use Current Price", "callback_data": f"sell:usecurrent:{slug}:{symbol}"}],
            [{"text": "\u270f\ufe0f Enter Custom Price", "callback_data": f"sell:askprice:{slug}:{symbol}"}],
            [{"text": "\u274c Cancel", "callback_data": "flow:cancel"}],
        ]
    }


def sell_confirm_buttons(slug, symbol):
    return {
        "inline_keyboard": [
            [{"text": "\u2705 Confirm Sell", "callback_data": f"sell:confirm:{slug}:{symbol}"}],
            [{"text": "\u270f\ufe0f Edit Qty", "callback_data": f"sell:editqty:{slug}:{symbol}"}],
            [{"text": "\u270f\ufe0f Edit Price", "callback_data": f"sell:editprice:{slug}:{symbol}"}],
            [{"text": "\u270f\ufe0f Add/Edit Fee", "callback_data": f"sell:editfee:{slug}:{symbol}"}],
            [{"text": "\u274c Cancel", "callback_data": "flow:cancel"}],
        ]
    }


def build_sell_confirm_text(slug, symbol, data):
    qty = data.get("quantity", 0)
    price = data.get("price", 0)
    fee = data.get("fee", config.DEFAULT_FEE_USD)
    name = data.get("name", symbol)

    is_test = 1 if config.TEST_MODE else 0
    pos = portfolio_db.get_position(symbol=symbol, token_key=data.get("token_key"), is_test=is_test)
    if not pos:
        return None
    proceeds = qty * price
    cost_removed = pos["avg_entry_price"] * qty
    realized = proceeds - cost_removed - fee
    remaining = pos["quantity"] - qty

    return (
        f"\u2705 <b>Confirm Sell</b>\n\n"
        f"Token: {symbol} \u2014 {name}\n"
        f"Sell Qty: {qty:.6f} {symbol}\n"
        f"Price: {format_usd(price)}\n"
        f"Value: {format_usd(proceeds)}\n"
        f"Fee: {format_usd(fee)}\n\n"
        f"Estimated Realized P&L:\n{format_usd(realized)}\n\n"
        f"Remaining:\n{remaining:.6f} {symbol}\n\n"
        f"Confirm?"
    )


def execute_sell(slug, symbol, data):
    qty = data.get("quantity", 0)
    price = data.get("price", 0)
    fee = data.get("fee", config.DEFAULT_FEE_USD)
    coin_id = slug
    token_key = data.get("token_key", "")
    is_test = 1 if config.TEST_MODE else 0

    result = portfolio_db.update_position_after_sell(symbol, qty, price, fee, token_key=token_key, is_test=is_test)
    if result is None:
        return None
    updated, realized_pnl, proceeds = result
    total_val = qty * price

    portfolio_db.add_transaction(
        coin_id, symbol, "sell", qty, price, total_val,
        fee_usd=fee, realized_pnl_usd=realized_pnl, notes="Via sell flow",
        token_key=token_key, is_test=is_test
    )
    portfolio_db.add_cash_movement("sell", proceeds - fee,
                                   f"Venta {qty:.6f} {symbol} @ {format_usd(price)}", is_test)

    session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)

    test_tag = " [TEST]" if is_test else ""
    pnl_emoji = "\U0001f7e2" if realized_pnl >= 0 else "\U0001f534"
    return (
        f"\u2705 <b>Sell executed{test_tag}</b>\n\n"
        f"Token: {symbol}\n"
        f"Qty sold: {qty:.6f} {symbol}\n"
        f"Price: {format_usd(price)}\n"
        f"Fee: {format_usd(fee)}\n"
        f"Proceeds: {format_usd(total_val)}\n\n"
        f"Realized P&L: {pnl_emoji} {format_usd(realized_pnl)}\n"
        f"Remaining: {updated['quantity']:.6f} {symbol}"
    )


DUMPS_WINDOW_PAGES = {"5m": {"pages": 1}, "15m": {"pages": 1},
                      "1h": {"pages": 1}, "24h": {"pages": 2},
                      "7d": {"pages": 2}}


def get_dumps_from_snapshots(window):
    from .storage import load_snapshots
    from .coingecko_client import fetch_market_coins

    snapshots = load_snapshots()
    if not snapshots:
        return []

    window_sec = {"5m": 300, "15m": 900, "1h": 3600}.get(window, 3600)
    market_data = fetch_market_coins(page=1, per_page=250)
    if not market_data:
        return []

    live_by_id = {}
    for c in market_data:
        live_by_id[c.get("id")] = c

    coins = []
    now = time.time()
    for cid, snap in snapshots.items():
        if not isinstance(snap, list) or len(snap) < 2:
            continue
        live = live_by_id.get(cid)
        if not live:
            continue
        current_px = live.get("current_price")
        if not current_px:
            continue
        target_ts = now - window_sec
        best = None
        for entry in snap:
            diff = abs(entry.get("ts", 0) - target_ts)
            if best is None or diff < best["diff"]:
                best = {"diff": diff, "price": entry.get("price", 0)}
        if best is None or best["price"] == 0:
            continue
        change = ((current_px - best["price"]) / best["price"]) * 100
        if change >= 0:
            continue

        mcap = live.get("market_cap", 0) or 0
        vol = live.get("total_volume", 0) or 0
        sym = (live.get("symbol") or cid[:5]).upper()
        name = live.get("name", sym)

        if sym.lower() in config.STABLECOINS or sym.lower() in config.WRAPPED_EXCLUDED:
            continue
        if cid in config.ALWAYS_EXCLUDED:
            continue
        if mcap < config.DUMPS_MIN_MARKET_CAP_USD:
            continue
        if vol < config.DUMPS_MIN_VOLUME_24H_USD:
            continue

        coins.append({
            "rank": live.get("market_cap_rank"),
            "symbol": sym, "name": name, "slug": cid,
            "current_price": current_px, f"price_change_{window}": change,
            "volume_24h": vol, "market_cap": mcap, "liquidity": live.get("liquidity"),
            "source": "snapshot",
        })

    coins.sort(key=lambda x: x.get(f"price_change_{window}", 0))
    return coins[:config.DUMPS_LIMIT]


def get_top_losers_from_cg(window):
    pages = DUMPS_WINDOW_PAGES.get(window, {}).get("pages", 1)
    field = {"5m": "1h", "15m": "1h", "1h": "1h", "24h": "24h", "7d": "7d"}.get(window, "24h")
    all_coins = []
    for page in range(1, pages + 1):
        data = fetch_market_coins(page=page, per_page=250)
        if not data:
            break
        all_coins.extend(data)
        time.sleep(1.2)

    filtered = []
    for c in all_coins:
        sym = (c.get("symbol") or "").lower()
        if sym in config.STABLECOINS or sym in config.WRAPPED_EXCLUDED:
            continue
        if c.get("id") in config.ALWAYS_EXCLUDED:
            continue
        current_price = c.get("current_price")
        if not current_price:
            continue
        vol = c.get("total_volume") or 0
        if vol < config.DUMPS_MIN_VOLUME_24H_USD:
            continue
        mcap = c.get("market_cap") or 0
        if mcap < config.DUMPS_MIN_MARKET_CAP_USD:
            continue

        ch = c.get(f"price_change_percentage_{field}")
        if ch is None or ch >= 0:
            continue

        filtered.append({
            "rank": c.get("market_cap_rank"),
            "symbol": c.get("symbol", "").upper(),
            "name": c.get("name", ""),
            "slug": c.get("id", ""),
            "current_price": current_price,
            f"price_change_{window}": ch,
            "volume_24h": vol,
            "market_cap": mcap,
            "source": "coingecko",
        })

    filtered.sort(key=lambda x: x.get(f"price_change_{window}", 0))
    return filtered[:config.DUMPS_LIMIT]


def get_dumps_data(window):
    if window in ("24h", "7d"):
        return get_top_losers_from_cg(window)
    from .storage import load_snapshots
    snapshots = load_snapshots()
    if not snapshots:
        return get_top_losers_from_cg(window)
    return get_dumps_from_snapshots(window)


def build_dumps_text(coins, window):
    if not coins:
        return f"\u2139\ufe0f No hay datos para {window}. Intenta con otra ventana."

    window_labels = {"5m": "5m", "15m": "15m", "1h": "1h", "24h": "24h", "7d": "7d"}
    now = datetime.utcnow().strftime("%I:%M %p").lstrip("0")
    lines = [
        f"\U0001f4c9 <b>Top Losers</b>\n",
        f"Window: {window_labels.get(window, window)}",
        f"Min Volume: {format_usd(config.DUMPS_MIN_VOLUME_24H_USD)}",
        f"Updated: {now}\n",
    ]

    for i, c in enumerate(coins, 1):
        sym = c.get("symbol", "?")
        name = c.get("name", sym)
        price = c.get("current_price")
        drop = c.get(f"price_change_{window}")
        vol = c.get("volume_24h")
        rank = c.get("rank")
        slug = c.get("slug", "")

        rank_str = f"#{rank}" if rank else ""
        drop_str = f"{drop:.1f}%" if drop is not None else "N/A"

        lines.append(f"{i}. <b>{sym} \u2014 {name}</b>")
        if rank_str:
            lines.append(f"   Rank: {rank_str}")
        lines.append(f"   Price: {format_usd(price)}")
        if vol:
            lines.append(f"   Volume: {format_usd(vol)}")
        lines.append(f"   {window}: {drop_str}")
        lines.append("")

    return "\n".join(lines)


def build_dumps_buttons(coins, window):
    windows = ["1h", "24h", "7d", "5m", "15m"]
    kb = []
    row = []
    for w in windows:
        marker = "\u25c9 " if w == window else ""
        row.append({"text": f"{marker}{w}",
                     "callback_data": f"dumps:window:{w}"})
        if len(row) >= 3:
            kb.append(row); row = []
    if row:
        kb.append(row)

    if coins:
        num_row = []
        for i, c in enumerate(coins[:5], 1):
            slug = c.get("slug", "")
            sym = c.get("symbol", "?")
            num_row.append({"text": str(i), "callback_data": f"dumps:open:{i}"})
        kb.append(num_row)

    kb.append([
        {"text": "\U0001f504 Refresh", "callback_data": "dumps:refresh"},
        {"text": "\u274c Close", "callback_data": "dumps:close"},
    ])
    return {"inline_keyboard": kb}


def build_dumps_token_menu(slug, symbol):
    token = resolve_token(slug)
    if not token:
        token = {"slug": slug, "symbol": symbol, "name": symbol}
    text = token_card_from_resolved(token, config.TELEGRAM_CHAT_ID)
    amounts = config.QUICK_BUY_AMOUNTS
    kb = []
    row = []
    for a in amounts:
        row.append({"text": f"Buy ${a}", "callback_data": f"buy:quick:{slug}:{symbol}:{a}"})
        if len(row) >= 2:
            kb.append(row); row = []
    if row:
        kb.append(row)
    kb.append([{"text": "\U0001f4b5 Buy Custom Amount", "callback_data": f"buy:custom:{slug}:{symbol}"}])
    kb.append([{"text": "\u2796 Sell", "callback_data": f"sell:select:{slug}:{symbol}"}])
    kb.append([
        {"text": "\U0001f4ca Position", "callback_data": f"dumps:pos:{slug}:{symbol}"},
        {"text": "\u2b50 Watchlist", "callback_data": f"watchlist:add:{slug}"},
    ])
    kb.append([
        {"text": "\U0001f50e Research", "callback_data": f"dumps:research:{slug}:{symbol}"},
        {"text": "\U0001f504 Refresh", "callback_data": f"dumps:tokenrefresh:{slug}:{symbol}"},
    ])
    kb.append([{"text": "\u2b05 Back to Dumps", "callback_data": "dumps:back"}])
    return text, {"inline_keyboard": kb}


def build_position_view(sym, token_data):
    pos = portfolio_db.get_position(symbol=sym)
    if not pos:
        return "\u274c Token no esta en tu portafolio.", None

    price = token_data.get("current_price")
    qty = pos["quantity"]
    avg = pos["avg_entry_price"]
    cost = pos["cost_basis_usd"]
    rpnl = pos.get("realized_pnl_usd", 0) or 0
    val = qty * price if price else 0
    upnl = (price - avg) * qty if price and avg > 0 else 0
    upnl_pct = ((price - avg) / avg) * 100 if price and avg > 0 else 0

    lines = [
        f"\U0001f4ca <b>{sym} Position</b>\n",
        f"Qty: {qty:.4f} {sym}",
        f"Avg Entry: {format_usd(avg)}",
        f"Cost Basis: {format_usd(cost)}",
    ]
    if price:
        lines.append(f"Current Price: {format_usd(price)}")
        lines.append(f"Current Value: {format_usd(val)}")
    lines.append("")
    ch1h = token_data.get("price_change_1h")
    ch24h = token_data.get("price_change_24h")
    ch7d = token_data.get("price_change_7d")
    changes = []
    if ch1h is not None:
        e = "\U0001f7e2" if ch1h >= 0 else "\U0001f534"
        changes.append(f"1h: {e} {ch1h:+.2f}%")
    if ch24h is not None:
        e = "\U0001f7e2" if ch24h >= 0 else "\U0001f534"
        changes.append(f"24h: {e} {ch24h:+.2f}%")
    if ch7d is not None:
        e = "\U0001f7e2" if ch7d >= 0 else "\U0001f534"
        changes.append(f"7d: {e} {ch7d:+.2f}%")
    if changes:
        lines.append("<b>Change</b>")
        lines.append(" | ".join(changes))
    lines.append("")
    if upnl != 0:
        e = "\U0001f7e2" if upnl >= 0 else "\U0001f534"
        lines.append(f"Unrealized P&L: {e} {format_usd(upnl)} ({upnl_pct:+.2f}%)")
    if rpnl:
        e = "\U0001f7e2" if rpnl >= 0 else "\U0001f534"
        lines.append(f"Realized P&L: {e} {format_usd(rpnl)}")

    txs = portfolio_db.get_transactions(symbol=sym, limit=3)
    if txs:
        lines.append("")
        lines.append("<b>Last transactions:</b>")
        for t in txs:
            tt = t["type"].replace("_", " ").title()
            lines.append(f"  \u2022 {tt} {t['quantity']:.4f} @ {format_usd(t['price_usd'])}")

    slug = token_data.get("slug", sym.lower())
    buttons = {
        "inline_keyboard": [
            [{"text": "\u2795 Buy More", "callback_data": f"buy:quick:{slug}:{sym}:{config.QUICK_BUY_AMOUNTS[0]}"},
             {"text": "\u2796 Sell", "callback_data": f"sell:select:{slug}:{sym}"}],
            [{"text": "\U0001f4cb Transactions", "callback_data": f"pos:tx:{sym}"},
             {"text": "\U0001f504 Refresh", "callback_data": f"buy:refresh:{slug}:{sym}"}],
        ]
    }
    return "\n".join(lines), buttons


def build_research_view(sym, token_data):
    slug = token_data.get("slug", sym.lower())
    name = token_data.get("name", sym)
    chain_id = token_data.get("chain_id", "")
    liq = token_data.get("liquidity_usd")
    vol = token_data.get("volume_24h")
    score = token_data.get("social_score")

    lines = [
        f"\U0001f50e <b>Research {sym} \u2014 {name}</b>\n",
        "<b>Links:</b>",
        f"\u2022 <a href='https://www.coingecko.com/en/coins/{slug}'>CoinGecko</a>",
        f"\u2022 <a href='https://dexscreener.com/search?q={slug}'>DexScreener</a>",
        f"\u2022 <a href='https://x.com/search?q=%24{sym.upper()}'>X Search</a>",
        f"\u2022 <a href='https://www.reddit.com/search/?q=%24{sym.upper()}+crypto'>Reddit Search</a>",
        "",
        "<b>Checks:</b>",
        f"Liquidity: {format_usd(liq)}" if liq else "Liquidity: N/A",
        f"Volume 24h: {format_usd(vol)}" if vol else "Volume: N/A",
    ]
    if chain_id:
        lines.append(f"Chain: {chain_id}")
    if score:
        lines.append(f"Social Score: {score}/100")

    buttons = {
        "inline_keyboard": [
            [{"text": "\U0001f4a1 CoinGecko", "url": f"https://www.coingecko.com/en/coins/{slug}"},
             {"text": "\U0001f4c8 DexScreener", "url": f"https://dexscreener.com/search?q={slug}"}],
            [{"text": "\U0001f30d X Search", "url": f"https://x.com/search?q=%24{sym.upper()}"},
             {"text": "\U0001f4dd Reddit", "url": f"https://www.reddit.com/search/?q=%24{sym.upper()}+crypto"}],
            [{"text": "\u2b05 Back", "callback_data": f"dumps:back"}],
        ]
    }
    return "\n".join(lines), buttons


def build_token_menu_text(token, chat_id):
    return token_card_from_resolved(token, chat_id)


def build_token_menu_buttons(slug, symbol):
    return buy_token_menu_buttons(slug, symbol)


def build_quick_buy_buttons(slug, symbol):
    return buy_token_menu_buttons(slug, symbol)


def build_confirm_buy_buttons(slug, symbol):
    return buy_confirm_buttons(slug, symbol)


def build_sell_pct_buttons(slug, symbol):
    return sell_pct_buttons(slug, symbol)


def build_confirm_sell_buttons(slug, symbol):
    return sell_confirm_buttons(slug, symbol)


def add_token_buttons_to_signal_buttons(buttons, slug, symbol):
    buttons["inline_keyboard"].insert(1, [
        {"text": "\u2795 Buy", "callback_data": f"buy:quick:{slug}:{symbol}:{config.QUICK_BUY_AMOUNTS[0]}"},
        {"text": "\u2796 Sell", "callback_data": f"sell:select:{slug}:{symbol}"},
        {"text": "\U0001f4ca Pos", "callback_data": f"buy:pos:{slug}:{symbol}"},
    ])
    buttons["inline_keyboard"].insert(2, [
        {"text": "\u2b50 Watchlist", "callback_data": f"watchlist:add:{slug}"},
        {"text": "\U0001f50e Research", "callback_data": f"dumps:research:{slug}:{symbol}"},
        {"text": "\U0001f504 Refresh", "callback_data": f"buy:refresh:{slug}:{symbol}"},
    ])
    buttons["inline_keyboard"].append([
        {"text": "\U0001fa99 Token Menu", "callback_data": f"buy:quick:{slug}:{symbol}:{config.QUICK_BUY_AMOUNTS[0]}"},
    ])
    return buttons
