import logging
from datetime import date, datetime
from celery_app import celery_app
from db_models import SessionLocal, DBUser, DBPosition
from crud import save_portfolio_snapshot
from services import calculate_portfolio
import twelve_data as td

logger = logging.getLogger("lucrum.tasks")

def _td_symbol(ticker: str, asset_class: str) -> str:
    """Portföy ticker → Twelve Data uyumlu sembol."""
    if asset_class == "Kripto" and not ticker.endswith("-USD") and "/" not in ticker:
        return f"{ticker}-USD"
    return ticker

_ASSET_CLASS_TO_TYPE = {
    "TEFAS Fonu": "fund",
    "BIST Hissesi": "stock_tr",
    "ABD Hisse/ETF": "stock_us",
    "Kripto": "crypto",
    "Emtia": "commodity",
}

@celery_app.task
def refresh_market_history_task():
    """Performans grafiğinin ihtiyaç duyduğu TÜM tarihsel serileri (döviz kurları,
    BIST100/S&P500/BTC benchmark'ları, portföydeki her varlığın fiyat geçmişi — TEFAS
    fonları dahil) ARKA PLANDA doldurur/tazeler.

    services.get_ticker_historical_prices (performans grafiğinin kullandığı yol) artık
    HER çağrıda live_fetch=False kullanıyor — yani hiçbir dış kaynağa (Twelve Data,
    Fonoloji, pytefas) canlı ağ isteği ATMIYOR, sadece bu görevin önceden doldurduğu
    yerel önbellekten okuyor. Bu görev olmadan yeni eklenen/hiç görülmemiş bir varlık,
    bu görev bir sonraki çalışmasına kadar performans grafiğinde düz bir çizgi olarak
    kalır — kabul edilebilir bir gecikme, bir HTTP isteğini (TEFAS için dakikalarca,
    diğerleri için saniyelerce) bloke etmekten çok daha iyi. Bkz. services.py
    get_ticker_historical_prices docstring'i — bu regresyon production'da canlı olarak
    gözlemlendi (kullanıcı: "3m-6m-1y-2y hiç sağlıklı çalışmıyor").
    """
    from datetime import date, timedelta
    from services import get_ticker_historical_prices

    end = date.today()
    start = end - timedelta(days=730)  # 2Y grafik aralığını kapsar

    # 1) Döviz kurları ve endeks/kripto benchmark'ları — HER kullanıcının grafiği
    # bunlara bağımlı, portföyünde ne olursa olsun.
    universal = [
        ("USDTRY=X", "exchange_rate"), ("EURTRY=X", "exchange_rate"), ("GBPTRY=X", "exchange_rate"),
        ("XU100.IS", "index"), ("^GSPC", "index"), ("BTC-USD", "crypto"),
    ]
    for ticker, asset_type in universal:
        try:
            get_ticker_historical_prices(ticker, asset_type, start, end, live_fetch=True)
        except Exception as u_err:
            logger.warning(f"[CELERY] Market history refresh failed for '{ticker}': {u_err}")

    # 2) Portföylerdeki her benzersiz varlık.
    db = SessionLocal()
    try:
        rows = db.query(DBPosition.ticker, DBPosition.asset_class).distinct().all()
    finally:
        db.close()

    if not rows:
        logger.info("[CELERY] No positions found for market history refresh.")
        return

    logger.info(f"[CELERY] Refreshing market history cache for {len(rows)} ticker/asset_class pairs.")
    for ticker, asset_class in rows:
        asset_type = _ASSET_CLASS_TO_TYPE.get(asset_class)
        if not asset_type:  # Nakit, AMFI Fonu (henüz canlı fiyatlandırma yok) vb.
            continue
        try:
            get_ticker_historical_prices(ticker, asset_type, start, end, live_fetch=True)
        except Exception as t_err:
            logger.warning(f"[CELERY] Market history refresh failed for '{ticker}': {t_err}")
    logger.info("[CELERY] Market history cache refresh complete.")

@celery_app.task
def check_price_alerts_and_rebalancing_task(user_id: int, portfolio: dict):
    """calculate_portfolio içindeki fiyat alarmı/rebalans-sapma kontrolünü gerçekten arka
    planda çalıştırır. Eskiden bu kontrol GET /api/portfolio isteği içinde SENKRON
    çalışıyordu (cache soğukken) — dashboard yüklemesini yavaşlatıyor ve idempotent olması
    gereken bir GET isteğini DB yazması yapan bir işleme çeviriyordu."""
    from services import check_price_alerts_and_rebalancing
    try:
        check_price_alerts_and_rebalancing(user_id, portfolio)
    except Exception as e:
        logger.error(f"[CELERY] Price alert/rebalance check failed for user_id={user_id}: {e}")

