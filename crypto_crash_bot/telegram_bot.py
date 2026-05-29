import time
from datetime import datetime
import requests
from . import config, storage, cache
from . import portfolio_db
from . import session as session_mgr
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
from . import trading_ui

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
    "/setthreshold": {"args": [("coin_id", True), ("window", True), ("percent", True)],
        "desc": "Umbral de alerta",
        "examples": ["/setthreshold bittensor 15m -15"]},
    "/portfolioedit": {"args": [], "desc": "Menu de edicion del portafolio"},
    "/editposition": {"args": [("symbol", True), ("qty", True), ("price", True)],
        "desc": "Editar cantidad y precio de un token",
        "examples": ["/editposition TAO 4.7 362.76"]},
    "/menu": {"args": [], "desc": "Menu principal"},
    "/start": {"args": [], "desc": "Iniciar el bot"},
    "/cancel": {"args": [], "desc": "Cancelar operacion actual"},
    "/dumps": {"args": [("window", False)], "desc": "Top tokens en caida",
        "examples": ["/dumps", "/dumps 1h"]},
    "/testcontracts": {"args": [], "desc": "Probar resolucion de contratos"},
    "/debugtoken": {"args": [("query", True)], "desc": "Debug resolucion de token",
        "examples": ["/debugtoken 0x...", "/debugtoken TAO"]},
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
    {"command": "setthreshold", "description": "Umbral de alerta por token"},
    {"command": "status", "description": "Estado del bot"},
    {"command": "menu", "description": "Menu principal"},
    {"command": "cancel", "description": "Cancelar operacion"},
    {"command": "dumps", "description": "Top tokens en caida"},
    {"command": "debugtoken", "description": "Debug resolucion de token"},
    {"command": "testcontracts", "description": "Probar resolucion de contratos"},
    {"command": "help", "description": "Ayuda"},
]


def _api_url(method):
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"


_last_sent_msg_id = None
_loading_msg_id = None
_first_response_time = None


def send_typing():
    try:
        session.post(_api_url("sendChatAction"), json={
            "chat_id": config.TELEGRAM_CHAT_ID, "action": "typing",
        }, timeout=5)
    except Exception:
        pass


def send_message(text, buttons=None):
    global _last_sent_msg_id, _first_response_time
    if _first_response_time is None:
        _first_response_time = time.time()
    parts = split_long_message(text) if isinstance(text, str) else text
    last_id = None
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
            result = resp.json()
            if result.get("ok") and result.get("result"):
                last_id = result["result"]["message_id"]
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
        time.sleep(0.3)
    if last_id:
        _last_sent_msg_id = last_id
        return last_id


def edit_message(text, message_id=None, buttons=None):
    global _last_sent_msg_id, _loading_msg_id
    mid = message_id or _last_sent_msg_id or _loading_msg_id
    if not mid:
        return send_message(text, buttons)
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "message_id": mid,
        "text": text,
        "parse_mode": "HTML",
    }
    if buttons:
        payload["reply_markup"] = buttons
    try:
        resp = session.post(_api_url("editMessageText"), json=payload, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        if "message is not modified" not in str(e).lower() and "message can't be edited" not in str(e).lower():
            logger.error(f"Telegram edit error: {e}")


def send_loading(text):
    global _loading_msg_id, _first_response_time
    if _first_response_time is None:
        _first_response_time = time.time()
    try:
        resp = session.post(_api_url("sendMessage"), json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("ok") and result.get("result"):
            _loading_msg_id = result["result"]["message_id"]
            return _loading_msg_id
    except Exception as e:
        logger.error(f"Telegram loading error: {e}")


def send_processing():
    send_typing()


# Performance metrics
_perf_records = []


def _perf_record(command, first_ms, total_ms, cache_hit=None, api=None):
    r = {"cmd": command, "first_ms": round(first_ms, 1), "total_ms": round(total_ms, 1), "ts": time.time()}
    if cache_hit is not None:
        r["cache"] = cache_hit
    if api:
        r["api"] = api
    _perf_records.append(r)
    if len(_perf_records) > 500:
        _perf_records[:] = _perf_records[-250:]
    logger.info(f"PERF command={command} first_response_ms={first_ms:.0f} final_response_ms={total_ms:.0f}" +
                (f" cache_hit={cache_hit}" if cache_hit is not None else "") +
                (f" api={api}" if api else ""))


def _get_perf_summary():
    if not _perf_records:
        return "No performance data yet."
    recent = _perf_records[-50:]
    first_times = [r["first_ms"] for r in recent]
    total_times = [r["total_ms"] for r in recent]
    avg_first = sum(first_times) / len(first_times)
    avg_total = sum(total_times) / len(total_times)
    sorted_total = sorted(total_times)
    p95 = sorted_total[int(len(sorted_total) * 0.95)] if len(sorted_total) > 1 else sorted_total[-1]
    slowest = max(recent, key=lambda r: r["total_ms"])
    cache_records = [r for r in recent if r.get("cache") is not None]
    cache_hits = sum(1 for r in cache_records if r["cache"] is True)
    cache_rate = round(cache_hits / len(cache_records) * 100, 1) if cache_records else 0
    return {
        "avg_first_ms": round(avg_first, 1),
        "avg_total_ms": round(avg_total, 1),
        "p95_total_ms": round(p95, 1),
        "cache_hit_rate": cache_rate,
        "slowest_cmd": slowest["cmd"],
        "slowest_ms": round(slowest["total_ms"], 1),
        "total_recorded": len(_perf_records),
    }


def _refresh_button(data):
    return {"inline_keyboard": [[{"text": "\U0001f504 Refresh", "callback_data": f"refresh:{data}"}]]}


def _loading_texts():
    return {
        "/start": "\U0001f3e0 Loading menu...",
        "/menu": "\U0001f3e0 Loading menu...",
        "/buy": "\u2795 Buy Token...",
        "/sell": "\u2796 Loading positions...",
        "/dumps": "\U0001f4c9 Loading Top Losers...",
        "/hype": "\u26a0\ufe0f Loading Hype Signals...",
        "/trends": "\U0001f525 Loading Trends...",
        "/early": "\U0001f7e2 Loading Early Signals...",
        "/portafolio": "\U0001f4ca Calculating portfolio...",
        "/precio": "\U0001f50e Looking up token...",
        "/search": "\U0001f50e Searching...",
        "/social": "\U0001f9e0 Loading social analysis...",
        "/status": "\u2699\ufe0f Checking bot status...",
        "/gainers": "\U0001f7e2 Loading gainers...",
        "/losers": "\U0001f534 Loading losers...",
        "/top": "\U0001f4ca Loading top coins...",
        "/alerts": "\u26a0\ufe0f Loading alerts...",
        "/watchlist": "\u2b50 Loading watchlist...",
        "/perftest": "\U0001f9e0 Running performance test...",
        "/testflows": "\U0001f9ea Testing flows...",
    }


def _loading_text(cmd):
    return _loading_texts().get(cmd, f"\U0001f504 Processing {cmd}...")


def _main_menu():
    positions = portfolio_db.get_active_positions()
    cash = portfolio_db.get_cash_balance()
    total_val = 0
    total_pnl = 0
    try:
        from .portfolio import calculate_portfolio
        pr = calculate_portfolio()
        total_val = pr.get("total_value_with_cash", 0)
        total_pnl = pr.get("total_pnl_usd", 0)
        pnl_pct = pr.get("total_pnl_pct", 0)
    except Exception:
        pnl_pct = 0

    lines = [
        "\U0001f3e0 <b>Crypto Crash Bot</b>\n",
    ]
    if total_val > 0:
        lines.append(f"\U0001f4ca Portfolio: {format_usd(total_val)}")
    if total_pnl != 0:
        e = "\U0001f7e2" if total_pnl >= 0 else "\U0001f534"
        lines.append(f"\U0001f4c8 P&L: {e} {format_usd(total_pnl)} ({pnl_pct:+.2f}%)")
    lines.append(f"\U0001f4b5 Cash: {format_usd(cash)}")
    lines.append("")

    return "\n".join(lines)


def _main_menu_buttons():
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f4ca Portfolio", "callback_data": "cmd:portafolio"},
                {"text": "\u2795 Buy", "callback_data": "flow:buy:select_source"},
            ],
            [
                {"text": "\u2796 Sell", "callback_data": "flow:sell:select"},
                {"text": "\U0001f50e Search", "callback_data": "flow:search"},
            ],
            [
                {"text": "\U0001f7e2 Early", "callback_data": "cmd:early"},
                {"text": "\U0001f525 Trends", "callback_data": "cmd:trends"},
            ],
            [
                {"text": "\u26a0\ufe0f Hype", "callback_data": "cmd:hype"},
                {"text": "\u2b50 Watchlist", "callback_data": "cmd:watchlist"},
            ],
            [
                {"text": "\u2699\ufe0f Settings", "callback_data": "cmd:portfolioedit"},
            ],
        ]
    }


