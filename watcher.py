import time
import requests
import json
import os
from datetime import datetime, timedelta

VS_CURRENCY = "usd"
DROP_THRESHOLD_PCT = -25.0
MIN_VOLUME_USD = 500_000
CRASH_INTERVAL = 300
PORTFOLIO_INTERVAL = 3600
POLL_INTERVAL = 30
MAX_PAGES = 2
COOLDOWN_HOURS = 24
COINS_CACHE_FILE = "coins_cache.json"
COINS_CACHE_TTL = 3600

TG_TOKEN = os.environ.get("TG_TOKEN", "8862906082:AAEIXM2RrXwVe_F8kBkFQB9SQIdONjoTmEE")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "1199212284")

ALERTED_FILE = "alerted_coins.json"
HISTORY_FILE = "history.log"
PORTFOLIO_DATA_FILE = "portfolio_data.json"

PORTFOLIO = [
    {"slug": "bittensor",            "symbol": "TAO",   "name": "Bittensor",              "alloc": 35.72},
    {"slug": "aria-ai",              "symbol": "ARIA",  "name": "Aria.AI",                "alloc": 28.92},
    {"slug": "bob-build-on-bitcoin", "symbol": "BOB",   "name": "BOB (Build on Bitcoin)", "alloc": 15.38},
    {"slug": "siren-2",              "symbol": "SIREN", "name": "Siren",                  "alloc": 13.84},
    {"slug": "ordinals",             "symbol": "ORDI",  "name": "ORDI",                   "alloc": 5.97},
    {"slug": "lighter",              "symbol": "LIT",   "name": "Lighter",                "alloc": 0.17},
]

HELP_TEXT = (
    "<b>🤖 Comandos disponibles:</b>\n\n"
    "/portafolio - Resumen del portafolio\n"
    "/search <coin> - Buscar cripto (precio, 1h, 24h, 7d)\n"
    "/precio <coin> - Alias de /search\n"
    "/top - Top 10 criptos por market cap\n"
    "/gainers - Top 10 ganadores 24h\n"
    "/losers - Top 10 perdedores 24h\n"
    "/setentry <SIMB> <precio> - Fijar precio de entrada\n"
    "/setqty <SIMB> <cantidad> - Fijar cantidad\n"
    "/settotal <usd> - Fijar total invertido\n"
    "/status - Estado del bot\n"
    "/help - Esta ayuda\n\n"
    "<b>Ejemplos:</b>\n"
    "/search bitcoin\n"
    "/precio TAO\n"
    "/setentry TAO 450\n"
    "/settotal 10000"
)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})
last_crash_time = 0
last_portfolio_time = 0
last_update_id = 0

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_alerted():
    data = load_json(ALERTED_FILE, {})
    cutoff = datetime.utcnow() - timedelta(hours=COOLDOWN_HOURS)
    return {k: v for k, v in data.items() if datetime.fromisoformat(v) > cutoff}

def load_portfolio_data():
    return load_json(PORTFOLIO_DATA_FILE, {})

def get_coins_cache():
    data = load_json(COINS_CACHE_FILE, {})
    ts = data.get("timestamp", 0)
    if time.time() - ts < COINS_CACHE_TTL:
        return data.get("coins", [])
    try:
        resp = session.get("https://api.coingecko.com/api/v3/coins/list", timeout=30)
        resp.raise_for_status()
        coins = resp.json()
        save_json(COINS_CACHE_FILE, {"timestamp": time.time(), "coins": coins})
        return coins
    except Exception as e:
        log(f"Error fetching coins list: {e}")
        return data.get("coins", [])

def find_coin_slug(query):
    query = query.lower().strip()
    coins = get_coins_cache()
    matches = []
    for coin in coins:
        if coin["symbol"].lower() == query or query in coin["id"] or query in coin["name"].lower():
            matches.append(coin)
            if len(matches) >= 5:
                break
    return matches

def fetch_all_coins():
    coins = []
    for page in range(1, MAX_PAGES + 1):
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": VS_CURRENCY,
            "order": "volume_desc",
            "per_page": 250,
            "page": page,
            "price_change_percentage": "24h",
            "sparkline": "false",
        }
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        coins.extend(data)
        if len(data) < 250:
            break
        time.sleep(1.5)
    return coins

