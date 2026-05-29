import os

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8862906082:AAEIXM2RrXwVe_F8kBkFQB9SQIdONjoTmEE")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1199212284")
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")

VS_CURRENCY = "usd"

MONITOR_INTERVAL = int(os.environ.get("MONITOR_INTERVAL_SECONDS", 300))
PORTFOLIO_INTERVAL = int(os.environ.get("PORTFOLIO_REPORT_INTERVAL_SECONDS", 3600))
POLL_INTERVAL = 30
MAX_PAGES = 2
COOLDOWN_MINUTES = int(os.environ.get("DEFAULT_ALERT_COOLDOWN_MINUTES", 60))

MIN_VOLUME_USD = float(os.environ.get("MIN_VOLUME_USD", 500_000))
MIN_MARKET_CAP_USD = float(os.environ.get("MIN_MARKET_CAP_USD", 1_000_000))

DROP_THRESHOLDS = {
    "dump": -15,
    "dump_severe": -25,
    "dump_extreme": -40,
}

SEVERITY_LABELS = {
    "dump": "⚠️ Dump Alert",
    "dump_severe": "🚨 Severe Dump",
    "dump_extreme": "🩸 Extreme Crash",
}

ALERT_WINDOWS = ["5m", "15m", "1h", "24h"]
WINDOW_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "24h": 86400}

STABLECOINS = {"usdt", "usdc", "dai", "fdusd", "tusd", "usde", "busd"}
WRAPPED_EXCLUDE = {"wbtc", "weth"}
ALWAYS_EXCLUDED = set()

PORTFOLIO = [
    {"slug": "bittensor",            "symbol": "TAO",   "name": "Bittensor",              "alloc": 35.72},
    {"slug": "aria-ai",              "symbol": "ARIA",  "name": "Aria.AI",                "alloc": 28.92},
    {"slug": "bob-build-on-bitcoin", "symbol": "BOB",   "name": "BOB (Build on Bitcoin)",  "alloc": 15.38},
    {"slug": "siren-2",              "symbol": "SIREN", "name": "Siren",                  "alloc": 13.84},
    {"slug": "ordinals",             "symbol": "ORDI",  "name": "ORDI",                   "alloc": 5.97},
    {"slug": "lighter",              "symbol": "LIT",   "name": "Lighter",                "alloc": 0.17},
]

MAX_SNAPSHOTS_PER_COIN = 300
SNAPSHOT_CLEANUP_AGE = 90000

QUICK_BUY_AMOUNTS = [int(x) for x in os.environ.get("QUICK_BUY_AMOUNTS", "10,50,100,250").split(",")]
DEFAULT_FEE_USD = float(os.environ.get("DEFAULT_FEE_USD", "0"))
DUMPS_DEFAULT_WINDOW = os.environ.get("DUMPS_DEFAULT_WINDOW", "24h")
DUMPS_DEFAULT_MIN_DROP = int(os.environ.get("DUMPS_DEFAULT_MIN_DROP", "0"))
DUMPS_MIN_VOLUME_24H_USD = float(os.environ.get("DUMPS_MIN_VOLUME_24H_USD", 300_000))
DUMPS_MIN_LIQUIDITY_USD = float(os.environ.get("DUMPS_MIN_LIQUIDITY_USD", 0))
DUMPS_MIN_MARKET_CAP_USD = float(os.environ.get("DUMPS_MIN_MARKET_CAP_USD", 0))
DUMPS_LIMIT = int(os.environ.get("DUMPS_LIMIT", "10"))
DUMPS_MAX_COINS = int(os.environ.get("DUMPS_MAX_COINS", "500"))
DUMPS_WINDOWS = ["5m", "15m", "1h", "24h", "7d"]

SOCIAL_SCAN_INTERVAL = int(os.environ.get("SOCIAL_SCAN_INTERVAL_SECONDS", 600))
MIN_OPPORTUNITY_SCORE = int(os.environ.get("MIN_OPPORTUNITY_SCORE", 70))
RISK_MODE = os.environ.get("RISK_MODE", "balanced")
MIN_LIQUIDITY_USD = float(os.environ.get("MIN_LIQUIDITY_USD", 100_000))
MIN_PAIR_AGE_HOURS = int(os.environ.get("MIN_PAIR_AGE_HOURS", 24))
ENABLE_DEXSCREENER = os.environ.get("ENABLE_DEXSCREENER", "true").lower() == "true"
ENABLE_REDDIT = os.environ.get("ENABLE_REDDIT", "false").lower() == "true"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
if not os.path.exists(DATA_DIR):
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

TOKEN_KEY_SEPARATOR = ":"

# DexScreener supported chains (auto-detected from response, this is for reference)
SUPPORTED_CHAINS = [
    "ethereum", "solana", "base", "bsc", "arbitrum", "optimism",
    "polygon", "avalanche", "fantom", "blast", "linea", "scroll",
    "mantle", "zksync", "celo", "cronos", "moonbeam", "pulsechain",
    "sui", "aptos", "tron",
]