def _token_action_buttons(slug, symbol, coin_id):
    return {
        "inline_keyboard": [
            [
                {"text": "\u2795 Buy/Add", "callback_data": f"flow:buy:token:{slug}:{symbol}"},
                {"text": "\u2796 Sell", "callback_data": f"flow:sell:token:{slug}"},
            ],
            [
                {"text": "\u2b50 Watchlist", "callback_data": f"watchlist:add:{slug}"},
                {"text": "\U0001f4ca Position", "callback_data": f"cmd:position:{symbol}"},
            ],
            [
                {"text": "\U0001f4a1 CoinGecko",
                 "url": f"https://www.coingecko.com/en/coins/{slug}"},
                {"text": "\U0001f4c8 DexScreener",
                 "url": f"https://dexscreener.com/search?q={slug}"},
            ],
        ]
    }


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
    _poll_start = time.time()
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
            else:
                active = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
                if active:
                    _handle_session_text(text)
    except requests.exceptions.ReadTimeout:
        pass
    except Exception as e:
        logger.error(f"Poll error: {e}")
    finally:
        _poll_elapsed = (time.time() - _poll_start) * 1000
        if config.ENABLE_PERFORMANCE_LOGS and _poll_elapsed > 100:
            logger.info(f"POLL: {_poll_elapsed:.0f}ms")


def handle_callback(cb):
    _start = time.time()
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
        for i, p in enumerate(parts):
            btns = None
            if i == len(parts) - 1 and results:
                first = results[0]
                slug = first.get("slug", first.get("symbol", "")).lower()
                symbol = (first.get("symbol") or slug).upper()
                btns = trading_ui.build_token_menu_buttons(slug, symbol)
            send_message(p, buttons=btns)
            time.sleep(0.3)
    elif cb_data == "cmd:early":
        results = social_scanner.get_early(limit=10)
        parts = format_early_list(results)
        for i, p in enumerate(parts):
            btns = None
            if i == len(parts) - 1 and results:
                first = results[0]
                slug = first.get("slug", first.get("symbol", "")).lower()
                symbol = (first.get("symbol") or slug).upper()
                btns = trading_ui.build_token_menu_buttons(slug, symbol)
            send_message(p, buttons=btns)
            time.sleep(0.3)
    elif cb_data == "cmd:buy":
        send_message("Usa: /buy <symbol> <quantity> <price> [fee]\nEj: /buy TAO 1.5 390")
    elif cb_data == "cmd:sell":
        send_message("Usa: /sell <symbol> <quantity> <price> [fee]\nEj: /sell TAO 1 420")
    elif cb_data == "cmd:hype":
        results = social_scanner.get_hype(limit=10)
        msg = format_hype_list(results)
        btns = None
        if results:
            first = results[0]
            slug = first.get("slug", first.get("symbol", "")).lower()
            symbol = (first.get("symbol") or slug).upper()
            btns = trading_ui.build_token_menu_buttons(slug, symbol)
        send_message(msg, buttons=btns)
    elif cb_data == "cmd:watchlist":
        settings = storage.load_settings()
        wl = settings.get("watchlist", {})
        msg = format_watchlist(wl)
        send_message(msg)
    elif cb_data == "flow:cancel":
        session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)
        send_message("\u274c Operacion cancelada.")
    elif cb_data == "cmd:tx":
        syms = [p["symbol"] for p in portfolio_db.get_active_positions()]
        if syms:
            send_message("Usa: /transactions <symbol>\nTokens: " + ", ".join(syms))
        else:
            send_message("No hay tokens activos en el portafolio")
    elif cb_data == "cmd:cash":
        balance = portfolio_db.get_cash_balance()
        send_message(f"\U0001f4b0 Efectivo disponible: {format_usd(balance)}")

    # ── FLOW CALLBACKS (from menu buttons) ──
    elif cb_data == "flow:buy:select_source":
        session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)
        session_mgr.create_session(config.TELEGRAM_CHAT_ID, "buy_waiting",
            {"step": "waiting_token_input"})
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_token_input")
        send_message(trading_ui.buy_flow_start_text(),
                     buttons=trading_ui.buy_flow_start_buttons())

    elif cb_data == "flow:sell:select":
        positions = portfolio_db.get_active_positions()
        if not positions:
            send_message("No hay posiciones activas para vender.")
            return
        send_message(trading_ui.sell_flow_start_text(),
                     buttons=trading_ui.sell_flow_position_buttons())

    elif cb_data == "flow:search":
        session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)
        session_mgr.create_session(config.TELEGRAM_CHAT_ID, "search_token",
            {"step": "waiting_query"})
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_query")
        send_message("\U0001f50e <b>Buscar Token</b>\n\nEscribe el nombre, simbolo o ID del token:")

    elif cb_data.startswith("flow:buy:token:"):
        parts = cb_data.split(":")
        slug = parts[3] if len(parts) > 3 else ""
        sym = parts[4] if len(parts) > 4 else slug.upper()
        _handle_buy_callback(f"buy:resolve:{slug}:{sym}")

    elif cb_data.startswith("flow:sell:token:"):
        parts = cb_data.split(":")
        slug = parts[3] if len(parts) > 3 else ""
        sym = slug.upper()
        _handle_sell_callback(f"sell:select:{slug}:{sym}")

    elif cb_data.startswith("flow:buy:select_result:"):
        parts = cb_data.split(":")
        slug = parts[3] if len(parts) > 3 else ""
        sym = parts[4] if len(parts) > 4 else slug.upper()
        _handle_buy_callback(f"buy:resolve:{slug}:{sym}")

    # ── BUY FLOW CALLBACKS ──
    elif cb_data.startswith("buy:"):
        _handle_buy_callback(cb_data)

    # ── SELL FLOW CALLBACKS ──
    elif cb_data.startswith("sell:"):
        _handle_sell_callback(cb_data)

    # ── DUMPS CALLBACKS ──
    elif cb_data.startswith("dumps:"):
        _handle_dumps_callback(cb_data)

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

    # ── REFRESH CALLBACKS ──
    elif cb_data.startswith("refresh:"):
        target = cb_data.split(":", 1)[1]
        cmd_map = {
            "dumps": "/dumps",
            "gainers": "/gainers",
            "losers": "/losers",
            "top": "/top",
            "trends": "/trends",
            "early": "/early",
            "hype": "/hype",
            "portafolio": "/portafolio",
            "portfolio": "/portafolio",
        }
        if target in cmd_map:
            # Clear relevant cache
            if target in ("dumps",):
                cache.get_dumps_cache().clear()
            elif target in ("gainers", "losers", "top"):
                cache.get_market_cache().clear()
            elif target in ("trends", "early", "hype"):
                cache.get_social_cache().clear()
            handle_command(cmd_map[target])

    try:
        session.post(_api_url("answerCallbackQuery"), json={
            "callback_query_id": cb["id"], "text": "Done",
        }, timeout=10)
    except Exception:
        pass
    finally:
        _dur_ms = (time.time() - _start) * 1000
        if _dur_ms > config.SLOW_COMMAND_THRESHOLD_MS:
            logger.warning(f"SLOW_CALLBACK {cb_data}: {_dur_ms:.0f}ms")
        if config.ENABLE_PERFORMANCE_LOGS:
            logger.info(f"CALLBACK {cb_data}: {_dur_ms:.0f}ms")


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


def show_menu():
    send_message(_main_menu(), buttons=_main_menu_buttons())


def _flow_cancel_handler():
    session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)
    send_message("\u274c Operacion cancelada.")


