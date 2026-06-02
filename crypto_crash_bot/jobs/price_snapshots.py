import time
from typing import Optional
from .. import config
from .. import trading_ui
from .. import portfolio_db
from .. import coingecko_client
from ..logger import logger
from ..database import models as db_models


_last_snapshot_time = 0
SNAPSHOT_INTERVAL = 3600


def save_price_snapshots():
    global _last_snapshot_time
    now = time.time()
    if now - _last_snapshot_time < SNAPSHOT_INTERVAL:
        return
    _last_snapshot_time = now
    try:
        positions = portfolio_db.get_all_positions(is_test=config.TEST_MODE)
        token_ids = []
        for pos in positions:
            slug = pos.get("coin_id", "").lower()
            sym = pos.get("symbol", "")
            if slug:
                token_ids.append((slug, sym))
        watched = db_models.get_all_tracked_token_ids()
        for tid in watched:
            if not any(tid == t[0] for t in token_ids):
                token_ids.append((tid, ""))
        if not token_ids:
            return
        batch_size = 50
        for i in range(0, len(token_ids), batch_size):
            batch = token_ids[i:i + batch_size]
            ids = ",".join(t[0] for t in batch if t[0])
            if not ids:
                continue
            try:
                prices = coingecko_client.fetch_simple_price(ids)
                if prices:
                    for token_id, sym in batch:
                        if token_id in prices:
                            price = prices[token_id].get("usd", 0)
                            if price and price > 0:
                                db_models.add_price_snapshot(token_id, price, symbol=sym)
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Snapshot batch error: {e}")
        logger.info(f"Saved {len(token_ids)} price snapshots")
    except Exception as e:
        logger.error(f"Price snapshot error: {e}")


def get_price_change_from_snapshots(token_id: str) -> dict:
    changes = {}
    for hours in [1, 2, 4, 24]:
        pct = db_models.get_price_change(token_id, hours)
        if pct is not None:
            changes[f"{hours}h"] = round(pct, 2)
    return changes
