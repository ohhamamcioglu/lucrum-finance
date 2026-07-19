"""
Birleşik Krallık (UK) vergi yardımcı hesaplamaları (Faz 3, task #58).

YASAL UYARI: Bu modül SADECE bilgilendirme amaçlıdır, profesyonel vergi tavsiyesi
DEĞİLDİR — bkz. frontend/src/components/TaxDashboardView.tsx'teki zorunlu uyarı metni.

ISA yıllık limiti (£20.000), 2017/18 vergi yılından beri değişmeyen, HMRC'nin
istikrarlı ve iyi bilinen resmi bir rakamıdır (kaynak: gov.uk/individual-savings-
accounts) — bu yüzden sabit kod olarak tutulur. Buna karşılık CGT (sermaye kazancı)
yıllık muafiyet tutarı son 3 vergi yılında üç kez değişti (2022/23: £12.300,
2023/24: £6.000, 2024/25: £3.000) — bu oynaklık nedeniyle SABİT KODLANMAZ,
kullanıcıdan güncel tutarı gov.uk/capital-gains-tax/allowances üzerinden teyit
edip girmesi istenir; sistem bu tutarı asla tahmin etmez.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

ISA_ANNUAL_ALLOWANCE_GBP = 20000.0  # gov.uk/individual-savings-accounts, 2017/18'den beri sabit


def uk_tax_year_start(as_of: date) -> date:
    """UK vergi yılı her 6 Nisan'da başlar. as_of 6 Nisan'dan önceyse bir önceki
    yılın 6 Nisan'ı, sonra/eşitse bu yılın 6 Nisan'ı döner."""
    candidate = date(as_of.year, 4, 6)
    if as_of < candidate:
        return date(as_of.year - 1, 4, 6)
    return candidate


def isa_allowance_used(buy_events_gbp: List[Dict[str, Any]], as_of: date) -> Dict[str, Any]:
    """Bu UK vergi yılında ISA sarmalı ile işaretli pozisyonlara yatırılan GERÇEK
    tutarı (gerçek işlem geçmişinden, sadece BUY işlemleri) toplar — tahmini değil.
    buy_events_gbp: [{"transaction_date": date, "amount_gbp": float}, ...] (sadece
    tax_wrapper == 'ISA' olan pozisyonların BUY işlemleri, çağıran taraf filtreler)."""
    year_start = uk_tax_year_start(as_of)
    used_gbp = sum(
        e["amount_gbp"] for e in buy_events_gbp
        if year_start <= e["transaction_date"] <= as_of
    )
    return {
        "tax_year_start": year_start.isoformat(),
        "used_gbp": round(used_gbp, 2),
        "allowance_gbp": ISA_ANNUAL_ALLOWANCE_GBP,
        "remaining_gbp": round(max(0.0, ISA_ANNUAL_ALLOWANCE_GBP - used_gbp), 2),
        "used_pct": round(min(100.0, used_gbp / ISA_ANNUAL_ALLOWANCE_GBP * 100), 1),
    }


def bed_and_isa_analysis(gia_unrealized_gains_gbp: List[float], cgt_allowance_gbp: float) -> Dict[str, Any]:
    """GIA (vergiye tabi genel yatırım hesabı) pozisyonlarındaki gerçekleşmemiş
    kazancı, kullanıcının girdiği GÜNCEL CGT muafiyet tutarıyla karşılaştırır —
    sadece pozitif (kâr) pozisyonlar CGT'ye tabi olabileceğinden dikkate alınır."""
    total_gain = sum(g for g in gia_unrealized_gains_gbp if g > 0)
    return {
        "total_gia_unrealized_gain_gbp": round(total_gain, 2),
        "cgt_allowance_gbp": cgt_allowance_gbp,
        "exceeds_allowance": total_gain > cgt_allowance_gbp,
        "excess_gbp": round(max(0.0, total_gain - cgt_allowance_gbp), 2),
    }
