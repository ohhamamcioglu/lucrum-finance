"""
Hindistan yatırım fonu (AMFI/mfapi.in) arama ve NAV sorgu endpoint'leri (Faz 3.5, task #59).
Vergi hesaplamaları için bkz. routers/tax.py (get_india_tax_summary).
"""
from fastapi import APIRouter, Depends, HTTPException, Query

import mfapi
from dependencies import get_current_user_id

router = APIRouter(prefix="/api/india", tags=["India"])


@router.get("/funds/search")
def search_india_funds(
    query: str = Query(..., min_length=2),
    user_id: int = Depends(get_current_user_id),
):
    """AMFI fon adı/kodunda arama yapar (mfapi.in üzerinden, ~75.000 fon)."""
    return {"results": mfapi.search_funds(query)}


@router.get("/funds/{scheme_code}")
def get_india_fund(
    scheme_code: str,
    user_id: int = Depends(get_current_user_id),
):
    """Belirli bir AMFI fonunun metadata'sını, güncel NAV'ını ve son ~1 yıllık
    NAV geçmişini döner."""
    data = mfapi.get_fund_data(scheme_code)
    if not data:
        raise HTTPException(status_code=404, detail="Fon bulunamadı.")
    nav_history = data.get("data") or []
    return {
        "meta": data.get("meta"),
        "latest_nav": nav_history[0] if nav_history else None,
        "is_equity_oriented": mfapi.is_equity_oriented(scheme_code),
        "nav_history": nav_history[:365],
    }