def handle_command(text):
    global _first_response_time, _loading_msg_id
    _first_response_time = None
    _loading_msg_id = None
    _start = time.time()
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
            send_loading("\U0001f4ca <b>Calculating portfolio...</b>")
            send_portfolio_report()

        elif cmd in ("/menu", "/start"):
            send_loading("\U0001f3e0 <b>Loading menu...</b>")
            show_menu()

        elif cmd == "/cancel":
            _flow_cancel_handler()

        elif cmd in ("/search", "/precio", "/buscar"):
            mid = send_loading("\U0001f50e <b>Looking up token...</b>")
            query = " ".join(args)
            cached_key = f"token_menu:{query.lower()}"
            cached = cache.get_menu_cache().get(cached_key)
            if cached:
                edit_message(cached[0], message_id=mid, buttons=cached[1])
                return
            resolved = trading_ui.resolve_token(query)
            if not resolved:
                edit_message(f"\u274c <b>{query}</b> no encontrado. Intenta con otro nombre o ID.", message_id=mid)
                return
            msg = trading_ui.build_token_menu_text(resolved, config.TELEGRAM_CHAT_ID)
            btns = trading_ui.build_token_menu_buttons(resolved.get("slug", resolved.get("symbol", query).lower()), resolved.get("symbol", query.upper()))
            try:
                cache.get_menu_cache().set(cached_key, (msg, btns), ttl=config.TOKEN_MENU_CACHE_TTL)
            except Exception:
                pass
            edit_message(msg, message_id=mid, buttons=btns)

        elif cmd == "/top":
            mid = send_loading("\U0001f4ca <b>Loading top coins...</b>")
            cached = cache.get_market_cache().get("top")
            if cached:
                edit_message(cached, message_id=mid)
                return
            coins = fetch_market_coins(page=1, per_page=10)
            if coins:
                msg = format_top_list(coins)
                cache.get_market_cache().set("top", msg, ttl=120)
                edit_message(msg, message_id=mid)
            else:
                edit_message(format_api_error("CoinGecko"), message_id=mid, buttons=_refresh_button("top"))

        elif cmd == "/gainers":
            mid = send_loading("\U0001f7e2 <b>Loading gainers...</b>")
            cached = cache.get_market_cache().get("gainers")
            if cached:
                edit_message("\n".join(cached) if isinstance(cached, list) else cached, message_id=mid)
                return
            coins = fetch_market_coins(page=1, per_page=250)
            if coins:
                valid = [c for c in coins if c.get("price_change_percentage_24h") is not None]
                top = sorted(valid, key=lambda x: x["price_change_percentage_24h"], reverse=True)[:10]
                parts = format_gainers_losers(top, [])
                cache.get_market_cache().set("gainers", parts, ttl=120)
                edit_message("\n".join(parts) if isinstance(parts, list) else parts, message_id=mid)
            else:
                edit_message(format_api_error("CoinGecko"), message_id=mid, buttons=_refresh_button("gainers"))

        elif cmd == "/losers":
            mid = send_loading("\U0001f534 <b>Loading losers...</b>")
            cached = cache.get_market_cache().get("losers")
            if cached:
                edit_message("\n".join(cached) if isinstance(cached, list) else cached, message_id=mid)
                return
            coins = fetch_market_coins(page=1, per_page=250)
            if coins:
                valid = [c for c in coins if c.get("price_change_percentage_24h") is not None]
                top = sorted(valid, key=lambda x: x["price_change_percentage_24h"])[:10]
                parts = format_gainers_losers([], top)
                cache.get_market_cache().set("losers", parts, ttl=120)
                edit_message("\n".join(parts) if isinstance(parts, list) else parts, message_id=mid)
            else:
                edit_message(format_api_error("CoinGecko"), message_id=mid, buttons=_refresh_button("losers"))

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
            if not args:
                session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)
                session_mgr.create_session(config.TELEGRAM_CHAT_ID, "buy_waiting",
                    {"step": "waiting_token_input"})
                session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_token_input")
                send_message(trading_ui.buy_flow_start_text(),
                             buttons=trading_ui.buy_flow_start_buttons())
                return
            if len(args) == 1:
                send_message(
                    "\u274c Incomplete advanced command.\n\n"
                    "You can use guided mode:\n/buy\n\n"
                    "Or use full format:\n/buy <symbol> <quantity> <price_usd> [fee_usd]"
                )
                return
            sym = args[0].upper()
            try:
                qty = float(args[1])
                price = float(args[2])
            except (ValueError, IndexError):
                send_message("\u274c Cantidad y precio deben ser numeros.\nEj: /buy TAO 1.5 390")
                return
            if qty <= 0 or price <= 0:
                send_message("\u274c Cantidad y precio deben ser positivos")
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
                    send_message(f"\u274c {sym} no encontrado. Usa /addtoken {sym} <coin_id> primero")
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
                f"Token: {sym} \u2014 {updated.get('name', '')}\n"
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
            if not args:
                positions = portfolio_db.get_active_positions()
                if not positions:
                    send_message("No hay posiciones activas para vender.")
                    return
                session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)
                send_message(trading_ui.sell_flow_start_text(),
                             buttons=trading_ui.sell_flow_position_buttons())
                return
            if len(args) == 1:
                send_message(
                    "\u274c Incomplete advanced command.\n\n"
                    "You can use guided mode:\n/sell\n\n"
                    "Or use full format:\n/sell <symbol> <quantity> <price_usd> [fee_usd]"
                )
                return
            sym = args[0].upper()
            try:
                qty = float(args[1])
                price = float(args[2])
            except (ValueError, IndexError):
                send_message("\u274c Cantidad y precio deben ser numeros.\nEj: /sell TAO 1 420")
                return
            if qty <= 0 or price <= 0:
                send_message("\u274c Cantidad y precio deben ser positivos")
                return
            fee = float(args[3]) if len(args) > 3 else 0
            send_processing()

            pos = portfolio_db.get_position(sym)
            if not pos:
                send_message(f"\u274c {sym} no esta en tu portafolio.\nUsa /buy {sym} <qty> <price> para comprar primero")
                return
            if qty > pos["quantity"]:
                send_message(
                    f"\u274c No puedes vender mas de lo que tienes.\n\n"
                    f"{sym} disponible: {pos['quantity']:.4f}\n"
                    f"Intentaste vender: {qty:.4f}"
                )
                return

            result = portfolio_db.update_position_after_sell(sym, qty, price, fee)
            if result is None:
                send_message("\u274c Error al procesar la venta")
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
                f"Token: {sym} \u2014 {updated.get('name', '')}\n"
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
            mid = send_loading(f"\U0001f4ca <b>Loading {sym} position...</b>")
            pos = portfolio_db.get_position(sym)
            if not pos:
                edit_message(f"\u274c {sym} no esta en tu portafolio activo", message_id=mid)
                return

            cached_price = cache.get_price_cache().get(f"price:{pos['coin_id']}")
            prices = {}
            if cached_price:
                prices = cached_price
            else:
                from .coingecko_client import fetch_market_coins_by_ids
                try:
                    market_data = fetch_market_coins_by_ids([pos["coin_id"]], changes="1h,24h,7d")
                    if market_data:
                        prices = market_data[0]
                        cache.get_price_cache().set(f"price:{pos['coin_id']}", prices, ttl=config.TOKEN_PRICE_CACHE_TTL)
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
            edit_message(msg, message_id=mid, buttons=buttons)

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
            mid = send_loading("\U0001f4b0 <b>Calculating cash summary...</b>")
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
            edit_message(msg, message_id=mid)

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

        elif cmd == "/dumps":
            mid = send_loading("\U0001f4c9 <b>Loading Top Losers...</b>")
            window = args[0] if args else config.DUMPS_DEFAULT_WINDOW
            if window not in config.DUMPS_WINDOWS:
                edit_message(f"Ventana invalida. Opciones: {', '.join(config.DUMPS_WINDOWS)}", message_id=mid)
                return
            cached_key = f"dumps:{window}:{config.DUMPS_LIMIT}"
            cached = cache.get_dumps_cache().get(cached_key)
            if cached:
                edit_message(cached["text"], message_id=mid, buttons=cached.get("buttons"))
                return
            coins = trading_ui.get_dumps_data(window)
            if coins is None:
                edit_message("\u26a0\ufe0f No se pudieron obtener datos. Intenta de nuevo.", message_id=mid, buttons=_refresh_button(f"dumps:{window}"))
                return
            msg = trading_ui.build_dumps_text(coins, window)
            btns = trading_ui.build_dumps_buttons(coins, window)
            cache.get_dumps_cache().set(cached_key, {"text": msg, "buttons": btns}, ttl=config.DUMPS_CACHE_TTL)
            edit_message(msg, message_id=mid, buttons=btns)

        elif cmd == "/debugtoken":
            send_processing()
            query = " ".join(args)
            if not query:
                send_message("\u274c Uso: /debugtoken <query>\nEj: /debugtoken 0x8408d45b61f5823298f19a09b53b7339c0280489")
                return
            debug = trading_ui.resolve_token_debug(query)
            lines = [
                f"\U0001f50e <b>Token Resolve Debug</b>\n",
                f"Input: {debug.get('input','')}",
                f"Detected family: {debug.get('family','?')}",
                f"Resolver used: {debug.get('resolver_used','none')}",
            ]
            sel = debug.get("selected")
            if sel:
                lines.append(f"\n<b>Selected:</b>")
                lines.append(f"Symbol: {sel.get('symbol','?')}")
                lines.append(f"Name: {sel.get('name','?')}")
                if sel.get("chain_id"):
                    lines.append(f"Chain: {sel.get('chain_id')}")
                if sel.get("dex_id"):
                    lines.append(f"DEX: {sel.get('dex_id')}")
                if sel.get("contract_address"):
                    lines.append(f"Contract: <code>{sel['contract_address'][:20]}...</code>")
                if sel.get("pair_address"):
                    lines.append(f"Pair: <code>{sel['pair_address'][:20]}...</code>")
                if sel.get("price_usd"):
                    lines.append(f"Price: ${sel.get('price_usd')}")
                if sel.get("liquidity_usd"):
                    lines.append(f"Liquidity: ${float(sel['liquidity_usd']):,.2f}")
                if sel.get("volume_h24"):
                    lines.append(f"Volume 24h: ${float(sel['volume_h24']):,.2f}")
                if sel.get("dex_url"):
                    lines.append(f"URL: {sel['dex_url']}")
                lines.append(f"Resolved: \u2705")
            elif debug.get("matches"):
                lines.append(f"\nMatches: {len(debug.get('matches',[]))}")
                for i, m in enumerate(debug["matches"][:5], 1):
                    lines.append(f"{i}. {m.get('symbol','?')} - {m.get('name','?')} ({m.get('chain_id','?')})")
            else:
                lines.append(f"\nResolved: \u274c")
                lines.append("No results found from any resolver.")
            send_message("\n".join(lines))

        elif cmd == "/testcontracts":
            send_processing()
            _run_contract_tests()

        elif cmd == "/trends":
            mid = send_loading("\U0001f525 <b>Loading Trends...</b>")
            cached = cache.get_social_cache().get("trends")
            if cached:
                text = "\n".join(cached) if isinstance(cached, list) else cached
                edit_message(text, message_id=mid)
                return
            results = social_scanner.get_trends(limit=15)
            if not results:
                edit_message("\u26a0\ufe0f No cached data available yet.\nI am refreshing data now. Try again shortly.", message_id=mid)
                return
            parts = format_trends_list(results)
            cache.get_social_cache().set("trends", parts, ttl=config.TRENDS_CACHE_TTL)
            text = "\n".join(parts) if isinstance(parts, list) else parts
            btns = None
            if results:
                first = results[0]
                slug = first.get("slug", first.get("symbol", "")).lower()
                symbol = (first.get("symbol") or slug).upper()
                btns = trading_ui.build_token_menu_buttons(slug, symbol)
            if btns:
                btns["inline_keyboard"].append([{"text": "\U0001f504 Force Refresh", "callback_data": "refresh:trends"}])
            else:
                btns = {"inline_keyboard": [[{"text": "\U0001f504 Force Refresh", "callback_data": "refresh:trends"}]]}
            edit_message(text, message_id=mid, buttons=btns)

        elif cmd == "/early":
            mid = send_loading("\U0001f7e2 <b>Loading Early Signals...</b>")
            cached = cache.get_social_cache().get("early")
            if cached:
                text = "\n".join(cached) if isinstance(cached, list) else cached
                edit_message(text, message_id=mid)
                return
            results = social_scanner.get_early(limit=15)
            if not results:
                edit_message("\u26a0\ufe0f No cached data available yet.\nI am refreshing data now. Try again shortly.", message_id=mid)
                return
            parts = format_early_list(results)
            cache.get_social_cache().set("early", parts, ttl=config.TRENDS_CACHE_TTL)
            text = "\n".join(parts) if isinstance(parts, list) else parts
            btns = None
            if results:
                first = results[0]
                slug = first.get("slug", first.get("symbol", "")).lower()
                symbol = (first.get("symbol") or slug).upper()
                btns = trading_ui.build_token_menu_buttons(slug, symbol)
            if btns:
                btns["inline_keyboard"].append([{"text": "\U0001f504 Force Refresh", "callback_data": "refresh:early"}])
            else:
                btns = {"inline_keyboard": [[{"text": "\U0001f504 Force Refresh", "callback_data": "refresh:early"}]]}
            edit_message(text, message_id=mid, buttons=btns)

        elif cmd == "/hype":
            mid = send_loading("\u26a0\ufe0f <b>Loading Hype Signals...</b>")
            cached = cache.get_social_cache().get("hype")
            if cached:
                edit_message(cached, message_id=mid)
                return
            results = social_scanner.get_hype(limit=10)
            if not results:
                edit_message("\u26a0\ufe0f No cached data available yet.\nI am refreshing data now. Try again shortly.", message_id=mid)
                return
            msg = format_hype_list(results)
            cache.get_social_cache().set("hype", msg, ttl=config.HYPE_CACHE_TTL)
            btns = None
            if results:
                first = results[0]
                slug = first.get("slug", first.get("symbol", "")).lower()
                symbol = (first.get("symbol") or slug).upper()
                btns = trading_ui.build_token_menu_buttons(slug, symbol)
            if btns:
                btns["inline_keyboard"].append([{"text": "\U0001f504 Force Refresh", "callback_data": "refresh:hype"}])
            else:
                btns = {"inline_keyboard": [[{"text": "\U0001f504 Force Refresh", "callback_data": "refresh:hype"}]]}
            edit_message(msg, message_id=mid, buttons=btns)

        elif cmd == "/perftest":
            mid = send_loading("\U0001f9e0 <b>Running performance test...</b>")
            slugs = ["all-oracle", "troll-face", "bonk"]
            lines = ["\U0001f9e0 <b>Performance Test</b>\n"]
            total = 0.0
            for s in slugs:
                t0 = time.time()
                tok = trading_ui.resolve_token(s)
                dt = (time.time() - t0) * 1000
                total += dt
                ok = "\u2705" if tok else "\u274c"
                lines.append(f"{ok} {s}: {dt:.0f}ms")
            lines.append(f"\n<b>Total:</b> {total:.0f}ms | <b>Avg:</b> {total/len(slugs):.0f}ms")
            lines.append(f"\n<b>Cache:</b> hit rate {cache.get_global_hit_rate():.1%}")
            s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
            if s:
                lines.append(f"\n<b>Active session:</b> flow={s.get('flow', 'none')}, step={s.get('step', 'none')}")
            edit_message("\n".join(lines), message_id=mid)

        elif cmd == "/testflows":
            if not config.TEST_MODE:
                send_message("\u26a0\ufe0f Solo disponible en TEST_MODE=true")
                return
            mid = send_loading("\U0001f9ea <b>Testing flows...</b>")
            msg_parts = ["\U0001f9ea <b>Flow Test</b>\n"]
            from session import parse_positive_decimal
            test_vals = ["100", "50,5", "-10", "abc"]
            msg_parts.append("<b>parse_positive_decimal tests:</b>")
            for v in test_vals:
                r = parse_positive_decimal(v)
                msg_parts.append(f"  '{v}' -> {r}")
            msg_parts.append("")
            s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
            if s:
                msg_parts.append(f"<b>Active session:</b> flow={s.get('flow')}, step={s.get('step')}")
                msg_parts.append(f"  slug={s['data'].get('slug')}, source={s['data'].get('source')}")
            else:
                msg_parts.append("No active session.")
            msg_parts.append("")
            msg_parts.append("<b>Cache stats:</b>")
            msg_parts.append(f"  Hit rate: {cache.get_global_hit_rate():.1%}")
            edit_message("\n".join(msg_parts), message_id=mid)

        elif cmd == "/status":
            mid = send_loading("\u2699\ufe0f <b>Checking bot status...</b>")
            stats = get_api_stats()
            perf = _get_perf_summary()
            if isinstance(perf, dict):
                lines = [
                    f"<b>\u2699\ufe0f Performance:</b>",
                    f"Avg first response: {perf['avg_first_ms']:.0f}ms" if perf['avg_first_ms'] < 1000 else f"Avg first response: {perf['avg_first_ms']/1000:.1f}s",
                    f"Avg final response: {perf['avg_total_ms']:.0f}ms" if perf['avg_total_ms'] < 1000 else f"Avg final response: {perf['avg_total_ms']/1000:.1f}s",
                    f"P95 final response: {perf['p95_total_ms']:.0f}ms" if perf['p95_total_ms'] < 1000 else f"P95 final response: {perf['p95_total_ms']/1000:.1f}s",
                    f"Cache hit rate: {perf['cache_hit_rate']}%",
                    f"Slowest command: {perf['slowest_cmd']} ({perf['slowest_ms']:.0f}ms)",
                    f"Total commands recorded: {perf['total_recorded']}",
                ]
                lines.append(f"\n{stats}" if isinstance(stats, str) else "")
                msg = "\n".join(lines)
            else:
                msg = f"{stats}\n\n{perf}"
            edit_message(msg, message_id=mid)

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
    finally:
        _dur_ms = (time.time() - _start) * 1000
        _first_ms = (_first_response_time - _start) * 1000 if _first_response_time else _dur_ms
        if _dur_ms > config.SLOW_COMMAND_THRESHOLD_MS:
            logger.warning(f"SLOW_COMMAND {cmd}: {_dur_ms:.0f}ms")
        if config.ENABLE_PERFORMANCE_LOGS:
            logger.info(f"CMD {cmd}: first={_first_ms:.0f}ms total={_dur_ms:.0f}ms")
        _perf_record(cmd, _first_ms, _dur_ms)


