from datetime import date, datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session

import twelve_data as td
from cache import finance_cache as _fc
from models import TargetAllocation, TargetAllocationCreate
from crud import (
    get_positions, get_target_allocations, save_target_allocations,
    save_portfolio_snapshot
)
from services import calculate_portfolio, calculate_twrr_and_metrics
from dependencies import get_current_user_id, get_db
from rate_limit import limiter

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])

@router.get("", response_model=dict)
@limiter.limit("120/minute")
def get_portfolio(
    request: Request,
    refresh: bool = False,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Portföy özetini ve detaylı holdings'i al"""
    portfolio = calculate_portfolio(user_id, bypass_cache=refresh)

    # Snapshot'ı kaydet
    try:
        save_portfolio_snapshot(user_id, date.today(), portfolio, db=db)
    except:
        pass

    return portfolio

@router.get("/performance")
@limiter.limit("60/minute")
def get_performance(
    request: Request,
    days: int = Query(90, ge=7, le=730),
    currency: str = Query('TRY'),
    user_id: int = Depends(get_current_user_id)
):
    """Portföy TWRR ve endeks performans karşılaştırmasını al"""
    try:
        metrics = calculate_twrr_and_metrics(user_id, days, currency)
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _compute_risk_score(symbol: str, asset_class: str) -> float:
    """
    Beta'dan riskScore hesapla (1-8 arası).
    US hisseler → Twelve Data beta.
    BIST → yfinance beta (Twelve Data'nın ücretsiz planı XIST beta göstergesini
    desteklemiyor — her çağrı sessizce başarısız olup varsayılana düşerken
    paylaşılan 55 istek/dk API kotasını boşuna tüketiyordu).
    TEFAS → Fonoloji'nin döndürdüğü SPK/KAP resmi risk seviyesi (1-7); eskiden
    TEFAS fon kodu (örn. "YAS") sanki bir BIST hissesiymiş gibi ".IS" eklenip
    Twelve Data'ya soruluyordu — var olmayan bir sembol için her zaman
    başarısız olan, tamamen boşa giden bir API çağrısıydı.
    Formül: riskScore = beta * 4
    """
    ac = (asset_class or '').strip()
    if ac in ('Nakit', 'Cash', 'TL Mevduat'):
        return 1.0
    if ac in ('FixedIncome', 'Tahvil', 'Bono', 'TL Tahvil'):
        return 2.0
    if ac == 'Kripto':
        return 7.0

    if ac == 'TEFAS Fonu':
        risk = td.get_tefas_risk_score(symbol)
        if risk is not None:
            return round(max(1.0, min(8.0, risk)), 2)
        return 4.0

    # US hisseler → Twelve Data (DB cache'li, hızlı)
    # Not: beta > 0 şartı KALDIRILDI — negatif/sıfıra yakın beta (örn. THYAO.IS
    # gerçek beta'sı -0.01) geçerli bir veridir, "veri yok" ile karıştırılmamalı.
    # Alt/üst sınır zaten aşağıdaki clamp (max/min) ile güvence altına alınıyor.
    if ac == 'ABD Hisse/ETF':
        beta = td.get_beta_value(symbol)
        if beta is not None:
            return round(max(1.0, min(8.0, beta * 4)), 2)
        return 4.0

    # BIST → yfinance beta
    yf_sym = symbol if symbol.upper().endswith('.IS') else symbol + '.IS'
    try:
        import yfinance as yf
        beta = yf.Ticker(yf_sym).info.get('beta')
        if beta is not None:
            return round(max(1.0, min(8.0, float(beta) * 4)), 2)
    except Exception:
        pass

    return 4.0

@router.get("/risk-scores")
def get_portfolio_risk_scores(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Portföydeki her sembol için yfinance beta'dan riskScore döner.
    Cache'de olanları anında döner, olmayanlara paralel yfinance çağrısı yapar.
    7 gün TTL ile SQLite'a cache'lenir.
    """
    positions = get_positions(user_id, db=db)
    scores: dict = {}
    to_fetch: list = []  # (sym, ac) — cache'de yok

    for pos in positions:
        sym = pos['ticker']
        ac  = pos.get('asset_class') or ''
        cache_key = f"risk_score_{sym}"
        cached = _fc.get(cache_key, ttl=7 * 24 * 3600)
        if cached is not None:
            scores[sym] = cached
        else:
            to_fetch.append((sym, ac))

    # Paralel yfinance çağrısı (en fazla 8 thread)
    def fetch_one(sym_ac):
        sym, ac = sym_ac
        score = _compute_risk_score(sym, ac)
        _fc.set(f"risk_score_{sym}", score)
        return sym, score

    if to_fetch:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for future in as_completed(ex.submit(fetch_one, t) for t in to_fetch):
                try:
                    sym, score = future.result()
                    scores[sym] = score
                except Exception:
                    pass

    return {"scores": scores}

@router.get("/targets", response_model=List[TargetAllocation])
def list_targets(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Hedef dağılım oranlarını al"""
    rows = get_target_allocations(user_id, db=db)
    return [TargetAllocation(**r) for r in rows]

@router.post("/targets", response_model=List[TargetAllocation])
def save_targets(
    allocations: List[TargetAllocationCreate],
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Hedef dağılım oranlarını kaydet. Toplamın ~%100 olması zorunlu — aksi halde
    rebalans sapma uyarıları yanlış hesaplanıyordu (eskiden hiç kontrol edilmiyordu)."""
    total_pct = sum(a.target_pct for a in allocations)
    if allocations and not (99.0 <= total_pct <= 101.0):
        raise HTTPException(
            status_code=400,
            detail=f"Hedef oranların toplamı %100 olmalı (şu an %{total_pct:.1f})."
        )
    rows = save_target_allocations(user_id, allocations, db=db)
    return [TargetAllocation(**r) for r in rows]

@router.post("/reset")
@limiter.limit("5/minute")
def reset_portfolio_db(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Çağıran kullanıcının kendi pozisyon/işlem geçmişini siler ve demo verileriyle değiştirir.

    GÜVENLİK DÜZELTMESİ: Bu endpoint eskiden hiçbir kimlik doğrulama içermiyordu VE
    init_db.init_database() çağırarak Base.metadata.drop_all() ile TÜM veritabanını
    (tüm kullanıcılar, tüm tablolar) silip yeniden oluşturuyordu — canlıda kimliksiz
    herhangi biri POST isteğiyle bunu tetikleyebiliyordu. Artık kimlik doğrulaması
    zorunlu ve etkisi SADECE çağıran kullanıcının kendi pozisyon/işlem kayıtlarıyla
    sınırlı; başka hiçbir kullanıcıya veya tabloya dokunulmuyor.
    """
    from db_models import DBPosition, DBTransaction
    from init_db import load_holdings_to_db
    try:
        db.query(DBTransaction).filter(DBTransaction.user_id == user_id).delete()
        db.query(DBPosition).filter(DBPosition.user_id == user_id).delete()
        db.commit()
        load_holdings_to_db(user_id=user_id)
        return {"status": "success", "message": "Portfolio reset to demo defaults"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
