import logging
from datetime import date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import twelve_data as td
from crud import get_or_create_user, get_positions, save_portfolio_snapshot
from services import calculate_portfolio

from database import get_db_session
from db_models import DBUser, DBPosition

logger = logging.getLogger("lucrum.scheduler")

scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")

def _td_symbol(ticker: str, asset_class: str) -> str:
    """Portföy ticker → Twelve Data uyumlu sembol."""
    if asset_class == "Kripto" and not ticker.endswith("-USD") and "/" not in ticker:
        return f"{ticker}-USD"
    return ticker

def daily_snapshot_job():
    """Her gün saat 18:00'de tüm kullanıcıların portföy snapshot'ını kaydeder."""
    try:
        with get_db_session() as db:
            users = db.query(DBUser).all()
            logger.info(f"[SCHEDULER] Running daily portfolio snapshots for {len(users)} users.")
            for user in users:
                try:
                    portfolio = calculate_portfolio(user.id, bypass_cache=True)
                    save_portfolio_snapshot(user.id, date.today(), portfolio, db=db)
                    logger.info(f"[SCHEDULER] Saved snapshot for '{user.email}'")
                except Exception as u_err:
                    logger.error(f"[SCHEDULER] Failed snapshot for '{user.email}': {u_err}")
    except Exception as e:
        logger.error(f"[SCHEDULER] Daily snapshot failed: {e}")

def enrich_portfolio_holdings_job():
    """Portföydeki sembolleri tarayıcıya ekler."""
    try:
        symbols = []
        asset_classes = {}
        # DBPosition alanlarına `with` bloğu İÇİNDE erişiyoruz — session commit()
        # ile nesneleri "expire" ediyor, session kapandıktan SONRA attribute'lara
        # erişmeye çalışmak "Instance ... is not bound to a Session" hatasına yol
        # açıyordu ve bu fonksiyon (dolayısıyla crawler'ın sembol kaydı) sessizce
        # hiç çalışmıyordu — financial_records tablosunun hep boş kalmasının sebebi buydu.
        with get_db_session() as db:
            positions = db.query(DBPosition).all()
            for pos in positions:
                if pos.asset_class in ("ABD Hisse/ETF", "BIST Hissesi", "Kripto"):
                    td_sym = _td_symbol(pos.ticker, pos.asset_class)
                    if td_sym not in symbols:
                        symbols.append(td_sym)
                        asset_classes[td_sym] = pos.asset_class
        if symbols:
            td.crawler.register_symbols(symbols, asset_classes)
            logger.info(f"[SCHEDULER] Registered {len(symbols)} symbols to TwelveDataCrawler for enrichment.")
    except Exception as e:
        logger.error(f"[SCHEDULER] Cache enrichment job failed: {e}")

def start_scheduler():
    """Arka plan tarayıcısını ve iş zamanlayıcıyı başlatır."""
    td.crawler.start()

    try:
        symbols = []
        asset_classes = {}
        # bkz. enrich_portfolio_holdings_job'daki not — attribute'lara session açıkken erişiyoruz.
        with get_db_session() as db:
            positions = db.query(DBPosition).all()
            for pos in positions:
                if pos.asset_class in ("ABD Hisse/ETF", "BIST Hissesi", "Kripto"):
                    td_sym = _td_symbol(pos.ticker, pos.asset_class)
                    if td_sym not in symbols:
                        symbols.append(td_sym)
                        asset_classes[td_sym] = pos.asset_class
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
