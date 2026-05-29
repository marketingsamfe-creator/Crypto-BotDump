import re
import time
from datetime import datetime
from . import config, portfolio_db
from .logger import logger
from .coingecko_client import fetch_coin_detail, fetch_market_coins, search_coins
from .social.dex_client import search_pairs, extract_market_data, get_best_pair
from .formatter import format_usd, _fmt_change
from . import session as session_mgr

SOLANA_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
EVM_ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def detect_input_type(query):
    q = query.strip()
    if SOLANA_ADDR_RE.match(q) and len(q) > 30:
        return "solana_contract"
    if EVM_ADDR_RE.match(q):
        return "evm_contract"
    if len(q) <= 12 and q.isalnum() and q.isascii():
        return "symbol_or_id"
    return "name_search"


def resolve_token(query):
    q = query.strip()
    inp_type = detect_input_type(q)

    if inp_type in ("solana_contract", "evm_contract"):
        pairs = search_pairs(q)
        if pairs:
            best = get_best_pair(pairs, q[:4])
            if best:
                dex = extract_market_data(best)
                base = best.get("baseToken", {})
                symbol = (base.get("symbol") or q[:4]).upper()
                name = base.get("name") or symbol
                slug = dex.get("pair_address", q)
                return {
                    "slug": slug,
                    "symbol": symbol,
                    "name": name,
                    "source": "dexscreener",
                    "current_price": dex.get("price"),
                    "price_change_1h": dex.get("price_change_1h"),
                    "price_change_24h": dex.get("price_change_24h"),
                    "volume_24h": dex.get("volume_24h"),
                    "liquidity": dex.get("liquidity"),
                    "fdv": dex.get("fdv"),
                    "chain": dex.get("chain"),
                    "dex_url": dex.get("dex_url"),
                    "pair_address": dex.get("pair_address"),
                }

    if inp_type in ("symbol_or_id", "name_search"):
        coin_data = search_coins(q.lower())
        if coin_data:
            coin = coin_data[0]
            result = {
                "slug": coin["id"],
                "symbol": coin["symbol"].upper(),
                "name": coin["name"],
                "source": "coingecko",
            }
            try:
                detail = fetch_coin_detail(coin["id"])
                md = detail.get("market_data", {})
                result["current_price"] = (md.get("current_price") or {}).get("usd")
                result["price_change_1h"] = (md.get("price_change_percentage_1h_in_currency") or {}).get("usd")
                result["price_change_24h"] = md.get("price_change_percentage_24h")
                result["price_change_7d"] = md.get("price_change_percentage_7d")
                result["volume_24h"] = (md.get("total_volume") or {}).get("usd")
                result["market_cap"] = (md.get("market_cap") or {}).get("usd")
                result["fdv"] = (md.get("fully_diluted_valuation") or {}).get("usd")
                result["name"] = detail.get("name", coin["name"])
            except Exception:
                pass
            try:
                pair = search_pairs(coin["symbol"])
                best = get_best_pair(pair, coin["symbol"])
                if best:
                    dex = extract_market_data(best)
                    result["liquidity"] = dex.get("liquidity")
                    result["chain"] = dex.get("chain")
                    result["dex_url"] = dex.get("dex_url")
                    result["pair_address"] = dex.get("pair_address")
                    result["current_price"] = result["current_price"] or dex.get("price")
                    result["price_change_1h"] = result["price_change_1h"] or dex.get("price_change_1h")
                    result["price_change_24h"] = result["price_change_24h"] or dex.get("price_change_24h")
                    result["volume_24h"] = result["volume_24h"] or dex.get("volume_24h")
            except Exception:
                pass
            return result

    return None


