import logging
from datetime import date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import twelve_data as td
from crud import get_or_create_user, get_positions, save_portfolio_snapshot
from services import calculate_portfolio

logger = logging.getLogger("lucrum.scheduler")

scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")

def _td_symbol(ticker: str, asset_class: str) -> str:
    """Portföy ticker → Twelve Data uyumlu sembol."""
    if asset_class == "Kripto" and not ticker.endswith("-USD") and "/" not in ticker:
        return f"{ticker}-USD"
    return ticker

def daily_snapshot_job():
    """Her gün saat 18:00'de portföy snapshot'ını kaydeder."""
    try:
        user = get_or_create_user("default@lucrum.app")
        user_id = user["id"]
        portfolio = calculate_portfolio(user_id, bypass_cache=True)
        save_portfolio_snapshot(user_id, date.today(), portfolio)
        logger.info(f"[SCHEDULER] Daily snapshot saved — value: {portfolio.get('summary', {}).get('total_value_tly', 0):,.0f} TRY")
    except Exception as e:
        logger.error(f"[SCHEDULER] Daily snapshot failed: {e}")

def enrich_portfolio_holdings_job():
    """Portföydeki sembolleri tarayıcıya ekler."""
    try:
        positions = get_positions(1)
        if not positions:
            return
        symbols = []
        asset_classes = {}
        for pos in positions:
            if pos.get("asset_class") in ("ABD Hisse/ETF", "BIST Hissesi", "Kripto"):
                td_sym = _td_symbol(pos["ticker"], pos.get("asset_class", ""))
                symbols.append(td_sym)
                asset_classes[td_sym] = pos.get("asset_class", "")
        if symbols:
            td.crawler.register_symbols(symbols, asset_classes)
            logger.info(f"[SCHEDULER] Registered {len(symbols)} symbols to TwelveDataCrawler for enrichment.")
    except Exception as e:
        logger.error(f"[SCHEDULER] Cache enrichment job failed: {e}")

def start_scheduler():
    """Arka plan tarayıcısını ve iş zamanlayıcıyı başlatır."""
    td.crawler.start()

    try:
        positions = get_positions(1)
        symbols = []
        asset_classes = {}
        for pos in positions:
            if pos.get("asset_class") in ("ABD Hisse/ETF", "BIST Hissesi", "Kripto"):
                td_sym = _td_symbol(pos["ticker"], pos.get("asset_class", ""))
                symbols.append(td_sym)
                asset_classes[td_sym] = pos.get("asset_class", "")
        if symbols:
            td.crawler.register_symbols(symbols, asset_classes)
    except Exception as e:
        logger.warning(f"[CRAWLER] Startup symbol registration failed: {e}")

    # If Redis is configured, delegate periodic cron jobs to Celery Beat
    import os
    if os.getenv("REDIS_URL"):
        logger.info("[SCHEDULER] REDIS_URL detected. Local APScheduler cron jobs disabled (delegated to Celery Beat).")
        return

    scheduler.add_job(daily_snapshot_job, CronTrigger(hour=18, minute=0), id="daily_snapshot", replace_existing=True)
    scheduler.add_job(enrich_portfolio_holdings_job, CronTrigger(hour=1, minute=0), id="cache_enrichment", replace_existing=True)
    scheduler.start()
    logger.info("[SCHEDULER] Daily portfolio snapshot scheduled at 18:00 Istanbul time")
    logger.info("[SCHEDULER] Cache enrichment scheduled daily at 01:00 Istanbul time")

def stop_scheduler():
    """Arka plan zamanlayıcıyı durdurur."""
    scheduler.shutdown()
    td.crawler.stop()