def _cancel_button():
    return {"inline_keyboard": [[{"text": "\u274c Cancelar", "callback_data": "flow:cancel"}]]}


def _price_buttons():
    return {
        "inline_keyboard": [
            [{"text": "\u2705 Usar precio actual", "callback_data": "flow:buy:use_current"}],
            [{"text": "\u270f\ufe0f Ingresar precio manual", "callback_data": "flow:buy:ask_manual"}],
            [{"text": "\u274c Cancelar", "callback_data": "flow:cancel"}],
        ]
    }


def _handle_session_text(text):
    active = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
    if not active:
        return
    flow = active.get("flow", "")
    step = active.get("step", "")
    data = active.get("data", {})

    if flow == "buy":
        if step == "waiting_token_query":
            matches = search_coins(text)
            if not matches:
                send_message(f"No se encontro <b>{text}</b>. Intenta con otro nombre o ID.",
                             buttons=_cancel_button())
                return
            if len(matches) == 1:
                coin = matches[0]
                session_mgr.set_data(config.TELEGRAM_CHAT_ID, "coin_id", coin["id"])
                session_mgr.set_data(config.TELEGRAM_CHAT_ID, "symbol", coin["symbol"].upper())
                session_mgr.set_data(config.TELEGRAM_CHAT_ID, "name", coin["name"])
                session_mgr.set_step(config.TELEGRAM_CHAT_ID, "token_selected")
                _flow_buy_show_token(coin["id"], coin["symbol"].upper())
                return
            lines = [f"<b>Resultados para \"{text}\":</b>\n"]
            buttons = {"inline_keyboard": []}
            for i, m in enumerate(matches[:8], 1):
                lines.append(
                    f"{i}. <b>{m['symbol'].upper()}</b> — {m['name']} ({m['id']})"
                )
                buttons["inline_keyboard"].append([
                    {"text": f"{m['symbol'].upper()} — {m['name']}",
                     "callback_data": f"flow:buy:select_result:{m['id']}:{m['symbol'].upper()}:{m['name']}"}
                ])
            buttons["inline_keyboard"].append([
                {"text": "\U0001f50d Buscar otra vez",
                 "callback_data": "flow:buy:search"},
                {"text": "\u274c Cancelar", "callback_data": "flow:cancel"}
            ])
            send_message("\n".join(lines), buttons=buttons)

        elif step == "waiting_quantity":
            try:
                qty = float(text.replace(",", "."))
            except ValueError:
                send_message("\u274c La cantidad debe ser un numero.\nEj: 1.5")
                return
            if qty <= 0:
                send_message("\u274c La cantidad debe ser positiva.\nEj: 1.5")
                return
            session_mgr.set_data(config.TELEGRAM_CHAT_ID, "quantity", qty)
            session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_price")
            current = data.get("current_price")
            price_hint = f"Precio actual estimado: {format_usd(current)}" if current else "Ej: 390"
            send_message(
                f"\U0001f4b5 <b>Precio de compra</b>\n\n"
                f"\u00bfA que precio compraste cada token?\n{price_hint}",
                buttons=_price_buttons()
            )

        elif step == "waiting_price":
            try:
                price = float(text.replace(",", "."))
            except ValueError:
                send_message("\u274c El precio debe ser un numero.\nEj: 390")
                return
            if price <= 0:
                send_message("\u274c El precio debe ser positivo.\nEj: 390")
                return
            session_mgr.set_data(config.TELEGRAM_CHAT_ID, "price", price)
            _flow_buy_ask_fee()

        elif step == "waiting_fee":
            try:
                fee = float(text.replace(",", "."))
            except ValueError:
                send_message("\u274c El fee debe ser un numero.\nEj: 2.50 o 0")
                return
            if fee < 0:
                send_message("\u274c El fee no puede ser negativo.")
                return
            session_mgr.set_data(config.TELEGRAM_CHAT_ID, "fee", fee)
            _flow_buy_confirm()

    elif flow == "sell":
        if step == "waiting_sell_amount":
            try:
                qty = float(text.replace(",", "."))
            except ValueError:
                send_message("\u274c La cantidad debe ser un numero.\nEj: 1.5")
                return
            slug = data.get("coin_id", "")
            pos = portfolio_db.get_position(slug) if slug else None
            if not pos:
                send_message("Posicion no encontrada.")
                return
            if qty <= 0:
                send_message("\u274c La cantidad debe ser positiva.")
                return
            if qty > pos["quantity"]:
                send_message(
                    f"\u274c No puedes vender mas de lo que tienes.\n"
                    f"Disponible: {pos['quantity']:.4f}"
                )
                return
            session_mgr.set_data(config.TELEGRAM_CHAT_ID, "quantity", qty)
            _flow_sell_ask_price()

        elif step == "waiting_sell_price":
            try:
                price = float(text.replace(",", "."))
            except ValueError:
                send_message("\u274c El precio debe ser un numero.\nEj: 420")
                return
            if price <= 0:
                send_message("\u274c El precio debe ser positivo.")
                return
            session_mgr.set_data(config.TELEGRAM_CHAT_ID, "price", price)
            _flow_sell_ask_fee()

        elif step == "waiting_sell_fee":
            try:
                fee = float(text.replace(",", "."))
            except ValueError:
                send_message("\u274c El fee debe ser un numero.\nEj: 1.50 o 0")
                return
            if fee < 0:
                send_message("\u274c El fee no puede ser negativo.")
                return
            session_mgr.set_data(config.TELEGRAM_CHAT_ID, "fee", fee)
            _flow_sell_confirm()

    elif flow == "search_token":
        matches = search_coins(text)
        if not matches:
            send_message(f"No se encontro <b>{text}</b>. Intenta con otro nombre.",
                         buttons=_cancel_button())
            return
        coin = matches[0]
        detail = fetch_coin_detail(coin["id"])
        if detail:
            msg = format_coin_detail(detail)
            send_message(msg, buttons=_token_action_buttons(coin["id"], coin["symbol"].upper(), coin["id"]))
        else:
            send_message(format_api_error("CoinGecko"))
        session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)


