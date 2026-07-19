"""
Almanya & UK vergi modülleri (Faz 3, task #58).

YASAL UYARI: Bu router'ın döndürdüğü hiçbir sayı profesyonel vergi tavsiyesi
DEĞİLDİR — sadece bilgilendirme amaçlıdır (bkz. frontend TaxDashboardView.tsx'teki
zorunlu ibare). Gerçekleşmiş kazanç ve kripto lot yaşlandırması TAMAMEN kullanıcının
gerçek işlem geçmişinden hesaplanır. Basiszins (Almanya) ve CGT muafiyet tutarı (UK)
gibi her yıl değişen resmi oranlar KULLANICIDAN istenir — sistem bunları asla
otomatik çekmez veya tahmin etmez (bkz. tax_germany.py / tax_uk.py docstring'leri).
"""
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import tax_germany
import tax_uk
from crud import get_positions, get_transactions
from dependencies import get_current_user_id, get_db
from models import VorabpauschaleRequest
from services import calculate_portfolio, get_usd_try_rate, get_eur_try_rate, get_gbp_try_rate

router = APIRouter(prefix="/api/tax", tags=["Tax"])


def _to_try(amount: float, currency: str, date_str: str) -> float:
    """Herhangi bir para birimindeki tutarı, o TARİHTEKİ gerçek kurla TRY'ye çevirir."""
    if currency == "TRY":
        return amount
    if currency == "USD":
        return amount * get_usd_try_rate(date_str)
    if currency == "EUR":
        return amount * get_eur_try_rate(date_str)
    if currency == "GBP":
        return amount * get_gbp_try_rate(date_str)
    return amount


def _convert(amount: float, from_currency: str, to_currency: str, date_str: str) -> Optional[float]:
    """İki para birimi arasında, o tarihteki gerçek çapraz kurla çevirir (TRY üzerinden)."""
    if from_currency == to_currency:
        return amount
    amount_try = _to_try(amount, from_currency, date_str)
    to_rate = 1.0
    if to_currency == "USD":
        to_rate = get_usd_try_rate(date_str)
    elif to_currency == "EUR":
        to_rate = get_eur_try_rate(date_str)
    elif to_currency == "GBP":
        to_rate = get_gbp_try_rate(date_str)
    return amount_try / to_rate if to_rate else None


@router.get("/germany")
def get_germany_tax_summary(
    married: bool = Query(False, description="Sparerpauschbetrag için evli çift muafiyeti (€2000) uygulanır"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Sparerpauschbetrag kullanım durumu ve kripto 1 yıllık muafiyet takibi —
    ikisi de kullanıcının gerçek işlem geçmişinden hesaplanır, hiçbir sayı tahmin
    edilmez."""
    transactions = get_transactions(user_id, db=db)
    txns_by_ticker: Dict[str, List[dict]] = defaultdict(list)
    for t in transactions:
        txns_by_ticker[t["ticker"]].append(t)

    today = date.today()
    realized_raw = tax_germany.realized_gains_this_year(txns_by_ticker, today.year)

    total_gain_eur = 0.0
    unconverted_events = 0
    for r in realized_raw:
        converted = _convert(r["gain_native"], r["currency"], "EUR", r["sell_date"].isoformat())
        if converted is None:
            unconverted_events += 1
            continue
        total_gain_eur += converted
    total_gain_eur = round(total_gain_eur, 2)

    exemption = tax_germany.SPARERPAUSCHBETRAG_MARRIED_EUR if married else tax_germany.SPARERPAUSCHBETRAG_SINGLE_EUR

    crypto_tickers = {p["ticker"] for p in get_positions(user_id, db=db) if p["asset_class"] == "Kripto"}
    crypto_txns = {tk: txns_by_ticker[tk] for tk in crypto_tickers if tk in txns_by_ticker}
    crypto_lots = tax_germany.crypto_holding_lots(crypto_txns, today)

    return {
        "year": today.year,
        "sparerpauschbetrag": {
            "married": married,
            "exemption_eur": exemption,
            "realized_gain_eur": total_gain_eur,
            "used_pct": round(min(100.0, max(0.0, total_gain_eur) / exemption * 100), 1) if exemption else 0,
            "remaining_eur": round(max(0.0, exemption - total_gain_eur), 2),
            "unconverted_events": unconverted_events,
        },
        "crypto_lots": crypto_lots,
        "crypto_tax_free_holding_days": tax_germany.CRYPTO_TAX_FREE_HOLDING_DAYS,
    }


@router.post("/germany/vorabpauschale")
def calculate_vorabpauschale(
    req: VorabpauschaleRequest,
    user_id: int = Depends(get_current_user_id),
):
    """Vorabpauschale vergi matrahı hesaplayıcısı. basiszins_pct KULLANICI girdisidir
    (bkz. tax_germany.py docstring'i) — resmi kaynak: BMF'nin yıllık İnvestmentsteuer
    sirküleri (bundesfinanzministerium.de), makine okunabilir bir API'si yoktur."""
    return tax_germany.vorabpauschale_base(
        value_start_eur=req.value_start_eur,
        basiszins_pct=req.basiszins_pct,
        fund_type=req.fund_type,
        months_held=req.months_held,
        value_end_eur=req.value_end_eur,
    )


@router.get("/uk")
def get_uk_tax_summary(
    cgt_allowance_gbp: Optional[float] = Query(
        None, description="Güncel UK CGT yıllık muafiyet tutarı — gov.uk/capital-gains-tax/allowances üzerinden teyit edilip girilmeli"
    ),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """ISA yıllık limit kullanımı (gerçek işlem geçmişinden) ve Bed-and-ISA analizi
    (kullanıcı CGT muafiyet tutarını girerse)."""
    positions = get_positions(user_id, db=db)
    isa_tickers = {p["ticker"] for p in positions if p.get("tax_wrapper") == "ISA"}
    gia_tickers = {p["ticker"] for p in positions if p.get("tax_wrapper") == "GIA"}

    today = date.today()
    buy_events_gbp = []
    if isa_tickers:
        transactions = get_transactions(user_id, db=db)
        for t in transactions:
            if t["ticker"] not in isa_tickers or t["transaction_type"] != "BUY":
                continue
            amount_native = t["quantity"] * t["price"]
            amount_gbp = _convert(amount_native, t["currency"], "GBP", t["transaction_date"].isoformat())
            if amount_gbp is None:
                continue
            buy_events_gbp.append({"transaction_date": t["transaction_date"], "amount_gbp": amount_gbp})

    isa_summary = tax_uk.isa_allowance_used(buy_events_gbp, today)

    bed_and_isa = None
    if cgt_allowance_gbp is not None:
        portfolio = calculate_portfolio(user_id)
        gains = [
            h["gross_return_gbp"]
            for h in portfolio.get("holdings", [])
            if h.get("tax_wrapper") == "GIA" and h["ticker"] in gia_tickers and h.get("gross_return_gbp") is not None
        ]
        bed_and_isa = tax_uk.bed_and_isa_analysis(gains, cgt_allowance_gbp)

    return {
        "isa_allowance": isa_summary,
        "bed_and_isa": bed_and_isa,
    }
