# -*- coding: utf-8 -*-
"""
tefas_analyzer.py — TEFAS Fon Analiz ve Backtest Motoru
======================================================
Kullanım:
    python tefas_analyzer.py --tickers AFT,TCD,MAC --weights 0.40,0.30,0.30 --dca 20000
    python tefas_analyzer.py --tickers AFT,TCD --weights 0.50,0.50 --lumpsum 100000 --start 2024-01-01
"""

import os
import sys
import json
import math
import argparse
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import pandas as pd
import numpy as np
import twelve_data as td

# Local modülleri içe aktarmak için workspace yolunu ekle
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# ── local TCMB faiz yükleyicisi ──────────────────────────────────────────────
try:
    from backtest_composite import _load_tcmb_monthly
except ImportError:
    _load_tcmb_monthly = lambda: None

def _get_tcmb_rf_series(start_date: date, end_date: date) -> dict[date, float]:
    """TCMB politika faiz geçmişini çeker, başarısızsa yıllık %40 varsayılan faiz döner."""
    tcmb_raw = _load_tcmb_monthly()
    tcmb_monthly_rf = {}
    if tcmb_raw:
        for dt, ann in tcmb_raw.items():
            tcmb_monthly_rf[dt] = (1 + ann/100) ** (1/12) - 1
    else:
        # Fallback: Sabit %40 yıllık faiz -> aylık bileşik
        d = start_date
        while d <= end_date:
            tcmb_monthly_rf[d] = (1.40 ** (1/12)) - 1
            d = d + relativedelta(months=1)
    return tcmb_monthly_rf

def _tcmb_rf(rf_dict: dict, sim_date: date) -> float:
    if not rf_dict:
        return (1.40 ** (1/12)) - 1
    cands = {k: v for k, v in rf_dict.items() if k <= sim_date}
    return rf_dict[max(cands)] if cands else (1.40 ** (1/12)) - 1

# ── TEFAS Veri Çekici ────────────────────────────────────────────────────────
def fetch_fund_data(ticker: str, start_date: date, end_date: date) -> pd.Series:
    """
    Belirli bir ticker için TEFAS'tan günlük fiyat serisini çeker.
    28 günlük parçalara bölerek sorgular ve her parçayı SQLite cache'de saklar.
    """
    from pytefas import Crawler
    from cache import finance_cache
    from datetime import timedelta
    
    ticker = ticker.upper().strip()
    
    # 28 günlük parçalara böl
    chunks = []
    curr = start_date
    while curr <= end_date:
        chunk_end = min(curr + timedelta(days=27), end_date)
        chunks.append((curr, chunk_end))
        curr = chunk_end + timedelta(days=1)
        
    total_chunks = len(chunks)
    crawler = Crawler()
    all_series = []
    
    # Doğru fon türünü bulmak için (YAT, EMK, BYF vs.) ilk bulduğumuz geçerli türü kilitleyeceğiz.
    # Böylece her chunk için tekrar tekrar tüm türleri denemek zorunda kalmayız.
    fund_kind = None
    
    # Önce cache'den kontrol et
    cached_kind_key = f"tefas_kind_{ticker}"
    try:
        fund_kind = finance_cache.get(cached_kind_key, ttl=finance_cache.TTL_FINANCIALS)
    except Exception:
        pass
        
    for idx, (c_start, c_end) in enumerate(chunks, 1):
        cache_key = f"tefas_chunk_{ticker}_{c_start.isoformat()}_{c_end.isoformat()}"
        chunk_prices = None
        try:
            chunk_prices = finance_cache.get(cache_key, ttl=finance_cache.TTL_PRICE)
        except Exception:
            pass
            
        if chunk_prices is not None and isinstance(chunk_prices, pd.Series):
            all_series.append(chunk_prices)
            continue
            
        # Cache'de yoksa çek
        start_str = c_start.strftime("%Y-%m-%d")
        end_str = c_end.strftime("%Y-%m-%d")
        
        kinds_to_try = [fund_kind] if fund_kind else ["YAT", "EMK", "BYF", "GYF", "GSYF"]
        success = False
        
        for kind in kinds_to_try:
            try:
                df = crawler.fetch(start_str, end_str, kind=kind, fund_code=ticker)
                if df is not None and not df.empty:
                    df['date'] = pd.to_datetime(df['date'])
                    df = df.sort_values('date')
                    chunk_prices = pd.Series(df['price'].values, index=pd.to_datetime(df['date']).dt.normalize())
                    
                    # Başarılı olunca türü kaydet ve cache'e yaz
                    if not fund_kind:
                        fund_kind = kind
                        try:
                            finance_cache.set(cached_kind_key, fund_kind)
                        except Exception:
                            pass
                            
                    try:
                        finance_cache.set(cache_key, chunk_prices)
                    except Exception:
                        pass
                        
                    all_series.append(chunk_prices)
                    success = True
                    break
            except Exception:
                continue
                
        # Eğer bu chunk için hiç veri bulunamadıysa (hafta sonu/tatil günleri denk gelirse boş dönebilir)
        if not success:
            # Boş seriyi cache'e yazıp devam ediyoruz ki her seferinde tekrar denemesin
            empty_s = pd.Series(dtype=float)
            try:
                finance_cache.set(cache_key, empty_s)
            except Exception:
                pass
            all_series.append(empty_s)
            
        print(f"  [{ticker}] Parça {idx}/{total_chunks} yüklendi ({c_start} - {c_end})", flush=True)
        
    if not all_series:
        return pd.Series(dtype=float)
        
    combined = pd.concat(all_series)
    # Çift kayıtları kaldır ve sırala
    combined = combined[~combined.index.duplicated(keep='last')].sort_index()
    return combined