def fetch_coin_detail(slug):
    url = f"https://api.coingecko.com/api/v3/coins/{slug}"
    params = {
        "localization": "false",
        "tickers": "false",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false",
    }
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def fetch_portfolio_prices():
    slugs = ",".join(p["slug"] for p in PORTFOLIO)
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": slugs,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def fetch_top_market():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 10,
        "page": 1,
        "price_change_percentage": "24h",
        "sparkline": "false",
    }
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def fetch_gainers_losers():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 250,
        "page": 1,
        "price_change_percentage": "24h",
        "sparkline": "false",
    }
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    coins = resp.json()
    valid = [c for c in coins if c.get("price_change_percentage_24h") is not None]
    gainers = sorted(valid, key=lambda x: x["price_change_percentage_24h"], reverse=True)[:10]
    losers = sorted(valid, key=lambda x: x["price_change_percentage_24h"])[:10]
    return gainers, losers

def build_portfolio_summary(custom_msg=""):
    prices = fetch_portfolio_prices()
    pdata = load_portfolio_data()
    total_invested = pdata.get("total_invested", 0)
    entry_prices = pdata.get("entry_prices", {})
    quantities = pdata.get("quantities", {})

    if custom_msg:
        lines = [custom_msg + "\n"]
    else:
        lines = ["<b>📊 PORTFOLIO SUMMARY</b>\n"]
    lines.append(f"<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</i>\n")

    total_weighted_change = 0.0
    total_alloc = 0.0
    total_pnl_usd = 0.0
    total_current_value = 0.0

    for coin in PORTFOLIO:
        data = prices.get(coin["slug"])
        if not data:
            continue
        price = data.get("usd", 0)
        change = data.get("usd_24h_change")
        alloc = coin["alloc"]
        sym = coin["symbol"]

        change_str = f"{change:+.2f}%" if change is not None else "N/A"
        entry = entry_prices.get(sym)
        qty = quantities.get(sym, 0)
        pnl_pct = None
        pnl_usd = None

        if entry and entry > 0:
            pnl_pct = ((price - entry) / entry) * 100
        if qty and qty > 0:
            current_val = qty * price
            total_current_value += current_val
            if entry and entry > 0:
                pnl_usd = (price - entry) * qty
                total_pnl_usd += pnl_usd

        emoji = "🟢" if (change is not None and change >= 0) else "🔴"
        line = (
            f"{emoji} <b>{coin['name']}</b> ({sym})\n"
            f"   ${price:,.6f} | 24h: {change_str}\n"
            f"   Alloc: {alloc}%\n"
        )
        if pnl_pct is not None:
            emoji_pnl = "🟢" if pnl_pct >= 0 else "🔴"
            line += f"   P&L: {emoji_pnl} {pnl_pct:+.2f}%"
            if pnl_usd is not None:
                line += f" (${pnl_usd:+,.2f})"
            line += "\n"
        lines.append(line)

        if change is not None:
            total_weighted_change += change * alloc
            total_alloc += alloc

    if total_alloc > 0:
        avg_change = total_weighted_change / total_alloc
        emoji = "🟢" if avg_change >= 0 else "🔴"
        lines.append(f"\n{emoji} <b>Portfolio 24h: {avg_change:+.2f}%</b>")

    if total_pnl_usd != 0:
        emoji_pnl = "🟢" if total_pnl_usd >= 0 else "🔴"
        lines.append(f"{emoji_pnl} <b>P&L No Realizado: ${total_pnl_usd:+,.2f}</b>")
        if total_invested > 0:
            overall_pnl_pct = (total_pnl_usd / total_invested) * 100
            lines.append(f"{emoji_pnl} <b>Rendimiento Total: {overall_pnl_pct:+.2f}%</b>")

    if total_invested > 0 and total_current_value > 0:
        lines.append(f"\n💰 Invertido: ${total_invested:,.2f}")
        lines.append(f"💼 Valor Actual: ${total_current_value:,.2f}")

    return "\n".join(lines)

