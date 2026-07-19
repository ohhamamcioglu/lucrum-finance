"""
Hindistan vergi yardımcı hesaplamaları (Faz 3.5, task #59).

YASAL UYARI: SEBI (Securities and Exchange Board of India) düzenlemeleri kapsamında
bu modül SADECE bilgilendirme amaçlıdır, profesyonel vergi/yatırım tavsiyesi DEĞİLDİR.

KAPSAM SINIRI (kritik): Bu modül SADECE hisse-ağırlıklı (equity-oriented) varlıkları
kapsar — listelenmiş hisse senetleri ve equity-oriented yatırım fonları (mfapi.in'in
scheme_category alanında "equity" geçenler, bkz. mfapi.is_equity_oriented). Borç
fonları (debt funds) 2023 Bütçesi'nden (1 Nisan 2023 sonrası alınanlar için)
itibaren TAMAMEN farklı kurallara tabi (indexation kaldırıldı, LTCG rejimi hiç
uygulanmıyor, tüm kazanç dilim oranından STCG sayılıyor) — bu karmaşıklık nedeniyle
borç fonları bu modülde SINIFLANDIRILMAZ.

LTCG/STCG VERGİ ORANLARI ve muafiyet tutarı KULLANICIDAN istenir — bu oranlar
Union Budget (yıllık bütçe) ile değişebiliyor (en son bilinen değişiklik: 23 Temmuz
2024 bütçesinde equity STCG %15→%20, LTCG %10→%12.5, muafiyet ₹1L→₹1.25L oldu) —
sistem güncel oranı asla otomatik varsaymaz veya tahmin etmez. Resmi kaynak:
incometax.gov.in.

Section 80C limiti (₹1,50,000) 2014'ten beri sabit, iyi bilinen bir rakam olduğundan
sabit kod olarak tutulur (kaynak: Income Tax Act §80C). ELSS'in 3 yıllık zorunlu
kilitlenme süresi de yasal olarak sabit bir yapı kuralıdır (SEBI ELSS düzenlemeleri).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Tuple

SECTION_80C_LIMIT_INR = 150000.0  # Income Tax Act §80C, 2014'ten beri sabit
ELSS_LOCKIN_YEARS = 3
LTCG_STCG_HOLDING_DAYS = 365  # ~12 ay — sadece hisse-ağırlıklı varlıklar için geçerli


@dataclass
class Lot:
    buy_date: date
    quantity: float
    unit_price: float
    currency: str


def fifo_match(transactions: List[Dict[str, Any]]) -> Tuple[List[Lot], List[Dict[str, Any]]]:
    """Tek bir ticker'ın kronolojik BUY/SELL işlemlerini FIFO ile eşler. Almanya
    modülündeki (tax_germany.fifo_match) ile aynı mantık — ayrı tutulmasının nedeni,
    iki ülkenin vergi kurallarının birbirinden bağımsız evrilebilmesi."""
    lots: deque = deque()
    realized: List[Dict[str, Any]] = []
    for txn in sorted(transactions, key=lambda t: t["transaction_date"]):
        if txn["transaction_type"] == "BUY":
            lots.append(Lot(txn["transaction_date"], txn["quantity"], txn["price"], txn["currency"]))
        elif txn["transaction_type"] == "SELL":
            qty_to_sell = txn["quantity"]
            while qty_to_sell > 1e-9 and lots:
                lot = lots[0]
                matched_qty = min(lot.quantity, qty_to_sell)
                realized.append({
                    "sell_date": txn["transaction_date"],
                    "buy_date": lot.buy_date,
                    "quantity": matched_qty,
                    "gain_native": (txn["price"] - lot.unit_price) * matched_qty,
                    "currency": txn["currency"],
                    "holding_days": (txn["transaction_date"] - lot.buy_date).days,
                })
                lot.quantity -= matched_qty
                qty_to_sell -= matched_qty
                if lot.quantity <= 1e-9:
                    lots.popleft()
    return list(lots), realized


def classify_gain(holding_days: int) -> str:
    """Hisse-ağırlıklı bir varlık için LTCG/STCG sınıflandırması yapar."""
    return "LTCG" if holding_days >= LTCG_STCG_HOLDING_DAYS else "STCG"


def summarize_realized_gains(
    realized_events: List[Dict[str, Any]],
    ltcg_rate_pct: float,
    stcg_rate_pct: float,
    ltcg_exemption_inr: float,
) -> Dict[str, Any]:
    """Gerçekleşmiş kazançları LTCG/STCG olarak ayırıp, KULLANICININ girdiği
    oranlarla vergiyi tahmin eder. Oranlar/muafiyet kullanıcı girdisidir — bkz.
    modül docstring'i, sistem bunları asla varsaymaz."""
    ltcg_total = sum(e["gain_native"] for e in realized_events if classify_gain(e["holding_days"]) == "LTCG")
    stcg_total = sum(e["gain_native"] for e in realized_events if classify_gain(e["holding_days"]) == "STCG")

    ltcg_taxable = max(0.0, ltcg_total - ltcg_exemption_inr)
    ltcg_tax = ltcg_taxable * (ltcg_rate_pct / 100.0)
    stcg_tax = max(0.0, stcg_total) * (stcg_rate_pct / 100.0)

    return {
        "ltcg_total_inr": round(ltcg_total, 2),
        "stcg_total_inr": round(stcg_total, 2),
        "ltcg_exemption_inr": ltcg_exemption_inr,
        "ltcg_taxable_inr": round(ltcg_taxable, 2),
        "ltcg_tax_estimate_inr": round(ltcg_tax, 2),
        "stcg_tax_estimate_inr": round(stcg_tax, 2),
    }


