from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import twelve_data as td
from crud import get_exchange_rate_history
from services import get_usd_try_rate, get_eur_try_rate, get_gbp_try_rate, get_current_price, get_price_currency
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
    asset_class: Optional[str] = None,
):
    """Belirli varlık için fiyat geçmişini al.

    Not: `price_history` tablosu hiçbir yerde yazılmıyor (save_price_history import
    edilmiş ama hiç çağrılmıyor) — bu yüzden burada her zaman boş dönerdi ve örn.
    Risk sekmesindeki korelasyon matrisi hiçbir zaman veri bulamazdı. Bunun yerine
    Twelve Data'nın kendi TTL'li time_series cache'inden (td_time_series) besleniyoruz.
    """
    td_symbol = ticker.upper().strip()
    if (asset_class or "") == "Kripto" and not td_symbol.endswith("-USD") and "/" not in td_symbol:
        td_symbol = f"{td_symbol}-USD"

    bars = td.get_time_series(td_symbol, days, "1day")
    is_try_priced = (asset_class or "") in ("BIST Hissesi", "TL Mevduat", "TL Tahvil")
    return [
        {
            "date": b["date"][:10],
            "price_usd": None if is_try_priced else b["close"],
            "price_try": b["close"] if is_try_priced else None,
            "source": "twelve_data"
        }
        for b in bars if b.get("close") is not None
    ]

@router.get("/{ticker}")
def get_price(ticker: str, asset_class: Optional[str] = None):
    """Belirli bir varlığın güncel fiyatını al. `currency` alanı, `price`'ın hangi para
    biriminde olduğunu açıkça belirtir (TEFAS Fonu / BIST Hissesi → TRY, diğerleri → USD) —
    frontend bunu asset_class'tan tahmin etmek zorunda kalmasın diye. Bu rota diğer sabit
    yollardan (/live, /rates, /history/{ticker}) SONRA tanımlanmalı, yoksa onları gölgeler."""
    try:
        price = get_current_price(ticker, asset_class or "ABD Hisse/ETF")
        if price is None:
            raise HTTPException(status_code=404, detail="Ticker not found")
        return {"ticker": ticker, "price": price, "currency": get_price_currency(asset_class or "ABD Hisse/ETF")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
