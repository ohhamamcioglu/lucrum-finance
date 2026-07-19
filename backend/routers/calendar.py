"""
Portföy temettü takvimi (Faz 3, task #58 — sadece kullanıcının portföyündeki
hisselerin GERÇEK temettü tarihleri; enflasyon/bilanço/vergi tarihlerini de
içeren çok ülkeli genel Finansal Takvim ayrı bir görev olarak planlanmıştır, #63).

Veri kaynağı: twelve_data.get_dividends() — Twelve Data API (yfinance fallback'li).
Tarih/tutar döndürmeyen veya ayrıştırılamayan kayıtlar sessizce ATLANIR, asla
tahmini bir tarihle doldurulmaz.
"""
from datetime import date
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import twelve_data as td
from crud import get_positions
from dependencies import get_current_user_id, get_db

router = APIRouter(prefix="/api/calendar", tags=["Calendar"])

# Sadece klasik anlamda "temettü" kavramı olan varlık sınıfları — TEFAS fonları farklı
# bir dağıtım mekanizmasına sahip, kripto ve nakit'in temettüsü yok.
_DIVIDEND_ELIGIBLE_ASSET_CLASSES = {"ABD Hisse/ETF", "BIST Hissesi"}


@router.get("/dividends")
def get_dividend_calendar(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Portföydeki her hisse için gerçek (Twelve Data/yfinance kaynaklı) temettü
    kayıtlarını döner. total_amount = gerçek pay başı temettü × kullanıcının GERÇEKTEN
    sahip olduğu adet — bir tahmin değil, aritmetik."""
    positions = get_positions(user_id, db=db)
    qty_by_ticker: Dict[str, float] = {}
    for p in positions:
        if p["asset_class"] not in _DIVIDEND_ELIGIBLE_ASSET_CLASSES:
            continue
        qty_by_ticker[p["ticker"]] = qty_by_ticker.get(p["ticker"], 0.0) + p["quantity"]

    today_str = date.today().isoformat()
    events: List[dict] = []
    for ticker, qty in qty_by_ticker.items():
        try:
            divs = td.get_dividends(ticker)
        except Exception:
            divs = []
        for d in divs:
            ex_date = d.get("date")
            amount = d.get("amount")
            if not ex_date or amount is None:
                continue
            events.append({
                "ticker": ticker,
                "ex_date": ex_date,
                "amount_per_share": amount,
                "quantity_held": qty,
                "total_amount": round(amount * qty, 2),
                "is_future": ex_date > today_str,
            })

    events.sort(key=lambda e: e["ex_date"], reverse=True)
    return {"events": events}