def handle_command(text, chat_id):
    global last_update_id
    parts = text.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in ("/portafolio", "/portfolio"):
        summary = build_portfolio_summary()
        send_telegram(summary)
        log("Portfolio sent via command")

    elif cmd in ("/search", "/precio", "/buscar"):
        if not args:
            send_telegram("Usa: /search <nombre o símbolo>\nEj: /search bitcoin, /precio TAO")
            return
        query = " ".join(args)
        matches = find_coin_slug(query)
        if not matches:
            send_telegram(f"No se encontró ninguna cripto para '{query}'")
            return
        if len(matches) > 1:
            names = "\n".join(f"• {m['name']} ({m['symbol'].upper()})" for m in matches[:5])
            msg = f"<b>Múltiples resultados para '{query}':</b>\n{names}\n\nSé más específico."
            send_telegram(msg)
            return
        coin = matches[0]
        detail = fetch_coin_detail(coin["id"])
        md = detail.get("market_data", {})
        price = md.get("current_price", {}).get("usd", 0)
        cap = md.get("market_cap", {}).get("usd", 0)
        vol = md.get("total_volume", {}).get("usd", 0)
        rank = md.get("market_cap_rank", "N/A")
        ch1h = md.get("price_change_percentage_1h_in_currency", {}).get("usd")
        ch24h = md.get("price_change_percentage_24h")
        ch7d = md.get("price_change_percentage_7d")

        def fmt(val):
            if val is None:
                return "N/A"
            e = "🟢" if val >= 0 else "🔴"
            return f"{e} {val:+.2f}%"

        msg = (
            f"<b>{coin['name']}</b> ({coin['symbol'].upper()})\n\n"
            f"💰 Price: ${price:,.8f}\n"
            f"🏆 Rank: #{rank}\n"
            f"📊 Market Cap: ${cap:,.0f}\n"
            f"📈 Vol 24h: ${vol:,.0f}\n\n"
            f"1h: {fmt(ch1h)}\n"
            f"24h: {fmt(ch24h)}\n"
            f"7d: {fmt(ch7d)}\n\n"
            f"🔗 <a href='https://www.coingecko.com/en/coins/{coin['id']}'>Ver en CoinGecko</a>"
        )
        send_telegram(msg)

    elif cmd == "/top":
        coins = fetch_top_market()
        lines = ["<b>🏆 Top 10 Criptos por Market Cap</b>\n"]
        for i, c in enumerate(coins, 1):
            ch = c.get("price_change_percentage_24h")
            ch_s = f"{ch:+.2f}%" if ch else "N/A"
            e = "🟢" if (ch and ch >= 0) else "🔴"
            lines.append(f"{i}. {c['name']} ({c['symbol'].upper()})")
            lines.append(f"   ${c['current_price']:,.2f} | {e} {ch_s}")
        send_telegram("\n".join(lines))

    elif cmd == "/gainers":
        gainers, _ = fetch_gainers_losers()
        lines = ["<b>🟢 Top 10 Ganadores 24h</b>\n"]
        for i, c in enumerate(gainers, 1):
            ch = c["price_change_percentage_24h"]
            lines.append(f"{i}. {c['name']} ({c['symbol'].upper()})")
            lines.append(f"   <b>+{ch:.2f}%</b> | ${c['current_price']:,.6f}")
        send_telegram("\n".join(lines))

    elif cmd == "/losers":
        _, losers = fetch_gainers_losers()
        lines = ["<b>🔴 Top 10 Perdedores 24h</b>\n"]
        for i, c in enumerate(losers, 1):
            ch = c["price_change_percentage_24h"]
            lines.append(f"{i}. {c['name']} ({c['symbol'].upper()})")
            lines.append(f"   <b>{ch:.2f}%</b> | ${c['current_price']:,.6f}")
        send_telegram("\n".join(lines))

    elif cmd == "/help":
        send_telegram(HELP_TEXT)

    elif cmd == "/status":
        status = (
            "<b>🤖 Bot Status</b>\n\n"
            f"✅ Crash monitor: cada {CRASH_INTERVAL}s\n"
            f"📊 Portfolio report: cada {PORTFOLIO_INTERVAL}s\n"
            f"🪙 Portafolio: {len(PORTFOLIO)} coins\n"
            f"⏱ Poll interval: {POLL_INTERVAL}s\n"
            f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )
        send_telegram(status)

    elif cmd == "/setentry":
        if len(args) < 2:
            send_telegram("Usa: /setentry <SIMBOLO> <precio>\nEj: /setentry TAO 450")
            return
        sym = args[0].upper()
        try:
            price = float(args[1])
        except:
            send_telegram("Precio inválido.")
            return
        pdata = load_portfolio_data()
        pdata.setdefault("entry_prices", {})[sym] = price
        save_json(PORTFOLIO_DATA_FILE, pdata)
        send_telegram(f"✅ Entry price for {sym} set to ${price:.6f}")

    elif cmd == "/setqty":
        if len(args) < 2:
            send_telegram("Usa: /setqty <SIMBOLO> <cantidad>\nEj: /setqty TAO 5.5")
            return
        sym = args[0].upper()
        try:
            qty = float(args[1])
        except:
            send_telegram("Cantidad inválida.")
            return
        pdata = load_portfolio_data()
        pdata.setdefault("quantities", {})[sym] = qty
        save_json(PORTFOLIO_DATA_FILE, pdata)
        send_telegram(f"✅ Quantity for {sym} set to {qty}")

    elif cmd == "/settotal":
        if not args:
            send_telegram("Usa: /settotal <usd>\nEj: /settotal 10000")
            return
        try:
            total = float(args[0])
        except:
            send_telegram("Valor inválido.")
            return
        pdata = load_portfolio_data()
        pdata["total_invested"] = total
        save_json(PORTFOLIO_DATA_FILE, pdata)
        send_telegram(f"✅ Total invertido fijado en ${total:,.2f}")

    else:
        send_telegram(f"Comando '{cmd}' no reconocido.\nUsa /help para ver comandos disponibles.")