def build_token_menu_text(token, chat_id):
    sym = token.get("symbol", "?")
    name = token.get("name", "")
    price = token.get("current_price")
    liq = token.get("liquidity")
    mcap = token.get("market_cap")
    vol = token.get("volume_24h")
    fdv = token.get("fdv")
    ch1h = token.get("price_change_1h")
    ch24h = token.get("price_change_24h")
    ch7d = token.get("price_change_7d")
    slug = token.get("slug", "")
    pair_addr = token.get("pair_address", "")
    chain = token.get("chain", "")

    pos = portfolio_db.get_position(sym) if sym else None
    cash = portfolio_db.get_cash_balance()

    lines = [
        f"\U0001fa99 <b>{sym} — {name}</b>",
        "",
    ]
    if pair_addr:
        lines.append(f"Contract/ID:\n<code>{pair_addr[:20]}...{pair_addr[-8:]}</code>\n")
    elif slug:
        lines.append(f"ID: <code>{slug}</code>\n")

    lines.append("<b>Market</b>")
    lines.append(f"Price: {format_usd(price)}")
    if liq:
        lines.append(f"Liquidity: {format_usd(liq)}")
    if mcap:
        lines.append(f"Market Cap: {format_usd(mcap)}")
    elif fdv:
        lines.append(f"FDV: {format_usd(fdv)}")
    if vol:
        lines.append(f"Volume 24h: {format_usd(vol)}")

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
        lines.append("")
        lines.append("<b>Change</b>")
        lines.append(" | ".join(changes))

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


def build_token_menu_buttons(slug, symbol):
    return {
        "inline_keyboard": [
            [
                {"text": "\u2795 Buy", "callback_data": f"t:buy:{slug}:{symbol}"},
                {"text": "\u2796 Sell", "callback_data": f"t:sell:{slug}:{symbol}"},
            ],
            [
                {"text": "\U0001f4ca Position", "callback_data": f"t:pos:{slug}:{symbol}"},
                {"text": "\u2b50 Watchlist", "callback_data": f"watchlist:add:{slug}"},
            ],
            [
                {"text": "\U0001f50e Research", "callback_data": f"t:research:{slug}:{symbol}"},
                {"text": "\U0001f504 Refresh", "callback_data": f"t:refresh:{slug}:{symbol}"},
            ],
            [
                {"text": "\U0001f4a1 CoinGecko",
                 "url": f"https://www.coingecko.com/en/coins/{slug}"},
                {"text": "\U0001f4c8 DexScreener",
                 "url": f"https://dexscreener.com/search?q={slug}"},
            ],
            [
                {"text": "\U0001f30d X Search",
                 "url": f"https://x.com/search?q=%24{symbol}"},
            ],
        ]
    }


def build_quick_buy_buttons(slug, symbol):
    amounts = config.QUICK_BUY_AMOUNTS
    kb = []
    row = []
    for a in amounts:
        row.append({"text": f"Buy ${a}", "callback_data": f"tb:qty:{slug}:{symbol}:{a}"})
        if len(row) >= 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([
        {"text": "\U0001f4b5 Custom Amount", "callback_data": f"tb:custom:{slug}:{symbol}"},
    ])
    kb.append([
        {"text": "\u270f\ufe0f Edit Price", "callback_data": f"tb:editprice:{slug}:{symbol}"},
        {"text": "\u274c Cancel", "callback_data": "flow:cancel"},
    ])
    return {"inline_keyboard": kb}


def build_confirm_buy_buttons(slug, symbol):
    return {
        "inline_keyboard": [
            [{"text": "\u2705 Confirm Buy", "callback_data": f"tb:confirm:{slug}:{symbol}"}],
            [
                {"text": "\u270f\ufe0f Edit Amount", "callback_data": f"tb:editamt:{slug}:{symbol}"},
                {"text": "\u270f\ufe0f Edit Price", "callback_data": f"tb:editprice:{slug}:{symbol}"},
            ],
            [
                {"text": "\u270f\ufe0f Add/Edit Fee", "callback_data": f"tb:editfee:{slug}:{symbol}"},
            ],
            [{"text": "\u274c Cancel", "callback_data": "flow:cancel"}],
        ]
    }


