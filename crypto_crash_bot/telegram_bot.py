import time
from datetime import datetime
import requests
from . import config, storage, cache
from . import portfolio_db
from .logger import logger
from .coingecko_client import (
    fetch_coin_detail, fetch_market_coins, search_coins, get_api_stats,
)
from .portfolio import calculate_portfolio
from .alerts import get_recent_alerts
from .formatter import (
    format_portfolio_report, format_dump_alert, format_coin_detail,
    format_top_list, format_gainers_losers, format_status,
    format_help, format_watchlist, format_alerts_list, format_error,
    format_api_error, format_usage_error, format_not_found,
    split_long_message, format_usd,
)
from .social import scanner as social_scanner
from .social.formatter import (
    format_trends_list, format_early_list, format_hype_list,
)

session = requests.Session()
last_update_id = 0

CMD_DEFS = {
    "/portafolio": {"args": [], "desc": "Resumen del portafolio"},
    "/precio": {"args": [("token", True)], "desc": "Precio de un token",
        "examples": ["/precio tao", "/precio bittensor"]},
    "/search": {"args": [("texto", True)], "desc": "Buscar criptomoneda",
        "examples": ["/search tao", "/search bitcoin"]},
    "/top": {"args": [], "desc": "Top 10 criptos"},
    "/gainers": {"args": [], "desc": "Top 10 ganadoras 24h"},
    "/losers": {"args": [], "desc": "Top 10 perdedoras 24h"},
    "/early": {"args": [], "desc": "Señales tempranas"},
    "/trends": {"args": [], "desc": "Tendencias sociales"},
    "/hype": {"args": [], "desc": "Ruido sin volumen"},
    "/alerts": {"args": [], "desc": "Alertas recientes"},
    "/watchlist": {"args": [], "desc": "Tokens vigilados"},
    "/addwatch": {"args": [("coin_id", True)], "desc": "Agregar a watchlist",
        "examples": ["/addwatch bittensor"]},
    "/removewatch": {"args": [("coin_id", True)], "desc": "Quitar de watchlist",
        "examples": ["/removewatch bittensor"]},
    "/setentry": {"args": [("SIMBOLO", True), ("precio", True)], "desc": "Precio de entrada",
        "examples": ["/setentry TAO 350"]},
    "/setqty": {"args": [("SIMBOLO", True), ("cantidad", True)], "desc": "Cantidad del token",
        "examples": ["/setqty TAO 3.5"]},
    "/settotal": {"args": [("usd", True)], "desc": "Total invertido",
        "examples": ["/settotal 10000"]},
    "/setthreshold": {"args": [("coin_id", True), ("window", True), ("percent", True)],
        "desc": "Umbral de alerta",
        "examples": ["/setthreshold bittensor 15m -15"]},
    "/status": {"args": [], "desc": "Estado del bot"},
    "/help": {"args": [], "desc": "Ayuda"},
    "/addtoken": {"args": [("symbol", True), ("coin_id", True)], "desc": "Agregar token al portafolio",
        "examples": ["/addtoken TAO bittensor"]},
    "/removetoken": {"args": [("symbol", True)], "desc": "Archivar token del portafolio",
        "examples": ["/removetoken ARIA"]},
    "/buy": {"args": [("symbol", True), ("quantity", True), ("price_usd", True), ("fee_usd", False)],
        "desc": "Registrar compra", "examples": ["/buy TAO 1.5 390", "/buy TAO 1.5 390 2.50"]},
    "/sell": {"args": [("symbol", True), ("quantity", True), ("price_usd", True), ("fee_usd", False)],
        "desc": "Registrar venta parcial", "examples": ["/sell TAO 1 420", "/sell TAO 1 420 1.50"]},
    "/sellall": {"args": [("symbol", True), ("price_usd", True), ("fee_usd", False)],
        "desc": "Vender posicion completa", "examples": ["/sellall ARIA 0.052", "/sellall ARIA 0.052 3"]},
    "/position": {"args": [("symbol", True)], "desc": "Detalle de posicion",
        "examples": ["/position TAO"]},
    "/transactions": {"args": [("symbol", True)], "desc": "Historial de operaciones",
        "examples": ["/transactions TAO"]},
    "/cash": {"args": [], "desc": "Efectivo disponible"},
    "/setcash": {"args": [("amount_usd", True)], "desc": "Definir efectivo",
        "examples": ["/setcash 1500"]},
    "/deposit": {"args": [("amount_usd", True), ("note", False)], "desc": "Agregar efectivo",
        "examples": ["/deposit 1000 capital inicial"]},
    "/withdraw": {"args": [("amount_usd", True), ("note", False)], "desc": "Retirar efectivo",
        "examples": ["/withdraw 300 retiro parcial"]},
    "/portfolioedit": {"args": [], "desc": "Menu de edicion del portafolio"},
    "/editposition": {"args": [("symbol", True), ("qty", True), ("price", True)],
        "desc": "Editar cantidad y precio de un token",
        "examples": ["/editposition TAO 4.7 362.76"]},
}