def load_benchmark_prices(ticker: str, start_date: date, end_date: date) -> pd.Series:
    """Benchmark fiyatlarını yerel historical_db'den veya Twelve Data'dan yükler."""
    try:
        import historical_db as hdb
        # Momentum hesaplaması için 7 ay öncesinden çek
        start_cov = start_date - relativedelta(months=7)
        db_prices = hdb.load_prices(ticker.upper(), date_from=start_cov, date_to=end_date)
        if not db_prices.empty:
            db_prices.index = pd.to_datetime(db_prices.index).tz_localize(None).normalize()
            return db_prices
    except Exception:
        pass
        
    try:
        start_cov = start_date - relativedelta(months=7)
        days_to_fetch = (end_date - start_cov).days + 10
        print(f"  Downloading benchmark {ticker} from Twelve Data...")
        series = td.get_time_series(ticker, days=max(days_to_fetch, 30), interval="1day")
        if series:
            dates = [pd.to_datetime(p["date"][:10]) for p in series]
            prices_list = [p["close"] for p in series]
            s = pd.Series(prices_list, index=dates)
            s.index = s.index.tz_localize(None).normalize()
            return s.sort_index()
    except Exception as e:
        print(f"  Benchmark {ticker} yüklenirken HATA: {e}")
    return pd.Series(dtype=float)

# ── Yardımcı Fiyat Alıcı ──────────────────────────────────────────────────────
def _price_as_of(prices: pd.Series, as_of: date) -> float | None:
    if prices is None or prices.empty:
        return None
    # Endeks tarih tipine göre arama yap (datetime64 vs date uyuşmazlığı önlemek için)
    ts = pd.Timestamp(as_of)
    idx = prices.index[prices.index <= ts]
    if idx.empty:
        return None
    return float(prices.loc[idx[-1]])