def check_telegram_commands():
    global last_update_id
    url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1, "timeout": 10}
    try:
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("result"):
            return
        for update in data["result"]:
            last_update_id = update["update_id"]
            msg = update.get("message")
            if not msg:
                continue
            text = msg.get("text", "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if chat_id != TG_CHAT_ID:
                continue
            if text.startswith("/"):
                handle_command(text, chat_id)
    except requests.exceptions.ReadTimeout:
        pass
    except Exception as e:
        log(f"Poll error: {e}")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        session.post(url, data={
            "chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"
        }, timeout=15)
    except Exception as e:
        log(f"Send error: {e}")

def log(msg):
    ts = datetime.utcnow().isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass

def main():
    global last_crash_time, last_portfolio_time
    log("Bot started")
    send_telegram(
        "<b>🚀 Crypto Crash Bot v2</b>\n"
        "✅ Crash monitor\n"
        "✅ Portfolio hourly report\n"
        "✅ /portafolio /search /top /gainers /losers"
    )
    last_crash_time = time.time()

    while True:
        now_ts = time.time()
        try:
            check_telegram_commands()
        except Exception as e:
            log(f"Cmd poll error: {e}")

        if now_ts - last_crash_time >= CRASH_INTERVAL:
            last_crash_time = now_ts
            try:
                alerted = load_alerted()
                coins = fetch_all_coins()
                now = datetime.utcnow().isoformat()
                new_alerts = 0

                for coin in coins:
                    slug = coin["id"]
                    name = coin.get("name", slug)
                    symbol = coin.get("symbol", "").upper()
                    change = coin.get("price_change_percentage_24h")
                    price = coin.get("current_price")
                    volume = coin.get("total_volume") or 0
                    rank = coin.get("market_cap_rank")

                    if change is None:
                        continue
                    if change <= DROP_THRESHOLD_PCT and volume >= MIN_VOLUME_USD:
                        if slug in alerted:
                            continue

                        msg = (
                            f"<b>🚨 CRASH DETECTED!</b>\n\n"
                            f"<b>{name}</b> ({symbol})\n"
                            f"💰 ${price:,.8f}\n"
                            f"📉 24h: <b>{change:.2f}%</b>\n"
                            f"📊 Vol: ${volume:,.0f}\n"
                        )
                        if rank:
                            msg += f"🏆 Rank: #{rank}\n"
                        msg += f"\n🔗 <a href='https://www.coingecko.com/en/coins/{slug}'>CoinGecko</a>"
                        send_telegram(msg)
                        alerted[slug] = now
                        new_alerts += 1
                        time.sleep(0.5)

                save_json(ALERTED_FILE, alerted)
                log(f"Crash check: {len(coins)} coins, {new_alerts} alerts")

            except requests.exceptions.HTTPError as e:
                s = e.response.status_code if e.response is not None else "?"
                log(f"HTTP {s}")
                if s == 429:
                    time.sleep(60)
            except Exception as e:
                log(f"Crash error: {e}")

        if now_ts - last_portfolio_time >= PORTFOLIO_INTERVAL:
            last_portfolio_time = now_ts
            try:
                summary = build_portfolio_summary()
                send_telegram(summary)
                log("Hourly portfolio sent")
            except Exception as e:
                log(f"Portfolio error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
