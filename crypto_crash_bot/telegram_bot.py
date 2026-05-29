import time
import requests
from . import config, storage
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
    split_long_message,
)

session = requests.Session()
last_update_id = 0


def _api_url(method):
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"


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


def send_startup_msg():
    msg = (
        "<b>🚀 Crypto Crash Bot v3</b>\n\n"
        "✅ Multi-level dump detection (15%/25%/40%)\n"
        "✅ 5m/15m/1h/24h windows\n"
        "✅ Portfolio snapshot w/ P&L\n"
        "✅ Watchlist + custom thresholds\n"
        "✅ Anti-spam cooldown\n\n"
        "📌 /help for commands"
    )
    send_message(msg)


def send_alert(alert):
    msg = format_dump_alert(alert)
    buttons = {
        "inline_keyboard": [
            [
                {"text": "📊 Portafolio", "callback_data": "cmd:portafolio"},
                {"text": "📈 Status", "callback_data": "cmd:status"},
            ]
        ]
    }
    send_message(msg, buttons=buttons)
    logger.info(
        f"Alert sent: {alert['coin'].get('name', '?')} "
        f"({alert['window']}, {alert['severity']})"
    )


def send_portfolio_report():
    try:
        result = calculate_portfolio()
        parts = format_portfolio_report(result)
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "📊 Portafolio", "callback_data": "cmd:portafolio"},
                    {"text": "📈 Status", "callback_data": "cmd:status"},
                ]
            ]
        }
        for part in parts:
            send_message(part, buttons=buttons)
            time.sleep(0.5)
        logger.info("Portfolio report sent")
    except Exception as e:
        logger.error(f"Portfolio report error: {e}")