# ── Metrik Hesaplama ──────────────────────────────────────────────────────────
def calculate_metrics(returns: list[float], rf_series: list[float]) -> dict:
    if not returns:
        return {}
    n_months = len(returns)
    n_years = n_months / 12.0
    
    # Time-Weighted Return (TWR) kümülatif getiri
    twr = 1.0
    for r in returns:
        twr *= (1 + r)
    total_return = twr - 1.0
    cagr = (twr ** (1 / n_years) - 1.0) if n_years > 0 else 0.0
    
    # Drawdown hesabı
    cum = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        cum *= (1 + r)
        peak = max(peak, cum)
        max_dd = max(max_dd, (peak - cum) / peak)
        
    # Sharpe Oranı (Değişken Aylık Politika Faizine Göre)
    ex = [r - rf for r, rf in zip(returns, rf_series)]
    mu = np.mean(ex)
    sd = np.std(ex, ddof=1) if len(ex) > 1 else 0.0
    sharpe = (mu / sd) * math.sqrt(12) if sd > 0.0 else 0.0
    
    # Win Rate
    win_rate = sum(1 for r in returns if r > 0) / len(returns)
    
    return {
        "cagr_pct": round(cagr * 100, 2),
        "total_return_pct": round(total_return * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 3),
        "win_rate_pct": round(win_rate * 100, 1)
    }

# ── Backtest Simülatörü ────────────────────────────────────────────────────────
def run_backtest(
    fund_prices: dict[str, pd.Series],
    weights: dict[str, float],
    usdtry_prices: pd.Series,
    rf_dict: dict,
    start_date: date,
    end_date: date,
    dca_amount: float = 20000.0,
    lump_sum: float = 0.0
) -> dict:
    months = []
    d = start_date
    while d <= end_date:
        months.append(d)
        d = d + relativedelta(months=1)
        
    if months[-1] != end_date:
        months.append(end_date)
        
    portfolio = {tk: 0.0 for tk in weights} # ticker -> sahip olunan pay adedi
    aum_series = []
    monthly_returns = []
    rf_series = []
    
    first_month = True
    prev_aum_start = 0.0
    
    for sim_date in months:
        # 1. Değerleme ve Getiri Hesabı (Önceki ayın yatırımlarının bu tarihteki değeri)
        if not first_month:
            aum_end_before_flow = 0.0
            for tk, shares in portfolio.items():
                px = _price_as_of(fund_prices[tk], sim_date)
                if px:
                    aum_end_before_flow += shares * px
            
            ret = (aum_end_before_flow / prev_aum_start - 1) if prev_aum_start > 0 else 0.0
            monthly_returns.append(ret)
            rf_series.append(_tcmb_rf(rf_dict, sim_date))
            
            if sim_date == end_date:
                aum_series.append({
                    "date": sim_date.strftime("%Y-%m-%d"),
                    "aum": round(aum_end_before_flow, 2)
                })
                prev_aum_start = aum_end_before_flow
                continue
        
        # 2. Yeni Akışların (DCA / Lumpsum) eklenmesi ve Alım yapılması
        flow_this_month = 0.0
        if first_month:
            flow_this_month = lump_sum + dca_amount
            first_month = False
        else:
            flow_this_month = dca_amount
            
        # Akışı dağıtıp alım yapıyoruz
        for tk, w in weights.items():
            px = _price_as_of(fund_prices[tk], sim_date)
            if px and px > 0:
                shares_bought = (flow_this_month * w) / px
                portfolio[tk] += shares_bought
                
        # Alım sonrası yeni AUM Başlangıç değeri
        aum_start = 0.0
        for tk, shares in portfolio.items():
            px = _price_as_of(fund_prices[tk], sim_date)
            if px:
                aum_start += shares * px
                
        prev_aum_start = aum_start
        
        aum_series.append({
            "date": sim_date.strftime("%Y-%m-%d"),
            "aum": round(aum_start, 2)
        })
        
    final_aum = prev_aum_start
    
    m = calculate_metrics(monthly_returns, rf_series)
    return {
        "metrics": m,
        "aum_series": aum_series,
        "monthly_returns": monthly_returns,
        "rf_series": rf_series,
        "final_aum": final_aum
    }

