from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import twelve_data as td
from crud import get_exchange_rate_history, get_price_history
from services import get_usd_try_rate, get_eur_try_rate, get_gbp_try_rate
from dependencies import get_current_user_id, get_db

router = APIRouter(prefix="/api/prices", tags=["Prices"])

@router.get("/live")
def get_live_price(ticker: str):
    """Canlı fiyat al"""
    try:
        price = td.get_live_price(ticker)
        if price is None:
            raise HTTPException(status_code=404, detail="Ticker not found")
        return {"ticker": ticker, "price": price}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rates")
def get_rates():
    """Güncel döviz kurlarını al"""
    try:
        usd = get_usd_try_rate()
        eur = get_eur_try_rate()
        gbp = get_gbp_try_rate()
        return {"usd_rate": usd, "eur_rate": eur, "gbp_rate": gbp}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rates/history")
def get_rates_history(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Kur geçmişini al"""
    rows = get_exchange_rate_history(days, db=db)
    return [
        {
            "date": r["rate_date"],
            "usd_try": r["usd_try_rate"],
            "source": r["source"]
        }
        for r in rows
    ]

@router.get("/history/{ticker}")
def get_ticker_price_history(
    ticker: str,
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Belirli varlık için fiyat geçmişini al"""
    rows = get_price_history(ticker, days, db=db)
    return [
        {
            "date": r["price_date"],
            "price_usd": r["price_usd"],
            "price_try": r["price_try"],
            "source": r["source"]
        }
        for r in rows
    ]