def _build_slug_symbol_from_data(data):
    return data.get("slug", ""), data.get("symbol", "")


# ── BUY FLOW HANDLER ────────────────────────────────────────────────────────

def _handle_buy_callback(cb_data):
    parts = cb_data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    slug = parts[2] if len(parts) > 2 else ""
    symbol = parts[3] if len(parts) > 3 else slug.upper()

    if action == "search":
        session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)
        session_mgr.create_session(config.TELEGRAM_CHAT_ID, "buy_waiting",
            {"step": "waiting_token_input"})
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_token_input")
        send_message(trading_ui.buy_flow_start_text(),
                     buttons=trading_ui.buy_flow_start_buttons())

    elif action in ("watchlist", "early", "trends"):
        if action == "watchlist":
            settings = storage.load_settings()
            wl = settings.get("watchlist", {})
            if not wl:
                send_message("Watchlist vacia.")
                return
            kb = []
            for wslug in wl:
                kb.append([{"text": wslug, "callback_data": f"buy:resolve:{wslug}:{wslug}"}])
            kb.append([{"text": "\u274c Close", "callback_data": "flow:cancel"}])
            send_message("Select from watchlist:", buttons={"inline_keyboard": kb})
        elif action == "early":
            results = social_scanner.get_early(limit=8)
            kb = []
            for r in results:
                s = r.get("symbol", r.get("slug", "?"))
                sl = r.get("slug", s)
                kb.append([{"text": f"{s} - {r.get('name', '')}",
                           "callback_data": f"buy:resolve:{sl}:{s}"}])
            kb.append([{"text": "\u274c Close", "callback_data": "flow:cancel"}])
            send_message("Select token:", buttons={"inline_keyboard": kb})
        elif action == "trends":
            results = social_scanner.get_trends(limit=8)
            kb = []
            for r in results:
                s = r.get("symbol", r.get("slug", "?"))
                sl = r.get("slug", s)
                kb.append([{"text": f"{s} - {r.get('name', '')}",
                           "callback_data": f"buy:resolve:{sl}:{s}"}])
            kb.append([{"text": "\u274c Close", "callback_data": "flow:cancel"}])
            send_message("Select token:", buttons={"inline_keyboard": kb})

    elif action == "resolve":
        sym = symbol.upper()
        send_message("\U0001f50e <b>Resolving token...</b>")
        token = trading_ui.resolve_token(slug)
        if not token:
            send_message(f"\u274c No se pudo resolver {slug}.")
            return
        sym = token.get("symbol", sym)
        slug = token.get("slug", slug)
        text = trading_ui.token_card_from_resolved(token, config.TELEGRAM_CHAT_ID)
        btns = trading_ui.buy_token_menu_buttons(slug, sym)
        session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)
        session_mgr.create_session(config.TELEGRAM_CHAT_ID, "buy_active", {
            "slug": slug, "symbol": sym, "name": token.get("name", sym),
            "current_price": token.get("current_price"),
            "token_key": token.get("token_key", ""),
            "source": token.get("source", "dexscreener"),
            "chain_id": token.get("chain_id", ""),
            "contract_address": token.get("contract_address", ""),
            "pair_address": token.get("pair_address", ""),
            "dex_id": token.get("dex_id", ""),
        }, step="token_menu")
        send_message(text, buttons=btns)

    elif action == "refresh":
        token = trading_ui.resolve_token(slug)
        if not token:
            send_message(f"No se pudo refrescar {symbol}.")
            return
        text = trading_ui.token_card_from_resolved(token, config.TELEGRAM_CHAT_ID)
        btns = trading_ui.buy_token_menu_buttons(slug, symbol)
        s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if s:
            session_mgr.set_data(config.TELEGRAM_CHAT_ID, "current_price", token.get("current_price"))
        send_message(text, buttons=btns)

    elif action in ("pos", "position"):
        token = trading_ui.resolve_token(slug)
        if not token:
            token = {"slug": slug, "symbol": symbol, "name": symbol}
        ptxt, pbtns = trading_ui.build_position_view(symbol, token)
        if pbtns:
            send_message(ptxt, buttons=pbtns)
        else:
            send_message(ptxt)

    elif action == "quick":
        amount_usd = float(parts[4]) if len(parts) > 4 else 0
        data = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if not data:
            return
        price = data["data"].get("current_price")
        if not price or price <= 0:
            send_message("Precio actual no disponible. Edita el precio manualmente.",
                         buttons=trading_ui.buy_price_buttons(slug, symbol))
            return
        qty = round(amount_usd / price, 6)
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "amount_usd", amount_usd)
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "quantity", qty)
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "price", price)
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "confirm_buy")
        msg = trading_ui.build_buy_confirm_text(slug, symbol, data["data"])
        btns = trading_ui.buy_confirm_buttons(slug, symbol)
        send_message(msg, buttons=btns)

    elif action == "custom":
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_buy_amount")
        send_message("\U0001f4b5 How much do you want to buy in USDT?\n\nExample:\n100")

    elif action == "askprice":
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_buy_price_input")
        price = None
        s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if s:
            price = s["data"].get("current_price")
        hint = f"Current detected price: {format_usd(price)}" if price else ""
        send_message(
            f"Purchase price:\n\n{hint}\n\nEnter a custom price in USD:")

    elif action == "usecurrent":
        s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if not s:
            return
        price = s["data"].get("current_price")
        if price and price > 0:
            session_mgr.set_data(config.TELEGRAM_CHAT_ID, "price", price)
            data = s["data"]
            amount = data.get("amount_usd", 0)
            if amount > 0 and "quantity" not in data:
                qty = round(amount / price, 6)
                session_mgr.set_data(config.TELEGRAM_CHAT_ID, "quantity", qty)
            session_mgr.set_step(config.TELEGRAM_CHAT_ID, "confirm_buy")
            msg = trading_ui.build_buy_confirm_text(slug, symbol, data)
            btns = trading_ui.buy_confirm_buttons(slug, symbol)
            send_message(msg, buttons=btns)
        else:
            send_message("Precio actual no disponible. Ingresa precio manual.",
                         buttons=trading_ui.buy_price_buttons(slug, symbol))

    elif action == "editprice":
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_buy_price_input")
        send_message("\u270f\ufe0f Enter purchase price:\n\nExample:\n418.20")

    elif action == "editamt":
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_buy_amount")
        send_message("\u270f\ufe0f Enter new amount in USDT:")

    elif action == "editfee":
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_buy_fee")
        send_message("\u270f\ufe0f Enter fee in USD (or 0):")

    elif action == "confirm":
        s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if not s:
            return
        msg = trading_ui.execute_buy(slug, symbol, s["data"])
        send_message(msg)


