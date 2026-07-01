# -*- coding: utf-8 -*-
"""
tefas_tools.py — TEFAS fon analiz çekirdeği (MCP server'a bağlanır)

Sağlanan işlevler:
  track_my_funds()      — YAY/GBG/HBU izleme, XIRR, korelasyon, rebalans
  screen_tefas_funds()  — tüm TEFAS tarama, CAGR/DD/Sharpe/split validation

API sınırlamaları (pytefas):
  - Tarih derinliği: maks 5 yıl (2021 öncesi hard-blocked)
  - breakdown endpoint fund_code filtresi çalışmıyor → tüm fonlar gelir
  - TER/yönetim ücreti, risk notu: API'de yok
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from dateutil.relativedelta import relativedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# ── Stopaj konfigürasyonu ────────────────────────────────────────────────────

_STOPAJ_CONFIG_PATH = os.path.join(_HERE, "stopaj_config.json")

def _load_stopaj_config() -> dict:
    try:
        with open(_STOPAJ_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _get_tax_category(fund_code: str, config: dict) -> str:
    """
    Fonun stopaj kategorisini döner: 'hisse_senedi_yogun_fon' | 'diger_fon'
    Önce stopaj_config.json'daki fon_siniflandirmalari tablosuna bakar,
    yoksa pytefas breakdown verisiyle dinamik tespit eder.
    """
    known = config.get("fon_siniflandirmalari", {}).get(fund_code.upper())
    if known:
        return known.get("kategori", "diger_fon")
    # Dinamik tespit: breakdown çek, stock_pct > %80 ise yoğun fon
    if not _TEFAS_OK or _crawler is None:
        return "diger_fon"
    try:
        today = date.today()
        week_ago = today - timedelta(days=7)
        df = _crawler.fetch_many(
            week_ago.isoformat(), today.isoformat(),
            kinds=("YAT",), columns="breakdown"
        )
        if not df.empty:
            sub = df[df["fund_code"] == fund_code.upper()]
            if not sub.empty:
                row = sub.sort_values("date").iloc[-1]
                stock = float(row.get("stock_pct", 0) or 0)
                foreign = float(row.get("foreign_stock_pct", 0) or 0)
                if stock >= 80.0 and foreign < 20.0:
                    return "hisse_senedi_yogun_fon"
    except Exception:
        pass
    return "diger_fon"

def _get_stopaj_rate(tax_category: str, holding_days: int, config: dict) -> float:
    """
    Verilen kategori için stopaj oranını döner.
    Tüm değerler stopaj_config.json'dan okunur — kod içinde sabit değer yok.
    holding_days parametresi şu an kullanılmıyor (mevcut kuralda elde tutma süresi etkisiz),
    ama ileride kural değişirse uyumluluk için signature'da tutuldu.
    """
    kategoriler = config.get("kategoriler", {})
    cat = kategoriler.get(tax_category, {})
    oranlar = cat.get("oranlar", {})
    # Her iki kategori de "tum_sureler" kullanıyor — yönetim ücreti/holding period yok
    return oranlar.get("tum_sureler", {}).get("stopaj_orani",
           0.0 if tax_category == "hisse_senedi_yogun_fon" else 0.175)

from cache import finance_cache

try:
    from backtest_composite import _load_tcmb_monthly
    _BACKTEST_OK = True
except ImportError:
    _BACKTEST_OK = False
    _load_tcmb_monthly = lambda: None

try:
    from pytefas import Crawler as _TefasCrawler
    _crawler = _TefasCrawler()
    _TEFAS_OK = True
except ImportError:
    _TEFAS_OK = False
    _crawler = None

# ── TCMB faiz serisi ────────────────────────────────────────────────────────

def _get_rf_dict() -> dict[date, float]:
    raw = _load_tcmb_monthly()
    if not raw:
        return {}
    return {dt: (1 + ann / 100) ** (1 / 12) - 1 for dt, ann in raw.items()}

def _tcmb_rf(rf_dict: dict, sim_date: date) -> float:
    cands = {k: v for k, v in rf_dict.items() if k <= sim_date}
    return cands[max(cands)] if cands else (1.40 ** (1 / 12)) - 1

# ── XIRR (bisection, scipy gerektirmez) ─────────────────────────────────────

def _xirr(cashflows: list[float], dates: list[date]) -> float:
    t0 = dates[0]
    def npv(r: float) -> float:
        return sum(cf / (1 + r) ** ((d - t0).days / 365.0)
                   for cf, d in zip(cashflows, dates))
    lo, hi = -0.9999, 500.0
    try:
        f_lo, f_hi = npv(lo), npv(hi)
        if f_lo * f_hi > 0:
            r = 0.15
            for _ in range(2000):
                f = npv(r)
                df_val = sum(
                    -cf * ((d - t0).days / 365.0) / (1 + r) ** ((d - t0).days / 365.0 + 1)
                    for cf, d in zip(cashflows, dates)
                )
                if df_val == 0:
                    break
                r_new = r - f / df_val
                if abs(r_new - r) < 1e-10:
                    return r_new
                r = r_new
            return r
        for _ in range(200):
            mid = (lo + hi) / 2.0
            f_mid = npv(mid)
            if abs(f_mid) < 1e-8 or (hi - lo) < 1e-10:
                return mid
            if f_lo * f_mid < 0:
                hi = mid
            else:
                lo = mid
                f_lo = f_mid
        return (lo + hi) / 2.0
    except Exception:
        return float("nan")

# ── Türkçe-dayanıklı string yardımcıları ────────────────────────────────────

def _ascii_upper(s: str) -> str:
    """
    Türkçe özel karakterleri ve pytefas'ın bozduğu (?) non-ASCII'yi
    ASCII eşdeğerine çevir, karşılaştırma için kullan.
    """
    s = s.upper()
    for fr, to in [("İ","I"),("Ş","S"),("Ğ","G"),("Ö","O"),("Ü","U"),("Ç","C"),
                   ("Â","A"),("Û","U"),("Î","I"),("I","I")]:
        s = s.replace(fr, to)
    # pytefas'ın garbled ettiği non-ASCII karakterleri sil
    s = re.sub(r'[^\x20-\x7E]', '', s)
    return s

def _cat_eq(a: str, b: str) -> bool:
    """Kategori isimlerini Türkçe-bağımsız karşılaştır."""
    return _ascii_upper(a) == _ascii_upper(b)


# ── Fon kategorisi (isim tabanlı, encoding-dayanıklı) ───────────────────────

def _categorize(fund_name: str) -> str:
    n = _ascii_upper(fund_name)
    # Anahtar kelimeler de normalize edilmiş halde karşılaştırılıyor
    if "YABANCI" in n:
        # Yabancı fon — hisse/ETF/karma ayırt et
        if any(k in n for k in ["HISSE", "G-20", "GLOBAL", "TEKNOLOJI"]):
            return "Yabancı Hisse Senedi"
        if any(k in n for k in ["TAHVIL", "BORCLANMA", "EUROBOND", "BONO"]):
            return "Yabancı Tahvil/Borç"
        return "Yabancı Hisse Senedi"  # yabancı fon → çoğunlukla hisse
    if any(k in n for k in ["BIST 30","BIST30","BIST 50","BIST 100","BIST100","ENDEKS"]):
        return "Endeks (BIST)"
    if any(k in n for k in ["HISSE","H SSE"]):  # H SSE = H?SSE normalize
        return "Hisse Senedi (TL)"
    if any(k in n for k in ["PARA PIYASASI","PARA P YASAS"]):
        return "Para Piyasası"
    if any(k in n for k in ["TAHVIL","BORCLANMA","EUROBOND","BONO"]):
        return "Tahvil/Borçlanma"
    if any(k in n for k in ["ALTIN","KIYMETLI MADEN","PRECIOUS"]):
        return "Altın/Kıymetli Maden"
    if any(k in n for k in ["FON SEPET","FUND OF"]):
        return "Fon Sepeti"
    if "KATILIM" in n:
        return "Katılım"
    if any(k in n for k in ["KARMA","DEGISKEN","SERBEST"]):
        return "Karma/Değişken"
    return "Diğer/Serbest"

# ── pytefas NAV çekici ───────────────────────────────────────────────────────

def _fund_kind(fund_code: str) -> str:
    """Fonun kind'ini belirle ve cache'le."""
    code = fund_code.upper().strip()
    cache_key = f"tefas_kind_{code}"
    cached = finance_cache.get(cache_key, ttl=30 * 24 * 3600)
    if cached:
        return cached

    # Standart TEFAS yatırım fonlarının %99'u 3 harflidir ve 'YAT' tipindedir.
    # Bu optimizasyon, Takasbank sunucusuna gereksiz istek atarak uygulamanın kilitlenmesini engeller.
    if len(code) == 3:
        finance_cache.set(cache_key, "YAT")
        return "YAT"

    if not _TEFAS_OK:
        return "YAT"
    today_str = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    for k in ("YAT", "EMK", "BYF", "GYF", "GSYF"):
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _crawler.fetch,
                    week_ago, today_str, kind=k,
                    columns="info", fund_code=code
                )
                df = future.result(timeout=4.0)
            if not df.empty:
                finance_cache.set(cache_key, k)
                return k
        except Exception as e:
            # Ağ zaman aşımı (timeout) durumunda diğer türleri deneyip vakit kaybetme
            if "timeout" in str(e).lower() or isinstance(e, TimeoutError):
                break
            continue
    finance_cache.set(cache_key, "YAT")
    return "YAT"

def _get_nav_series(fund_code: str, start_date: date, end_date: date) -> pd.Series:
    """
    Belirli bir fonun günlük NAV serisini veritabanı önbelleğinden çeker.
    Döner: pd.Series (index=date, value=float).
    """
    import twelve_data as td
    return td.get_tefas_nav(fund_code, start_date, end_date)

def _price_as_of(nav: pd.Series, as_of: date) -> Optional[float]:
    if nav is None or nav.empty:
        return None
    ts = pd.Timestamp(as_of)
    idx = nav.index[nav.index <= ts]
    return float(nav.loc[idx[-1]]) if not idx.empty else None

# ── Toplu aylık snapshot (tarama için) ──────────────────────────────────────

def _get_all_funds_snapshot(month_date: date) -> pd.DataFrame:
    """
    Belirtilen ay için tüm YAT+EMK+BYF fonlarının NAV snapshot'ını çek.
    Bir haftalık pencere alır, her fonun son mevcut fiyatını döner.
    Döner: DataFrame (fund_code, fund_name, price, portfolio_size, investor_count, date)
    """
    if not _TEFAS_OK:
        return pd.DataFrame()

    cache_key = f"tefas_snapshot_{month_date.isoformat()}"
    cached = finance_cache.get(cache_key, ttl=7 * 24 * 3600)
    if cached is not None:
        return cached

    window_start = month_date
    window_end = min(month_date + timedelta(days=6), date.today())
    if window_start > date.today():
        return pd.DataFrame()

    try:
        df = _crawler.fetch_many(
            window_start.isoformat(), window_end.isoformat(),
            kinds=("YAT", "EMK", "BYF"),
            columns="info"
        )
        if df is None or df.empty:
            finance_cache.set(cache_key, pd.DataFrame())
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["date"])
        # Her fon için en son tarihi al
        df = df.sort_values("date")
        df = df.groupby("fund_code", as_index=False).last()
        finance_cache.set(cache_key, df)
        return df
    except Exception:
        return pd.DataFrame()

# ── Metrik hesaplama (aylık getiri serisinden) ───────────────────────────────

def _compute_metrics(monthly_returns: list[float],
                     monthly_rf: list[float]) -> dict:
    if len(monthly_returns) < 3:
        return {}
    n = len(monthly_returns)
    twr = 1.0
    for r in monthly_returns:
        twr *= (1 + r)
    cagr = (twr ** (12 / n) - 1) * 100

    cum = 1.0; peak = 1.0; max_dd = 0.0
    for r in monthly_returns:
        cum *= (1 + r); peak = max(peak, cum)
        max_dd = max(max_dd, (peak - cum) / peak)

    ex = [r - rf for r, rf in zip(monthly_returns, monthly_rf)]
    mu = sum(ex) / len(ex)
    sd = math.sqrt(sum((x - mu) ** 2 for x in ex) / max(len(ex) - 1, 1))
    sharpe = (mu / sd) * math.sqrt(12) if sd > 0 else 0.0
    win_rate = sum(1 for r in monthly_returns if r > 0) / n * 100

    # Split validation
    mid = n // 2
    def _half_cagr(rl: list[float]) -> Optional[float]:
        if len(rl) < 3:
            return None
        t = 1.0
        for r in rl: t *= (1 + r)
        return round((t ** (12 / len(rl)) - 1) * 100, 2)

    split_a = _half_cagr(monthly_returns[:mid])
    split_b = _half_cagr(monthly_returns[mid:])

    return {
        "cagr_pct": round(cagr, 2),
        "max_dd_pct": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 3),
        "win_rate_pct": round(win_rate, 1),
        "months": n,
        "split_a_cagr": split_a,
        "split_b_cagr": split_b,
        "split_consistent": bool(
            split_a is not None and split_b is not None
            and split_a > 0 and split_b > 0
        ),
    }

# ════════════════════════════════════════════════════════════════════════════
# TOOL 1 — track_my_funds
# ════════════════════════════════════════════════════════════════════════════

def track_my_funds(
    fund_weights: Optional[dict[str, float]] = None,
    dca_start: str = "2023-06-21",
    dca_monthly_tl: float = 20_000.0,
) -> dict:
    """
    YAY/GBG/HBU (veya özel sepet) izleme:
    - Güncel NAV, 1A/3A/6A/12A getiri
    - Lot bazlı DCA takibi → Brüt XIRR + Net XIRR (stopaj sonrası)
    - TWR metrikleri (CAGR, MaxDD, Sharpe)
    - Stopaj sınıflandırması ve lot bazında vergi tahmini
    - Korelasyon matrisi
    - Rebalans sapması (hedef vs. mevcut ağırlıklar)

    fund_weights: {fon_kodu: ağırlık} toplamı 1.0 olmalı.
                 Varsayılan: {"YAY": 0.45, "GBG": 0.30, "HBU": 0.25}
    """
    if not _TEFAS_OK:
        return {"error": "pytefas kurulu değil. `pip install pytefas`"}

    if fund_weights is None:
        fund_weights = {"YAY": 0.45, "GBG": 0.30, "HBU": 0.25}

    start_date = date.fromisoformat(dca_start)
    end_date = date.today()
    rf_dict = _get_rf_dict()
    stopaj_config = _load_stopaj_config()

    # ── Stopaj kategorileri ─────────────────────────────────────────────────
    tax_categories: dict[str, str] = {
        code: _get_tax_category(code, stopaj_config)
        for code in fund_weights
    }

    # ── NAV serileri ────────────────────────────────────────────────────────
    nav_data: dict[str, pd.Series] = {}
    fund_meta: dict[str, dict] = {}
    fetch_start = start_date - timedelta(days=390)  # 13 ay öncesi (12A getiri için)

    for code in fund_weights:
        nav = _get_nav_series(code, fetch_start, end_date)
        nav_data[code] = nav
        if not nav.empty:
            current_nav = float(nav.iloc[-1])

            def _ret(months_back: int, _nav: pd.Series = nav,
                     _cn: float = current_nav) -> Optional[float]:
                past = end_date - relativedelta(months=months_back)
                px_past = _price_as_of(_nav, past)
                if px_past and px_past > 0:
                    return round((_cn / px_past - 1) * 100, 2)
                return None

            fund_meta[code] = {
                "current_nav": round(current_nav, 4),
                "nav_date": nav.index[-1].strftime("%Y-%m-%d"),
                "return_1m_pct": _ret(1),
                "return_3m_pct": _ret(3),
                "return_6m_pct": _ret(6),
                "return_12m_pct": _ret(12),
                "tax_category": tax_categories[code],
            }
        else:
            fund_meta[code] = {"error": "Veri çekilemedi",
                                "tax_category": tax_categories[code]}

    # ── Lot bazlı DCA simülasyonu ───────────────────────────────────────────
    # Her aylık alım ayrı bir "lot" — elde tutma süresi için purchase_date gerekli
    dca_months: list[date] = []
    d = start_date
    while d <= end_date:
        dca_months.append(d)
        d += relativedelta(months=1)
    N = len(dca_months)

    # Lot kaydı: her lot için {fund, purchase_date, cost_tl, shares, nav_at_buy}
    lots: list[dict] = []
    shares_total: dict[str, float] = {c: 0.0 for c in fund_weights}
    prev_aum = 0.0
    twr_returns: list[float] = []
    rf_series: list[float] = []
    monthly_aum: list[float] = []

    for sim_date in dca_months:
        dietz_denom = prev_aum + dca_monthly_tl
        for code, w in fund_weights.items():
            cost_tl = dca_monthly_tl * w
            px = _price_as_of(nav_data[code], sim_date)
            if px and px > 0:
                sh = cost_tl / px
                shares_total[code] += sh
                lots.append({
                    "fund": code,
                    "purchase_date": sim_date,
                    "cost_tl": cost_tl,
                    "shares": sh,
                    "nav_at_buy": px,
                })

        aum = sum(
            shares_total[c] * (_price_as_of(nav_data[c], sim_date) or 0.0)
            for c in fund_weights
        )
        dietz = (aum / dietz_denom - 1) if dietz_denom > 0 else 0.0
        twr_returns.append(dietz)
        rf_series.append(_tcmb_rf(rf_dict, sim_date))
        monthly_aum.append(aum)
        prev_aum = aum

    final_aum = monthly_aum[-1] if monthly_aum else 0.0
    total_invested = dca_monthly_tl * N
    twr_metrics = _compute_metrics(twr_returns, rf_series)

    # ── Brüt XIRR ───────────────────────────────────────────────────────────
    gross_cfs = [-dca_monthly_tl] * N
    gross_cfs[-1] += final_aum
    gross_xirr = _xirr(gross_cfs, dca_months)

    # ── Stopaj (lot bazlı) + Net XIRR ───────────────────────────────────────
    # "Şu an satılsaydı" senaryosu: her lotun stopaj tahmini
    lot_tax_details: list[dict] = []
    total_gross_gain = 0.0
    total_tax = 0.0
    total_net_proceeds = 0.0

    # Per-fund net için ara toplamlar
    fund_tax_summary: dict[str, dict] = {
        c: {"cost_tl": 0.0, "current_value_tl": 0.0, "gross_gain_tl": 0.0,
            "tax_tl": 0.0, "net_proceeds_tl": 0.0, "tax_category": tax_categories[c],
            "lots": 0, "lots_over_1yr": 0}
        for c in fund_weights
    }

    for lot in lots:
        code = lot["fund"]
        current_nav = _price_as_of(nav_data[code], end_date)
        if current_nav is None or current_nav <= 0:
            # Fallback: son bilinen NAV
            nav_s = nav_data[code]
            current_nav = float(nav_s.iloc[-1]) if not nav_s.empty else lot["nav_at_buy"]

        current_value = lot["shares"] * current_nav
        gross_gain = current_value - lot["cost_tl"]
        holding_days = (end_date - lot["purchase_date"]).days
        tax_cat = tax_categories[code]
        rate = _get_stopaj_rate(tax_cat, holding_days, stopaj_config)
        tax = max(0.0, gross_gain) * rate  # kayıplar için stopaj yok
        net = current_value - tax

        lot_tax_details.append({
            "fund": code,
            "purchase_date": lot["purchase_date"].isoformat(),
            "cost_tl": round(lot["cost_tl"], 2),
            "current_value_tl": round(current_value, 2),
            "gross_gain_tl": round(gross_gain, 2),
            "holding_days": holding_days,
            "holding_years": round(holding_days / 365, 2),
            "tax_category": tax_cat,
            "stopaj_rate_pct": round(rate * 100, 2),
            "tax_tl": round(tax, 2),
            "net_proceeds_tl": round(net, 2),
        })

        total_gross_gain += gross_gain
        total_tax += tax
        total_net_proceeds += net

        fs = fund_tax_summary[code]
        fs["cost_tl"] += lot["cost_tl"]
        fs["current_value_tl"] += current_value
        fs["gross_gain_tl"] += gross_gain
        fs["tax_tl"] += tax
        fs["net_proceeds_tl"] += net
        fs["lots"] += 1
        if holding_days >= 365:
            fs["lots_over_1yr"] += 1

    # Fund bazlı özet yuvarlama
    for c in fund_tax_summary:
        fs = fund_tax_summary[c]
        for k in ("cost_tl", "current_value_tl", "gross_gain_tl", "tax_tl", "net_proceeds_tl"):
            fs[k] = round(fs[k], 0)
        eff_rate = (fs["tax_tl"] / fs["gross_gain_tl"] * 100) if fs["gross_gain_tl"] > 0 else 0.0
        fs["effective_tax_rate_pct"] = round(eff_rate, 2)

    # Net XIRR
    net_cfs = [-dca_monthly_tl] * N
    net_cfs[-1] += total_net_proceeds
    net_xirr = _xirr(net_cfs, dca_months)

    # ── Korelasyon matrisi (haftalık getiri) ────────────────────────────────
    corr_result: dict = {}
    weekly_data: dict[str, pd.Series] = {}
    for code, nav in nav_data.items():
        if not nav.empty:
            w_nav = nav.resample("W").last().ffill()
            weekly_data[code] = w_nav
    if len(weekly_data) >= 2:
        combined = pd.concat(weekly_data, axis=1).dropna()
        if len(combined) >= 5:
            corr_result = combined.pct_change().corr().round(3).to_dict()

    # ── Rebalans sapması ─────────────────────────────────────────────────────
    rebalance: dict = {}
    if final_aum > 0:
        current_values = {
            c: shares_total[c] * (_price_as_of(nav_data[c], end_date) or 0.0)
            for c in fund_weights
        }
        max_drift = 0.0
        drift_details = {}
        for c, target_w in fund_weights.items():
            actual_w = current_values.get(c, 0.0) / final_aum
            drift = actual_w - target_w
            drift_details[c] = {
                "target_pct": round(target_w * 100, 1),
                "actual_pct": round(actual_w * 100, 1),
                "drift_pp": round(drift * 100, 2),
                "rebalance_needed": abs(drift) > 0.05,
                "current_value_tl": round(current_values.get(c, 0.0), 0),
            }
            max_drift = max(max_drift, abs(drift))
        rebalance = {
            "max_drift_pp": round(max_drift * 100, 2),
            "needs_rebalance": max_drift > 0.05,
            "details": drift_details,
        }

    stopaj_config_meta = {
        "last_updated": stopaj_config.get("_meta", {}).get("last_updated", "bilinmiyor"),
        "config_path": _STOPAJ_CONFIG_PATH,
        "warning": "Stopaj oranları sık değişiyor — stopaj_config.json'u periyodik güncelleyin.",
    }

    return {
        "period": {"start": dca_start, "end": end_date.isoformat(), "months": N},
        "dca": {"monthly_tl": dca_monthly_tl, "total_invested_tl": round(total_invested, 0)},
        "fund_info": fund_meta,
        "portfolio": {
            "final_aum_tl": round(final_aum, 0),
            "net_gain_gross_tl": round(total_gross_gain, 0),
            "net_gain_gross_pct": round((final_aum / total_invested - 1) * 100, 2) if total_invested > 0 else 0,
            "xirr_gross_pct": round(gross_xirr * 100, 2),
            "twr_cagr_pct": twr_metrics.get("cagr_pct"),
            "max_dd_pct": twr_metrics.get("max_dd_pct"),
            "sharpe": twr_metrics.get("sharpe"),
            "win_rate_pct": twr_metrics.get("win_rate_pct"),
        },
        "stopaj": {
            "config": stopaj_config_meta,
            "senaryo": "su_an_satilsaydi",
            "toplam_stopaj_tl": round(total_tax, 0),
            "net_proceeds_tl": round(total_net_proceeds, 0),
            "xirr_net_pct": round(net_xirr * 100, 2),
            "xirr_fark_pp": round((gross_xirr - net_xirr) * 100, 2),
            "fon_bazli_ozet": fund_tax_summary,
            "not": (
                "Stopaj kazanç üzerinden hesaplanır (maliyet düşüldükten sonra). "
                "Zarar eden lotlarda stopaj=0. "
                "Lot bazlı detay 'lot_detaylari' alanında."
            ),
        },
        "lot_detaylari": lot_tax_details,
        "rebalance": rebalance,
        "correlation": corr_result,
    }


# ════════════════════════════════════════════════════════════════════════════
# TOOL 2 — suggest_next_contribution
# ════════════════════════════════════════════════════════════════════════════

def suggest_next_contribution(
    monthly_amount: float = 20_000.0,
    fund_weights: Optional[dict[str, float]] = None,
    dca_start: str = "2023-06-21",
    correction_alpha: float = 1.0,
    min_floor_pct: float = 10.0,
    convergence_threshold_pp: float = 2.0,
) -> dict:
    """
    Mevcut sapma için satışsız (contribution-tilt) rebalans önerisi.

    Gelecek ayın katkısını hedefe en hızlı yaklaştıracak şekilde dağıtır.
    Satış yapılmaz — sadece yeni para dağılımı değiştirilir.

    correction_alpha : 1.0 = tam drift düzeltmesi (agresif),
                       0.5 = yarım düzeltme (daha dengeli)
    min_floor_pct    : Hiçbir fona bu %'nin altında para gitmesin (varsayılan %10)
    convergence_threshold_pp : Bu pp altına inince "hedefe ulaşıldı" (varsayılan 2pp)
    """
    if fund_weights is None:
        fund_weights = {"YAY": 0.45, "GBG": 0.30, "HBU": 0.25}

    # ── Mevcut durumu al (cache'li — tekrar çekilmez) ───────────────────────
    state = track_my_funds(
        fund_weights=fund_weights,
        dca_start=dca_start,
        dca_monthly_tl=monthly_amount,
    )

    rebal   = state["rebalance"]
    stopaj  = state["stopaj"]
    port    = state["portfolio"]
    final_aum = port["final_aum_tl"]

    # Mevcut değerler ve ağırlıklar
    current_values: dict[str, float] = {
        c: rebal["details"][c]["current_value_tl"] for c in fund_weights
    }
    current_weights: dict[str, float] = {
        c: rebal["details"][c]["actual_pct"] / 100.0 for c in fund_weights
    }
    target_weights: dict[str, float] = {
        c: rebal["details"][c]["target_pct"] / 100.0 for c in fund_weights
    }
    drift: dict[str, float] = {
        c: current_weights[c] - target_weights[c] for c in fund_weights
    }  # pozitif = fazla, negatif = eksik

    # ── Tilt dağılımını hesapla ─────────────────────────────────────────────
    # Temel formül: alloc[i] = target[i] - alpha * drift[i]
    # Overweight fona daha az, underweight fona daha fazla ver.
    min_floor = min_floor_pct / 100.0
    raw: dict[str, float] = {
        c: target_weights[c] - correction_alpha * drift[c] for c in fund_weights
    }
    # Floor uygula
    floored: dict[str, float] = {c: max(min_floor, raw[c]) for c in raw}
    # Yeniden normalize et (floor sonrası toplam 1'den sapabilir)
    total = sum(floored.values())
    tilt: dict[str, float] = {c: floored[c] / total for c in floored}

    # TL tutarlar
    tilt_amounts: dict[str, float] = {
        c: round(monthly_amount * tilt[c], 2) for c in tilt
    }

    # Hedef dağılımla kıyaslama
    target_amounts: dict[str, float] = {
        c: round(monthly_amount * target_weights[c], 2) for c in fund_weights
    }
    delta_amounts: dict[str, float] = {
        c: round(tilt_amounts[c] - target_amounts[c], 2) for c in fund_weights
    }

    # ── Yakınsama tahmini (statik, getiri=0 varsayımı) ──────────────────────
    sim_values = {c: current_values[c] for c in fund_weights}
    sim_aum = final_aum
    months_to_converge: Optional[int] = None

    for m in range(1, 241):  # maks 20 yıl
        for c in tilt:
            sim_values[c] += monthly_amount * tilt[c]
        sim_aum += monthly_amount
        max_drift_pp = max(
            abs(sim_values[c] / sim_aum - target_weights[c]) * 100
            for c in fund_weights
        )
        if max_drift_pp < convergence_threshold_pp:
            months_to_converge = m
            break

    # ── Stopaj uyarısı ──────────────────────────────────────────────────────
    fon_ozet = stopaj.get("fon_bazli_ozet", {})
    stopaj_warnings: list[str] = []
    for c, fs in fon_ozet.items():
        tax = fs.get("tax_tl", 0)
        if tax > 0:
            stopaj_warnings.append(
                f"{c}'dan satış yapılsaydı {tax:,.0f} TL stopaj (%{fs.get('effective_tax_rate_pct',0):.1f}) tetiklerdi."
            )

    # Mevcut drift özeti
    drift_summary: dict[str, dict] = {}
    for c in fund_weights:
        d_pp = drift[c] * 100
        drift_summary[c] = {
            "current_pct": round(current_weights[c] * 100, 2),
            "target_pct":  round(target_weights[c]  * 100, 2),
            "drift_pp":    round(d_pp, 2),
            "status":      "fazla" if d_pp > 0.5 else ("eksik" if d_pp < -0.5 else "dengeli"),
        }

    return {
        "mevcut_durum": {
            "final_aum_tl": round(final_aum, 0),
            "dca_aum_orani_pct": round(monthly_amount / final_aum * 100, 2),
            "drift": drift_summary,
            "max_drift_pp": rebal["max_drift_pp"],
        },
        "oneri": {
            "algorithm":  f"contribution-tilt (alpha={correction_alpha}, floor={min_floor_pct}%)",
            "dagilim": {
                c: {
                    "pct":    round(tilt[c] * 100, 2),
                    "tl":     tilt_amounts[c],
                    "delta_vs_target_tl": delta_amounts[c],
                }
                for c in fund_weights
            },
            "toplam_tl": monthly_amount,
        },
        "yakinasma_tahmini": {
            "threshold_pp": convergence_threshold_pp,
            "months": months_to_converge,
            "years":  round(months_to_converge / 12, 1) if months_to_converge else None,
            "not": (
                "Statik projeksiyon — fiyat değişimi sıfır varsayılmıştır. "
                "Gerçek süre piyasa koşullarına göre değişir."
                if months_to_converge else
                "240 ay içinde yakınsama sağlanamıyor — satış veya büyük katkı artışı gerekebilir."
            ),
        },
        "stopaj_uyarisi": {
            "oneri": "Satışsız dengeleme öneriliyor — stopaj tetiklenmiyor.",
            "satis_senaryosu": stopaj_warnings,
            "toplam_kacinilab_stopaj_tl": round(stopaj.get("toplam_stopaj_tl", 0), 0),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# TOOL 3 — screen_tefas_funds
# ════════════════════════════════════════════════════════════════════════════

def screen_tefas_funds(
    category: Optional[str] = None,
    min_track_months: int = 24,
    top_n: int = 15,
    start_date_str: str = "2023-01-01",
    sort_by: str = "sharpe",
    require_split_consistent: bool = True,
) -> dict:
    """
    Tüm TEFAS fonlarını tara, filtrele ve sırala.

    category: None (hepsi) | "Yabancı Hisse Senedi" | "Hisse Senedi (TL)" |
              "Endeks (BIST)" | "Para Piyasası" | "Tahvil/Borçlanma" |
              "Altın/Kıymetli Maden" | "Fon Sepeti" | "Katılım" |
              "Karma/Değişken" | "Diğer/Serbest"
    min_track_months: en az kaç aylık geçmiş gerekli (varsayılan 24)
    top_n: kaç fon dönsün (varsayılan 15)
    sort_by: "sharpe" | "cagr" | "max_dd" | "win_rate" | "split_consistent"
    require_split_consistent: True ise her iki yarı-dönem de pozitif CAGR
                               olan fonları öne çıkar
    """
    if not _TEFAS_OK:
        return {"error": "pytefas kurulu değil."}

    start_date = date.fromisoformat(start_date_str)
    end_date = date.today()
    rf_dict = _get_rf_dict()

    # ── Aylık snapshot'lar ──────────────────────────────────────────────────
    monthly_dates: list[date] = []
    d = start_date
    while d <= end_date:
        monthly_dates.append(d)
        d += relativedelta(months=1)

    print(f"  {len(monthly_dates)} aylık snapshot alınıyor...", flush=True)
    fund_prices: dict[str, dict[date, float]] = {}
    fund_names: dict[str, str] = {}

    for i, dt in enumerate(monthly_dates):
        snap = _get_all_funds_snapshot(dt)
        if snap.empty:
            continue
        for _, row in snap.iterrows():
            code = row["fund_code"]
            if code not in fund_prices:
                fund_prices[code] = {}
                fund_names[code] = row.get("fund_name", code)
            if pd.notna(row["price"]) and row["price"] > 0:
                fund_prices[code][dt] = float(row["price"])
        if (i + 1) % 6 == 0:
            print(f"  {i+1}/{len(monthly_dates)} ay işlendi, {len(fund_prices)} fon...",
                  flush=True)
        time.sleep(0.02)

    print(f"  Toplam {len(fund_prices)} fon için veri alındı.", flush=True)

    # ── Metrik hesapla ──────────────────────────────────────────────────────
    results: list[dict] = []

    for code, price_dict in fund_prices.items():
        if len(price_dict) < min_track_months:
            continue
        sorted_dates = sorted(price_dict)
        prices = [price_dict[dt] for dt in sorted_dates]
        if len(prices) < 4:
            continue

        monthly_rets = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]
        monthly_rf = [_tcmb_rf(rf_dict, dt) for dt in sorted_dates[1:]]

        m = _compute_metrics(monthly_rets, monthly_rf)
        if not m:
            continue

        fund_name = fund_names.get(code, code)
        cat = _categorize(fund_name)

        if category and not _cat_eq(cat, category):
            continue
        if require_split_consistent and not m.get("split_consistent"):
            continue

        results.append({
            "fund_code": code,
            "fund_name": fund_name,
            "category": cat,
            "cagr_pct": m["cagr_pct"],
            "max_dd_pct": m["max_dd_pct"],
            "sharpe": m["sharpe"],
            "win_rate_pct": m["win_rate_pct"],
            "months": m["months"],
            "split_a_cagr": m["split_a_cagr"],
            "split_b_cagr": m["split_b_cagr"],
            "split_consistent": m["split_consistent"],
        })

    # ── Sırala ──────────────────────────────────────────────────────────────
    sort_keys = {
        "sharpe":   (lambda r: r["sharpe"], True),
        "cagr":     (lambda r: r["cagr_pct"], True),
        "max_dd":   (lambda r: r["max_dd_pct"], False),  # küçük DD iyi
        "win_rate": (lambda r: r["win_rate_pct"], True),
    }
    key_fn, reverse = sort_keys.get(sort_by, sort_keys["sharpe"])
    results.sort(key=key_fn, reverse=reverse)
    top = results[:top_n]

    # ── Kategori dağılımı (gelen tüm filtreli sonuçlarda) ─────────────────
    cat_counts: dict[str, int] = {}
    for r in results:
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1

    return {
        "query": {
            "category": category or "Tümü",
            "min_track_months": min_track_months,
            "sort_by": sort_by,
            "require_split_consistent": require_split_consistent,
            "start_date": start_date_str,
            "top_n": top_n,
        },
        "summary": {
            "total_funds_fetched": len(fund_prices),
            "passed_filters": len(results),
            "category_distribution": cat_counts,
        },
        "top_funds": top,
        "note": (
            "Metrikler aylık NAV değişiminden hesaplanmıştır (TWR). "
            "TER/yönetim ücreti pytefas API'sinde mevcut değil — brüt getiriler. "
            "split_consistent=True: her iki dönem yarısında da CAGR>0 demektir. "
            "Tarih derinliği maks 5 yıl (API kısıtı)."
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# TOOL 4 — screen_tax_exempt_funds  (hisse senedi yoğun fon evreni)
# ════════════════════════════════════════════════════════════════════════════

def _get_breakdown_snapshot() -> pd.DataFrame:
    """
    Tüm YAT fonlarının en güncel breakdown'ını tek seferde çek.
    Her fon için son mevcut satırı döner.
    Cache TTL: 1 gün.
    """
    cache_key = f"tefas_breakdown_{date.today().isoformat()}"
    cached = finance_cache.get(cache_key, ttl=24 * 3600)
    if cached is not None:
        return cached
    if not _TEFAS_OK:
        return pd.DataFrame()
    today = date.today()
    week_ago = today - timedelta(days=7)
    try:
        df = _crawler.fetch_many(
            week_ago.isoformat(), today.isoformat(),
            kinds=("YAT",), columns="breakdown"
        )
        if df is None or df.empty:
            finance_cache.set(cache_key, pd.DataFrame())
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        df = df.groupby("fund_code", as_index=False).last()
        finance_cache.set(cache_key, df)
        return df
    except Exception as e:
        print(f"  [WARN] Breakdown alınamadı: {e}", flush=True)
        return pd.DataFrame()


def screen_tax_exempt_funds(
    min_track_months: int = 24,
    top_n: int = 15,
    start_date_str: str = "2023-01-01",
    sort_by: str = "sharpe",
    require_split_consistent: bool = True,
    stock_pct_threshold: float = 80.0,
    foreign_pct_max: float = 20.0,
) -> dict:
    """
    Hisse senedi yoğun fon evreni taraması — vergi muaf (%0 stopaj) fonlar.

    Filtre: pytefas breakdown'dan
      stock_pct >= stock_pct_threshold  (varsayılan 80.0)
      VE foreign_stock_pct < foreign_pct_max (varsayılan 20.0)

    Bu eşiği geçen her fon GVK Geç.Md.67 kapsamında %0 stopaj;
    isim/etiket/kategori bağımsız.

    Metrikler: CAGR, MaxDD, Sharpe (TCMB excess return), split validation.
    """
    if not _TEFAS_OK:
        return {"error": "pytefas kurulu değil."}

    start_date = date.fromisoformat(start_date_str)
    end_date = date.today()
    rf_dict = _get_rf_dict()

    # ── 1. Breakdown → hisse_yogun aday listesi ─────────────────────────────
    print("  Breakdown verisi çekiliyor (tüm YAT fonları)...", flush=True)
    bkdn = _get_breakdown_snapshot()

    if bkdn.empty:
        return {"error": "Breakdown verisi alınamadı."}

    cols = list(bkdn.columns)
    print(f"  Breakdown sütunları: {cols}", flush=True)

    # Sütun adlarını bul (pytefas versiyonuna göre değişebilir)
    stock_col = next(
        (c for c in cols if c in ("stock_pct", "stock", "hisse_pct", "equity_pct")), None
    )
    foreign_col = next(
        (c for c in cols if c in (
            "foreign_stock_pct", "foreign_stock", "foreign_equity_pct",
            "yabanci_hisse_pct", "foreign_equity"
        )), None
    )

    if not stock_col:
        return {"error": f"stock_pct sütunu bulunamadı. Mevcut sütunlar: {cols}"}

    bkdn[stock_col] = pd.to_numeric(bkdn[stock_col], errors="coerce").fillna(0.0)

    if foreign_col:
        bkdn[foreign_col] = pd.to_numeric(bkdn[foreign_col], errors="coerce").fillna(0.0)
        # 0-1 mi 0-100 mi? (HBU=%94.55 → 0-100)
        if bkdn[stock_col].max() <= 1.5:
            bkdn[stock_col] *= 100
            bkdn[foreign_col] *= 100
        mask = (bkdn[stock_col] >= stock_pct_threshold) & (bkdn[foreign_col] < foreign_pct_max)
    else:
        if bkdn[stock_col].max() <= 1.5:
            bkdn[stock_col] *= 100
        mask = bkdn[stock_col] >= stock_pct_threshold

    yogun_df = bkdn[mask].copy()
    yogun_codes: set[str] = set(yogun_df["fund_code"].astype(str).str.upper())

    # Breakdown istatistiklerini sakla (çıktıda göstermek için)
    yogun_stats: dict[str, dict] = {}
    for _, row in yogun_df.iterrows():
        code = str(row["fund_code"]).upper()
        sp = float(row[stock_col])
        fp = float(row[foreign_col]) if foreign_col else 0.0
        yogun_stats[code] = {
            "stock_pct": round(sp, 2),
            "foreign_pct": round(fp, 2),
            "domestic_pct": round(sp - fp, 2),
        }

    print(
        f"  {len(bkdn)} fondan {len(yogun_codes)} hisse yoğun fon tespit edildi "
        f"(stock>={stock_pct_threshold}%, foreign<{foreign_pct_max}%).",
        flush=True,
    )

    # ── 2. Aylık snapshot → fiyat serileri (cache'den) ──────────────────────
    monthly_dates: list[date] = []
    d = start_date
    while d <= end_date:
        monthly_dates.append(d)
        d += relativedelta(months=1)

    print(f"  {len(monthly_dates)} aylık snapshot işleniyor (cache'den)...", flush=True)
    fund_prices: dict[str, dict[date, float]] = {}
    fund_names: dict[str, str] = {}

    for i, dt in enumerate(monthly_dates):
        snap = _get_all_funds_snapshot(dt)
        if snap.empty:
            continue
        for _, row in snap.iterrows():
            code = str(row["fund_code"]).upper()
            if code not in yogun_codes:
                continue
            if code not in fund_prices:
                fund_prices[code] = {}
                fund_names[code] = row.get("fund_name", code)
            if pd.notna(row["price"]) and row["price"] > 0:
                fund_prices[code][dt] = float(row["price"])
        if (i + 1) % 6 == 0:
            print(
                f"  {i+1}/{len(monthly_dates)} ay, {len(fund_prices)} yogun fon bulundu...",
                flush=True,
            )
        time.sleep(0.02)

    print(f"  NAV geçmişi: {len(fund_prices)} hisse yoğun fon.", flush=True)

    # ── 3. Metrik hesapla ───────────────────────────────────────────────────
    results: list[dict] = []

    for code, price_dict in fund_prices.items():
        if len(price_dict) < min_track_months:
            continue
        sorted_dates_p = sorted(price_dict)
        prices = [price_dict[dt] for dt in sorted_dates_p]
        if len(prices) < 4:
            continue

        monthly_rets = [prices[j] / prices[j - 1] - 1 for j in range(1, len(prices))]
        monthly_rf = [_tcmb_rf(rf_dict, dt) for dt in sorted_dates_p[1:]]

        m = _compute_metrics(monthly_rets, monthly_rf)
        if not m:
            continue
        if require_split_consistent and not m.get("split_consistent"):
            continue

        stats = yogun_stats.get(code, {})
        results.append({
            "fund_code": code,
            "fund_name": fund_names.get(code, code),
            "stock_pct": stats.get("stock_pct"),
            "foreign_pct": stats.get("foreign_pct"),
            "domestic_pct": stats.get("domestic_pct"),
            "cagr_pct": m["cagr_pct"],
            "max_dd_pct": m["max_dd_pct"],
            "sharpe": m["sharpe"],
            "win_rate_pct": m["win_rate_pct"],
            "months": m["months"],
            "split_a_cagr": m["split_a_cagr"],
            "split_b_cagr": m["split_b_cagr"],
            "split_consistent": m["split_consistent"],
        })

    # ── 4. Sırala ───────────────────────────────────────────────────────────
    sort_keys = {
        "sharpe":   (lambda r: r["sharpe"], True),
        "cagr":     (lambda r: r["cagr_pct"], True),
        "max_dd":   (lambda r: r["max_dd_pct"], False),
        "win_rate": (lambda r: r["win_rate_pct"], True),
    }
    key_fn, reverse = sort_keys.get(sort_by, sort_keys["sharpe"])
    results.sort(key=key_fn, reverse=reverse)

    return {
        "query": {
            "stock_pct_threshold": stock_pct_threshold,
            "foreign_pct_max": foreign_pct_max,
            "min_track_months": min_track_months,
            "sort_by": sort_by,
            "require_split_consistent": require_split_consistent,
            "start_date": start_date_str,
            "top_n": top_n,
        },
        "summary": {
            "total_breakdown_funds": len(bkdn),
            "yogun_candidates": len(yogun_codes),
            "with_nav_history": len(fund_prices),
            "passed_filters": len(results),
            "breakdown_columns": cols,
        },
        "top_funds": results[:top_n],
        "all_funds": results,
        "note": (
            "Hisse senedi yoğun fon = GVK Geç.Md.67 kapsamında %0 stopaj. "
            f"Filtre: stock_pct>={stock_pct_threshold} VE foreign_pct<{foreign_pct_max} "
            "(pytefas breakdown). Metrikler aylık NAV'dan TWR; "
            "Sharpe TCMB faizi excess return ile hesaplanmıştır."
        ),
    }
