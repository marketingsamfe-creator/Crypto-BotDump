import time
from datetime import datetime
from . import config
from .logger import logger
from .coingecko_client import fetch_all_market_coins, get_api_stats
from .alerts import check_alerts, save_price_snapshots
from .telegram_bot import (
    poll_updates, send_alert, send_portfolio_report, send_startup_msg,
    delete_webhook,
)

last_crash_time = 0
last_portfolio_time = 0


def run_crash_detection():
    global last_crash_time
    now = time.time()

    if now - last_crash_time < config.MONITOR_INTERVAL:
        return

    last_crash_time = now
    logger.info("Running crash detection...")

    try:
        coins = fetch_all_market_coins()
        if not coins:
            logger.warning("No coins fetched")
            return

        logger.info(f"Fetched {len(coins)} coins")

        snapshots = save_price_snapshots(coins)
        alerts = check_alerts(coins, snapshots)

        for alert in alerts:
            send_alert(alert)
            time.sleep(0.5)

        if alerts:
            logger.info(f"Alerts sent: {len(alerts)}")
        else:
            logger.info("No alerts triggered")

    except Exception as e:
        logger.error(f"Crash detection error: {e}")


def run_portfolio_report():
    global last_portfolio_time
    now = time.time()

    if now - last_portfolio_time < config.PORTFOLIO_INTERVAL:
        return

    last_portfolio_time = now
    logger.info("Sending hourly portfolio report...")
    send_portfolio_report()


def run_main_loop():
    global last_crash_time, last_portfolio_time

    logger.info("Bot started — v3 modular")
    last_crash_time = time.time()
    last_portfolio_time = 0

    delete_webhook()

    try:
        send_startup_msg()
    except Exception as e:
        logger.error(f"Startup message error: {e}")

    while True:
        try:
            poll_updates()
        except Exception as e:
            logger.error(f"Poll error: {e}")

        try:
            run_crash_detection()
        except Exception as e:
            logger.error(f"Crash detection error: {e}")

        try:
            run_portfolio_report()
        except Exception as e:
            logger.error(f"Portfolio report error: {e}")

        time.sleep(config.POLL_INTERVAL)