# ── SELL FLOW HANDLER ────────────────────────────────────────────────────────

def _handle_sell_callback(cb_data):
    parts = cb_data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    slug = parts[2] if len(parts) > 2 else ""
    symbol = parts[3] if len(parts) > 3 else slug.upper()

    if action == "select":
        pos = portfolio_db.get_position(symbol) if symbol else None
        if not pos:
            send_message(f"No position for {symbol}.")
            return
        text, price = trading_ui.sell_flow_position_text(slug, symbol)
        if not text:
            send_message("Position not found.")
            return
        session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)
        session_mgr.create_session(config.TELEGRAM_CHAT_ID, "sell_active", {
            "slug": slug, "symbol": symbol, "name": pos.get("name", symbol),
            "current_price": price, "quantity": pos["quantity"],
        })
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "position_selected")
        send_message(text, buttons=trading_ui.sell_pct_buttons(slug, symbol))

    elif action == "pct":
        pct = float(parts[4]) if len(parts) > 4 else 0
        s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if not s:
            return
        data = s["data"]
        qty = round(data.get("quantity", 0) * pct / 100, 6)
        price = data.get("current_price")
        if not price or price <= 0:
            send_message("Current price not available.",
                         buttons=trading_ui.sell_price_buttons(slug, symbol))
            return
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "quantity", qty)
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "price", price)
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "confirm_sell")
        msg = trading_ui.build_sell_confirm_text(slug, symbol, data)
        btns = trading_ui.sell_confirm_buttons(slug, symbol)
        send_message(msg, buttons=btns)

    elif action == "custom":
        s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if not s:
            return
        max_qty = s["data"].get("quantity", 0)
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_sell_qty")
        send_message(f"\U0001f4b5 Enter qty to sell (max: {max_qty:.6f}):")

    elif action == "askprice":
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_sell_price_input")
        price = None
        s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if s:
            price = s["data"].get("current_price")
        hint = f"Current detected price: {format_usd(price)}" if price else ""
        send_message(
            f"Sell price:\n\n{hint}\n\nEnter a custom price in USD:")

    elif action == "usecurrent":
        s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if not s:
            return
        price = s["data"].get("current_price")
        if price and price > 0:
            session_mgr.set_data(config.TELEGRAM_CHAT_ID, "price", price)
            data = s["data"]
            session_mgr.set_step(config.TELEGRAM_CHAT_ID, "confirm_sell")
            msg = trading_ui.build_sell_confirm_text(slug, symbol, data)
            btns = trading_ui.sell_confirm_buttons(slug, symbol)
            send_message(msg, buttons=btns)
        else:
            send_message("Current price not available. Enter manually.",
                         buttons=trading_ui.sell_price_buttons(slug, symbol))

    elif action == "refresh":
        pos = portfolio_db.get_position(symbol)
        if not pos:
            send_message(f"No position for {symbol}.")
            return
        text, price = trading_ui.sell_flow_position_text(slug, symbol)
        if text:
            send_message(text, buttons=trading_ui.sell_pct_buttons(slug, symbol))

    elif action == "editprice":
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_sell_price_edit")
        send_message("\u270f\ufe0f Enter new sell price in USD:")

    elif action == "editqty":
        s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if not s:
            return
        max_qty = s["data"].get("quantity", 0)
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_sell_qty")
        send_message(f"\u270f\ufe0f Enter new qty (max: {max_qty:.6f}):")

    elif action == "editfee":
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_sell_fee")
        send_message("\u270f\ufe0f Enter fee in USD (or 0):")

    elif action == "confirm":
        s = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
        if not s:
            return
        msg = trading_ui.execute_sell(slug, symbol, s["data"])
        if msg:
            send_message(msg)