def poll_updates():
    global last_update_id
    params = {"offset": last_update_id + 1, "timeout": 10}
    try:
        resp = session.get(_api_url("getUpdates"), params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
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
                handle_command(text)

    except requests.exceptions.ReadTimeout:
        pass
    except Exception as e:
        logger.error(f"Poll error: {e}")


def handle_callback(cb):
    cb_data = cb.get("data", "")
    chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
    msg_id = cb.get("message", {}).get("message_id")
    from_id = str(cb.get("from", {}).get("id", ""))

    if from_id != config.TELEGRAM_CHAT_ID:
        return

    if cb_data == "cmd:portafolio":
        send_portfolio_report()
    elif cb_data == "cmd:status":
        stats = get_api_stats()
        msg = format_status(stats)
        send_message(msg)

    try:
        session.post(_api_url("answerCallbackQuery"), json={
            "callback_query_id": cb["id"],
            "text": "Done",
        }, timeout=10)
    except Exception:
        pass


def handle_command(text):
    parts = text.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]

    logger.info(f"Command: {cmd}")

    try:
        if cmd in ("/portafolio", "/portfolio"):
            send_portfolio_report()

        elif cmd in ("/search", "/precio", "/buscar"):
            if not args:
                send_message("Usa: /precio <nombre o simbolo>\nEj: /precio bitcoin")
                return
            query = " ".join(args)
            matches = search_coins(query)
            if not matches:
                send_message(format_error(f"No se encontro '{query}'"))
                return
            if len(matches) > 1:
                names = "\n".join(
                    f"  {m['name']} ({m['symbol'].upper()})" for m in matches[:5]
                )
                msg = f"<b>Multiples resultados:</b>\n{names}\n\nSe mas especifico."
                send_message(msg)
                return
            coin = matches[0]
            detail = fetch_coin_detail(coin["id"])
            if detail:
                msg = format_coin_detail(detail)
                btns = {
                    "inline_keyboard": [[
                        {"text": " CoinGecko",
                         "url": f"https://www.coingecko.com/en/coins/{coin['id']}"},
                        {"text": "+ Watchlist",
                         "callback_data": f"watchlist:add:{coin['id']}"},
                    ]]
                }
                send_message(msg, buttons=btns)
            else:
                send_message(format_error("Error al obtener datos"))

        elif cmd == "/top":
            coins = fetch_market_coins(page=1, per_page=10)
            if coins:
                msg = format_top_list(coins)
                send_message(msg)
            else:
                send_message(format_error("Error al obtener top"))

        elif cmd == "/gainers":
            coins = fetch_market_coins(page=1, per_page=250)
            if coins:
                valid = [c for c in coins if c.get("price_change_percentage_24h") is not None]
                gainers = sorted(valid, key=lambda x: x["price_change_percentage_24h"], reverse=True)[:10]
                losers = []
                msg_parts = format_gainers_losers(gainers, losers)
                for part in msg_parts:
                    send_message(part)
            else:
                send_message(format_error("Error al obtener datos"))

        elif cmd == "/losers":
            coins = fetch_market_coins(page=1, per_page=250)
            if coins:
                valid = [c for c in coins if c.get("price_change_percentage_24h") is not None]
                gainers = []
                losers = sorted(valid, key=lambda x: x["price_change_percentage_24h"])[:10]
                msg_parts = format_gainers_losers(gainers, losers)
                for part in msg_parts:
                    send_message(part)
            else:
                send_message(format_error("Error al obtener datos"))

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
            if not args:
                send_message("Usa: /addwatch <coin_id>\nEj: /addwatch bittensor")
                return
            slug = args[0].lower()
            settings = storage.load_settings()
            wl = settings.setdefault("watchlist", {})
            if slug in wl:
                send_message(f"{slug} ya esta en la watchlist")
                return
            wl[slug] = {"symbol": slug, "alert_thresholds": {}}
            storage.save_settings(settings)
            send_message(f"OK {slug} agregado a la watchlist")

        elif cmd == "/removewatch":
            if not args:
                send_message("Usa: /removewatch <coin_id>\nEj: /removewatch bittensor")
                return
            slug = args[0].lower()
            settings = storage.load_settings()
            wl = settings.setdefault("watchlist", {})
            if slug in wl:
                del wl[slug]
                storage.save_settings(settings)
                send_message(f"OK {slug} removido de la watchlist")
            else:
                send_message(f"{slug} no esta en la watchlist")

        elif cmd == "/setentry":
            if len(args) < 2:
                send_message("Usa: /setentry <SIMBOLO> <precio>\nEj: /setentry TAO 450")
                return
            sym = args[0].upper()
            try:
                price = float(args[1])
            except ValueError:
                send_message("Precio invalido.")
                return
            pdata = storage.load_portfolio_data()
            pdata.setdefault("entry_prices", {})[sym] = price
            storage.save_portfolio_data(pdata)
            send_message(f"OK Entry price for {sym}: ${price:.6f}")

        elif cmd == "/setqty":
            if len(args) < 2:
                send_message("Usa: /setqty <SIMBOLO> <cantidad>\nEj: /setqty TAO 5.5")
                return
            sym = args[0].upper()
            try:
                qty = float(args[1])
            except ValueError:
                send_message("Cantidad invalida.")
                return
            pdata = storage.load_portfolio_data()
            pdata.setdefault("quantities", {})[sym] = qty
            storage.save_portfolio_data(pdata)
            send_message(f"OK Quantity for {sym}: {qty}")

        elif cmd == "/settotal":
            if not args:
                send_message("Usa: /settotal <usd>\nEj: /settotal 10000")
                return
            try:
                total = float(args[0])
            except ValueError:
                send_message("Valor invalido.")
                return
            pdata = storage.load_portfolio_data()
            pdata["total_invested"] = total
            storage.save_portfolio_data(pdata)
            send_message(f"OK Total invertido: ${total:,.2f}")

        elif cmd == "/setthreshold":
            if len(args) < 3:
                send_message("Usa: /setthreshold <coin_id> <window> <percent>\nEj: /setthreshold bittensor 15m -8")
                return
            slug = args[0].lower()
            window = args[1].lower()
            try:
                pct = float(args[2])
            except ValueError:
                send_message("Porcentaje invalido.")
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
            send_message(f"OK Threshold for {slug} ({window}): {pct}%")

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

    except Exception as e:
        logger.error(f"Command error ({cmd}): {e}")
        send_message(format_error(f"Error ejecutando {cmd}: {str(e)[:100]}"))