def elss_lockin_status(buy_date: date, quantity: float, as_of: date) -> Dict[str, Any]:
    """Bir ELSS lot'unun kilitlenme durumunu döner — 3 yıllık zorunlu kilitlenme
    süresi (SEBI ELSS düzenlemeleri) gerçek alım tarihinden hesaplanır."""
    try:
        unlock_date = buy_date.replace(year=buy_date.year + ELSS_LOCKIN_YEARS)
    except ValueError:
        # 29 Şubat gibi kabise günleri — hedef yıl kabise değilse 28 Şubat'a düşer.
        unlock_date = buy_date.replace(year=buy_date.year + ELSS_LOCKIN_YEARS, day=28)
    locked = as_of < unlock_date
    return {
        "buy_date": buy_date.isoformat(),
        "quantity": quantity,
        "unlock_date": unlock_date.isoformat(),
        "locked": locked,
        "days_until_unlock": max(0, (unlock_date - as_of).days) if locked else 0,
    }


def india_fy_start(as_of: date) -> date:
    """Hindistan mali yılı her 1 Nisan'da başlar."""
    candidate = date(as_of.year, 4, 1)
    if as_of < candidate:
        return date(as_of.year - 1, 4, 1)
    return candidate


def section_80c_used(elss_buy_events_inr: List[Dict[str, Any]], as_of: date) -> Dict[str, Any]:
    """Bu Hindistan mali yılında ELSS'e yatırılan GERÇEK tutarı ₹1,50,000 birleşik
    §80C limitiyle karşılaştırır. NOT: §80C kapsamına giren TEK yatırım türü bu
    araçta takip edilen ELSS — sigorta primi/PPF/diğer §80C kalemleri dahil değil,
    kullanıcı bunları ayrıca hesaba katmalı."""
    fy_start = india_fy_start(as_of)
    used = sum(
        e["amount_inr"] for e in elss_buy_events_inr
        if fy_start <= e["transaction_date"] <= as_of
    )
    return {
        "fy_start": fy_start.isoformat(),
        "used_inr": round(used, 2),
        "limit_inr": SECTION_80C_LIMIT_INR,
        "remaining_inr": round(max(0.0, SECTION_80C_LIMIT_INR - used), 2),
        "used_pct": round(min(100.0, used / SECTION_80C_LIMIT_INR * 100), 1),
    }