# ── DUMPS HANDLER ───────────────────────────────────────────────────────────

_dumps_cache = {"coins": [], "window": config.DUMPS_DEFAULT_WINDOW}


def _handle_dumps_callback(cb_data):
    global _dumps_cache
    parts = cb_data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "window":
        window = parts[2] if len(parts) > 2 else config.DUMPS_DEFAULT_WINDOW
        coins = trading_ui.get_dumps_data(window)
        _dumps_cache = {"coins": coins, "window": window}
        msg = trading_ui.build_dumps_text(coins, window)
        btns = trading_ui.build_dumps_buttons(coins, window)
        send_message(msg, buttons=btns)

    elif action == "refresh":
        window = _dumps_cache.get("window", config.DUMPS_DEFAULT_WINDOW)
        coins = trading_ui.get_dumps_data(window)
        _dumps_cache = {"coins": coins, "window": window}
        msg = trading_ui.build_dumps_text(coins, window)
        btns = trading_ui.build_dumps_buttons(coins, window)
        send_message(msg, buttons=btns)

    elif action == "open":
        idx = int(parts[2]) - 1 if len(parts) > 2 else 0
        coins = _dumps_cache.get("coins", [])
        if idx < 0 or idx >= len(coins):
            return
        c = coins[idx]
        slug = c.get("slug", "")
        sym = c.get("symbol", "?")
        text, btns = trading_ui.build_dumps_token_menu(slug, sym)
        send_message(text, buttons=btns)

    elif action == "back":
        window = _dumps_cache.get("window", config.DUMPS_DEFAULT_WINDOW)
        coins = _dumps_cache.get("coins", [])
        if not coins:
            coins = trading_ui.get_dumps_data(window)
            _dumps_cache["coins"] = coins
        msg = trading_ui.build_dumps_text(coins, window)
        btns = trading_ui.build_dumps_buttons(coins, window)
        send_message(msg, buttons=btns)

    elif action == "close":
        send_message("Closed.")

    elif action in ("pos", "position"):
        slug = parts[2] if len(parts) > 2 else ""
        sym = parts[3] if len(parts) > 3 else slug.upper()
        token = trading_ui.resolve_token(slug)
        if not token:
            token = {"slug": slug, "symbol": sym, "name": sym}
        ptxt, pbtns = trading_ui.build_position_view(sym, token)
        if pbtns:
            send_message(ptxt, buttons=pbtns)
        else:
            send_message(ptxt)

    elif action == "research":
        slug = parts[2] if len(parts) > 2 else ""
        sym = parts[3] if len(parts) > 3 else slug.upper()
        token = trading_ui.resolve_token(slug)
        if not token:
            token = {"slug": slug, "symbol": sym, "name": sym}
        rtxt, rbtns = trading_ui.build_research_view(sym, token)
        send_message(rtxt, buttons=rbtns)

    elif action == "tokenrefresh":
        slug = parts[2] if len(parts) > 2 else ""
        sym = parts[3] if len(parts) > 3 else slug.upper()
        token = trading_ui.resolve_token(slug)
        if not token:
            send_message(f"No se pudo refrescar {sym}.")
            return
        text, btns = trading_ui.build_dumps_token_menu(slug, sym)
        send_message(text, buttons=btns)

    elif action == "watchlist":
        slug = parts[2] if len(parts) > 2 else ""
        settings = storage.load_settings()
        wl = settings.setdefault("watchlist", {})
        if slug not in wl:
            wl[slug] = {"symbol": parts[3] if len(parts) > 3 else slug, "alert_thresholds": {}}
            storage.save_settings(settings)


# ── SESSION TEXT HANDLERS ────────────────────────────────────────────────────

def _handle_buy_waiting_text(text):
    active = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
    if not active or active.get("flow") != "buy_waiting":
        return False
    step = active.get("step", "")
    data = active.get("data", {})

    if step == "waiting_token_input":
        send_message("\U0001f50e <b>Resolving token...</b>")
        token = trading_ui.resolve_token(text)
        if not token:
            send_message(f"\u274c No se encontro <b>{text}</b>. Intenta con otro nombre o ID.",
                         buttons={"inline_keyboard": [[
                             {"text": "\u274c Cancel", "callback_data": "flow:cancel"}
                         ]]})
            return True
        sym = token.get("symbol", text.upper())
        slug = token.get("slug", text.lower())
        card = trading_ui.token_card_from_resolved(token, config.TELEGRAM_CHAT_ID)
        btns = trading_ui.buy_token_menu_buttons(slug, sym)
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "slug", slug)
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "symbol", sym)
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "name", token.get("name", sym))
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "current_price", token.get("current_price"))
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "token_key", token.get("token_key", ""))
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "source", token.get("source", "dexscreener"))
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "chain_id", token.get("chain_id", ""))
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "contract_address", token.get("contract_address", ""))
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "pair_address", token.get("pair_address", ""))
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "dex_id", token.get("dex_id", ""))
        session_mgr.cancel_session(config.TELEGRAM_CHAT_ID)
        session_mgr.create_session(config.TELEGRAM_CHAT_ID, "buy_active", {
            "slug": slug, "symbol": sym, "name": token.get("name", sym),
            "current_price": token.get("current_price"),
            "token_key": token.get("token_key", ""),
            "source": token.get("source", "dexscreener"),
            "chain_id": token.get("chain_id", ""),
            "contract_address": token.get("contract_address", ""),
            "pair_address": token.get("pair_address", ""),
            "dex_id": token.get("dex_id", ""),
        }, step="token_menu")
        send_message(card, buttons=btns)
        return True

    return False


