"""
Almanya vergi yardımcı hesaplamaları (Faz 3, task #58).

YASAL UYARI: Bu modül SADECE bilgilendirme amaçlıdır, profesyonel vergi tavsiyesi
DEĞİLDİR ve bir Steuerberater'ın (yeminli mali müşavir) yerini tutmaz — bkz.
frontend/src/components/TaxDashboardView.tsx'teki zorunlu uyarı metni.

Sparerpauschbetrag ve kripto 1 yıllık muafiyet hesaplamaları TAMAMEN kullanıcının
gerçek işlem geçmişinden (DBTransaction, FIFO eşleştirme) türetilir — hiçbir sayı
tahmin edilmez. Vorabpauschale hesaplayıcısı ise "Basiszins"i KULLANICIDAN ister:
bu oran Almanya Maliye Bakanlığı'nca (BMF) her yıl SADECE bir PDF sirkülerle
yayınlanır (örn. 2025 için %2,53 — bundesfinanzministerium.de/.../Investmentsteuer/
2025-01-10-basiszins-vorabpauschale-zum-2-1-2025.html), makine okunabilir hiçbir
resmi kaynağı yoktur (doğrulandı) — bu yüzden sistem bu oranı ASLA otomatik çekmez
veya varsayılan bir değer önermez.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Tuple

# §20 Abs. 9 EStG, 2023 itibarıyla (kaynak: gesetze-im-internet.de/estg/__20.html).
# Yasa değişirse bu sabitlerin güncellenmesi gerekir.
SPARERPAUSCHBETRAG_SINGLE_EUR = 1000.0
SPARERPAUSCHBETRAG_MARRIED_EUR = 2000.0

# §20 InvStG Teilfreistellung oranları (kaynak: gesetze-im-internet.de/invstg_2018/__20.html)
TEILFREISTELLUNG_RATES: Dict[str, float] = {
    "equity": 0.30,   # Aktienfonds (>=%51 hisse senedi)
    "mixed": 0.15,    # Mischfonds (>=%25 hisse senedi)
    "other": 0.0,
}

CRYPTO_TAX_FREE_HOLDING_DAYS = 365  # §23 Abs. 1 Nr. 2 EStG (Spekulationsfrist)


@dataclass
class Lot:
    buy_date: date
    quantity: float
    unit_price: float
    currency: str


def fifo_match(transactions: List[Dict[str, Any]]) -> Tuple[List[Lot], List[Dict[str, Any]]]:
    """Tek bir ticker'ın kronolojik BUY/SELL işlemlerini FIFO ile eşler.
    Döner: (hâlâ açık lotlar, gerçekleşmiş kazanç olayları). Satılan miktar mevcut
    lotlardan fazlaysa (örn. pozisyon manuel düzenlemeyle eklendi) fazlalık sessizce
    yok sayılır — uydurma bir lot OLUŞTURULMAZ."""
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
                gain_per_unit = txn["price"] - lot.unit_price
                realized.append({
                    "sell_date": txn["transaction_date"],
                    "buy_date": lot.buy_date,
                    "quantity": matched_qty,
                    "gain_native": gain_per_unit * matched_qty,
                    "currency": txn["currency"],
                    "holding_days": (txn["transaction_date"] - lot.buy_date).days,
                })
                lot.quantity -= matched_qty
                qty_to_sell -= matched_qty
                if lot.quantity <= 1e-9:
                    lots.popleft()
    return list(lots), realized


def crypto_holding_lots(transactions_by_ticker: Dict[str, List[Dict[str, Any]]], as_of: date) -> List[Dict[str, Any]]:
    """Her kripto ticker için hâlâ elde tutulan lotları, vergiden muaf olup olmadığıyla
    birlikte döner (>=365 gün = muaf, §23 Abs. 1 Nr. 2 EStG)."""
    out: List[Dict[str, Any]] = []
    for ticker, txns in transactions_by_ticker.items():
        open_lots, _ = fifo_match(txns)
        for lot in open_lots:
            holding_days = (as_of - lot.buy_date).days
            out.append({
                "ticker": ticker,
                "buy_date": lot.buy_date.isoformat(),
                "quantity": lot.quantity,
                "unit_price": lot.unit_price,
                "currency": lot.currency,
                "holding_days": holding_days,
                "tax_free": holding_days >= CRYPTO_TAX_FREE_HOLDING_DAYS,
                "days_until_tax_free": max(0, CRYPTO_TAX_FREE_HOLDING_DAYS - holding_days),
            })
    return out


def realized_gains_this_year(transactions_by_ticker: Dict[str, List[Dict[str, Any]]], year: int) -> List[Dict[str, Any]]:
    """Bu takvim yılındaki (Almanya vergi yılı = takvim yılı) tüm gerçekleşmiş kazanç
    olaylarını döner (EUR'a çevrilmemiş, ham — kur çevrimi I/O gerektirdiğinden çağıran
    tarafta yapılır)."""
    out: List[Dict[str, Any]] = []
    for ticker, txns in transactions_by_ticker.items():
        _, realized = fifo_match(txns)
        for r in realized:
            if r["sell_date"].year == year:
                r2 = dict(r)
                r2["ticker"] = ticker
                out.append(r2)
    return out


def vorabpauschale_base(
    value_start_eur: float,
    basiszins_pct: float,
    fund_type: str = "equity",
    months_held: int = 12,
    value_end_eur: float | None = None,
) -> Dict[str, Any]:
    """Vorabpauschale VERGİ MATRAHINI hesaplar (nihai vergi tutarını değil — o kişisel
    Sparerpauschbetrag kullanımına, kilise vergisine vb. bağlıdır).

    basiszins_pct KULLANICI TARAFINDAN girilir (bkz. modül docstring'i) — hiçbir
    zaman burada varsayılan/tahmini bir değer atanmaz.

    Formül (§18 InvStG): Basisertrag = Fondswert(yıl başı) × Basiszins × %70, ay
    bazında kıst hesaplanır (§18 Abs. 2). Vorabpauschale, gerçek yıllık değer artışını
    AŞAMAZ (§18 Abs. 1 Satz 3) — value_end_eur verilirse bu sınırlama uygulanır;
    verilmezse sınırlama uygulanmadığı bir uyarı ile belirtilir.
    """
    if fund_type not in TEILFREISTELLUNG_RATES:
        fund_type = "other"
    months = max(0, min(12, months_held))

    basisertrag = value_start_eur * (basiszins_pct / 100.0) * 0.7
    basisertrag_prorated = round(basisertrag * (months / 12.0), 2)

    capped = False
    vorabpauschale_gross = basisertrag_prorated
    if value_end_eur is not None:
        actual_gain = value_end_eur - value_start_eur
        capped_value = max(0.0, min(basisertrag_prorated, actual_gain))
        capped = capped_value < basisertrag_prorated
        vorabpauschale_gross = round(capped_value, 2)

    teilfreistellung = TEILFREISTELLUNG_RATES[fund_type]
    taxable_base = round(vorabpauschale_gross * (1 - teilfreistellung), 2)

    return {
        "basisertrag_prorated_eur": basisertrag_prorated,
        "vorabpauschale_gross_eur": vorabpauschale_gross,
        "capped_by_actual_gain": capped,
        "actual_gain_provided": value_end_eur is not None,
        "teilfreistellung_pct": teilfreistellung * 100,
        "taxable_base_eur": taxable_base,
    }