@celery_app.task
def daily_snapshot_task():
    """Her gün tüm SaaS kullanıcılarının portföy snapshot'larını kaydeder (Çoklu kiracılık)."""
    db = SessionLocal()
    try:
        users = db.query(DBUser).all()
        logger.info(f"[CELERY] Starting daily portfolio snapshots for {len(users)} users.")
        
        for user in users:
            try:
                portfolio = calculate_portfolio(user.id, bypass_cache=True)
                save_portfolio_snapshot(user.id, date.today(), portfolio, db=db)
                val = portfolio.get('summary', {}).get('total_value_tly', 0)
                logger.info(f"[CELERY] Saved daily snapshot for user '{user.email}' — total value: {val:,.2f} TRY")
            except Exception as user_err:
                logger.error(f"[CELERY] Failed daily snapshot for user '{user.email}': {user_err}")
                
    except Exception as e:
        logger.error(f"[CELERY] Daily snapshot master task failed: {e}")
    finally:
        db.close()

@celery_app.task
def enrich_portfolio_holdings_task():
    """Her saat başı tüm kullanıcıların portföyündeki varlıkları Twelve Data önbelleğe kaydeder."""
    db = SessionLocal()
    try:
        positions = db.query(DBPosition).all()
        if not positions:
            logger.info("[CELERY] No positions found for cache enrichment.")
            return
            
        symbols = []
        asset_classes = {}
        for pos in positions:
            if pos.asset_class in ("ABD Hisse/ETF", "BIST Hissesi", "Kripto"):
                td_sym = _td_symbol(pos.ticker, pos.asset_class)
                if td_sym not in symbols:
                    symbols.append(td_sym)
                    asset_classes[td_sym] = pos.asset_class
                    
        if symbols:
            # Register symbols in Twelve Data crawler
            td.crawler.register_symbols(symbols, asset_classes)
            # Fetch prices to warm cache
            for sym in symbols:
                try:
                    td.get_live_price(sym)
                except:
                    pass
            logger.info(f"[CELERY] Registered and warmed cache for {len(symbols)} symbols.")
    except Exception as e:
        logger.error(f"[CELERY] Cache enrichment task failed: {e}")
    finally:
        db.close()

@celery_app.task
def warm_portfolio_cache_task():
    """Kullanıcı bazlı portföy önbelleğini (5 dk TTL) süresi dolmadan arka planda tazeler.
    Bunsuz, önbellek her 5 dakikada bir soğuyor ve o an siteye giren kullanıcı fiyat
    çekme/TEFAS/kripto gecikmesinin TAMAMINI canlı canlı bekliyordu. Bu görev 4 dakikada
    bir çalışarak önbelleği hep TTL'in içinde tutuyor — kullanıcı asla soğuk yüklemeye
    denk gelmiyor. Sadece en az bir pozisyonu olan kullanıcılar için çalışır (boşuna
    API kullanımını önlemek için)."""
    db = SessionLocal()
    try:
        user_ids = [row[0] for row in db.query(DBPosition.user_id).distinct().all()]
        for user_id in user_ids:
            try:
                calculate_portfolio(user_id, bypass_cache=True)
            except Exception as user_err:
                logger.error(f"[CELERY] Portfolio cache warm failed for user_id={user_id}: {user_err}")
        if user_ids:
            logger.info(f"[CELERY] Warmed portfolio cache for {len(user_ids)} user(s).")
    except Exception as e:
        logger.error(f"[CELERY] Portfolio cache warm task failed: {e}")
    finally:
        db.close()

@celery_app.task
def refresh_instrument_catalog_task():
    """BIST, NASDAQ, NYSE, Kripto ve TEFAS arama kataloğunu periyodik tazeler
    (bkz. twelve_data.refresh_instrument_catalog — her kaynağın kendi 14 günlük
    TTL'i var, taze olanlar için ağa istek atılmaz)."""
    try:
        counts = td.refresh_instrument_catalog()
        logger.info(f"[CELERY] Instrument catalog refreshed: {counts}")
    except Exception as e:
        logger.error(f"[CELERY] Instrument catalog refresh failed: {e}")

@celery_app.task
def downgrade_expired_subscriptions_task():
    """Süresi dolmuş (subscription_ends_at geçmiş) ücretli abonelikleri FREE'ye düşürür.
    Tek seferlik/dönemsel ödeme modelinde otomatik yenileme olmadığı için bu görev
    olmadan süresi dolan kullanıcı sonsuza dek PRO/ENTERPRISE limitlerinde kalırdı."""
    db = SessionLocal()
    try:
        expired = db.query(DBUser).filter(
            DBUser.subscription_tier != "FREE",
            DBUser.subscription_ends_at.isnot(None),
            DBUser.subscription_ends_at < datetime.utcnow(),
        ).all()
        for user in expired:
            user.subscription_tier = "FREE"
            user.subscription_status = "active"
            logger.info(f"[CELERY] Subscription expired, downgraded to FREE: '{user.email}'")
        db.commit()
        logger.info(f"[CELERY] Downgraded {len(expired)} expired subscription(s).")
    except Exception as e:
        db.rollback()
        logger.error(f"[CELERY] Subscription downgrade task failed: {e}")
    finally:
        db.close()