def _handle_buy_active_text(text):
    active = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
    if not active or active.get("flow") != "buy_active":
        return False
    step = active.get("step", "")
    data = active.get("data", {})
    slug = data.get("slug", "")
    symbol = data.get("symbol", "")

    if step == "waiting_buy_amount":
        try:
            amount = float(text.replace(",", "."))
        except ValueError:
            send_message("Enter a valid number (e.g. 100).")
            return True
        if amount <= 0:
            send_message("Amount must be positive.")
            return True
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "amount_usd", amount)
        price = data.get("current_price")
        if price and price > 0:
            qty = round(amount / price, 6)
            session_mgr.set_data(config.TELEGRAM_CHAT_ID, "quantity", qty)
            # Show price options
            hint = f"Current detected price: {format_usd(price)}"
            send_message(
                f"Purchase price:\n\n{hint}\n\nUse current price or enter custom.",
                buttons=trading_ui.buy_price_buttons(slug, symbol))
        else:
            session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_buy_price_input")
            send_message("Enter purchase price in USD:")
        return True

    elif step == "waiting_buy_price_input":
        try:
            price = float(text.replace(",", "."))
        except ValueError:
            send_message("Enter a valid price.")
            return True
        if price <= 0:
            send_message("Price must be positive.")
            return True
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "price", price)
        if "quantity" not in data or not data["quantity"]:
            amount = data.get("amount_usd", 0)
            if amount > 0:
                qty = round(amount / price, 6)
                session_mgr.set_data(config.TELEGRAM_CHAT_ID, "quantity", qty)
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "confirm_buy")
        msg = trading_ui.build_buy_confirm_text(slug, symbol, data)
        btns = trading_ui.buy_confirm_buttons(slug, symbol)
        send_message(msg, buttons=btns)
        return True

    elif step == "waiting_buy_fee":
        try:
            fee = float(text.replace(",", "."))
        except ValueError:
            send_message("Enter a valid fee (e.g. 2.50).")
            return True
        if fee < 0:
            send_message("Fee cannot be negative.")
            return True
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "fee", fee)
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "confirm_buy")
        msg = trading_ui.build_buy_confirm_text(slug, symbol, data)
        btns = trading_ui.buy_confirm_buttons(slug, symbol)
        send_message(msg, buttons=btns)
        return True

    return False


def _handle_sell_active_text(text):
    active = session_mgr.get_session(config.TELEGRAM_CHAT_ID)
    if not active or active.get("flow") != "sell_active":
        return False
    step = active.get("step", "")
    data = active.get("data", {})
    slug = data.get("slug", "")
    symbol = data.get("symbol", "")

    if step == "waiting_sell_qty":
        try:
            qty = float(text.replace(",", "."))
        except ValueError:
            send_message("Enter a valid qty.")
            return True
        max_qty = data.get("quantity", 0)
        if qty <= 0 or qty > max_qty:
            send_message(f"Qty must be between 0 and {max_qty:.6f}.")
            return True
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "quantity", qty)
        price = data.get("current_price")
        if price and price > 0:
            hint = f"Current detected price: {format_usd(price)}"
            send_message(
                f"Sell price:\n\n{hint}\n\nUse current price or enter custom.",
                buttons=trading_ui.sell_price_buttons(slug, symbol))
        else:
            session_mgr.set_step(config.TELEGRAM_CHAT_ID, "waiting_sell_price_input")
            send_message("Enter sell price in USD:")
        return True

    elif step == "waiting_sell_price_input":
        try:
            price = float(text.replace(",", "."))
        except ValueError:
            send_message("Enter a valid price.")
            return True
        if price <= 0:
            send_message("Price must be positive.")
            return True
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "price", price)
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "confirm_sell")
        msg = trading_ui.build_sell_confirm_text(slug, symbol, data)
        btns = trading_ui.sell_confirm_buttons(slug, symbol)
        send_message(msg, buttons=btns)
        return True

    elif step == "waiting_sell_price_edit":
        try:
            price = float(text.replace(",", "."))
        except ValueError:
            send_message("Enter a valid price.")
            return True
        if price <= 0:
            send_message("Price must be positive.")
            return True
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "price", price)
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "confirm_sell")
        msg = trading_ui.build_sell_confirm_text(slug, symbol, data)
        btns = trading_ui.sell_confirm_buttons(slug, symbol)
        send_message(msg, buttons=btns)
        return True

    elif step == "waiting_sell_fee":
        try:
            fee = float(text.replace(",", "."))
        except ValueError:
            send_message("Enter a valid fee (e.g. 1.50).")
            return True
        if fee < 0:
            send_message("Fee cannot be negative.")
            return True
        session_mgr.set_data(config.TELEGRAM_CHAT_ID, "fee", fee)
        session_mgr.set_step(config.TELEGRAM_CHAT_ID, "confirm_sell")
        msg = trading_ui.build_sell_confirm_text(slug, symbol, data)
        btns = trading_ui.sell_confirm_buttons(slug, symbol)
        send_message(msg, buttons=btns)
        return True

    return False


# ── CONTRACT TESTS ──────────────────────────────────────────────────────────

TEST_CONTRACTS = [
    {"name": "ALLO", "symbol": "ALLO", "contract": "0x8408d45b61f5823298f19a09b53b7339c0280489"},
    {"name": "TROLL", "symbol": "TROLL", "contract": "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"},
    {"name": "bONK", "symbol": "bONK", "contract": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"},
]


def _run_contract_tests():
    send_processing()
    results = []
    for tc in TEST_CONTRACTS:
        result = _test_single_contract(tc)
        results.append(result)
        logger.info(f"TEST_CONTRACT token={tc['name']} result={'OK' if result.get('passed') else 'FAIL'}")

    lines = ["\U0001f9ea <b>Contract Search Test Results</b>\n"]
    for r in results:
        name = r.get("name", "?")
        passed = r.get("passed", False)
        icon = "\u2705" if passed else "\u274c"
        lines.append(f"{icon} <b>{name}</b>")
        lines.append(f"Input type: {r.get('family', '?')}")
        lines.append(f"Resolved: {'✅' if r.get('resolved') else '❌'}")
        if not r.get("resolved") and r.get("error"):
            lines.append(f"Reason: {r['error']}")
        if r.get("endpoint"):
            lines.append(f"Endpoint: {r['endpoint']}")
        if r.get("price"):
            lines.append(f"Price: ✅")
        if r.get("liquidity"):
            lines.append(f"Liquidity: ✅")
        lines.append(f"Buy flow: {'✅' if r.get('buy_ok') else '❌'}")
        lines.append(f"Sell flow: {'✅' if r.get('sell_ok') else '❌'}")
        lines.append("")

    send_message("\n".join(lines))
    return results


def _test_single_contract(tc):
    name = tc["name"]
    symbol = tc["symbol"]
    contract = tc["contract"]
    result = {"name": name, "symbol": symbol, "contract": contract,
              "passed": False, "resolved": False, "buy_ok": False,
              "sell_ok": False, "family": "?", "error": "", "endpoint": ""}

    family = trading_ui.detect_token_input_type(contract)
    result["family"] = family

    token = trading_ui.resolve_token(contract)
    if not token:
        result["error"] = "No se pudo resolver el contrato"
        return result

    result["resolved"] = True
    if token.get("chain_id"):
        result["endpoint"] = f"dexscreener:{token['chain_id']}"
    else:
        result["endpoint"] = "dexscreener:search"

    price = token.get("current_price")
    liq = token.get("liquidity_usd")
    if price:
        result["price"] = True
    if liq:
        result["liquidity"] = True

    old_test_mode = config.TEST_MODE
    try:
        config.TEST_MODE = True

        slug = token.get("slug", contract)
        sym = token.get("symbol", symbol)

        data = {
            "slug": slug, "symbol": sym, "name": token.get("name", name),
            "current_price": price, "quantity": 0,
            "amount_usd": 10, "price": price or 0.001,
            "fee": 0,
            "token_key": token.get("token_key", ""),
            "source": token.get("source", "dexscreener"),
            "chain_id": token.get("chain_id", ""),
            "contract_address": token.get("contract_address", ""),
            "pair_address": token.get("pair_address", ""),
            "dex_id": token.get("dex_id", ""),
        }

        msg = trading_ui.build_buy_confirm_text(slug, sym, data)
        if msg:
            result["buy_ok"] = True

        sell_data = {
            "slug": slug, "symbol": sym, "name": token.get("name", name),
            "quantity": 1, "price": price or 0.001,
            "fee": 0, "token_key": token.get("token_key", ""),
        }
        msg2 = trading_ui.build_sell_confirm_text(slug, sym, sell_data)
        if msg2:
            result["sell_ok"] = True

    except Exception as e:
        if not result.get("error"):
            result["error"] = str(e)
    finally:
        config.TEST_MODE = old_test_mode

    result["passed"] = all([
        result["resolved"],
        result.get("buy_ok"),
        result.get("sell_ok"),
    ])
    return result


# Patch _handle_session_text
_original_handle_session_text = _handle_session_text

def _patched_handle_session_text(text):
    if _handle_buy_waiting_text(text):
        return
    if _handle_buy_active_text(text):
        return
    if _handle_sell_active_text(text):
        return
    _original_handle_session_text(text)

_handle_session_text = _patched_handle_session_text