BOT_COMMANDS = [
    {"command": "portafolio", "description": "Resumen del portafolio"},
    {"command": "buy", "description": "Comprar token"},
    {"command": "sell", "description": "Vender token"},
    {"command": "sellall", "description": "Vender todo un token"},
    {"command": "position", "description": "Detalle de una posicion"},
    {"command": "transactions", "description": "Historial de operaciones"},
    {"command": "addtoken", "description": "Agregar token al portafolio"},
    {"command": "removetoken", "description": "Archivar token"},
    {"command": "cash", "description": "Efectivo disponible"},
    {"command": "deposit", "description": "Agregar efectivo"},
    {"command": "withdraw", "description": "Retirar efectivo"},
    {"command": "setcash", "description": "Definir efectivo manual"},
    {"command": "portfolioedit", "description": "Menu de edicion del portafolio"},
    {"command": "editposition", "description": "Editar cantidad/precio de un token"},
    {"command": "precio", "description": "Precio de un token"},
    {"command": "search", "description": "Buscar criptomoneda"},
    {"command": "top", "description": "Top criptos"},
    {"command": "gainers", "description": "Ganadoras 24h"},
    {"command": "losers", "description": "Perdedoras 24h"},
    {"command": "trends", "description": "Tendencias sociales"},
    {"command": "early", "description": "Senales tempranas"},
    {"command": "hype", "description": "Ruido sin volumen"},
    {"command": "alerts", "description": "Alertas recientes"},
    {"command": "watchlist", "description": "Watchlist"},
    {"command": "addwatch", "description": "Agregar a watchlist"},
    {"command": "removewatch", "description": "Quitar de watchlist"},
    {"command": "status", "description": "Estado del bot"},
    {"command": "help", "description": "Ayuda"},
]


def _api_url(method):
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"


def send_typing():
    try:
        session.post(_api_url("sendChatAction"), json={
            "chat_id": config.TELEGRAM_CHAT_ID, "action": "typing",
        }, timeout=5)
    except Exception:
        pass


def send_message(text, buttons=None):
    parts = split_long_message(text) if isinstance(text, str) else text
    for part in parts:
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": part,
            "parse_mode": "HTML",
        }
        if buttons:
            payload["reply_markup"] = buttons
        try:
            resp = session.post(_api_url("sendMessage"), json=payload, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
        time.sleep(0.3)


def send_processing():
    send_typing()


def _portfolio_buttons():
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f504 Actualizar", "callback_data": "cmd:portafolio"},
                {"text": "\U0001f4a1 Trends", "callback_data": "cmd:trends"},
            ],
            [
                {"text": "\U0001f7e2 Early", "callback_data": "cmd:early"},
                {"text": "\u2699\ufe0f Status", "callback_data": "cmd:status"},
            ],
        ]
    }


def _alert_buttons(slug):
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f4a1 CoinGecko",
                 "url": f"https://www.coingecko.com/en/coins/{slug}"},
                {"text": "\U0001f4c8 DexScreener",
                 "url": f"https://dexscreener.com/search?q={slug}"},
            ],
            [
                {"text": "\U0001f30d X Search",
                 "url": f"https://x.com/search?q=%24{slug.upper()}"},
                {"text": "\u2795 Watchlist",
                 "callback_data": f"watchlist:add:{slug}"},
            ],
        ]
    }


def _coin_detail_buttons(slug):
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f4a1 CoinGecko",
                 "url": f"https://www.coingecko.com/en/coins/{slug}"},
                {"text": "\U0001f4c8 DexScreener",
                 "url": f"https://dexscreener.com/search?q={slug}"},
            ],
            [
                {"text": "\U0001f30d X Search",
                 "url": f"https://x.com/search?q=%24{slug.upper()}"},
                {"text": "\u2795 Watchlist",
                 "callback_data": f"watchlist:add:{slug}"},
            ],
        ]
    }


def _position_buttons(symbol, coin_id):
    return {
        "inline_keyboard": [
            [
                {"text": "\u2795 Buy", "callback_data": f"pos:buy:{symbol}"},
                {"text": "\u2796 Sell", "callback_data": f"pos:sell:{symbol}"},
            ],
            [
                {"text": "\U0001f4cb Transactions", "callback_data": f"pos:tx:{symbol}"},
                {"text": "\U0001f5d1 Archive", "callback_data": f"pos:archive:{symbol}"},
            ],
            [
                {"text": "\U0001f4a1 CoinGecko",
                 "url": f"https://www.coingecko.com/en/coins/{coin_id}"},
            ],
        ]
    }


def _portfolio_edit_buttons():
    return {
        "inline_keyboard": [
            [
                {"text": "\u2795 Buy", "callback_data": "cmd:buy"},
                {"text": "\u2796 Sell", "callback_data": "cmd:sell"},
            ],
            [
                {"text": "\U0001f4cb Transactions", "callback_data": "cmd:tx"},
                {"text": "\U0001f4b0 Cash", "callback_data": "cmd:cash"},
            ],
            [
                {"text": "\U0001f504 Refresh", "callback_data": "cmd:portafolio"},
            ],
        ]
    }


def _trend_buttons(slug):
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f4a1 CoinGecko",
                 "url": f"https://www.coingecko.com/en/coins/{slug}"},
                {"text": "\U0001f4c8 DexScreener",
                 "url": f"https://dexscreener.com/search?q={slug}"},
            ],
            [
                {"text": "\U0001f30d X Search",
                 "url": f"https://x.com/search?q=%24{slug.upper()}"},
                {"text": "\u2795 Watchlist",
                 "callback_data": f"watchlist:add:{slug}"},
            ],
        ]
    }


def set_bot_commands():
    try:
        resp = session.post(_api_url("setMyCommands"), json={
            "commands": BOT_COMMANDS,
        }, timeout=10)
        if resp.json().get("ok"):
            logger.info(f"Bot commands registered ({len(BOT_COMMANDS)} commands)")
        else:
            logger.warning(f"setMyCommands failed: {resp.json().get('description')}")
    except Exception as e:
        logger.warning(f"setMyCommands error: {e}")


