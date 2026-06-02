import time
from datetime import datetime
from . import config
from .logger import logger
from .coingecko_client import fetch_all_market_coins, get_api_stats
from .alerts import check_alerts, save_price_snapshots as alerts_save_snapshots
from . import portfolio_db
from .telegram_bot import (
    poll_updates, send_alert, send_portfolio_report, send_startup_msg,
    delete_webhook, set_bot_commands, send_batch_hype_alerts, send_message,
)
from .social import scanner as social_scanner
from .database import models as db_models
from .jobs.price_snapshots import save_price_snapshots as db_save_snapshots
from .jobs.hourly_reports import get_hourly_report, should_send_report, reset_report_timer

last_crash_time = 0
last_portfolio_time = 0
last_social_scan_time = 0


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

        snapshots = alerts_save_snapshots(coins)
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


def run_social_scan():
    global last_social_scan_time
    now = time.time()
    if now - last_social_scan_time < config.SOCIAL_SCAN_INTERVAL:
        return
    last_social_scan_time = now
    logger.info("Running social trend scan...")
    try:
        social_scanner.run_scan()
        send_batch_hype_alerts()
    except Exception as e:
        logger.error(f"Social scan error: {e}")


def run_main_loop():
    global last_crash_time, last_portfolio_time, last_social_scan_time

    logger.info("Bot started — v3 modular")
    portfolio_db.init_db()
    portfolio_db.migrate_from_json()
    db_models.init_database()
    last_crash_time = time.time()
    last_portfolio_time = 0
    last_social_scan_time = 0

    delete_webhook()
    set_bot_commands()

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

        try:
            run_social_scan()
        except Exception as e:
            logger.error(f"Social scan error: {e}")

        try:
            db_save_snapshots()
        except Exception as e:
            logger.error(f"Price snapshot error: {e}")

        try:
            if should_send_report():
                report = get_hourly_report()
                if report:
                    send_message(report)
        except Exception as e:
            logger.error(f"Hourly report error: {e}")

        time.sleep(config.POLL_INTERVAL)
