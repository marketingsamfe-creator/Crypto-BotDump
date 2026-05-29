import time
import requests
from . import config, storage, cache
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
    split_long_message,
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
}

BOT_COMMANDS = [
    {"command": "portafolio", "description": "Resumen del portafolio"},
    {"command": "precio", "description": "Precio de un token"},
    {"command": "search", "description": "Buscar criptomoneda"},
    {"command": "early", "description": "Señales tempranas"},
    {"command": "trends", "description": "Tendencias sociales"},
    {"command": "top", "description": "Top criptos"},
    {"command": "gainers", "description": "Ganadoras 24h"},
    {"command": "losers", "description": "Perdedoras 24h"},
    {"command": "alerts", "description": "Alertas recientes"},
    {"command": "watchlist", "description": "Watchlist"},
    {"command": "addwatch", "description": "Agregar a watchlist"},
    {"command": "setentry", "description": "Precio de entrada"},
    {"command": "setqty", "description": "Cantidad del token"},
    {"command": "settotal", "description": "Total invertido"},
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

        elif cmd == "/setentry":
            sym = args[0].upper()
            try:
                price = float(args[1])
            except ValueError:
                send_message("El precio debe ser un numero.\nEj: /setentry TAO 350")
                return
            pdata = storage.load_portfolio_data()
            pdata.setdefault("entry_prices", {})[sym] = price
            storage.save_portfolio_data(pdata)
            send_message(f"\u2705 Entry price for {sym}: ${price:.6f}")

        elif cmd == "/setqty":
            sym = args[0].upper()
            try:
                qty = float(args[1])
            except ValueError:
                send_message("La cantidad debe ser un numero.\nEj: /setqty TAO 3.5")
                return
            pdata = storage.load_portfolio_data()
            pdata.setdefault("quantities", {})[sym] = qty
            storage.save_portfolio_data(pdata)
            send_message(f"\u2705 Quantity for {sym}: {qty}")

        elif cmd == "/settotal":
            try:
                total = float(args[0])
            except ValueError:
                send_message("El monto debe ser un numero.\nEj: /settotal 10000")
                return
            pdata = storage.load_portfolio_data()
            pdata["total_invested"] = total
            storage.save_portfolio_data(pdata)
            send_message(f"\u2705 Total invertido: ${total:,.2f}")

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
