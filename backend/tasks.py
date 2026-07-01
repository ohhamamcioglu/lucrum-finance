import logging
from datetime import date
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