def build_sell_pct_buttons(slug, symbol):
    return {
        "inline_keyboard": [
            [
                {"text": "Sell 25%", "callback_data": f"ts:pct:{slug}:{symbol}:25"},
                {"text": "Sell 50%", "callback_data": f"ts:pct:{slug}:{symbol}:50"},
            ],
            [
                {"text": "Sell 75%", "callback_data": f"ts:pct:{slug}:{symbol}:75"},
                {"text": "Sell 100%", "callback_data": f"ts:pct:{slug}:{symbol}:100"},
            ],
            [
                {"text": "\U0001f4b5 Custom Qty", "callback_data": f"ts:custom:{slug}:{symbol}"},
            ],
            [
                {"text": "\u270f\ufe0f Edit Price", "callback_data": f"ts:editprice:{slug}:{symbol}"},
                {"text": "\u274c Cancel", "callback_data": "flow:cancel"},
            ],
        ]
    }


def build_confirm_sell_buttons(slug, symbol):
    return {
        "inline_keyboard": [
            [{"text": "\u2705 Confirm Sell", "callback_data": f"ts:confirm:{slug}:{symbol}"}],
            [
                {"text": "\u270f\ufe0f Edit Qty", "callback_data": f"ts:editqty:{slug}:{symbol}"},
                {"text": "\u270f\ufe0f Edit Price", "callback_data": f"ts:editprice:{slug}:{symbol}"},
            ],
            [
                {"text": "\u270f\ufe0f Add/Edit Fee", "callback_data": f"ts:editfee:{slug}:{symbol}"},
            ],
            [{"text": "\u274c Cancel", "callback_data": "flow:cancel"}],
        ]
    }


def build_position_view(sym, token_data):
    pos = portfolio_db.get_position(sym)
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

    txs = portfolio_db.get_transactions(sym, limit=3)
    if txs:
        lines.append("")
        lines.append("<b>Last transactions:</b>")
        for t in txs:
            tt = t["type"].replace("_", " ").title()
            lines.append(f"  \u2022 {tt} {t['quantity']:.4f} @ {format_usd(t['price_usd'])}")

    slug = token_data.get("slug", sym.lower())
    buttons = {
        "inline_keyboard": [
            [
                {"text": "\u2795 Buy More", "callback_data": f"t:buy:{slug}:{sym}"},
                {"text": "\u2796 Sell", "callback_data": f"t:sell:{slug}:{sym}"},
            ],
            [
                {"text": "\U0001f4cb Transactions", "callback_data": f"pos:tx:{sym}"},
                {"text": "\U0001f504 Refresh", "callback_data": f"t:refresh:{slug}:{sym}"},
            ],
            [{"text": "\u2b05 Token Menu", "callback_data": f"t:menu:{slug}:{sym}"}],
        ]
    }
    return "\n".join(lines), buttons


