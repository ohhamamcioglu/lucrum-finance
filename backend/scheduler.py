import logging
import threading
from datetime import date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

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

_ASSET_CLASS_TO_TYPE = {
    "TEFAS Fonu": "fund",
    "BIST Hissesi": "stock_tr",
    "ABD Hisse/ETF": "stock_us",
    "Kripto": "crypto",
    "Emtia": "commodity",
}

def refresh_market_history_job():
    """Performans grafiğinin ihtiyaç duyduğu TÜM tarihsel serileri (döviz kurları,
    BIST100/S&P500/BTC benchmark'ları, portföydeki her varlığın fiyat geçmişi — TEFAS
    fonları dahil) ARKA PLANDA doldurur/tazeler. Bkz. tasks.refresh_market_history_task
    (Celery Beat'teki ikizi, production Redis ortamında bu iş yerine o çalışır) —
    aynı mantık, sadece yerel/Redis'siz ortamlar için."""
    from services import get_ticker_historical_prices

    end = date.today()
    start = end - timedelta(days=730)  # 2Y grafik aralığını kapsar

    universal = [
        ("USDTRY=X", "exchange_rate"), ("EURTRY=X", "exchange_rate"), ("GBPTRY=X", "exchange_rate"),
        ("XU100.IS", "index"), ("^GSPC", "index"), ("BTC-USD", "crypto"),
    ]
    for ticker, asset_type in universal:
        try:
            get_ticker_historical_prices(ticker, asset_type, start, end, live_fetch=True)
        except Exception as u_err:
            logger.warning(f"[SCHEDULER] Piyasa geçmişi tazeleme başarısız ({ticker}): {u_err}")

    try:
        with get_db_session() as db:
            rows = db.query(DBPosition.ticker, DBPosition.asset_class).distinct().all()
    except Exception as e:
        logger.error(f"[SCHEDULER] Piyasa geçmişi önbellek işi başarısız: {e}")
        return

    if not rows:
        return
    logger.info(f"[SCHEDULER] Piyasa geçmişi önbelleği tazeleniyor: {len(rows)} varlık.")
    for ticker, asset_class in rows:
        asset_type = _ASSET_CLASS_TO_TYPE.get(asset_class)
        if not asset_type:
            continue
        try:
            get_ticker_historical_prices(ticker, asset_type, start, end, live_fetch=True)
        except Exception as t_err:
            logger.warning(f"[SCHEDULER] Piyasa geçmişi tazeleme başarısız ({ticker}): {t_err}")
    logger.info("[SCHEDULER] Piyasa geçmişi önbelleği tazelendi.")

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

    # Arama kataloğunu (BIST/NASDAQ/NYSE/Kripto/TEFAS) arka planda tazele — app
    # başlangıcını bloklamaz, sadece kataloğun 14 günlük TTL'i dolmuşsa ağa gider.
    threading.Thread(target=td.refresh_instrument_catalog, daemon=True, name="catalog-seed").start()

    # Piyasa geçmişi önbelleğini arka planda doldur — REDIS_URL olsun olmasın her açılışta
    # bir kez çalışır (deploy sonrası önbellek hemen ısınsın diye), Redis varsa periyodik
    # tazeleme ayrıca Celery Beat'e devredilir (bkz. tasks.refresh_market_history_task).
    threading.Thread(target=refresh_market_history_job, daemon=True, name="market-history-seed").start()

    # If Redis is configured, delegate periodic cron jobs to Celery Beat
    import os
    if os.getenv("REDIS_URL"):
        logger.info("[SCHEDULER] REDIS_URL detected. Local APScheduler cron jobs disabled (delegated to Celery Beat).")
        return

    scheduler.add_job(daily_snapshot_job, CronTrigger(hour=18, minute=0), id="daily_snapshot", replace_existing=True)
    scheduler.add_job(enrich_portfolio_holdings_job, CronTrigger(hour=1, minute=0), id="cache_enrichment", replace_existing=True)
    scheduler.add_job(refresh_market_history_job, IntervalTrigger(minutes=15), id="market_history_refresh", replace_existing=True)
    scheduler.start()
    logger.info("[SCHEDULER] Daily portfolio snapshot scheduled at 18:00 Istanbul time")
    logger.info("[SCHEDULER] Cache enrichment scheduled daily at 01:00 Istanbul time")

def stop_scheduler():
    """Arka plan zamanlayıcıyı durdurur."""
    scheduler.shutdown()
    td.crawler.stop()