def send_batch_hype_alerts():
    results = social_scanner.get_hype(limit=10)
    if not results:
        return False

    settings = storage.load_settings()
    notified = set(settings.get("notified_hype_slugs", []))
    new_hype = [r for r in results if r.get("slug") not in notified]

    if not new_hype:
        return False

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    header = (
        f"\u26a0\ufe0f <b>Hype sin Volumen</b>\n"
        f"\U0001f552 {now}\n\n"
        "Tokens con atenci\u00f3n sin respaldo de liquidez/volumen:\n"
    )
    lines = [header]
    for r in new_hype[:5]:
        symbol = r.get("symbol", "?")
        score = r.get("score", 0)
        liq = r.get("liquidity")
        vol = r.get("volume_24h")
        lines.append(
            f"\u2022 <b>{symbol}</b> | Score: {score}/100"
        )
        if liq:
            lines.append(f"  Liq: ${liq:,.0f}")
        if vol:
            lines.append(f"  Vol: ${vol:,.0f}")
        lines.append("")

    lines.append("\u26a0\ufe0f No es consejo financiero.")
    lines.append("\ud83d\udc49 /hype para lista completa")

    msg = "\n".join(lines)
    first_slug = new_hype[0].get("slug", "")
    send_message(msg, buttons=_trend_buttons(first_slug))

    notified.update(r.get("slug") for r in new_hype)
    settings["notified_hype_slugs"] = list(notified)
    storage.save_settings(settings)

    logger.info(f"Batch hype alert sent: {len(new_hype)} new tokens")
    return True


def send_startup_msg():
    msg = (
        "<b>\U0001f680 Crypto Crash Bot v3</b>\n\n"
        "\u2705 Multi-level dump detection\n"
        "\u2705 Early Trend Hunter\n"
        "\u2705 Portfolio + P&L\n"
        "\u2705 Social scanning\n\n"
        "\U0001f4cc Type / for commands\n"
        "\U0001f4cc /help for help"
    )
    send_message(msg)


def send_alert(alert):
    msg = format_dump_alert(alert)
    slug = alert["coin"].get("id", "")
    send_message(msg, buttons=_alert_buttons(slug))
    logger.info(
        f"Alert sent: {alert['coin'].get('name', '?')} "
        f"({alert['window']}, {alert['severity']})"
    )


def send_portfolio_report():
    send_processing()
    try:
        result = calculate_portfolio()
        parts = format_portfolio_report(result)
        buttons = _portfolio_buttons()
        for part in parts:
            send_message(part, buttons=buttons)
            time.sleep(0.5)
        logger.info("Portfolio report sent")
    except requests.exceptions.HTTPError:
        send_message(format_api_error("CoinGecko"))
    except Exception as e:
        logger.error(f"Portfolio report error: {e}")
        send_message(format_error("Error al calcular portafolio. Intenta de nuevo."))


def delete_webhook():
    try:
        resp = session.get(_api_url("deleteWebhook"),
                           params={"drop_pending_updates": "true"}, timeout=10)
        data = resp.json()
        if data.get("ok"):
            logger.info("Webhook cleared")
        else:
            logger.warning(f"Webhook delete: {data.get('description', '?')}")
    except Exception as e:
        logger.warning(f"Webhook delete error: {e}")