def build_research_view(sym, token_data):
    slug = token_data.get("slug", sym.lower())
    name = token_data.get("name", sym)
    chain = token_data.get("chain", "")
    liq = token_data.get("liquidity")
    vol = token_data.get("volume_24h")
    score = token_data.get("social_score")

    lines = [
        f"\U0001f50e <b>Research {sym} — {name}</b>\n",
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
    if chain:
        lines.append(f"Chain: {chain}")
    if score:
        lines.append(f"Social Score: {score}/100")

    buttons = {
        "inline_keyboard": [
            [
                {"text": "\U0001f4a1 CoinGecko",
                 "url": f"https://www.coingecko.com/en/coins/{slug}"},
                {"text": "\U0001f4c8 DexScreener",
                 "url": f"https://dexscreener.com/search?q={slug}"},
            ],
            [
                {"text": "\U0001f30d X Search",
                 "url": f"https://x.com/search?q=%24{sym.upper()}"},
                {"text": "\U0001f4dd Reddit",
                 "url": f"https://www.reddit.com/search/?q=%24{sym.upper()}+crypto"},
            ],
            [{"text": "\u2b05 Token Menu", "callback_data": f"t:menu:{slug}:{sym}"}],
        ]
    }
    return "\n".join(lines), buttons


# ── /dumps ──────────────────────────────────────────────────────────────────

def build_dumps_text(coins, window):
    if not coins:
        return f"\u2139\ufe0f No dumping tokens found in the last {window}."

    window_label = {"5m":"5 min", "15m":"15 min", "1h":"1 hour",
                    "6h":"6 hours", "24h":"24 hours"}.get(window, window)
    lines = [
        f"\U0001f4a5 <b>Top Dumping Tokens ({window_label})</b>\n"
    ]
    for i, c in enumerate(coins, 1):
        sym = c.get("symbol", "?").upper()
        name = c.get("name", sym)
        price = c.get("current_price")
        drop = c.get(f"price_change_{window}")
        vol = c.get("volume_24h")
        liq = c.get("liquidity")
        mcap = c.get("market_cap")
        slug = c.get("slug", "")
        source = c.get("source", "")

        if drop is None and "price_change_percentage_" in c:
            drop = c.get(f"price_change_percentage_{window}")

        if drop is not None and drop >= 0:
            continue

        e = "\U0001f534"
        drop_str = f"<b>{drop:+.1f}%</b>" if drop is not None else "N/A"
        lines.append(
            f"{i}. {e} <b>{sym}</b> — {name}"
        )
        lines.append(f"   Price: {format_usd(price)} | Drop: {drop_str}")
        info_parts = []
        if vol:
            info_parts.append(f"Vol: {format_usd(vol)}")
        if liq:
            info_parts.append(f"Liq: {format_usd(liq)}")
        if mcap:
            info_parts.append(f"MCap: {format_usd(mcap)}")
        if info_parts:
            lines.append("   " + " | ".join(info_parts))
        lines.append("")

    return "\n".join(lines).rstrip()


def build_dumps_buttons(window):
    windows = config.DUMPS_WINDOWS
    kb = []
    row = []
    for w in windows:
        label = f"{' 5m' if w=='5m' else '15m' if w=='15m' else '1h' if w=='1h' else '6h' if w=='6h' else '24h'}"
        marker = "\u25c9 " if w == window else ""
        row.append({"text": f"{marker}{label}",
                     "callback_data": f"dumps:window:{w}"})
        if len(row) >= 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([
        {"text": "\U0001f504 Refresh", "callback_data": "dumps:refresh"},
        {"text": "\u274c Close", "callback_data": "dumps:close"},
    ])
    return {"inline_keyboard": kb}


def get_dumps_data(window):
    from .storage import load_snapshots
    from .coingecko_client import fetch_market_coins

    snapshots = load_snapshots()
    if not snapshots:
        return []

    slugs = list(snapshots.keys())
    market_data = fetch_market_coins(page=1, per_page=250)
    if not market_data:
        return []

    live_by_id = {}
    for c in market_data:
        live_by_id[c.get("id")] = c

    coins = []
    for cid, snap in snapshots.items():
        if not isinstance(snap, list) or len(snap) < 2:
            continue
        live = live_by_id.get(cid)
        if not live:
            continue
        current_px = live.get("current_price")
        if not current_px:
            continue
        old = snap[-2]
        old_px = old.get("price")
        if not old_px or old_px <= 0:
            continue
        change = ((current_px - old_px) / old_px) * 100

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
            "symbol": sym,
            "name": name,
            "slug": cid,
            "current_price": current_px,
            f"price_change_{window}": change,
            "volume_24h": vol,
            "market_cap": mcap,
            "source": "snapshot",
        })

    coins.sort(key=lambda x: x.get(f"price_change_{window}", 0))
    return coins[:config.DUMPS_LIMIT]


def add_token_buttons_to_signal_buttons(buttons, slug, symbol):
    buttons["inline_keyboard"].insert(1, [
        {"text": "\u2795 Buy", "callback_data": f"t:buy:{slug}:{symbol}"},
        {"text": "\u2796 Sell", "callback_data": f"t:sell:{slug}:{symbol}"},
        {"text": "\U0001f4ca Pos", "callback_data": f"t:pos:{slug}:{symbol}"},
    ])
    buttons["inline_keyboard"].insert(2, [
        {"text": "\u2b50 Watchlist", "callback_data": f"watchlist:add:{slug}"},
        {"text": "\U0001f50e Research", "callback_data": f"t:research:{slug}:{symbol}"},
        {"text": "\U0001f504 Refresh", "callback_data": f"t:refresh:{slug}:{symbol}"},
    ])
    buttons["inline_keyboard"].append([
        {"text": "\U0001fa99 Token Menu", "callback_data": f"t:menu:{slug}:{symbol}"},
    ])
    return buttons
