SEPARATOR = "\n" + "\u2501" * 20 + "\n"
HEADER_SEPARATOR = "\u2501" * 30

SUPPORTED_NETWORKS = [
    "ethereum", "solana", "bsc", "polygon", "arbitrum",
    "optimism", "avalanche", "base", "tron", "fantom",
]

NETWORK_EXPLORERS = {
    "ethereum": "https://etherscan.io/token/{address}",
    "solana": "https://solscan.io/token/{address}",
    "bsc": "https://bscscan.com/token/{address}",
    "polygon": "https://polygonscan.com/token/{address}",
    "arbitrum": "https://arbiscan.io/token/{address}",
    "optimism": "https://optimistic.etherscan.io/token/{address}",
    "avalanche": "https://snowtrace.io/token/{address}",
    "base": "https://basescan.org/token/{address}",
    "tron": "https://tronscan.org/#/token20/{address}",
}

DEFAULT_CURRENCIES = ["usd", "eur", "gbp", "btc", "eth"]

RISK_FLAGS = {
    "low_liquidity": "Low liquidity (< $10k)",
    "low_volume": "Low 24h volume",
    "new_pair": "Pair less than 24h old",
    "honeypot": "Possible honeypot",
    "high_concentration": "High holder concentration",
    "no_social": "No social presence found",
    "rugged": "Possible rug pull indicators",
}