def run_benchmark_dca(
    prices: pd.Series,
    usdtry_prices: pd.Series,
    start_date: date,
    end_date: date,
    dca_amount: float = 20000.0,
    lump_sum: float = 0.0,
    is_usd_asset: bool = False
) -> dict:
    months = []
    d = start_date
    while d <= end_date:
        months.append(d)
        d = d + relativedelta(months=1)
        
    if months[-1] != end_date:
        months.append(end_date)
        
    shares = 0.0
    aum_series = []
    monthly_returns = []
    rf_series = []
    
    # load rf
    rf_raw = _load_tcmb_monthly()
    rf_dict = {}
    if rf_raw:
        for dt, ann in rf_raw.items():
            rf_dict[dt] = (1 + ann/100) ** (1/12) - 1
            
    first_month = True
    prev_aum_start = 0.0
    
    for sim_date in months:
        kur = _price_as_of(usdtry_prices, sim_date) or 38.0
        
        # 1. Değerleme ve Getiri Hesabı
        if not first_month:
            px = _price_as_of(prices, sim_date)
            if px:
                if is_usd_asset:
                    aum_end_before_flow = shares * px * kur
                else:
                    aum_end_before_flow = shares * px
            else:
                aum_end_before_flow = prev_aum_start
                
            ret = (aum_end_before_flow / prev_aum_start - 1) if prev_aum_start > 0 else 0.0
            monthly_returns.append(ret)
            rf_series.append(_tcmb_rf(rf_dict, sim_date))
            
            if sim_date == end_date:
                aum_series.append({
                    "date": sim_date.strftime("%Y-%m-%d"),
                    "aum": round(aum_end_before_flow, 2)
                })
                prev_aum_start = aum_end_before_flow
                continue
                
        # 2. Yeni Akışların Eklenmesi ve Alım
        flow_this_month = 0.0
        if first_month:
            flow_this_month = lump_sum + dca_amount
            first_month = False
        else:
            flow_this_month = dca_amount
            
        px = _price_as_of(prices, sim_date)
        if px and px > 0:
            if is_usd_asset:
                shares += (flow_this_month / kur) / px
            else:
                shares += flow_this_month / px
                
        # Alım sonrası yeni AUM Başlangıç değeri
        px_now = _price_as_of(prices, sim_date)
        if px_now:
            if is_usd_asset:
                aum_start = shares * px_now * kur
            else:
                aum_start = shares * px_now
        else:
            aum_start = prev_aum_start
            
        prev_aum_start = aum_start
        
        aum_series.append({
            "date": sim_date.strftime("%Y-%m-%d"),
            "aum": round(aum_start, 2)
        })
        
    final_aum = prev_aum_start
    m = calculate_metrics(monthly_returns, rf_series)
    return {
        "metrics": m,
        "aum_series": aum_series,
        "monthly_returns": monthly_returns,
        "final_aum": final_aum
    }

# ── Korelasyon Analizi ────────────────────────────────────────────────────────
def compute_correlations(fund_prices: dict[str, pd.Series]) -> pd.DataFrame:
    df_list = []
    for tk, s in fund_prices.items():
        # Günlük serileri haftalık ortalamaya çekip hizala
        s_weekly = s.resample('W').last().ffill()
        df_list.append(s_weekly.rename(tk.upper()))
    combined = pd.concat(df_list, axis=1).dropna()
    if combined.empty or len(combined) < 5:
        return pd.DataFrame()
    return combined.pct_change().corr()

