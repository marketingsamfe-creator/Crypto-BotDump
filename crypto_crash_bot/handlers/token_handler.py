from typing import Optional
from .. import config
from .. import trading_ui
from .. import coingecko_client
from ..logger import logger
from ..formatter import format_coin_detail, format_usd
from ..services import coinmarketcap_service, geckoterminal_service
from ..utils.validators import is_valid_address, is_evm_address, is_solana_address
from ..utils.formatters import format_token_report


def handle_search(args: list) -> str:
    if not args:
        return "Usage: /search <query>\nExample: /search bitcoin"
    query = " ".join(args)
    matches = coingecko_client.search_coins(query)
    if not matches:
        return f"No results for '{query}'."
    coin = matches[0]
    detail = coingecko_client.fetch_coin_detail(coin["id"])
    if detail:
        return format_coin_detail(detail)
    return f"Found: {coin['name']} ({coin['symbol']}) - /precio {coin['id']}"


def handle_token(args: list) -> str:
    return handle_search(args)


def handle_scan(args: list) -> str:
    if not args:
        return "Usage: /scan <contract_address>\nExample: /scan 0x6982508145454ce325ddbe47a25d4ec3d2311933"
    address = args[0].strip()
    if not is_valid_address(address):
        return "Invalid contract address."
    network = "ethereum"
    if is_solana_address(address):
        network = "solana"
    result = _scan_contract(network, address)
    if result:
        return result
    return f"No data found for contract {address[:20]}..."


def handle_contract(args: list) -> str:
    if len(args) < 2:
        return "Usage: /contract <network> <contract_address>\nExample: /contract ethereum 0x..."
    network = args[0].lower()
    address = args[1].strip()
    if not is_valid_address(address):
        return "Invalid contract address."
    result = _scan_contract(network, address)
    if result:
        return result
    return f"No data found for {network} contract."


def _scan_contract(network: str, address: str) -> Optional[str]:
    changes = {}
    try:
        gt_info = geckoterminal_service.get_token_info(network, address)
        if gt_info:
            changes = {
                "1h": gt_info.get("price_change_1h"),
                "24h": gt_info.get("price_change_24h"),
            }
            pairs = geckoterminal_service.get_token_pairs(network, address)
            dex_pairs = len(pairs)
            gt_info["price_changes"] = changes
            gt_info["contract"] = address
            gt_info["network"] = network
            gt_info["dex_pairs"] = dex_pairs
            risk_notes = []
            liq = gt_info.get("liquidity", 0)
            if liq and liq < 10000:
                risk_notes.append("Low liquidity (< $10k)")
            vol = gt_info.get("volume_24h", 0)
            if vol and vol < 10000:
                risk_notes.append("Low 24h volume")
            links = {}
            if network == "ethereum":
                links["Etherscan"] = f"https://etherscan.io/token/{address}"
            elif network == "solana":
                links["Solscan"] = f"https://solscan.io/token/{address}"
            links["DexScreener"] = f"https://dexscreener.com/{network}/{address}"
            return format_token_report(
                name=gt_info.get("name", ""),
                symbol=gt_info.get("symbol", ""),
                contract=address,
                network=network,
                price=gt_info.get("price"),
                fdv=gt_info.get("fdv"),
                volume_24h=gt_info.get("volume_24h"),
                liquidity=liq,
                price_changes=changes,
                dex_pairs=dex_pairs,
                risk_notes=risk_notes if risk_notes else None,
                links=links,
            )
    except Exception as e:
        logger.warning(f"GeckoTerminal scan error: {e}")
    try:
        ds = trading_ui.resolve_token(address)
        if ds:
            changes = {
                "1h": ds.get("price_change_1h"),
                "2h": ds.get("price_change_2h"),
                "4h": ds.get("price_change_4h"),
                "24h": ds.get("price_change_24h"),
            }
            risk_notes = []
            liq = ds.get("liquidity", 0)
            if liq and liq < 10000:
                risk_notes.append("Low liquidity (< $10k)")
            links = {}
            dex_url = ds.get("dex_url", "")
            if dex_url:
                links["DexScreener"] = dex_url
            cg_slug = ds.get("slug", "")
            if cg_slug:
                links["CoinGecko"] = f"https://www.coingecko.com/en/coins/{cg_slug}"
            return format_token_report(
                name=ds.get("name", ""),
                symbol=ds.get("symbol", ""),
                contract=address,
                network=ds.get("chain_id", network),
                price=ds.get("current_price"),
                volume_24h=ds.get("volume_24h"),
                liquidity=liq,
                price_changes=changes,
                risk_notes=risk_notes if risk_notes else None,
                links=links,
            )
    except Exception as e:
        logger.warning(f"DexScreener scan error: {e}")
    try:
        cmc = coinmarketcap_service.search_token(address)
        if cmc:
            return format_token_report(
                name=cmc.get("name", ""),
                symbol=cmc.get("symbol", ""),
                price=cmc.get("price"),
                market_cap=cmc.get("market_cap"),
                volume_24h=cmc.get("volume_24h"),
                price_changes={"1h": cmc.get("percent_change_1h"), "24h": cmc.get("percent_change_24h")},
                links={"CoinMarketCap": f"https://coinmarketcap.com/currencies/{cmc.get('slug', '')}/"},
            )
    except Exception as e:
        logger.warning(f"CMC scan error: {e}")
    return None
