from .. import config
from ..logger import logger
from ..database import models as db_models
from ..utils.formatters import format_usd, format_pnl_percent

TELEGRAM_ID = config.TELEGRAM_CHAT_ID


def handle_dump_alerts_on(args: list) -> str:
    user_id = db_models.register_user(TELEGRAM_ID)
    db_models.update_user_setting(user_id, "dump_alerts_enabled", True)
    return "\U0001f514 Dump alerts enabled. You will be notified of significant price drops."


def handle_dump_alerts_off(args: list) -> str:
    user_id = db_models.register_user(TELEGRAM_ID)
    db_models.update_user_setting(user_id, "dump_alerts_enabled", False)
    return "\U0001f515 Dump alerts disabled."


def handle_alerts(args: list) -> str:
    user_id = db_models.register_user(TELEGRAM_ID)
    settings = db_models.get_user_settings(user_id)
    status = "enabled" if settings.get("dump_alerts_enabled") else "disabled"
    return (
        f"\U0001f514 Dump Alerts: {status}\n\n"
        "Commands:\n"
        "/dump_alerts_on - Enable alerts\n"
        "/dump_alerts_off - Disable alerts\n"
        "/alerts - Show alert status\n"
        "/hourly_report_on - Enable hourly reports\n"
        "/hourly_report_off - Disable hourly reports\n\n"
        "Alerts trigger when:\n"
        "\u2022 Price drops >5% in 1 hour\n"
        "\u2022 Price drops >12% in 4 hours\n"
        "\u2022 Price drops >20% in 24 hours\n"
        "\u2022 Volume increases during price drop"
    )


def handle_hourly_report_on(args: list) -> str:
    user_id = db_models.register_user(TELEGRAM_ID)
    db_models.update_user_setting(user_id, "hourly_report_enabled", True)
    return "\U0001f4ca Hourly reports enabled. You will receive a market summary every hour."


def handle_hourly_report_off(args: list) -> str:
    user_id = db_models.register_user(TELEGRAM_ID)
    db_models.update_user_setting(user_id, "hourly_report_enabled", False)
    return "\U0001f4ca Hourly reports disabled."
