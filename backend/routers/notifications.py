from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session

from models import PriceAlert, PriceAlertCreate, Notification
from crud import (
    get_price_alerts, create_price_alert, delete_price_alert,
    get_notifications, mark_notifications_read, get_positions
)
from dependencies import get_current_user_id, get_db, check_price_alert_limit
from cache import finance_cache as _news_db
# Import helpers from assets router to avoid duplicate crawler logic
from routers.assets import (
    _is_tefas, _fetch_twelve_data_news, _get_news_for_ticker,
    _fetch_google_news_rss, _NEWS_TTL
)

router = APIRouter(prefix="/api", tags=["Notifications"])

_MACRO_QUERIES = [
    ("macro_fed", "Federal Reserve interest rate decision"),
    ("macro_inflation", "inflation CPI economy"),
    ("macro_tcmb", "TCMB faiz kararı Türkiye ekonomi"),
    ("macro_bist", "Borsa Istanbul BIST piyasa"),
]

@router.get("/price-alerts", response_model=List[PriceAlert])
def list_alerts(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Fiyat alarmlarını listele"""
    rows = get_price_alerts(user_id, db=db)
    return [PriceAlert(**r) for r in rows]

@router.post("/price-alerts", response_model=PriceAlert)
def add_alert(
    item: PriceAlertCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    _limit_guard: None = Depends(check_price_alert_limit)
):
    """Yeni fiyat alarmı ekle"""
    row = create_price_alert(user_id, item, db=db)
    return PriceAlert(**row)

@router.delete("/price-alerts/{alert_id}")
def remove_alert(
    alert_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Fiyat alarmı sil"""
    success = delete_price_alert(user_id, alert_id, db=db)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert deleted"}

@router.get("/notifications", response_model=List[Notification])
def list_notifications(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Kullanıcı bildirimlerini al"""
    rows = get_notifications(user_id, db=db)
    return [Notification(**r) for r in rows]

@router.post("/notifications/read")
def read_notifications(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Tüm bildirimleri okundu olarak işaretle"""
    mark_notifications_read(user_id, db=db)
    return {"message": "Notifications marked as read"}

@router.get("/notifications/news")
def get_news_notifications(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Portföye özel derlenmiş haber akışı (Smart News Feed).
    1) Kullanıcının pozisyonundaki ticker'lar için haberleri çeker.
    2) Genel makroekonomik haberleri ekler.
    3) Sonuçları tarih sırasına göre harmanlayıp döner.
    """
    positions = get_positions(user_id, db=db)
    tickers = list(set([p['ticker'] for p in positions]))
    
    all_news = []
    
    def fetch_ticker_news(ticker):
        if _is_tefas(ticker):
            return []
        return _get_news_for_ticker(ticker)
        
    def fetch_macro_news(query_id, query):
        cached = _news_db.get(f"news_macro_{query_id}", ttl=_NEWS_TTL)
        if cached:
            return cached
        rss_news = _fetch_google_news_rss(query)
        # Mark macro source
        for item in rss_news:
            item["related_ticker"] = "Macro"
        _news_db.set(f"news_macro_{query_id}", rss_news)
        return rss_news

    # Paralel çalıştır (En fazla 10 worker)
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for ticker in tickers:
            futures.append(executor.submit(fetch_ticker_news, ticker))
        for q_id, q in _MACRO_QUERIES:
            futures.append(executor.submit(fetch_macro_news, q_id, q))
            
        for future in as_completed(futures):
            try:
                all_news.extend(future.result())
            except Exception:
                pass
                
    # Tarihe göre azalan sırala
    def parse_dt(dt_str):
        if not dt_str:
            return datetime.min
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except:
            try:
                return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            except:
                return datetime.min

    all_news.sort(key=lambda x: parse_dt(x.get("datetime")), reverse=True)
    return all_news[:30]