# ── Raporlama ─────────────────────────────────────────────────────────────────
def print_report(
    tickers: list[str],
    weights: dict[str, float],
    sepet_result: dict,
    xu100_result: dict,
    spy_result: dict,
    usd_result: dict,
    corr_matrix: pd.DataFrame,
    start_date: date,
    end_date: date,
    dca: float,
    lump_sum: float
):
    print()
    print("=" * 90)
    print("  TEFAS FON SEPETİ GERİYE DÖNÜK TEST RAPORU (BACKTEST)")
    print(f"  Dönem : {start_date} — {end_date}  ({len(sepet_result['monthly_returns'])} ay)")
    print(f"  Katkı : DCA = {dca:,.0f} TL/ay  |  Toplu Para = {lump_sum:,.0f} TL")
    print("=" * 90)
    
    # Portföy yapısı
    print("\nSepet Dağılımı:")
    for tk in tickers:
        print(f"  - {tk.upper()}: %{weights[tk]*100:.1f}")
        
    # Karşılaştırma Tablosu
    print("\nPerformans ve Risk Karşılaştırması:")
    col_w = 18
    print(f"  {'Metrik':<28} {'Sepetim':>{col_w}} {'BIST 100':>{col_w}} {'S&P 500 (TL)':>{col_w}} {'Dolar (TRY)':>{col_w}}")
    print("  " + "-" * 105)
    
    metrics_list = [
        sepet_result["metrics"],
        xu100_result["metrics"],
        spy_result["metrics"],
        usd_result["metrics"]
    ]
    
    rows = [
        ("CAGR (%)", "cagr_pct", "{:.2f}%"),
        ("Toplam TWR (%)", "total_return_pct", "{:.2f}%"),
        ("Maksimum Düşüş (%)", "max_drawdown_pct", "{:.2f}%"),
        ("Sharpe Oranı", "sharpe", "{:.3f}"),
        ("Kazanma Oranı (Ay %)", "win_rate_pct", "{:.1f}%")
    ]
    
    for label, key, fmt in rows:
        row_str = f"  {label:<28}"
        for m in metrics_list:
            val = m.get(key, 0.0)
            row_str += f" {fmt.format(val):>{col_w}}"
        print(row_str)
        
    total_invested = lump_sum + dca * len(sepet_result["monthly_returns"])
    print("  " + "-" * 105)
    print(f"  {'Toplam Yatırılan':<28} {total_invested:>17,.0f} TL {total_invested:>17,.0f} TL {total_invested:>17,.0f} TL {total_invested:>17,.0f} TL")
    print(f"  {'Final Portföy Değeri':<28} {sepet_result['final_aum']:>17,.0f} TL {xu100_result['final_aum']:>17,.0f} TL {spy_result['final_aum']:>17,.0f} TL {usd_result['final_aum']:>17,.0f} TL")
    
    gain_sepet = sepet_result['final_aum'] - total_invested
    gain_xu = xu100_result['final_aum'] - total_invested
    gain_spy = spy_result['final_aum'] - total_invested
    gain_usd = usd_result['final_aum'] - total_invested
    print(f"  {'Net Kazanç / Kayıp':<28} {gain_sepet:>+17,.0f} TL {gain_xu:>+17,.0f} TL {gain_spy:>+17,.0f} TL {gain_usd:>+17,.0f} TL")
    print(f"  {'Net Getiri Oranı':<28} {(sepet_result['final_aum']/total_invested-1)*100:>16.1f}% {(xu100_result['final_aum']/total_invested-1)*100:>16.1f}% {(spy_result['final_aum']/total_invested-1)*100:>16.1f}% {(usd_result['final_aum']/total_invested-1)*100:>16.1f}%")

    # Korelasyon Matrisi
    if not corr_matrix.empty:
        print("\nSepet İçi Haftalık Fiyat Değişim Korelasyonu:")
        print(corr_matrix.to_string())
        print("\n  * Not: Düşük veya negatif korelasyon, portföy çeşitlendirmesinin kalitesini gösterir.")
        
    print("\n" + "=" * 90)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="TEFAS Mutual Fund Backtester")
    parser.add_argument("--tickers", type=str, default="AFT,TCD,MAC",
                        help="Karşılaştırılacak TEFAS fon kodları (virgülle ayrılmış)")
    parser.add_argument("--weights", type=str, default="0.40,0.30,0.30",
                        help="Fon ağırlıkları (virgülle ayrılmış, toplamı 1.0 olmalı)")
    parser.add_argument("--dca", type=float, default=20000.0,
                        help="Aylık DCA katkı tutarı (TL)")
    parser.add_argument("--lumpsum", type=float, default=0.0,
                        help="Başlangıç toplu para yatırma tutarı (TL)")
    parser.add_argument("--start", type=str, default="2023-05-01",
                        help="Simülasyon başlangıç tarihi (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-05-31",
                        help="Simülasyon bitiş tarihi (YYYY-MM-DD)")
    args = parser.parse_args()

    # Parametreleri parse et
    tickers = [t.upper().strip() for t in args.tickers.split(",")]
    weights_list = [float(w) for w in args.weights.split(",")]
    
    if len(tickers) != len(weights_list):
        print("HATA: Ticker sayısı ile ağırlık sayısı eşleşmiyor!")
        sys.exit(1)
        
    if not math.isclose(sum(weights_list), 1.0, abs_tol=1e-5):
        print(f"HATA: Ağırlıklar toplamı 1.0 olmalıdır! (Şu anki toplam: {sum(weights_list):.4f})")
        sys.exit(1)
        
    weights = dict(zip(tickers, weights_list))
    
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    
    print("[1/4] TEFAS verileri yükleniyor...")
    fund_prices = {}
    # start_date'ten 15 gün öncesinden başlatarak ilk tarihteki fiyatı doğru bulmayı garanti ediyoruz
    start_fetch = start_date - relativedelta(days=15)
    for tk in tickers:
        prices = fetch_fund_data(tk, start_fetch, end_date)
        if prices.empty:
            print(f"HATA: {tk} fonu için TEFAS'tan veri çekilemedi!")
            sys.exit(1)
        fund_prices[tk] = prices
        
    print("[2/4] Döviz kuru ve endeks verileri yükleniyor...")
    usdtry = load_benchmark_prices("USDTRY=X", start_date, end_date)
    xu100 = load_benchmark_prices("XU100.IS", start_date, end_date)
    spy = load_benchmark_prices("SPY", start_date, end_date)
    
    if usdtry.empty:
        # Fallback — Twelve Data'dan geçmiş kur serisi
        print("  Dolar kuru alınamadı, Twelve Data araması yapılıyor...")
        td_series = td.get_time_series("USD/TRY", days=1825, interval="1day")
        if td_series:
            usdtry = pd.Series(
                {pd.to_datetime(item["date"][:10]): float(item["close"])
                 for item in td_series if item.get("close")},
                dtype=float
            )
            usdtry.index = pd.to_datetime(usdtry.index).tz_localize(None).normalize()
        
    print("[3/4] TCMB politika faiz geçmişi yükleniyor...")
    rf_dict = _get_tcmb_rf_series(start_date, end_date)
    
    # ── Simülasyonlar ─────────────────────────────────────────────────────────
    print("[4/4] Backtest simülasyonları çalıştırılıyor...")
    
    # 1. Sepet backtest'i
    sepet_result = run_backtest(
        fund_prices, weights, usdtry, rf_dict,
        start_date, end_date, dca_amount=args.dca, lump_sum=args.lumpsum
    )
    
    # 2. BIST 100 backtest'i
    xu100_result = run_benchmark_dca(
        xu100, usdtry, start_date, end_date,
        dca_amount=args.dca, lump_sum=args.lumpsum, is_usd_asset=False
    )
    
    # 3. SPY backtest'i (USD asset)
    spy_result = run_benchmark_dca(
        spy, usdtry, start_date, end_date,
        dca_amount=args.dca, lump_sum=args.lumpsum, is_usd_asset=True
    )
    
    # 4. Sadece Dolar (USD Cash) backtest'i
    usd_only_prices = pd.Series(1.0, index=usdtry.index)
    usd_result = run_benchmark_dca(
        usd_only_prices, usdtry, start_date, end_date,
        dca_amount=args.dca, lump_sum=args.lumpsum, is_usd_asset=True
    )
    
    # Korelasyon
    corr_matrix = compute_correlations(fund_prices)
    
    # Raporu yazdır
    print_report(
        tickers, weights, sepet_result, xu100_result, spy_result, usd_result,
        corr_matrix, start_date, end_date, args.dca, args.lumpsum
    )
    
    # Sonuçları JSON olarak kaydet
    out_data = {
        "tickers": tickers,
        "weights": weights,
        "start": args.start,
        "end": args.end,
        "dca": args.dca,
        "lumpsum": args.lumpsum,
        "results": {
            "sepet": sepet_result["metrics"],
            "xu100": xu100_result["metrics"],
            "spy": spy_result["metrics"],
            "usd": usd_result["metrics"]
        }
    }
    with open(os.path.join(_HERE, "tefas_results.json"), "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    print("Sonuçlar tefas_results.json dosyasına yazıldı.")

if __name__ == "__main__":
    main()