def poll_updates():
    global last_update_id
    params = {"offset": last_update_id + 1, "timeout": 10}
    try:
        resp = session.get(_api_url("getUpdates"), params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Telegram API error: {data.get('description', 'unknown')}")
            return
        if not data.get("result"):
            return
        for update in data["result"]:
            last_update_id = update["update_id"]
            if "callback_query" in update:
                handle_callback(update["callback_query"])
                continue
            msg = update.get("message")
            if not msg:
                continue
            text = msg.get("text", "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if chat_id != config.TELEGRAM_CHAT_ID:
                continue
            if text.startswith("/"):
                logger.info(f"Command received: {text.split()[0]}")
                handle_command(text)
    except requests.exceptions.ReadTimeout:
        pass
    except Exception as e:
        logger.error(f"Poll error: {e}")


def handle_callback(cb):
    cb_data = cb.get("data", "")
    from_id = str(cb.get("from", {}).get("id", ""))
    if from_id != config.TELEGRAM_CHAT_ID:
        return

    if cb_data == "cmd:portafolio":
        send_portfolio_report()
    elif cb_data == "cmd:status":
        stats = get_api_stats()
        msg = format_status(stats)
        send_message(msg)
    elif cb_data == "cmd:trends":
        results = social_scanner.get_trends(limit=10)
        parts = format_trends_list(results)
        for p in parts:
            send_message(p)
            time.sleep(0.3)
    elif cb_data == "cmd:early":
        results = social_scanner.get_early(limit=10)
        parts = format_early_list(results)
        for p in parts:
            send_message(p)
            time.sleep(0.3)
    elif cb_data == "cmd:buy":
        send_message("Usa: /buy <symbol> <quantity> <price> [fee]\nEj: /buy TAO 1.5 390")
    elif cb_data == "cmd:sell":
        send_message("Usa: /sell <symbol> <quantity> <price> [fee]\nEj: /sell TAO 1 420")
    elif cb_data == "cmd:tx":
        syms = [p["symbol"] for p in portfolio_db.get_active_positions()]
        if syms:
            send_message("Usa: /transactions <symbol>\nTokens: " + ", ".join(syms))
        else:
            send_message("No hay tokens activos en el portafolio")
    elif cb_data == "cmd:cash":
        balance = portfolio_db.get_cash_balance()
        send_message(f"\U0001f4b0 Efectivo disponible: {format_usd(balance)}")
    elif cb_data.startswith("pos:buy:"):
        sym = cb_data.split(":", 2)[2]
        send_message(f"Usa: /buy {sym} <quantity> <price> [fee]\nEj: /buy {sym} 1 100")
    elif cb_data.startswith("pos:sell:"):
        sym = cb_data.split(":", 2)[2]
        send_message(f"Usa: /sell {sym} <quantity> <price> [fee]\nEj: /sell {sym} 0.5 150")
    elif cb_data.startswith("pos:tx:"):
        sym = cb_data.split(":", 2)[2]
        handle_command(f"/transactions {sym}")
    elif cb_data.startswith("pos:archive:"):
        sym = cb_data.split(":", 2)[2]
        handle_command(f"/removetoken {sym}")
    elif cb_data.startswith("edit:"):
        sym = cb_data.split(":", 1)[1]
        pos = portfolio_db.get_position(sym)
        if pos:
            msg = (
                f"\u2699\ufe0f <b>Editando {sym}</b>\n\n"
                f"Actual: {pos['quantity']:.4f} @ {format_usd(pos['avg_entry_price'])}\n"
                f"Cost basis: {format_usd(pos['cost_basis_usd'])}\n\n"
                f"Usa:\n"
                f"/editposition {sym} <qty> <price> — Editar cantidad y precio\n"
                f"/buy {sym} <qty> <price> [fee] — Comprar mas\n"
                f"/sell {sym} <qty> <price> [fee] — Vender"
            )
            send_message(msg)
        else:
            send_message(f"{sym} no encontrado en el portafolio")
    elif cb_data.startswith("watchlist:add:"):
        slug = cb_data.split(":", 2)[2]
        settings = storage.load_settings()
        wl = settings.setdefault("watchlist", {})
        if slug not in wl:
            wl[slug] = {"symbol": slug, "alert_thresholds": {}}
            storage.save_settings(settings)
            logger.info(f"Added {slug} to watchlist via callback")

    try:
        session.post(_api_url("answerCallbackQuery"), json={
            "callback_query_id": cb["id"], "text": "Done",
        }, timeout=10)
    except Exception:
        pass


def _get_usage_error(cmd):
    defn = CMD_DEFS.get(cmd)
    if not defn:
        return format_usage_error(cmd, [], [])
    required = [a[0] for a in defn.get("args", []) if a[1]]
    all_args = [a[0] for a in defn.get("args", [])]
    examples = defn.get("examples", [])
    return format_usage_error(cmd, required, examples)


def _validate_args(cmd, args):
    defn = CMD_DEFS.get(cmd)
    if not defn:
        return True, None
    required = [a for a in defn.get("args", []) if a[1]]
    if len(args) < len(required):
        return False, _get_usage_error(cmd)
    return True, None


def handle_command(text):
    parts = text.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]
    logger.info(f"Command: {cmd}")

    valid, error = _validate_args(cmd, args)
    if not valid:
        send_message(error)
        return

    try:
        if cmd in ("/portafolio", "/portfolio"):
            send_portfolio_report()

        elif cmd in ("/search", "/precio", "/buscar"):
            send_processing()
            query = " ".join(args)
            cached = cache.get_detail_cache().get(f"search:{query}")
            if cached:
                send_message(cached["msg"], buttons=cached.get("buttons"))
                return
            matches = search_coins(query)
            if not matches:
                send_message(format_not_found(query))
                return
            if len(matches) > 1:
                names = "\n".join(
                    f"  \u2022 {m['name']} ({m['symbol'].upper()})" for m in matches[:5]
                )
                msg = (
                    f"<b>Multiples resultados para '{query}':</b>\n{names}\n\n"
                    f"Se mas especifico o usa el CoinGecko ID."
                )
                send_message(msg)
                return
            coin = matches[0]
            detail = fetch_coin_detail(coin["id"])
            if detail:
                msg = format_coin_detail(detail)
                btns = _coin_detail_buttons(coin["id"])
                cache.get_detail_cache().set(f"search:{query}",
                    {"msg": msg, "buttons": btns}, ttl=30)
                send_message(msg, buttons=btns)
            else:
                send_message(format_api_error("CoinGecko"))

        elif cmd == "/top":
            send_processing()
            cached = cache.get_market_cache().get("top")
            if cached:
                send_message(cached)
                return
            coins = fetch_market_coins(page=1, per_page=10)
            if coins:
                msg = format_top_list(coins)
                cache.get_market_cache().set("top", msg, ttl=120)
                send_message(msg)
            else:
                send_message(format_api_error("CoinGecko"))

        elif cmd == "/gainers":
            send_processing()
            cached = cache.get_market_cache().get("gainers")
            if cached:
                for part in cached:
                    send_message(part)
                return
            coins = fetch_market_coins(page=1, per_page=250)
            if coins:
                valid = [c for c in coins if c.get("price_change_percentage_24h") is not None]
                top = sorted(valid, key=lambda x: x["price_change_percentage_24h"], reverse=True)[:10]
                parts = format_gainers_losers(top, [])
                cache.get_market_cache().set("gainers", parts, ttl=120)
                for part in parts:
                    send_message(part)
            else:
                send_message(format_api_error("CoinGecko"))

        elif cmd == "/losers":
            send_processing()
            cached = cache.get_market_cache().get("losers")
            if cached:
                for part in cached:
                    send_message(part)
                return
            coins = fetch_market_coins(page=1, per_page=250)
            if coins:
                valid = [c for c in coins if c.get("price_change_percentage_24h") is not None]
                top = sorted(valid, key=lambda x: x["price_change_percentage_24h"])[:10]
                parts = format_gainers_losers([], top)
                cache.get_market_cache().set("losers", parts, ttl=120)
                for part in parts:
                    send_message(part)
            else:
                send_message(format_api_error("CoinGecko"))

        elif cmd == "/alerts":
            alerts = get_recent_alerts(10)
            msg = format_alerts_list(alerts)
            send_message(msg)

        elif cmd == "/watchlist":
            settings = storage.load_settings()
            wl = settings.get("watchlist", {})
            msg = format_watchlist(wl)
            send_message(msg)

        elif cmd == "/addwatch":
            slug = args[0].lower()
            settings = storage.load_settings()
            wl = settings.setdefault("watchlist", {})
            if slug in wl:
                send_message(f"\u2705 {slug} ya esta en la watchlist")
                return
            wl[slug] = {"symbol": slug, "alert_thresholds": {}}
            storage.save_settings(settings)
            send_message(f"\u2705 {slug} agregado a la watchlist")

        elif cmd == "/removewatch":
            slug = args[0].lower()
            settings = storage.load_settings()
            wl = settings.setdefault("watchlist", {})
            if slug in wl:
                del wl[slug]
                storage.save_settings(settings)
                send_message(f"\u2705 {slug} removido de la watchlist")
            else:
                send_message(f"{slug} no esta en la watchlist")

        elif cmd == "/addtoken":
            sym = args[0].upper()
            coin_id = args[1].lower()
            pos = portfolio_db.get_position(sym)
            if pos:
                send_message(f"\u2705 {sym} ya existe en el portafolio")
                return
            portfolio_db.add_position(coin_id, sym)
            send_message(
                f"\u2705 <b>{sym}</b> agregado al portafolio\n"
                f"CoinGecko ID: {coin_id}\n"
                f"Usa /buy {sym} <qty> <price> para registrar una compra"
            )

        elif cmd == "/removetoken":
            sym = args[0].upper()
            pos = portfolio_db.get_position(sym)
            if not pos:
                send_message(f"❌ {sym} no esta en tu portafolio activo")
                return
            portfolio_db.archive_position(sym)
            portfolio_db.add_transaction(sym.lower(), sym, "remove", 0, 0, 0, notes="Token archived")
            send_message(f"\u2705 <b>{sym}</b> archivado. El historial se conserva.\nUsa /portfolioedit para ver opciones.")

        elif cmd == "/buy":
            sym = args[0].upper()
            try:
                qty = float(args[1])
                price = float(args[2])
            except (ValueError, IndexError):
                send_message("❌ Cantidad y precio deben ser numeros.\nEj: /buy TAO 1.5 390")
                return
            if qty <= 0 or price <= 0:
                send_message("❌ Cantidad y precio deben ser positivos")
                return
            fee = float(args[3]) if len(args) > 3 else 0
            send_processing()

            pos = portfolio_db.get_position(sym)
            if not pos:
                coin_data = search_coins(sym)
                if coin_data:
                    coin_id = coin_data[0]["id"]
                    pos = portfolio_db.add_position(coin_id, sym, coin_data[0].get("name", ""))
                else:
                    send_message(f"❌ {sym} no encontrado. Usa /addtoken {sym} <coin_id> primero")
                    return

            total_cost = qty * price + fee
            updated = portfolio_db.update_position_after_buy(sym, qty, price, fee)
            portfolio_db.add_transaction(
                updated["coin_id"], sym, "buy", qty, price, total_cost,
                fee_usd=fee, notes=""
            )
            portfolio_db.add_cash_movement("buy", -total_cost, f"Compra {qty} {sym} @ ${price}")

            msg = (
                f"\u2705 <b>Compra registrada</b>\n\n"
                f"Token: {sym} — {updated.get('name', '')}\n"
                f"Cantidad comprada: {qty:.4f} {sym}\n"
                f"Precio: {format_usd(price)}\n"
                f"Fee: {format_usd(fee)}\n"
                f"Costo total: {format_usd(total_cost)}\n\n"
                f"Nueva cantidad: {updated['quantity']:.4f} {sym}\n"
                f"Nuevo precio promedio: {format_usd(updated['avg_entry_price'])}\n"
                f"Nuevo cost basis: {format_usd(updated['cost_basis_usd'])}"
            )
            send_message(msg)

        elif cmd == "/sell":
            sym = args[0].upper()
            try:
                qty = float(args[1])
                price = float(args[2])
            except (ValueError, IndexError):
                send_message("❌ Cantidad y precio deben ser numeros.\nEj: /sell TAO 1 420")
                return
            if qty <= 0 or price <= 0:
                send_message("❌ Cantidad y precio deben ser positivos")
                return
            fee = float(args[3]) if len(args) > 3 else 0
            send_processing()

            pos = portfolio_db.get_position(sym)
            if not pos:
                send_message(f"❌ {sym} no esta en tu portafolio.\nUsa /buy {sym} <qty> <price> para comprar primero")
                return
            if qty > pos["quantity"]:
                send_message(
                    f"❌ No puedes vender mas de lo que tienes.\n\n"
                    f"{sym} disponible: {pos['quantity']:.4f}\n"
                    f"Intentaste vender: {qty:.4f}"
                )
                return

            result = portfolio_db.update_position_after_sell(sym, qty, price, fee)
            if result is None:
                send_message("❌ Error al procesar la venta")
                return
            updated, realized_pnl, proceeds = result
            total_val = qty * price
            portfolio_db.add_transaction(
                updated["coin_id"], sym, "sell", qty, price, total_val,
                fee_usd=fee, realized_pnl_usd=realized_pnl, notes=""
            )
            portfolio_db.add_cash_movement("sell", proceeds - fee, f"Venta {qty} {sym} @ ${price}")

            pnl_emoji = "\U0001f7e2" if realized_pnl >= 0 else "\U0001f534"
            msg = (
                f"\u2705 <b>Venta registrada</b>\n\n"
                f"Token: {sym} — {updated.get('name', '')}\n"
                f"Cantidad vendida: {qty:.4f} {sym}\n"
                f"Precio venta: {format_usd(price)}\n"
                f"Fee: {format_usd(fee)}\n"
                f"Valor venta: {format_usd(total_val)}\n\n"
                f"P&L realizado: {pnl_emoji} {format_usd(realized_pnl)}\n"
                f"Cantidad restante: {updated['quantity']:.4f} {sym}\n"
                f"Cost basis restante: {format_usd(updated['cost_basis_usd'])}"
            )
            send_message(msg)

        elif cmd == "/sellall":
            sym = args[0].upper()
            try:
                price = float(args[1])
            except (ValueError, IndexError):
                send_message("❌ Precio debe ser un numero.\nEj: /sellall ARIA 0.052")
                return
            if price <= 0:
                send_message("❌ El precio debe ser positivo")
                return
            fee = float(args[2]) if len(args) > 2 else 0
            send_processing()

            pos = portfolio_db.get_position(sym)
            if not pos:
                send_message(f"❌ {sym} no esta en tu portafolio")
                return

            qty = pos["quantity"]
            result = portfolio_db.update_position_after_sell(sym, qty, price, fee)
            if result is None:
                send_message("❌ Error al procesar la venta total")
                return
            updated, realized_pnl, proceeds = result
            total_val = qty * price
            portfolio_db.add_transaction(
                updated["coin_id"], sym, "sell_all", qty, price, total_val,
                fee_usd=fee, realized_pnl_usd=realized_pnl, notes="Venta total"
            )
            portfolio_db.add_cash_movement("sell", proceeds - fee, f"Venta total {qty} {sym} @ ${price}")

            pnl_emoji = "\U0001f7e2" if realized_pnl >= 0 else "\U0001f534"
            msg = (
                f"\u2705 <b>Venta total registrada</b>\n\n"
                f"Token: {sym} — {updated.get('name', '')}\n"
                f"Cantidad vendida: {qty:.4f} {sym}\n"
                f"Precio venta: {format_usd(price)}\n"
                f"Fee: {format_usd(fee)}\n"
                f"Valor venta: {format_usd(total_val)}\n\n"
                f"P&L realizado: {pnl_emoji} {format_usd(realized_pnl)}\n"
                f"{sym} fue archivado del portafolio activo."
            )
            send_message(msg)

        elif cmd == "/position":
            sym = args[0].upper()
            send_processing()
            pos = portfolio_db.get_position(sym)
            if not pos:
                send_message(f"❌ {sym} no esta en tu portafolio activo")
                return

            from .coingecko_client import fetch_market_coins_by_ids
            prices = {}
            try:
                market_data = fetch_market_coins_by_ids([pos["coin_id"]], changes="1h,24h,7d")
                if market_data:
                    prices = market_data[0]
            except Exception:
                pass

            current_price = prices.get("current_price") if prices else None
            ch1h = prices.get("price_change_percentage_1h_in_currency") if prices else None
            ch24h = prices.get("price_change_percentage_24h") if prices else None
            ch7d = prices.get("price_change_percentage_7d_in_currency") if prices else None
            mcap = prices.get("market_cap") if prices else None
            vol24h = prices.get("total_volume") if prices else None

            current_value = pos["quantity"] * current_price if current_price and pos["quantity"] > 0 else 0
            unrealized_pnl = (current_price - pos["avg_entry_price"]) * pos["quantity"] if current_price and pos["avg_entry_price"] > 0 and pos["quantity"] > 0 else None
            unrealized_pnl_pct = ((current_price - pos["avg_entry_price"]) / pos["avg_entry_price"]) * 100 if current_price and pos["avg_entry_price"] > 0 else None

            lines = [
                f"\U0001f4ca <b>{sym} — {pos.get('name', '')}</b>\n",
                f"Cantidad: {pos['quantity']:.4f} {sym}",
                f"Precio promedio: {format_usd(pos['avg_entry_price'])}",
                f"Cost basis: {format_usd(pos['cost_basis_usd'])}",
                f"P&L realizado: {format_usd(pos['realized_pnl_usd'])}",
                "",
            ]
            if current_price is not None:
                lines.append(f"Precio actual: {format_usd(current_price)}")
                lines.append(f"Valor actual: {format_usd(current_value)}")
                if unrealized_pnl is not None:
                    e = "\U0001f7e2" if unrealized_pnl >= 0 else "\U0001f534"
                    lines.append(f"P&L no realizado: {e} {format_usd(unrealized_pnl)} ({unrealized_pnl_pct:+.2f}%)" if unrealized_pnl_pct is not None else f"P&L no realizado: {e} {format_usd(unrealized_pnl)}")
            if ch1h is not None:
                e = "\U0001f7e2" if ch1h >= 0 else "\U0001f534"
                lines.append(f"1h: {e} {ch1h:+.2f}%")
            if ch24h is not None:
                e = "\U0001f7e2" if ch24h >= 0 else "\U0001f534"
                lines.append(f"24h: {e} {ch24h:+.2f}%")
            if ch7d is not None:
                e = "\U0001f7e2" if ch7d >= 0 else "\U0001f534"
                lines.append(f"7d: {e} {ch7d:+.2f}%")
            if mcap:
                lines.append(f"Market Cap: {format_usd(mcap)}")
            if vol24h:
                lines.append(f"Volume 24h: {format_usd(vol24h)}")

            lines.append("")
            txs = portfolio_db.get_transactions(sym, limit=5)
            if txs:
                lines.append(f"<b>Ultimas transacciones:</b>")
                for t in txs:
                    ttype = t["type"].replace("_", " ").title()
                    lines.append(f"  \u2022 {ttype} {t['quantity']:.4f} @ {format_usd(t['price_usd'])}")
            else:
                lines.append("Sin transacciones registradas.")

            msg = "\n".join(lines)
            buttons = _position_buttons(sym, pos["coin_id"])
            send_message(msg, buttons=buttons)

        elif cmd == "/transactions":
            sym = args[0].upper()
            txs = portfolio_db.get_transactions(sym, limit=25)
            if not txs:
                send_message(f"Sin transacciones registradas para {sym}")
                return

            lines = [f"\U0001f4cb <b>Transacciones: {sym}</b>\n"]
            for t in txs:
                ttype = t["type"].replace("_", " ").title()
                ts = t.get("created_at", "")[:19]
                pnl_str = ""
                if t.get("realized_pnl_usd"):
                    e = "\U0001f7e2" if t["realized_pnl_usd"] >= 0 else "\U0001f534"
                    pnl_str = f" | P&L: {e} {format_usd(t['realized_pnl_usd'])}"
                lines.append(
                    f"\u2022 <b>{ttype}</b> {ts}\n"
                    f"   {t['quantity']:.4f} @ {format_usd(t['price_usd'])}"
                    f"{pnl_str}"
                )
                if t.get("notes"):
                    lines.append(f"   Nota: {t['notes']}")
                lines.append("")
            send_message("\n".join(lines))

        elif cmd == "/cash":
            balance = portfolio_db.get_cash_balance()
            total_positions_value = 0
            total_cost_basis = 0
            total_realized_pnl = 0
            active_positions = portfolio_db.get_active_positions()
            slugs = [p["coin_id"] for p in active_positions]
            prices = {}
            if slugs:
                try:
                    from .coingecko_client import fetch_market_coins_by_ids
                    market_data = fetch_market_coins_by_ids(slugs, changes="")
                    if market_data:
                        prices = {c["id"]: c.get("current_price", 0) or 0 for c in market_data}
                except Exception:
                    pass
            for p in active_positions:
                cost_basis = p["cost_basis_usd"] or 0
                total_cost_basis += cost_basis
                current_price = prices.get(p["coin_id"], 0)
                current_value = p["quantity"] * current_price if current_price else 0
                total_positions_value += current_value
                total_realized_pnl += p.get("realized_pnl_usd", 0) or 0

            total_value = total_positions_value + balance
            unrealized_pnl = total_positions_value - total_cost_basis if total_cost_basis > 0 else 0
            total_pnl = unrealized_pnl + total_realized_pnl

            msg = (
                f"\U0001f4b0 <b>Resumen de Efectivo</b>\n\n"
                f"Efectivo disponible: {format_usd(balance)}\n"
                f"Valor en posiciones: {format_usd(total_positions_value)}\n"
                f"Valor total: {format_usd(total_value)}\n"
                f"Cost basis total: {format_usd(total_cost_basis)}\n"
                f"P&L no realizado: {format_usd(unrealized_pnl)}\n"
                f"P&L realizado: {format_usd(total_realized_pnl)}\n"
                f"P&L total: {format_usd(total_pnl)}"
            )
            send_message(msg)

        elif cmd == "/setcash":
            try:
                amount = float(args[0])
            except ValueError:
                send_message("❌ El monto debe ser un numero.\nEj: /setcash 1500")
                return
            portfolio_db.set_cash_balance(amount)
            send_message(f"\u2705 Efectivo definido en {format_usd(amount)}")

        elif cmd == "/deposit":
            try:
                amount = float(args[0])
            except ValueError:
                send_message("❌ El monto debe ser un numero.\nEj: /deposit 1000")
                return
            note = " ".join(args[1:]) if len(args) > 1 else ""
            portfolio_db.add_cash_movement("deposit", amount, note)
            send_message(f"\u2705 Deposito: {format_usd(amount)}\nNuevo saldo: {format_usd(portfolio_db.get_cash_balance())}")

        elif cmd == "/withdraw":
            try:
                amount = float(args[0])
            except ValueError:
                send_message("❌ El monto debe ser un numero.\nEj: /withdraw 300")
                return
            current = portfolio_db.get_cash_balance()
            if amount > current:
                send_message(f"❌ No tienes suficiente efectivo.\nDisponible: {format_usd(current)}\nIntentaste retirar: {format_usd(amount)}")
                return
            note = " ".join(args[1:]) if len(args) > 1 else ""
            portfolio_db.add_cash_movement("withdraw", -amount, note)
            send_message(f"\u2705 Retiro: {format_usd(amount)}\nNuevo saldo: {format_usd(portfolio_db.get_cash_balance())}")

        elif cmd == "/portfolioedit":
            positions = portfolio_db.get_active_positions()
            lines = [
                "\u2699\ufe0f <b>Editar Portafolio</b>\n",
                "Selecciona un token para editar:\n",
            ]
            token_buttons = []
            for p in positions:
                sym = p["symbol"]
                qty = p["quantity"]
                entry = p["avg_entry_price"]
                if qty > 0 and entry > 0:
                    lines.append(
                        f"\u2022 <b>{sym}</b> — {qty:.4f} @ {format_usd(entry)}"
                    )
                else:
                    lines.append(f"\u2022 <b>{sym}</b> — Sin precio/configurar")
                token_buttons.append(
                    {"text": sym, "callback_data": f"edit:{sym}"}
                )

            lines.extend([
                "",
                "Acciones rapidas:",
                "\u2022 /buy <sym> <qty> <price> — Comprar",
                "\u2022 /sell <sym> <qty> <price> — Vender",
                "\u2022 /addtoken <sym> <coin_id> — Agregar token",
                "\u2022 /removetoken <sym> — Archivar token",
                "\u2022 /editposition <sym> <qty> <price> — Editar cantidad/precio",
                "\u2022 /deposit <amount> — Depositar",
                "\u2022 /withdraw <amount> — Retirar",
            ])

            buttons = {"inline_keyboard": []}
            row = []
            for i, btn in enumerate(token_buttons):
                row.append(btn)
                if len(row) >= 3:
                    buttons["inline_keyboard"].append(row)
                    row = []
            if row:
                buttons["inline_keyboard"].append(row)
            buttons["inline_keyboard"].append([
                {"text": "\U0001f4b0 Cash", "callback_data": "cmd:cash"},
                {"text": "\U0001f504 Refresh", "callback_data": "cmd:portafolio"},
            ])

            send_message("\n".join(lines), buttons=buttons)

        elif cmd == "/editposition":
            sym = args[0].upper()
            try:
                new_qty = float(args[1])
                new_price = float(args[2])
            except (ValueError, IndexError):
                send_message("❌ Uso: /editposition <sym> <qty> <price>\nEj: /editposition TAO 4.7 362.76")
                return
            if new_qty < 0 or new_price < 0:
                send_message("❌ Cantidad y precio deben ser positivos")
                return
            pos = portfolio_db.get_position(sym)
            if not pos:
                send_message(f"❌ {sym} no esta en el portafolio activo")
                return
            updated = portfolio_db.edit_position(sym, new_qty, new_price)
            portfolio_db.add_transaction(
                updated["coin_id"], sym, "manual_adjustment", new_qty, new_price,
                new_qty * new_price,
                notes=f"Manual adjustment: qty={new_qty}, price={new_price}"
            )
            msg = (
                f"\u2705 <b>Posicion actualizada</b>\n\n"
                f"Token: {sym}\n"
                f"Nueva cantidad: {new_qty:.4f}\n"
                f"Nuevo precio promedio: {format_usd(new_price)}\n"
                f"Nuevo cost basis: {format_usd(new_qty * new_price)}\n\n"
                "\u26a0\ufe0f Correccion manual registrada en el historial"
            )
            send_message(msg)

        elif cmd == "/setthreshold":
            slug = args[0].lower()
            window = args[1].lower()
            try:
                pct = float(args[2])
            except ValueError:
                send_message("El porcentaje debe ser un numero.\nEj: /setthreshold bittensor 15m -15")
                return
            if window not in config.ALERT_WINDOWS:
                send_message(f"Ventana invalida. Usa: {', '.join(config.ALERT_WINDOWS)}")
                return
            settings = storage.load_settings()
            wl = settings.setdefault("watchlist", {})
            if slug not in wl:
                wl[slug] = {"symbol": slug, "alert_thresholds": {}}
            wl[slug].setdefault("alert_thresholds", {})[window] = pct
            storage.save_settings(settings)
            send_message(f"\u2705 Threshold for {slug} ({window}): {pct}%")

        elif cmd == "/trends":
            send_processing()
            cached = cache.get_social_cache().get("trends")
            if cached:
                for part in cached:
                    send_message(part)
                return
            results = social_scanner.get_trends(limit=15)
            parts = format_trends_list(results)
            cache.get_social_cache().set("trends", parts, ttl=120)
            for part in parts:
                send_message(part)
                time.sleep(0.3)

        elif cmd == "/early":
            send_processing()
            cached = cache.get_social_cache().get("early")
            if cached:
                for part in cached:
                    send_message(part)
                return
            results = social_scanner.get_early(limit=15)
            parts = format_early_list(results)
            cache.get_social_cache().set("early", parts, ttl=120)
            for part in parts:
                send_message(part)
                time.sleep(0.3)

        elif cmd == "/hype":
            results = social_scanner.get_hype(limit=10)
            msg = format_hype_list(results)
            send_message(msg)

        elif cmd == "/status":
            stats = get_api_stats()
            msg = format_status(stats)
            send_message(msg)

        elif cmd == "/help":
            msg = format_help()
            send_message(msg)

        else:
            send_message(
                f"Comando '{cmd}' no reconocido.\n"
                "Usa /help para ver los comandos disponibles."
            )

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        logger.error(f"HTTP {status} in {cmd}: {e}")
        send_message(format_api_error("CoinGecko" if status != 404 else "the API"))
    except requests.exceptions.Timeout:
        send_message("\u26a0\ufe0f La consulta tard\u00f3 demasiado. Intenta de nuevo.")
    except requests.exceptions.ConnectionError:
        send_message("\u26a0\ufe0f Error de conexi\u00f3n. Verifica tu internet.")
    except Exception as e:
        logger.error(f"Command error ({cmd}): {e}")
        send_message(format_error(f"Error inesperado. Intenta de nuevo."))
