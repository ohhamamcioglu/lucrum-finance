"""
LUCRUM Finance MCP Server
Finansal analiz araçları: yfinance + SEC EDGAR
"""

import re
import time
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Any
import twelve_data as td
import pandas as pd
import numpy as np
import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("lucrum-finance")

from cache import finance_cache as _fc

def _cached(key: str, ttl: float | None = None) -> Any:
    return _fc.get(key, ttl if ttl is not None else _fc.TTL_FINANCIALS)

def _set_cache(key: str, val: Any) -> None:
    _fc.set(key, val)


class TwelveDataTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self._info = None
        self._financials = None
        self._balance_sheet = None
        self._cashflow = None
        
    @property
    def info(self) -> dict:
        if self._info is None:
            q = td.get_quote(self.symbol) or {}
            p = td.get_profile(self.symbol) or {}
            s = td.get_statistics(self.symbol) or {}
            self._info = {
                "longName": p.get("name") or q.get("name") or self.symbol,
                "shortName": p.get("name") or q.get("name") or self.symbol,
                "sector": p.get("sector") or "N/A",
                "industry": p.get("industry") or "N/A",
                "exchange": p.get("exchange") or "N/A",
                "currency": p.get("currency") or "USD",
                "marketCap": s.get("market_cap"),
                "currentPrice": q.get("close"),
                "regularMarketPrice": q.get("close"),
                "previousClose": q.get("previous_close") or q.get("close"),
                "fiftyTwoWeekHigh": q.get("wk52_high"),
                "fiftyTwoWeekLow": q.get("wk52_low"),
                "averageVolume": q.get("avg_volume"),
                "fullTimeEmployees": p.get("employees"),
                "longBusinessSummary": p.get("description", ""),
                "trailingPE": s.get("pe_trailing"),
                "priceToBook": s.get("pb_ratio"),
                "pegRatio": s.get("peg_ratio"),
                "dividendYield": None,
                "regularMarketVolume": q.get("volume"),
                "volume": q.get("volume"),
            }
        return self._info
        
    def history(self, period: str = "1y", start=None, end=None) -> pd.DataFrame:
        days = 365
        if period == "1d": days = 1
        elif period == "5d": days = 5
        elif period == "1m": days = 30
        elif period == "3m": days = 90
        elif period == "6m": days = 180
        elif period == "1y": days = 365
        elif period == "2y": days = 730
        elif period == "max": days = 730
        
        series = td.get_time_series(self.symbol, days=days, interval="1day")
        if not series:
            return pd.DataFrame()
            
        df = pd.DataFrame(series)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)
        df.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        }, inplace=True)
        df = df.apply(pd.to_numeric, errors='coerce')
        return df
        
    def _fetch_financials(self):
        if self._financials is not None:
            return
            
        raw_inc = td.get_income_statement(self.symbol)
        raw_bs = td.get_balance_sheet(self.symbol)
        raw_cf = td.get_cash_flow(self.symbol)
        
        inc_list = raw_inc.get("income_statement", [])
        cf_list = raw_cf.get("cash_flow", [])
        
        bs_data = {}
        for row in raw_bs:
            date_str = row.get("fiscal_date")
            if not date_str:
                continue
            bs_data[date_str] = {
                "Total Assets": row.get("total_assets"),
                "Total Liabilities Net Minority Interest": row.get("total_liab"),
                "Total Liabilities": row.get("total_liab"),
                "Stockholders Equity": row.get("total_equity"),
                "Cash Cash Equivalents And Short Term Investments": row.get("cash"),
                "Cash And Cash Equivalents": row.get("cash"),
                "Long Term Debt": row.get("total_debt"),
                "Total Debt": row.get("total_debt"),
                "Retained Earnings": row.get("retained_earnings") or 0.0,
                "Working Capital": (row.get("total_assets") - row.get("total_liab")) if (row.get("total_assets") and row.get("total_liab")) else 0.0
            }
            
        inc_data = {}
        for row in inc_list:
            date_str = row.get("fiscal_date")
            if not date_str:
                continue
            inc_data[date_str] = {
                "Total Revenue": float(row.get("sales") or row.get("revenue") or 0.0),
                "Net Income": float(row.get("net_income") or 0.0),
                "EBITDA": float(row.get("ebitda") or 0.0),
                "Operating Income": float(row.get("operating_income") or 0.0),
                "Gross Profit": float(row.get("gross_profit") or 0.0),
            }
            
        cf_data = {}
        for row in cf_list:
            date_str = row.get("fiscal_date")
            if not date_str:
                continue
            cf_data[date_str] = {
                "Operating Cash Flow": float(row.get("operating_cash_flow") or row.get("cash_flow_from_operating_activities") or 0.0),
                "Free Cash Flow": float(row.get("free_cash_flow") or 0.0)
            }
            
        self._financials = pd.DataFrame(inc_data)
        self._balance_sheet = pd.DataFrame(bs_data)
        self._cashflow = pd.DataFrame(cf_data)
        
    @property
    def financials(self) -> pd.DataFrame:
        self._fetch_financials()
        return self._financials
        
    @property
    def balance_sheet(self) -> pd.DataFrame:
        self._fetch_financials()
        return self._balance_sheet
        
    @property
    def cashflow(self) -> pd.DataFrame:
        self._fetch_financials()
        return self._cashflow


def _ticker(symbol: str) -> TwelveDataTicker:
    return TwelveDataTicker(symbol)


def _safe_float(val) -> float | None:
    try:
        v = float(val)
        return None if (np.isnan(v) or np.isinf(v)) else v
    except Exception:
        return None


def _is_bist(symbol: str) -> bool:
    return symbol.upper().endswith(".IS")


def _fmt_large(val) -> str:
    if val is None:
        return "N/A"
    val = float(val)
    if abs(val) >= 1e12:
        return f"{val/1e12:.2f}T"
    if abs(val) >= 1e9:
        return f"{val/1e9:.2f}B"
    if abs(val) >= 1e6:
        return f"{val/1e6:.2f}M"
    return f"{val:.2f}"


# ── 1. get_stock_overview ──────────────────────────────────────────────────────
@mcp.tool()
def get_stock_overview(ticker: str) -> dict:
    """Şirket genel bilgisi: ad, sektör, piyasa değeri, fiyat, 52h aralığı."""
    key = f"overview_{ticker}"
    cached = _cached(key, _fc.TTL_PRICE)
    if cached:
        return cached

    t = _ticker(ticker)
    info = t.info

    result = {
        "ticker": ticker.upper(),
        "name": info.get("longName") or info.get("shortName", "N/A"),
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        "exchange": info.get("exchange", "N/A"),
        "currency": info.get("currency", "N/A"),
        "market_cap": _fmt_large(info.get("marketCap")),
        "market_cap_raw": _safe_float(info.get("marketCap")),
        "current_price": _safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
        "previous_close": _safe_float(info.get("previousClose")),
        "52w_high": _safe_float(info.get("fiftyTwoWeekHigh")),
        "52w_low": _safe_float(info.get("fiftyTwoWeekLow")),
        "avg_volume": _safe_float(info.get("averageVolume") or info.get("averageDailyVolume10Day")),
        "employees": info.get("fullTimeEmployees"),
        "description": (info.get("longBusinessSummary") or "")[:300],
    }
    # Likidite hesabı
    _av = result["avg_volume"]
    _pr = result["current_price"]
    _is_bist_ov = ticker.upper().endswith(".IS")
    _liq_thr = 5_000_000 if _is_bist_ov else 1_000_000
    _dvol = _av * _pr if (_av and _pr) else None
    result["daily_vol_raw"] = round(_dvol, 0) if _dvol else None
    result["is_illiquid"] = (_dvol < _liq_thr) if _dvol else None
    result["liq_cap_raw"] = round(_dvol * 0.01, 2) if _dvol else None
    _set_cache(key, result)
    return result


# ── 2. get_financials ──────────────────────────────────────────────────────────
@mcp.tool()
def get_financials(ticker: str) -> dict:
    """Gelir tablosu, bilanço ve nakit akış tablosu (son 2-4 yıl). Z/F-score için gerekli kalemler dahil."""
    key = f"financials_{ticker}"
    cached = _cached(key)
    if cached:
        return cached

    t = _ticker(ticker)

    def df_to_records(df: pd.DataFrame) -> list[dict]:
        if df is None or df.empty:
            return []
        df = df.fillna(0)
        records = []
        for col in df.columns:
            row: dict[str, Any] = {"period": str(col)[:10]}
            for idx in df.index:
                row[str(idx)] = _safe_float(df.loc[idx, col])
            records.append(row)
        return records

    income = df_to_records(t.financials)
    balance = df_to_records(t.balance_sheet)
    cashflow = df_to_records(t.cashflow)

    # özet kalemler (son dönem)
    summary: dict[str, Any] = {"ticker": ticker.upper(), "note": ""}

    def _latest(records: list[dict], *keys) -> float | None:
        if not records:
            return None
        row = records[0]
        for k in keys:
            for rk in row:
                if k.lower() in rk.lower():
                    v = row[rk]
                    if v is not None:
                        return v
        return None

    total_assets = _latest(balance, "Total Assets")
    total_liab = _latest(balance, "Total Liabilities")
    current_assets = _latest(balance, "Current Assets")
    current_liab = _latest(balance, "Current Liabilities")
    retained = _latest(balance, "Retained Earnings")
    total_revenue = _latest(income, "Total Revenue")
    net_income = _latest(income, "Net Income")
    ebitda = _latest(income, "EBITDA")
    op_cashflow = _latest(cashflow, "Operating Cash Flow")

    working_capital = (
        current_assets - current_liab
        if current_assets is not None and current_liab is not None
        else None
    )

    summary.update(
        {
            "total_assets": total_assets,
            "total_liabilities": total_liab,
            "total_liabilities_fmt": _fmt_large(total_liab),
            "working_capital": working_capital,
            "retained_earnings": retained,
            "total_revenue": total_revenue,
            "total_revenue_fmt": _fmt_large(total_revenue),
            "net_income": net_income,
            "net_income_fmt": _fmt_large(net_income),
            "ebitda": ebitda,
            "ebitda_fmt": _fmt_large(ebitda),
            "operating_cashflow": op_cashflow,
        }
    )

    # BIST için KAP'tan güncel veriyi özet'e ekle
    kap_data: dict | None = None
    if _is_bist(ticker):
        try:
            from kap_scraper import get_kap_financials
            kap_data = get_kap_financials(ticker)
        except Exception:
            kap_data = None

    if kap_data:
        # KAP birim çarpanı: Bin TL=1000, Milyon TL=1_000_000 → yfinance tam-TL ölçeğine çevir
        _kap_mult = kap_data.get("unit_multiplier", 1_000)

        # KAP'tan gelen kalemler yfinance'te None ise doldur; her zaman kap_* alanı olarak ekle (ölçekli)
        KAP_TO_SUMMARY = {
            "total_assets":        "total_assets",
            "total_liabilities":   "total_liabilities",
            "working_capital":     "working_capital",
            "retained_earnings":   "retained_earnings",
            "revenue":             "total_revenue",
            "net_income":          "net_income",
            "operating_cash_flow": "operating_cashflow",
        }
        for kap_key, sum_key in KAP_TO_SUMMARY.items():
            kv = kap_data.get(kap_key)
            if kv is not None:
                kv_scaled = kv * _kap_mult
                if summary.get(sum_key) is None:
                    summary[sum_key] = kv_scaled
                summary[f"kap_{kap_key}"] = kv_scaled

        summary["kap_meta"] = {
            "disclosure_index": kap_data.get("disclosure_index"),
            "period":           kap_data.get("period"),
            "year":             kap_data.get("year"),
            "publish_date":     kap_data.get("publish_date"),
        }
        summary["note"] = "BIST hissesi: özet kalemler KAP + yfinance birleşimi. kap_* alanları KAP'tan."
        summary["data_source"] = "KAP+yfinance"
    elif _is_bist(ticker):
        summary["note"] = "BIST hissesi: bazı kalemler eksik/gecikmeli olabilir."
        summary["data_source"] = "yfinance"

    result = {
        "summary": summary,
        "income_statement": income[:4],
        "balance_sheet": balance[:4],
        "cash_flow": cashflow[:4],
    }
    _set_cache(key, result)
    return result


# ── 2b. compare_kap_yfinance ──────────────────────────────────────────────────
@mcp.tool()
def compare_kap_yfinance(ticker: str) -> dict:
    """KAP ve yfinance finansal verilerini karşılaştır (yalnızca BIST hisseleri).

    Her iki kaynaktan aynı kalemleri çekip yan yana gösterir.
    %5'ten fazla farklılık olan kalemler 'flagged' listesine eklenir.
    """
    if not _is_bist(ticker):
        return {"error": f"{ticker} bir BIST hissesi değil. Bu araç yalnızca BIST için çalışır."}

    # ── KAP verisi ────────────────────────────────────────────────────────────
    try:
        from kap_scraper import get_kap_financials
        kap = get_kap_financials(ticker)
    except Exception as e:
        kap = None

    # ── yfinance verisi ───────────────────────────────────────────────────────
    yf_raw = get_financials(ticker)
    yf = yf_raw.get("summary", {})

    # Kalem eşleştirme: (standart_ad, kap_key, yfinance_key)
    KALEMLER = [
        ("total_assets",        "total_assets",        "total_assets"),
        ("total_liabilities",   "total_liabilities",   "total_liabilities"),
        ("current_assets",      "current_assets",      None),
        ("current_liabilities", "current_liabilities", None),
        ("working_capital",     "working_capital",     "working_capital"),
        ("equity",              "equity",              None),
        ("retained_earnings",   "retained_earnings",   "retained_earnings"),
        ("cash",                "cash",                None),
        ("revenue",             "revenue",             "total_revenue"),
        ("gross_profit",        "gross_profit",        None),
        ("operating_income",    "operating_income",    None),
        ("net_income",          "net_income",          "net_income"),
        ("operating_cash_flow", "operating_cash_flow", "operating_cashflow"),
    ]

    # KAP birim çarpanı: Bin TL=1000, Milyon TL=1_000_000 → yfinance tam TL ile aynı ölçeğe getir
    unit_multiplier = kap.get("unit_multiplier", 1_000) if kap else 1_000
    unit_label = kap.get("unit_label", "Bin TL") if kap else "Bin TL"

    rows = []
    flagged = []

    for std_name, kap_key, yf_key in KALEMLER:
        kap_raw = kap.get(kap_key) if kap else None
        yf_val  = yf.get(yf_key) if yf_key else None

        # KAP değerini yfinance tam-TL ölçeğine çevir
        kap_scaled = kap_raw * unit_multiplier if kap_raw is not None else None

        # Fark hesapla (yalnızca her iki kaynak mevcut olduğunda)
        pct_diff = None
        flag = False
        if kap_scaled is not None and yf_val is not None and yf_val != 0:
            pct_diff = round((kap_scaled - yf_val) / abs(yf_val) * 100, 1)
            flag = abs(pct_diff) > 5

        row = {
            "kalem":       std_name,
            "kap_raw":     round(kap_raw)    if kap_raw    is not None else None,
            "kap_scaled":  round(kap_scaled) if kap_scaled is not None else None,
            "yfinance":    round(yf_val)     if yf_val     is not None else None,
            "pct_diff":    pct_diff,
            "flag":        flag,
        }
        rows.append(row)
        if flag:
            flagged.append(std_name)

    result: dict = {
        "ticker": ticker.upper(),
        "unit_label": unit_label,
        "unit_multiplier": unit_multiplier,
        "note": f"kap_raw: KAP'tan ({unit_label}), kap_scaled: yfinance tam-TL ölçeğine çevrilmiş, yfinance: tam TL",
        "comparison": rows,
        "flagged_items": flagged,
        "summary": {
            "total_items":    len(rows),
            "kap_populated":  sum(1 for r in rows if r["kap_raw"]  is not None),
            "yf_populated":   sum(1 for r in rows if r["yfinance"] is not None),
            "flags":          len(flagged),
        },
    }

    if kap:
        result["kap_meta"] = {
            "disclosure_index": kap.get("disclosure_index"),
            "period":           kap.get("period"),
            "year":             kap.get("year"),
            "publish_date":     kap.get("publish_date"),
            "data_source":      kap.get("data_source"),
        }
    else:
        result["kap_error"] = "KAP verisi alınamadı."

    return result


# ── 3. get_price_history ───────────────────────────────────────────────────────
@mcp.tool()
def get_price_history(ticker: str, period: str = "1y") -> dict:
    """OHLCV verisi ve dönemsel % değişim (1A/3A/6A/12A)."""
    key = f"history_{ticker}_{period}"
    cached = _cached(key, _fc.TTL_PRICE)
    if cached:
        return cached

    t = _ticker(ticker)
    hist = t.history(period="2y")  # karşılaştırma için 2y çek

    if hist.empty:
        return {"ticker": ticker, "error": "Fiyat verisi bulunamadı."}

    def pct_change(days: int) -> float | None:
        close = hist["Close"].dropna()
        if len(close) < days:
            return None
        old = _safe_float(close.iloc[-days])
        new = _safe_float(close.iloc[-1])
        if old is None or new is None or old == 0:
            return None
        return round((new - old) / old * 100, 2)

    trading_days = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}

    recent = hist.tail(252 if period == "1y" else len(hist))
    records = [
        {
            "date": str(idx.date()),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]),
        }
        for idx, row in recent.iterrows()
    ]

    result = {
        "ticker": ticker.upper(),
        "period": period,
        "current_price": round(float(hist["Close"].iloc[-1]), 4),
        "changes": {
            "1m_pct": pct_change(trading_days["1m"]),
            "3m_pct": pct_change(trading_days["3m"]),
            "6m_pct": pct_change(trading_days["6m"]),
            "12m_pct": pct_change(trading_days["12m"]),
        },
        "data_points": len(records),
        "ohlcv": records[-60:],  # son 60 gün döndür (bant genişliği)
    }
    _set_cache(key, result)
    return result


# ── 4. get_sec_filings ────────────────────────────────────────────────────────
@mcp.tool()
def get_sec_filings(ticker: str) -> dict:
    """SEC EDGAR'dan son 10-K/10-Q dosyaları. Sadece ABD hisseleri için."""
    if _is_bist(ticker):
        return {
            "ticker": ticker,
            "available": False,
            "message": "SEC verisi yok — bu ABD hissesi değil (BIST/IS uzantılı hisse).",
        }

    key = f"sec_{ticker}"
    cached = _cached(key)
    if cached:
        return cached

    headers = {"User-Agent": "lucrum-finance-mcp ohhamamcioglu@gmail.com"}

    # EDGAR full-text search
    try:
        search_url = (
            f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22"
            f"&forms=10-K,10-Q&dateRange=custom&startdt=2022-01-01"
        )
        r = requests.get(search_url, headers=headers, timeout=10)
        data = r.json() if r.ok else {}
        hits = data.get("hits", {}).get("hits", [])
        filings = []
        for h in hits[:6]:
            src = h.get("_source", {})
            filings.append(
                {
                    "form": src.get("form_type"),
                    "filed": src.get("file_date"),
                    "description": src.get("entity_name"),
                    "url": f"https://www.sec.gov/Archives/edgar/data/{src.get('entity_id','')}/{src.get('file_num','')}/",
                }
            )
    except Exception:
        filings = []

    # Alternatif: submissions endpoint ile CIK bul
    try:
        t = _ticker(ticker)
        info = t.info
        cik_raw = None

        # yfinance bazen CIK vermez; EDGAR company search dene
        cik_search = requests.get(
            f"https://www.sec.gov/cgi-bin/browse-edgar?company={ticker}&CIK=&type=10-K"
            f"&dateb=&owner=include&count=5&search_text=&action=getcompany&output=atom",
            headers=headers,
            timeout=10,
        )
        # CIK'i XML'den parse etme (basit string arama)
        txt = cik_search.text
        cik_match = re.search(r"CIK=(\d+)", txt)
        if cik_match:
            cik_raw = cik_match.group(1).zfill(10)
            sub_url = f"https://data.sec.gov/submissions/CIK{cik_raw}.json"
            sub_r = requests.get(sub_url, headers=headers, timeout=10)
            if sub_r.ok:
                sub_data = sub_r.json()
                recent = sub_data.get("filings", {}).get("recent", {})
                forms = recent.get("form", [])
                dates = recent.get("filingDate", [])
                accessions = recent.get("accessionNumber", [])
                edgar_filings = []
                for i, f in enumerate(forms):
                    if f in ("10-K", "10-Q") and i < len(dates):
                        acc = accessions[i].replace("-", "")
                        edgar_filings.append(
                            {
                                "form": f,
                                "filed": dates[i],
                                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik_raw)}/{acc}/",
                                "viewer": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_raw}&type={f}&dateb=&owner=include&count=5",
                            }
                        )
                if edgar_filings:
                    filings = edgar_filings[:6]
    except Exception:
        pass

    result = {
        "ticker": ticker.upper(),
        "available": True,
        "filings": filings,
        "edgar_search": f"https://www.sec.gov/cgi-bin/browse-edgar?company={ticker}&action=getcompany",
    }
    _set_cache(key, result)
    return result


# ── 5. compare_peers ──────────────────────────────────────────────────────────
@mcp.tool()
def compare_peers(tickers: list[str]) -> dict:
    """Çoklu ticker için P/E, piyasa değeri, marj karşılaştırması."""

    def _fetch_peer(sym: str) -> dict:
        try:
            info = _ticker(sym).info
            return {
                "ticker": sym.upper(),
                "name": (info.get("longName") or info.get("shortName", "N/A"))[:30],
                "sector": info.get("sector", "N/A"),
                "market_cap": _fmt_large(info.get("marketCap")),
                "pe_ratio": _safe_float(info.get("trailingPE")),
                "forward_pe": _safe_float(info.get("forwardPE")),
                "pb_ratio": _safe_float(info.get("priceToBook")),
                "profit_margin": _safe_float(info.get("profitMargins")),
                "gross_margin": _safe_float(info.get("grossMargins")),
                "revenue_growth": _safe_float(info.get("revenueGrowth")),
                "earnings_growth": _safe_float(info.get("earningsGrowth")),
                "dividend_yield": _safe_float(info.get("dividendYield")),
                "beta": _safe_float(info.get("beta")),
            }
        except Exception as e:
            return {"ticker": sym.upper(), "error": str(e)}

    with ThreadPoolExecutor(max_workers=min(len(tickers), 6)) as pool:
        rows = list(pool.map(_fetch_peer, tickers))
    return {"comparison": rows}


# ── 6. get_altman_zscore ──────────────────────────────────────────────────────
@mcp.tool()
def get_altman_zscore(ticker: str) -> dict:
    """
    Altman Z-Score hesaplar.
    ABD/Gelişmiş: Z  = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5  — >2.99 Güvenli | 1.81-2.99 Gri | <1.81 Risk
    BIST/Gelişen: Z' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4 (X5 yok) — >2.6 Güvenli | 1.1-2.6 Gri | <1.1 Sıkıntı
    Eksik veri varsa hangi kalem eksik olduğunu açıklar.
    """
    key = f"zscore_{ticker}"
    cached = _cached(key)
    if cached:
        return cached

    t = _ticker(ticker)
    info = t.info

    # Finansal sektör kontrolü — Altman modeli bankalar/sigortalar için geçerli değil
    _FIN_SECTORS = {
        "Financial Services", "Finance", "Banks", "Insurance",
        "Capital Markets", "Mortgage Finance",
    }
    _fin_kw = {"bank", "financ", "sigorta", "insurance", "leasing", "kredi", "reit", "fon"}

    def _is_fin_str(s: str) -> bool:
        sl = s.lower()
        return any(kw in sl for kw in _fin_kw)

    _sector = (info.get("sector") or "").strip()
    _industry = (info.get("industry") or "").strip()

    if _sector in _FIN_SECTORS or _is_fin_str(_sector) or _is_fin_str(_industry):
        res = {
            "ticker": ticker.upper(),
            "z_score": None,
            "z_score_note": "Finansal sektör — Altman Z-Score uygulanamaz",
            "sector": _sector,
            "industry": _industry,
            "interpretation": "N/A",
        }
        _set_cache(key, res)
        return res

    bs = t.balance_sheet
    inc = t.financials
    cf = t.cashflow

    def get_val(df: pd.DataFrame, *keys) -> float | None:
        if df is None or df.empty:
            return None
        for k in keys:
            for idx in df.index:
                if k.lower() in str(idx).lower():
                    try:
                        col = df.columns[0]
                        v = _safe_float(df.loc[idx, col])
                        if v is not None:
                            return v
                    except Exception:
                        pass
        return None

    # KAP entegrasyonu — BIST hisselerinde en son YILLIK KAP verisi kullan
    # (Z-Score yıllık finansallar üzerine tasarlanmıştır; quarterly data bozar)
    _kap_z: dict | None = None
    _kap_z_mult = 1
    if _is_bist(ticker):
        try:
            from kap_scraper import get_kap_financials_annual_pair
            _kap_z, _ = get_kap_financials_annual_pair(ticker)
            if _kap_z:
                _kap_z_mult = _kap_z.get("unit_multiplier", 1_000)
        except Exception:
            _kap_z = None

    def _kap_val(key: str) -> float | None:
        if _kap_z is None:
            return None
        v = _kap_z.get(key)
        return v * _kap_z_mult if v is not None else None

    # Bilanço + gelir kalemleri: KAP öncelikli, yoksa yfinance
    total_assets   = _kap_val("total_assets")        or get_val(bs, "Total Assets")
    current_assets = _kap_val("current_assets")       or get_val(bs, "Current Assets")
    current_liab   = _kap_val("current_liabilities")  or get_val(bs, "Current Liabilities")
    retained       = _kap_val("retained_earnings")    or get_val(bs, "Retained Earnings")
    total_liab     = _kap_val("total_liabilities")    or get_val(bs, "Total Liabilities")
    revenue        = _kap_val("revenue")              or get_val(inc, "Total Revenue")
    # EBITDA: KAP'ta yok → yfinance EBITDA, yoksa operating_income proxy
    ebitda         = get_val(inc, "EBITDA") or _kap_val("operating_income")
    market_cap     = _safe_float(info.get("marketCap"))

    working_capital = _kap_val("working_capital")
    if working_capital is None:
        working_capital = (
            current_assets - current_liab
            if current_assets is not None and current_liab is not None
            else None
        )

    missing = []
    components: dict[str, Any] = {}

    def ratio(name: str, num, denom, label: str) -> float | None:
        if num is None:
            missing.append(f"{label} (pay)")
            return None
        if denom is None or denom == 0:
            missing.append(f"Total Assets (payda)")
            return None
        v = num / denom
        components[name] = round(v, 4)
        return v

    is_em = _is_bist(ticker)  # Gelişen piyasa modeli (Altman 2005) BIST için geçerli

    X1 = ratio("X1_working_capital/assets", working_capital, total_assets, "Working Capital")
    X2 = ratio("X2_retained/assets", retained, total_assets, "Retained Earnings")
    X3 = ratio("X3_ebitda/assets", ebitda, total_assets, "EBITDA")
    X4 = ratio("X4_mktcap/liab", market_cap, total_liab, "Market Cap / Total Liabilities")
    if not is_em:
        X5 = ratio("X5_revenue/assets", revenue, total_assets, "Revenue")
    else:
        X5 = None  # EM modeli X5 (Satış/Aktif) kullanmaz

    available = [x for x in ([X1, X2, X3, X4] if is_em else [X1, X2, X3, X4, X5]) if x is not None]

    if len(available) == 0:
        result = {
            "ticker": ticker.upper(),
            "z_score": None,
            "interpretation": "Hesaplanamadı",
            "missing_items": missing,
            "components": components,
        }
    else:
        if is_em:
            # Altman EM Modeli (2005): gelişen piyasalar / BIST için
            weights = [6.56, 3.26, 6.72, 1.05]
            vals = [X1, X2, X3, X4]
            formula_str = "6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4"
        else:
            # Altman Orijinal Modeli (1968): ABD halka açık şirketleri için
            weights = [1.2, 1.4, 3.3, 0.6, 1.0]
            vals = [X1, X2, X3, X4, X5]
            formula_str = "1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5"

        z = sum(w * v for w, v in zip(weights, vals) if v is not None)

        if len(missing) > 0:
            interp = f"Kısmi hesaplama ({len(missing)} kalem eksik)"
        elif is_em:
            if z > 2.6:
                interp = "Güvenli Bölge (Z' > 2.6) — Gelişen Piyasa Modeli"
            elif z >= 1.1:
                interp = "Gri Bölge (1.1 ≤ Z' ≤ 2.6) — Gelişen Piyasa Modeli"
            else:
                interp = "Sıkıntı Bölgesi (Z' < 1.1) — Gelişen Piyasa Modeli"
        else:
            if z > 2.99:
                interp = "Güvenli Bölge (Z > 2.99)"
            elif z >= 1.81:
                interp = "Gri Bölge (1.81 ≤ Z ≤ 2.99)"
            else:
                interp = "Risk Bölgesi (Z < 1.81)"

        result = {
            "ticker": ticker.upper(),
            "z_score": round(z, 3),
            "interpretation": interp,
            "missing_items": missing,
            "components": components,
            "formula": formula_str,
        }

    if _is_bist(ticker):
        if _kap_z:
            result["data_source"] = "KAP"
            result["kap_period"] = f"{_kap_z.get('year')} {_kap_z.get('period')}".strip()
            result["kap_note"] = "Yillik KAP verisinden hesaplandi; market_cap ve EBITDA yfinance'ten."
        else:
            result["data_source"] = "yfinance"
            result["bist_note"] = "KAP verisi alinamadi, yfinance kullanildi."

    _set_cache(key, result)
    return result


# ── 7. get_piotroski_fscore ────────────────────────────────────────────────────
@mcp.tool()
def get_piotroski_fscore(ticker: str) -> dict:
    """
    Piotroski F-Score (0-9).
    9 binary kriter: kârlılık (4) + kaldıraç/likidite (3) + verimlilik (2).
    Son 2 yıl finansalını karşılaştırır.
    """
    key = f"fscore_{ticker}"
    cached = _cached(key)
    if cached:
        return cached

    t = _ticker(ticker)
    bs = t.balance_sheet
    inc = t.financials
    cf = t.cashflow

    def col_val(df: pd.DataFrame, col_idx: int, *keys) -> float | None:
        if df is None or df.empty or col_idx >= len(df.columns):
            return None
        col = df.columns[col_idx]
        for k in keys:
            for idx in df.index:
                if k.lower() in str(idx).lower():
                    try:
                        return _safe_float(df.loc[idx, col])
                    except Exception:
                        pass
        return None

    # KAP entegrasyonu — BIST hisselerinde son iki yıllık bildirimi çek
    _kap_f_curr: dict | None = None
    _kap_f_prev: dict | None = None
    _kap_f_mult_c = 1
    _kap_f_mult_p = 1
    if _is_bist(ticker):
        try:
            from kap_scraper import get_kap_financials_annual_pair
            _kap_f_curr, _kap_f_prev = get_kap_financials_annual_pair(ticker)
            if _kap_f_curr:
                _kap_f_mult_c = _kap_f_curr.get("unit_multiplier", 1_000)
            if _kap_f_prev:
                _kap_f_mult_p = _kap_f_prev.get("unit_multiplier", 1_000)
        except Exception:
            _kap_f_curr = _kap_f_prev = None

    def _kv_c(key: str) -> float | None:
        if _kap_f_curr is None:
            return None
        v = _kap_f_curr.get(key)
        return v * _kap_f_mult_c if v is not None else None

    def _kv_p(key: str) -> float | None:
        if _kap_f_prev is None:
            return None
        v = _kap_f_prev.get(key)
        return v * _kap_f_mult_p if v is not None else None

    # Son yıl = index 0, Önceki yıl = index 1
    # Her kalem: KAP öncelikli, yoksa yfinance fallback
    net_income_curr = _kv_c("net_income") or col_val(inc, 0, "Net Income")
    net_income_prev = _kv_p("net_income") or col_val(inc, 1, "Net Income")
    op_cf_curr      = _kv_c("operating_cash_flow") or col_val(cf, 0, "Operating Cash Flow")

    total_assets_curr = _kv_c("total_assets") or col_val(bs, 0, "Total Assets")
    total_assets_prev = _kv_p("total_assets") or col_val(bs, 1, "Total Assets")

    roa_curr = (
        net_income_curr / total_assets_curr
        if net_income_curr is not None and total_assets_curr
        else None
    )
    roa_prev = (
        net_income_prev / total_assets_prev
        if net_income_prev is not None and total_assets_prev
        else None
    )

    # Uzun vadeli borç: KAP'ta direkt yok → toplam_yükümlülük - kısa_vadeli proxy
    def _kap_long_debt(kv_fn) -> float | None:
        tl = kv_fn("total_liabilities")
        cl = kv_fn("current_liabilities")
        return tl - cl if tl is not None and cl is not None else None

    long_debt_curr = _kap_long_debt(_kv_c) or col_val(bs, 0, "Long Term Debt", "Long-Term Debt")
    long_debt_prev = _kap_long_debt(_kv_p) or col_val(bs, 1, "Long Term Debt", "Long-Term Debt")

    lev_curr = (
        long_debt_curr / total_assets_curr
        if long_debt_curr is not None and total_assets_curr
        else None
    )
    lev_prev = (
        long_debt_prev / total_assets_prev
        if long_debt_prev is not None and total_assets_prev
        else None
    )

    curr_assets_curr = _kv_c("current_assets")  or col_val(bs, 0, "Current Assets")
    curr_liab_curr   = _kv_c("current_liabilities") or col_val(bs, 0, "Current Liabilities")
    curr_assets_prev = _kv_p("current_assets")  or col_val(bs, 1, "Current Assets")
    curr_liab_prev   = _kv_p("current_liabilities") or col_val(bs, 1, "Current Liabilities")

    curr_ratio_curr = (
        curr_assets_curr / curr_liab_curr
        if curr_assets_curr and curr_liab_curr
        else None
    )
    curr_ratio_prev = (
        curr_assets_prev / curr_liab_prev
        if curr_assets_prev and curr_liab_prev
        else None
    )

    # Hisse adedi: KAP'ta yok, yfinance'ten
    shares_curr = col_val(bs, 0, "Share Issued", "Common Stock", "Ordinary Shares")
    shares_prev = col_val(bs, 1, "Share Issued", "Common Stock", "Ordinary Shares")

    gross_curr = _kv_c("gross_profit") or col_val(inc, 0, "Gross Profit")
    gross_prev = _kv_p("gross_profit") or col_val(inc, 1, "Gross Profit")
    rev_curr   = _kv_c("revenue")      or col_val(inc, 0, "Total Revenue")
    rev_prev   = _kv_p("revenue")      or col_val(inc, 1, "Total Revenue")

    gm_curr = gross_curr / rev_curr if gross_curr and rev_curr else None
    gm_prev = gross_prev / rev_prev if gross_prev and rev_prev else None

    at_curr = rev_curr / total_assets_curr if rev_curr and total_assets_curr else None
    at_prev = rev_prev / total_assets_prev if rev_prev and total_assets_prev else None

    def score(condition) -> int | None:
        if condition is None:
            return None  # veri eksik — 0'dan ayırt edilmeli
        return 1 if condition else 0

    criteria = {
        "F1_positive_net_income": score(
            net_income_curr > 0 if net_income_curr is not None else None
        ),
        "F2_positive_op_cashflow": score(
            op_cf_curr > 0 if op_cf_curr is not None else None
        ),
        "F3_roa_improving": score(
            roa_curr > roa_prev if roa_curr is not None and roa_prev is not None else None
        ),
        "F4_cashflow_gt_net_income": score(
            op_cf_curr > net_income_curr
            if op_cf_curr is not None and net_income_curr is not None
            else None
        ),
        "F5_leverage_decreasing": score(
            lev_curr < lev_prev
            if lev_curr is not None and lev_prev is not None
            else None
        ),
        "F6_current_ratio_improving": score(
            curr_ratio_curr > curr_ratio_prev
            if curr_ratio_curr is not None and curr_ratio_prev is not None
            else None
        ),
        "F7_no_share_dilution": score(
            shares_curr <= shares_prev
            if shares_curr is not None and shares_prev is not None
            else None
        ),
        "F8_gross_margin_improving": score(
            gm_curr > gm_prev if gm_curr is not None and gm_prev is not None else None
        ),
        "F9_asset_turnover_improving": score(
            at_curr > at_prev if at_curr is not None and at_prev is not None else None
        ),
    }

    # Ham değerler — her kriterin neden 0/1 olduğunu gösterir
    criteria_detail = {
        "F1_pozitif_net_kar": {
            "net_income": _fmt_large(net_income_curr),
            "sonuc": criteria["F1_positive_net_income"],
        },
        "F2_pozitif_nakit_akisi": {
            "op_cashflow": _fmt_large(op_cf_curr),
            "sonuc": criteria["F2_positive_op_cashflow"],
        },
        "F3_roa_artisi": {
            "roa_curr": round(roa_curr, 4) if roa_curr is not None else None,
            "roa_prev": round(roa_prev, 4) if roa_prev is not None else None,
            "sonuc": criteria["F3_roa_improving"],
        },
        "F4_nakit_akisi_gt_net_kar": {
            "op_cashflow": _fmt_large(op_cf_curr),
            "net_income": _fmt_large(net_income_curr),
            "sonuc": criteria["F4_cashflow_gt_net_income"],
        },
        "F5_kaldirac_azalisi": {
            "uzun_vadeli_borc_curr": _fmt_large(long_debt_curr),
            "uzun_vadeli_borc_prev": _fmt_large(long_debt_prev),
            "kaldirac_curr": round(lev_curr, 4) if lev_curr is not None else None,
            "kaldirac_prev": round(lev_prev, 4) if lev_prev is not None else None,
            "sonuc": criteria["F5_leverage_decreasing"],
        },
        "F6_cari_oran_artisi": {
            "cari_oran_curr": round(curr_ratio_curr, 4) if curr_ratio_curr is not None else None,
            "cari_oran_prev": round(curr_ratio_prev, 4) if curr_ratio_prev is not None else None,
            "sonuc": criteria["F6_current_ratio_improving"],
        },
        "F7_hisse_seyrelmesi_yok": {
            "hisse_curr": shares_curr,
            "hisse_prev": shares_prev,
            "sonuc": criteria["F7_no_share_dilution"],
        },
        "F8_brut_marj_artisi": {
            "brut_marj_curr_pct": round(gm_curr * 100, 2) if gm_curr is not None else None,
            "brut_marj_prev_pct": round(gm_prev * 100, 2) if gm_prev is not None else None,
            "sonuc": criteria["F8_gross_margin_improving"],
        },
        "F9_varlik_devir_hizi_artisi": {
            "devir_hizi_curr": round(at_curr, 4) if at_curr is not None else None,
            "devir_hizi_prev": round(at_prev, 4) if at_prev is not None else None,
            "sonuc": criteria["F9_asset_turnover_improving"],
        },
    }

    total = sum(v for v in criteria.values() if v is not None)
    missing_count = sum(1 for v in criteria.values() if v is None)
    available_count = 9 - missing_count

    if total >= 7:
        quality = "Güçlü (7-9)"
    elif total >= 4:
        quality = "Orta (4-6)"
    else:
        quality = "Zayıf (0-3)"

    result = {
        "ticker": ticker.upper(),
        "f_score": total,
        "f_score_max": available_count,
        "quality": quality,
        "data_quality": f"{available_count}/9 kriterden veri mevcut",
        "missing_criteria_count": missing_count,
        "criteria": criteria,
        "criteria_detail": criteria_detail,
        "note": "1: kriter sağlandı | 0: kriter sağlanmadı | null: veri eksik",
    }

    if _is_bist(ticker):
        if _kap_f_curr:
            result["data_source"] = "KAP+yfinance"
            result["kap_curr_period"] = f"{_kap_f_curr.get('year')} {_kap_f_curr.get('period')}".strip()
            result["kap_prev_period"] = (
                f"{_kap_f_prev.get('year')} {_kap_f_prev.get('period')}".strip()
                if _kap_f_prev else "yfinance (KAP onceki yillik mevcut degil)"
            )
            result["kap_note"] = (
                "Mevcut yil: KAP yillik; onceki yil: KAP veya yfinance fallback; "
                "F7 (hisse seyrelmesi) her zaman yfinance'ten."
            )
        else:
            result["data_source"] = "yfinance"
            result["bist_note"] = "KAP yillik verisi alinamadi, yfinance kullanildi."

    _set_cache(key, result)
    return result


# ── 8. get_valuation ──────────────────────────────────────────────────────────
@mcp.tool()
def get_valuation(ticker: str) -> dict:
    """P/E, P/B, EV/EBITDA, PEG ve forward metrikler. P/E anormallik + PEG sebebi dahil."""
    key = f"valuation_{ticker}"
    cached = _cached(key, _fc.TTL_PRICE)
    if cached:
        return cached

    t = _ticker(ticker)
    info = t.info

    pe_raw = _safe_float(info.get("trailingPE"))
    trailing_eps = _safe_float(info.get("trailingEps"))
    current_price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
    net_income_raw = _safe_float(info.get("netIncomeToCommon"))
    earnings_growth = _safe_float(info.get("earningsGrowth"))
    peg_raw = _safe_float(info.get("pegRatio"))

    # P/E sanity check — çok düşük EPS'li anormal P/E değerlerini işaretle
    pe_note = None
    if pe_raw is not None:
        if (
            trailing_eps is not None
            and current_price is not None
            and current_price > 0
            and abs(trailing_eps) < 0.01 * current_price
        ):
            pe_note = (
                f"Anlamsız P/E: EPS={trailing_eps:.4f} fiyatın "
                f"({current_price:.2f}) %1'inden küçük — düşük geçici kâra bağlı"
            )
        elif pe_raw > 200 and pe_note is None:
            pe_note = (
                f"Yüksek P/E ({pe_raw:.1f}) — geçici düşük kâr veya bir kerelik kalem olabilir"
            )
    elif trailing_eps is not None and trailing_eps < 0:
        pe_note = f"Negatif EPS ({trailing_eps:.4f}) — P/E tanımsız"

    # PEG neden N/A açıklaması
    peg_note = None
    if peg_raw is None:
        if earnings_growth is None:
            peg_note = "Büyüme oranı verisi yok"
        elif earnings_growth <= 0:
            peg_note = (
                f"Negatif büyüme ({earnings_growth * 100:.1f}%) — PEG anlamsız"
            )
        else:
            peg_note = "PEG hesaplanamadı (EPS veya büyüme verisi eksik)"

    # Likidite — averageVolume × fiyat
    avg_volume = _safe_float(
        info.get("averageVolume") or info.get("averageDailyVolume10Day")
    )
    _is_bist_t = ticker.upper().endswith(".IS")
    _LIQ_THRESH = 5_000_000 if _is_bist_t else 1_000_000
    daily_vol_raw = avg_volume * (current_price or 0) if avg_volume is not None else None
    is_illiquid = (
        (daily_vol_raw < _LIQ_THRESH)
        if (daily_vol_raw is not None and daily_vol_raw > 0)
        else None
    )
    liq_cap_raw = round(daily_vol_raw * 0.01, 2) if daily_vol_raw else None

    result = {
        "ticker": ticker.upper(),
        "trailing_pe": pe_raw,
        "pe_note": pe_note,
        "trailing_eps": trailing_eps,
        "net_income_raw": net_income_raw,
        "net_income_fmt": _fmt_large(net_income_raw),
        "forward_pe": _safe_float(info.get("forwardPE")),
        "peg_ratio": peg_raw,
        "peg_note": peg_note,
        "earnings_growth_pct": (
            round(earnings_growth * 100, 2) if earnings_growth is not None else None
        ),
        "price_to_book": _safe_float(info.get("priceToBook")),
        "price_to_sales": _safe_float(info.get("priceToSalesTrailing12Months")),
        "ev_to_ebitda": _safe_float(info.get("enterpriseToEbitda")),
        "ev_to_revenue": _safe_float(info.get("enterpriseToRevenue")),
        "enterprise_value": _fmt_large(info.get("enterpriseValue")),
        "market_cap": _fmt_large(info.get("marketCap")),
        "dividend_yield_pct": (
            round(_safe_float(info.get("dividendYield")) * 100, 2)
            if info.get("dividendYield")
            else None
        ),
        "sector": info.get("sector", "N/A"),
        # Likidite alanları
        "avg_volume": avg_volume,
        "daily_vol_raw": daily_vol_raw,
        "is_illiquid": is_illiquid,
        "liq_cap_raw": liq_cap_raw,
        "liq_threshold": _LIQ_THRESH,
    }
    _set_cache(key, result)
    return result


# ── 9. get_momentum ───────────────────────────────────────────────────────────
@mcp.tool()
def get_momentum(ticker: str, benchmark: str = "SPY") -> dict:
    """Fiyat momentum ve benchmark'a (default: SPY) göre relative strength."""
    key = f"momentum_{ticker}_{benchmark}"
    cached = _cached(key, _fc.TTL_PRICE)
    if cached:
        return cached

    t = _ticker(ticker)
    hist = t.history(period="2y")

    if _is_bist(ticker):
        bench_sym = "XU100.IS"  # BIST için daha anlamlı benchmark
    else:
        bench_sym = benchmark

    try:
        b = _ticker(bench_sym)
        bench_hist = b.history(period="2y")
    except Exception:
        bench_hist = pd.DataFrame()

    def pct(h: pd.DataFrame, days: int) -> float | None:
        close = h["Close"].dropna()
        if len(close) < days:
            return None
        old = _safe_float(close.iloc[-days])
        new = _safe_float(close.iloc[-1])
        if old is None or new is None or old == 0:
            return None
        return round((new - old) / old * 100, 2)

    trading = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}

    stock_chg = {p: pct(hist, d) for p, d in trading.items()}
    bench_chg = {p: pct(bench_hist, d) for p, d in trading.items()}

    relative = {}
    for p in trading:
        s = stock_chg[p]
        b_val = bench_chg[p]
        if s is not None and b_val is not None:
            relative[f"rs_{p}"] = round(s - b_val, 2)
        else:
            relative[f"rs_{p}"] = None

    result = {
        "ticker": ticker.upper(),
        "benchmark": bench_sym,
        "stock_change": stock_chg,
        "benchmark_change": bench_chg,
        "relative_strength": relative,
    }
    _set_cache(key, result)
    return result


# ── 10. screen_watchlist ──────────────────────────────────────────────────────
@mcp.tool()
def screen_watchlist(tickers: list[str]) -> dict:
    """
    Tüm analiz araçlarını listedeki her ticker için çalıştırır.
    Tek tabloda birleştirir, Z>3 ve F≥7 olanları 'Kaliteli' işaretler.
    PEG'e göre artan sıralar.
    """
    errors: dict[str, list[str]] = {}

    def _scan_one(sym: str) -> dict:
        row: dict[str, Any] = {"ticker": sym.upper()}
        sym_errors: list[str] = []

        try:
            z_data = get_altman_zscore(sym)
            row["z_score"] = z_data.get("z_score")
            row["z_interpretation"] = z_data.get("interpretation", "")
            row["z_score_note"] = z_data.get("z_score_note", "")
        except Exception as e:
            row["z_score"] = None
            row["z_score_note"] = ""
            sym_errors.append(f"Z-Score: {e}")

        try:
            f_data = get_piotroski_fscore(sym)
            row["f_score"] = f_data.get("f_score")
        except Exception as e:
            row["f_score"] = None
            sym_errors.append(f"F-Score: {e}")

        try:
            val = get_valuation(sym)
            row["pe"] = val.get("trailing_pe")
            row["forward_pe"] = val.get("forward_pe")
            row["peg"] = val.get("peg_ratio")
            row["pb"] = val.get("price_to_book")
            row["ev_ebitda"] = val.get("ev_to_ebitda")
        except Exception as e:
            row["pe"] = row["forward_pe"] = row["peg"] = row["pb"] = row["ev_ebitda"] = None
            sym_errors.append(f"Valuation: {e}")

        try:
            mom = get_momentum(sym)
            row["momentum_6m"] = mom["stock_change"].get("6m")
            row["rs_6m"] = mom["relative_strength"].get("rs_6m")
        except Exception as e:
            row["momentum_6m"] = row["rs_6m"] = None
            sym_errors.append(f"Momentum: {e}")

        z = row.get("z_score")
        f = row.get("f_score")
        z_note = row.get("z_score_note", "") or ""
        is_fin = "finansal sektör" in z_note.lower()

        if is_fin and f is not None and f >= 7:
            tag = "⭐ Kaliteli (Fin.)"
        elif not is_fin and z is not None and f is not None and z > 3 and f >= 7:
            tag = "⭐ Kaliteli"
        elif not is_fin and z is not None and z < 1.81:
            tag = "⚠️ Risk"
        elif f is not None and f <= 3:
            tag = "🔴 Zayıf"
        else:
            tag = "➖ Nötr"

        row["tag"] = tag
        row["_errors"] = sym_errors
        return row

    with ThreadPoolExecutor(max_workers=min(len(tickers), 6)) as pool:
        rows = list(pool.map(_scan_one, tickers))

    for row in rows:
        sym_errors = row.pop("_errors", [])
        if sym_errors:
            errors[row["ticker"]] = sym_errors

    rows.sort(key=lambda r: (r.get("peg") is None, r.get("peg") or 9999))

    return {
        "watchlist": rows,
        "errors": errors,
        "summary": (
            f"{len(tickers)} hisse tarandı. "
            f"Kaliteli: {sum(1 for r in rows if '⭐' in r.get('tag',''))} | "
            f"Risk: {sum(1 for r in rows if '⚠️' in r.get('tag',''))}"
        ),
    }


# ── Yardımcılar (portfolio) ───────────────────────────────────────────────────

# Ak Yatırım / Akbank komisyon yapısı
BROKER_CONFIG = {
    "US_COMMISSION_STRUCTURE":  "tiered",
    "US_FLAT_COMMISSION_USD":   0.75,    # ≤ threshold için sabit komisyon
    "US_FLAT_THRESHOLD_USD":    375.0,   # bu tutarın altında sabit komisyon uygulanır
    "US_PROPORTIONAL_RATE":     0.002,   # %0.2 — threshold üzeri orantılı oran
    "US_BSMV_BUFFER":           0.001,   # %0.1 BSMV tamponu (netleşince güncellenecek)
    "MAX_COMMISSION_RATIO":     0.015,   # %1.5 — komisyon/işlem tutarı maksimum hedef
}

_MAX_WEIGHT = 0.10              # max %10 per position
_TARGET_SIZE = 22               # hedef portföy büyüklüğü


def get_usd_try_rate() -> float:
    """Twelve Data USD/TRY kuru çeker. Hata durumunda 35.0 döner."""
    try:
        price = td.get_price("USDTRY=X")
        if price and float(price) > 1:
            return round(float(price), 4)
    except Exception:
        pass
    return 35.0


def calculate_us_commission(trade_usd: float) -> float:
    """
    Ak Yatırım tiered komisyon hesapla (BSMV tamponu dahil).
    trade_usd ≤ 375: 0.75 * (1 + BSMV_BUFFER)
    trade_usd > 375: trade_usd * (0.002 + BSMV_BUFFER)
    """
    flat     = BROKER_CONFIG["US_FLAT_COMMISSION_USD"]
    thresh   = BROKER_CONFIG["US_FLAT_THRESHOLD_USD"]
    prop     = BROKER_CONFIG["US_PROPORTIONAL_RATE"]
    bsmv     = BROKER_CONFIG["US_BSMV_BUFFER"]
    if trade_usd <= thresh:
        return flat * (1 + bsmv)
    return trade_usd * (prop + bsmv)


def _us_min_trade_usd() -> float:
    """
    Flat komisyon bölgesinde MAX_COMMISSION_RATIO hedefini karşılayan minimum işlem tutarı.
    flat * (1 + bsmv) / max_ratio  →  0.75 * 1.001 / 0.015 ≈ 50.05 USD
    """
    flat   = BROKER_CONFIG["US_FLAT_COMMISSION_USD"]
    bsmv   = BROKER_CONFIG["US_BSMV_BUFFER"]
    max_r  = BROKER_CONFIG["MAX_COMMISSION_RATIO"]
    return (flat * (1 + bsmv)) / max_r

_REBALANCING_CONFIG = {
    "entry_rank_threshold": 25,
    "exit_rank_threshold": 40,
    "quality_gate_confirm_months": 2,
    "max_new_positions_per_month": 3,
    "target_portfolio_size": _TARGET_SIZE,
}


def _is_fin_row(row: dict) -> bool:
    """CSV satırının finansal sektöre ait olup olmadığını kontrol eder."""
    sec = (row.get("sector") or "").lower()
    note = (row.get("z_score_note") or "").lower()
    return (
        "financial" in sec or "bank" in sec
        or "sigorta" in sec or "insurance" in sec
        or "finansal sektör" in note or "uygulanamaz" in note
    )


def _passes_gate(row: dict) -> bool:
    """Kalite kapısı: finansal sektörde sadece F>=7, diğerinde Z>3 VE F>=7.
    api_error=True olan satırlar gate hesaplamasına GİRMEZ."""
    ae = row.get("api_error", "")
    if ae is True or str(ae).lower() in {"true", "1"}:
        return False
    try:
        f = float(row.get("f_score") or "")
    except Exception:
        return False
    if _is_fin_row(row):
        return f >= 7
    try:
        z = float(row.get("z_score") or "")
    except Exception:
        return False
    return z > 3 and f >= 7


def _minmax(values: list) -> list:
    """Min-max normalizasyon; None değerleri None olarak kalır."""
    vals = [v for v in values if v is not None]
    if not vals:
        return [None] * len(values)
    mn, mx = min(vals), max(vals)
    if mx == mn:
        return [0.5 if v is not None else None for v in values]
    return [(v - mn) / (mx - mn) if v is not None else None for v in values]


def _composite_scores(rows: list[dict]) -> list[float]:
    """
    Composite = 0.40*kalite_norm + 0.30*(1/PEG)_norm + 0.30*momentum_norm
    Eksik bileşen varsa ağırlıklar yeniden dağıtılır.
    Winsorize: PEG < 0.1 → 0.1 (1/PEG patlamasını önler); momentum winsorize [-50, +50].
    Not: Z-Score composite'te YOK — sadece gate filtresinde kullanılır (_passes_gate).
    """
    _PEG_MIN = 0.1   # 1/PEG maksimum = 10
    _MOM_CAP = 50.0  # 6 aylık getiri cap: uç momentum değerinin normalizasyonu domine etmesini önler

    def sf(v):
        try:
            f = float(v)
            return None if (np.isnan(f) or np.isinf(f)) else f
        except Exception:
            return None

    f_scores = [sf(r.get("f_score")) or 0 for r in rows]
    pegs_raw = [sf(r.get("peg")) for r in rows]
    momenta_raw = [sf(r.get("momentum_6m")) for r in rows]

    # Winsorize PEG: negatif/sıfır PEG geçersiz kalır (None), pozitif PEG en az 0.1
    pegs_safe = [max(_PEG_MIN, p) if (p is not None and p > 0) else p for p in pegs_raw]
    inv_pegs = [1.0 / p if (p is not None and p > 0) else None for p in pegs_safe]

    # Winsorize momentum: [-50, +50] aralığına kırp
    momenta = [
        max(-_MOM_CAP, min(_MOM_CAP, m)) if m is not None else None
        for m in momenta_raw
    ]

    kn_list = [f / 9 for f in f_scores]
    pn_list = _minmax(inv_pegs)
    mn_list = _minmax(momenta)

    scores = []
    for kn, pn, mn in zip(kn_list, pn_list, mn_list):
        if pn is None and mn is None:
            c = kn
        elif pn is None:
            c = (0.40 / 0.70) * kn + (0.30 / 0.70) * mn
        elif mn is None:
            c = (0.40 / 0.70) * kn + (0.30 / 0.70) * pn
        else:
            c = 0.40 * kn + 0.30 * pn + 0.30 * mn
        scores.append(round(c, 6))
    return scores


def _cap_weights(rows: list[dict], max_w: float = _MAX_WEIGHT) -> None:
    """Ağırlıkları max_w ile kırp; fazlayı diğerlerine orantılı dağıt. In-place."""
    for _ in range(30):
        over = [r for r in rows if r["_weight"] > max_w]
        if not over:
            break
        excess = sum(r["_weight"] - max_w for r in over)
        for r in over:
            r["_weight"] = max_w
        under = [r for r in rows if r["_weight"] < max_w]
        if not under:
            break
        s = sum(r["_weight"] for r in under)
        if s == 0:
            break
        for r in under:
            r["_weight"] += excess * (r["_weight"] / s)


def _assert_weight_cap(allocs: list[dict], total_amount: float, max_w: float) -> None:
    """Hard invariant: hiçbir pozisyon max_w'yi aşamaz. İhlal → ValueError."""
    max_tl = round(total_amount * max_w, 2)
    violations = [(e["ticker"], e["tl_amount"]) for e in allocs if e["tl_amount"] > max_tl + 0.02]
    if violations:
        raise ValueError(
            f"WEIGHT CAP İHLALİ ({max_w*100:.0f}% = {max_tl:.0f}₺): "
            + ", ".join(f"{t}={v:.0f}₺" for t, v in violations)
        )


def _save_pending_cash(pending_us_tl: float, pending_pool_tl: float = 0.0, _path: str | None = None) -> None:
    """Bekleyen US nakit ve havuz nakit birikimini pending_cash.json'a ekler."""
    import os, json as _j
    from datetime import datetime as _dt
    path = _path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "pending_cash.json")
    existing_us = 0.0
    existing_pool = 0.0
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                d = _j.load(fh)
                existing_us = float(d.get("pending_us_tl", 0))
                existing_pool = float(d.get("pending_pool_tl", 0))
        except Exception:
            pass
    with open(path, "w", encoding="utf-8") as fh:
        _j.dump(
            {
                "pending_us_tl": round(existing_us + pending_us_tl, 2),
                "pending_pool_tl": round(existing_pool + pending_pool_tl, 2),
                "last_updated": _dt.now().strftime("%Y-%m"),
            },
            fh, ensure_ascii=False, indent=2,
        )


def _load_pending_cash(_path: str | None = None) -> float:
    """pending_cash.json'daki toplam bekleyen nakit tutarını okur (us + pool)."""
    import os, json as _j
    path = _path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "pending_cash.json")
    if not os.path.exists(path):
        return 0.0
    try:
        with open(path, encoding="utf-8") as fh:
            d = _j.load(fh)
            return float(d.get("pending_us_tl", 0)) + float(d.get("pending_pool_tl", 0))
    except Exception:
        return 0.0


def _compute_aum(holdings: list[dict], amount: float, pending_cash_path: str | None = None) -> tuple[float, float]:
    """
    total_aum = holdings piyasa değeri + pending_cash + yeni katkı (amount)
    pending_execution: gerçek shares yok, entry_tl_amount kullanılır.
    confirmed: tl_value > shares × last_price > shares × entry_price önceliği.
    Döner: (total_aum, pending_cash_tl)
    """
    portfolio_val = 0.0
    for h in holdings:
        if h.get("status") == "pending_execution":
            portfolio_val += _safe_float(h.get("entry_tl_amount") or h.get("tl_amount")) or 0.0
        else:
            val = _safe_float(h.get("tl_value"))
            if val:
                portfolio_val += val
            else:
                shares = _safe_float(h.get("shares") or h.get("qty")) or 0.0
                price = _safe_float(h.get("last_price") or h.get("entry_price")) or 0.0
                portfolio_val += shares * price
    pending = _load_pending_cash(pending_cash_path)
    return round(portfolio_val + pending + amount, 2), round(pending, 2)


def _load_csv() -> list[dict]:
    import csv as _csv, os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return list(_csv.DictReader(fh))


# ── 11. get_cached_screen ────────────────────────────────────────────────────
@mcp.tool()
def get_cached_screen(
    min_zscore: float = 3.0,
    min_fscore: int = 7,
    max_peg: float = 0.0,
    sort_by: str = "peg",
) -> dict:
    """
    results.csv'den okur, filtreler, sıralar. Canlı API çağrısı yapmaz.
    max_peg=0 → PEG filtresi uygulanmaz.
    sort_by: 'peg' | 'z_score' | 'f_score' | 'momentum_6m'
    """
    import csv as _csv
    import os

    csv_path = os.path.join(os.path.dirname(__file__), "results.csv")
    if not os.path.exists(csv_path):
        return {
            "error": "results.csv bulunamadı. Önce 'python scanner.py' çalıştırın.",
            "hint": "Tarama çalıştırmak için refresh_scan() tool'unu kullanın.",
        }

    def _try_float(v) -> float | None:
        try:
            f = float(v)
            return None if (np.isnan(f) or np.isinf(f)) else f
        except Exception:
            return None

    rows = []
    with open(csv_path, encoding="utf-8") as fh:
        reader = _csv.DictReader(fh)
        for row in reader:
            z = _try_float(row.get("z_score"))
            f_val = _try_float(row.get("f_score"))
            peg = _try_float(row.get("peg"))

            z_ok = (z is not None and z >= min_zscore) if min_zscore > 0 else True
            f_ok = (f_val is not None and f_val >= min_fscore) if min_fscore > 0 else True
            peg_ok = (peg is not None and peg <= max_peg) if max_peg > 0 else True

            if z_ok and f_ok and peg_ok:
                rows.append(
                    {
                        "ticker": row.get("ticker"),
                        "z_score": z,
                        "f_score": int(f_val) if f_val is not None else None,
                        "pe": _try_float(row.get("pe")),
                        "peg": peg,
                        "pb": _try_float(row.get("pb")),
                        "ev_ebitda": _try_float(row.get("ev_ebitda")),
                        "momentum_6m": _try_float(row.get("momentum_6m")),
                        "rs_6m": _try_float(row.get("rs_6m")),
                        "sector": row.get("sector", ""),
                        "tag": row.get("tag", ""),
                        "timestamp": row.get("timestamp", ""),
                    }
                )

    # Sırala
    valid_sorts = {"peg", "z_score", "f_score", "momentum_6m"}
    if sort_by not in valid_sorts:
        sort_by = "peg"

    if sort_by in ("peg",):
        rows.sort(key=lambda r: (r.get(sort_by) is None, r.get(sort_by) or 9999))
    else:
        rows.sort(
            key=lambda r: (r.get(sort_by) is None, -(r.get(sort_by) or 0))
        )

    return {
        "filter": {"min_zscore": min_zscore, "min_fscore": min_fscore, "max_peg": max_peg},
        "sort_by": sort_by,
        "result_count": len(rows),
        "results": rows,
    }


# ── 13. allocate_monthly ─────────────────────────────────────────────────────
@mcp.tool()
def allocate_monthly(amount: float = 20000, usd_try_rate: float | None = None, dry_run: bool = True) -> dict:
    """
    Aylık tahsisat motoru (commission-aware + pool-ratio-aware + liquidity-capped).
    Gate: Z>3 VE F>=7 — finansal sektörde sadece F>=7.
    SORUN 2: Havuz < hedef büyüklüğünde orantılı nakit tut.
    SORUN 3: Likidite düşükse tahsisatı günlük hacmin %1'iyle sınırla.
    dry_run=True (varsayılan): State dosyalarına YAZMAZ — önizleme modu.
    dry_run=False: pending_cash.json'a gerçekten yazar.
    usd_try_rate=None: USDTRY=X'ten otomatik çeker.
    """
    if usd_try_rate is None:
        usd_try_rate = get_usd_try_rate()
    min_tl_us = _us_min_trade_usd() * usd_try_rate

    # AUM: holdings değeri + pending nakit + yeni katkı → cap basis
    import os as _os, json as _jj
    _h_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "holdings.json")
    _h_alloc: list[dict] = []
    if _os.path.exists(_h_path):
        try:
            with open(_h_path, encoding="utf-8") as _fh:
                _h_alloc = _jj.load(_fh)
        except Exception:
            pass
    total_aum, total_pending_cash = _compute_aum(_h_alloc, amount)

    rows = _load_csv()
    if not rows:
        return {"error": "results.csv bulunamadı veya boş. Önce refresh_scan() çalıştırın."}

    qualified = [r for r in rows if _passes_gate(r)]
    if not qualified:
        return {"error": "Gate geçen hisse bulunamadı. Tarama güncel değil olabilir."}

    # SORUN 2 — havuz küçükse orantılı dağıt
    pool_ratio = min(1.0, len(qualified) / _REBALANCING_CONFIG["target_portfolio_size"])
    effective_amount = round(amount * pool_ratio, 2)
    pending_pool_tl = round(amount - effective_amount, 2)

    scores = _composite_scores(qualified)
    for r, s in zip(qualified, scores):
        r["_composite"] = s

    qualified.sort(key=lambda r: r["_composite"], reverse=True)
    candidates = qualified[: _REBALANCING_CONFIG["target_portfolio_size"]]

    total_c = sum(r["_composite"] for r in candidates)
    for r in candidates:
        r["_weight"] = r["_composite"] / total_c
    _cap_weights(candidates)

    def _liq_cap_tl(r: dict, base_tl: float) -> tuple[float, bool]:
        """Likidite kapısını uygular; (nihai_tl, capped) döner."""
        liq_raw = _safe_float(r.get("liq_cap_raw"))
        if not liq_raw or liq_raw <= 0:
            return base_tl, False
        is_bist = r["ticker"].upper().endswith(".IS")
        max_tl = liq_raw if is_bist else liq_raw * usd_try_rate
        if base_tl > max_tl:
            return round(max_tl, 2), True
        return base_tl, False

    bist_allocs, us_allocs = [], []
    for r in candidates:
        tl = round(effective_amount * r["_weight"], 2)
        tl, liq_capped = _liq_cap_tl(r, tl)
        is_bist = r["ticker"].upper().endswith(".IS")

        entry: dict = {
            "ticker": r["ticker"].upper(),
            "composite_score": round(r["_composite"], 4),
            "weight_pct": round(r["_weight"] * 100, 2),
            "tl_amount": tl,
            "z_score": _safe_float(r.get("z_score")),
            "f_score": _safe_float(r.get("f_score")),
            "peg": _safe_float(r.get("peg")),
            "momentum_6m": _safe_float(r.get("momentum_6m")),
            "sector": r.get("sector", ""),
            "is_financial": _is_fin_row(r),
            "is_illiquid": r.get("is_illiquid") in (True, "True"),
        }
        if liq_capped:
            entry["liquidity_capped"] = True
        if is_bist:
            bist_allocs.append(entry)
        else:
            entry["usd_amount"] = round(tl / usd_try_rate, 2)
            us_allocs.append(entry)

    # Komisyon eşiği — top-down pooling: en iyi US adayları önce, BIST'e kesinlikle geçmez
    # max_pos_tl: toplam AUM'un %10'u (sabit monthly amount DEĞİL)
    us_allocs.sort(key=lambda e: e["composite_score"], reverse=True)
    max_tl_pos = round(total_aum * _MAX_WEIGHT, 2)
    total_us_pool = round(sum(e["tl_amount"] for e in us_allocs), 2)
    remaining_pool = total_us_pool
    confirmed_us: list[dict] = []
    pending_comm_tl = 0.0
    pending_us_tickers: list[str] = []

    for e in us_allocs:
        if remaining_pool <= 0:
            break
        alloc = round(min(remaining_pool, max_tl_pos), 2)
        remaining_pool = round(remaining_pool - alloc, 2)
        e["tl_amount"] = alloc
        if "usd_amount" in e:
            e["usd_amount"] = round(alloc / usd_try_rate, 2)
        if alloc >= min_tl_us:
            confirmed_us.append(e)
        else:
            pending_comm_tl = round(pending_comm_tl + alloc, 2)
            pending_us_tickers.append(e["ticker"])

    pending_comm_tl = round(pending_comm_tl + remaining_pool, 2)

    if not dry_run:
        if pending_comm_tl > 0 or pending_pool_tl > 0:
            _save_pending_cash(pending_comm_tl, pending_pool_tl)

    all_allocs = sorted(bist_allocs + confirmed_us, key=lambda x: x["composite_score"], reverse=True)

    # HARD INVARIANT — hiçbir pozisyon toplam AUM'un %10'unu aşamaz
    _assert_weight_cap(all_allocs, total_aum, _MAX_WEIGHT)

    return {
        "amount_tl": amount,
        "effective_amount_tl": effective_amount,
        "pending_pool_tl": pending_pool_tl,
        "pool_ratio_pct": round(pool_ratio * 100, 1),
        "pool_note": (
            f"Havuz {len(qualified)}/{_REBALANCING_CONFIG['target_portfolio_size']} dolu → "
            f"{pool_ratio*100:.1f}% dağıtıldı, {pending_pool_tl:.0f}₺ nakitte"
        ) if pool_ratio < 1.0 else f"Havuz tam ({len(qualified)} aday)",
        "usd_try_rate": usd_try_rate,
        "gate": "Z>3 AND F>=7 (finansal: F>=7)",
        "qualified_count": len(qualified),
        "selected_count": len(candidates),
        "allocations": all_allocs,
        "pending_us_tl": round(pending_comm_tl, 2),
        "pending_us_tickers": pending_us_tickers,
        "commission_info": (
            f"ABD eşiği: ${_us_min_trade_usd():.0f} (~{min_tl_us:.0f}₺) | "
            f"Flat<${BROKER_CONFIG['US_FLAT_THRESHOLD_USD']:.0f}: ${BROKER_CONFIG['US_FLAT_COMMISSION_USD']:.2f} | "
            f"Oran: %{BROKER_CONFIG['US_PROPORTIONAL_RATE']*100:.1f}+BSMV"
        ),
        "total_aum": total_aum,
        "max_position_tl": max_tl_pos,
        "total_pending_cash": total_pending_cash,
        "dry_run": dry_run,
    }


# ── 14. monthly_cycle ─────────────────────────────────────────────────────────
@mcp.tool()
def monthly_cycle(amount: float = 20000, usd_try_rate: float | None = None, dry_run: bool = True, state_path: str = "") -> dict:
    """
    Tam aylık döngü:
    1) Mevcut pozisyonları skorla ve çıkış sinyali üret
    2) Sağlıklı pozisyonları top-up et
    3) Yeni pozisyon aç (max_new_positions_per_month kadar)
    4) Komisyon eşiği kontrolü (US)
    5) Sonuçları monthly_cycle.json'a kaydet
    dry_run=True (varsayılan): State dosyalarına YAZMAZ — önizleme modu.
    dry_run=False: holdings.json, pending_cash.json, portfolio_state.json ve monthly_cycle.json'a yazar.
    state_path="": Gerçek dosyalar. state_path="test_": test_holdings.json vb. kullanır.
    usd_try_rate=None: USDTRY=X'ten otomatik çeker.
    """
    import os, json as _json
    from datetime import datetime

    if usd_try_rate is None:
        usd_try_rate = get_usd_try_rate()

    _HERE = os.path.dirname(os.path.abspath(__file__))
    HOLDINGS_FILE = os.path.join(_HERE, f"{state_path}holdings.json")
    STATE_FILE = os.path.join(_HERE, f"{state_path}portfolio_state.json")
    CYCLE_OUT = os.path.join(_HERE, f"{state_path}monthly_cycle.json")
    PENDING_CASH_FILE = os.path.join(_HERE, f"{state_path}pending_cash.json")

    CONF = _REBALANCING_CONFIG
    min_tl_us = _us_min_trade_usd() * usd_try_rate
    current_month = datetime.now().strftime("%Y-%m")

    # ── Makro rejim (GOZLEM MODU — karara girmiyor) ───────────────────────────
    # Aktif strateji: "Composite (makro YOK)" — multiplier her zaman 1.0
    # Savunmaci ve kontraryen filtreler deneysel/devre disi; sadece bilgi olarak gosteriliyor.
    market_regime: dict = {}
    _defensive_mult_obs      = 1.0  # savunmaci skor (gozlem)
    _bist_mult_obs           = 1.0  # BIST savunmaci skor (gozlem)
    _vix_val_obs             = None
    _fear_score_obs          = None
    _contrarian_mult_obs     = None
    _contrarian_signal_obs   = "N/A"
    try:
        from macro_regime import get_market_regime as _get_regime
        market_regime = _get_regime(use_cache=True)
        # Savunmaci filtre — gozlem degerleri
        _defensive_mult_obs = market_regime.get("deployment_multiplier", 1.0)
        _bist_mult_obs      = market_regime.get("bist_deployment_multiplier", _defensive_mult_obs)
        # Kontraryen filtre — VIX uzerinden hesaplanir, gozlem
        _vix_ind = (market_regime.get("indicators") or {}).get("vix", {})
        _vix_val_obs = _vix_ind.get("value") if isinstance(_vix_ind, dict) else None
        if _vix_val_obs is not None:
            _fear_score_obs = round(max(0.0, min(1.0, (_vix_val_obs - 15.0) / (30.0 - 15.0))), 3)
            _contrarian_mult_obs = round(max(0.80, min(1.20, 1.0 + (_fear_score_obs - 0.5) * 0.4)), 3)
            _contrarian_signal_obs = (
                "ASIRI KORKU" if _fear_score_obs >= 0.67 else
                "RAHATLAMA"   if _fear_score_obs <= 0.17 else
                "NORMAL"
            )
    except Exception as _re:
        market_regime = {"error": str(_re)}

    # AKTIF STRATEJI: deployment_multiplier sabit 1.0 — makro filtreler DEVRE DISI
    deployment_multiplier      = 1.0
    bist_deployment_multiplier = 1.0
    regime_adjusted_amount     = amount   # tam katki kullanilir
    regime_held_back_tl        = 0.0      # hicbir sey tutulmuyor

    # ── Veri yükleme ──────────────────────────────────────────────────────────
    rows = _load_csv()
    if not rows:
        return {"error": "results.csv bulunamadı. Önce refresh_scan() çalıştırın."}

    holdings: list[dict] = []
    if os.path.exists(HOLDINGS_FILE):
        with open(HOLDINGS_FILE, encoding="utf-8") as fh:
            try:
                holdings = _json.load(fh)
            except Exception:
                holdings = []
    held_tickers = {h["ticker"].upper() for h in holdings if h.get("ticker")}

    # AUM: holdings piyasa değeri + pending nakit + yeni katkı → cap basis
    total_aum, total_pending_cash = _compute_aum(holdings, amount, PENDING_CASH_FILE)

    state: dict = {"quality_gate_history": {}}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as fh:
            try:
                state = _json.load(fh)
            except Exception:
                pass
    qg_hist: dict = state.setdefault("quality_gate_history", {})

    # ── Tüm adayları skorla + sırala ─────────────────────────────────────────
    scores = _composite_scores(rows)
    for r, s in zip(rows, scores):
        r["_composite"] = s
    rows.sort(key=lambda r: r["_composite"], reverse=True)
    for i, r in enumerate(rows):
        r["_rank"] = i + 1
    by_ticker = {r["ticker"].upper(): r for r in rows}

    # ── Kalite kapısı geçmişi güncelle ────────────────────────────────────────
    for ticker, r in by_ticker.items():
        passed = _passes_gate(r)
        hist = qg_hist.setdefault(ticker, [])
        if hist and hist[-1]["month"] == current_month:
            hist[-1]["passed"] = passed
        else:
            hist.append({"month": current_month, "passed": passed})
        qg_hist[ticker] = hist[-3:]  # son 3 ay yeterli

    # ── Çıkış sinyalleri ──────────────────────────────────────────────────────
    sell_signals = []
    for h in holdings:
        if not h.get("ticker"):
            continue
        tk = h["ticker"].upper()
        r = by_ticker.get(tk)
        hist = qg_hist.get(tk, [])
        reasons = []

        recent = sorted(hist, key=lambda x: x["month"])[-CONF["quality_gate_confirm_months"]:]
        if (
            len(recent) >= CONF["quality_gate_confirm_months"]
            and all(not m["passed"] for m in recent)
        ):
            reasons.append(
                f"Kalite kapısı {CONF['quality_gate_confirm_months']} ay üst üste başarısız"
            )

        if r and r.get("_rank", 0) > CONF["exit_rank_threshold"]:
            reasons.append(
                f"Composite sıralama {r['_rank']} > eşik ({CONF['exit_rank_threshold']})"
            )

        if reasons:
            sell_signals.append({
                "ticker": tk,
                "reasons": reasons,
                "current_rank": r.get("_rank") if r else None,
                "f_score": _safe_float(r.get("f_score")) if r else None,
                "z_score": _safe_float(r.get("z_score")) if r else None,
            })

    sell_set = {s["ticker"] for s in sell_signals}
    healthy_held = [h for h in holdings if h.get("ticker", "").upper() not in sell_set]
    healthy_set = {h["ticker"].upper() for h in healthy_held}

    # ── Para dağıtımı ─────────────────────────────────────────────────────────
    qualified = [r for r in rows if _passes_gate(r)]
    q_tickers = {r["ticker"].upper() for r in qualified}

    held_q = [r for r in qualified if r["ticker"].upper() in healthy_set]
    new_cands = [
        r for r in qualified
        if r["ticker"].upper() not in healthy_set
    ][: CONF["max_new_positions_per_month"]]

    # İlk ay: holdings boşsa tüm bütçe new_buys'a gider (target_size kadar)
    if not holdings:
        alloc_pool = qualified[: CONF["target_portfolio_size"]]
        is_first_month = True
    else:
        alloc_pool = held_q + new_cands
        is_first_month = False

    if not alloc_pool:
        result = {
            "cycle_month": current_month,
            "sell_signals": sell_signals,
            "topup": [], "new_buys": [],
            "pending_us_tl": 0, "pending_us_tickers": [],
            "total_allocated_tl": 0,
            "summary": {"sat": len(sell_signals), "top_up": 0, "yeni_alim": 0, "beklemede_tl": 0},
            "note": "Kalite kapısı geçen uygun aday bulunamadı",
        }
        _write_cycle_json(CYCLE_OUT, result)
        return result

    # SORUN 2 — havuz < hedef büyüklüğünde orantılı dağıt + rejim çarpanı
    pool_ratio = min(1.0, len(qualified) / CONF["target_portfolio_size"])
    effective_amount = round(regime_adjusted_amount * pool_ratio, 2)
    pending_pool_tl = round(amount - effective_amount, 2)  # hem havuz hem rejim kısıtı buraya gider

    total_c = sum(r["_composite"] for r in alloc_pool)
    for r in alloc_pool:
        r["_weight"] = r["_composite"] / total_c
    _cap_weights(alloc_pool)

    topup_rows, new_buy_rows = [], []
    bist_entries: list[dict] = []
    us_entries: list[dict] = []
    max_tl_pos = round(total_aum * _MAX_WEIGHT, 2)  # AUM-tabanlı cap

    for r in alloc_pool:
        tl = round(effective_amount * r["_weight"], 2)
        tk = r["ticker"].upper()
        is_bist = tk.endswith(".IS")
        is_new = tk not in healthy_set or is_first_month

        # SORUN 3 — likidite kapısı
        liq_raw = _safe_float(r.get("liq_cap_raw"))
        liq_capped = False
        if liq_raw and liq_raw > 0:
            liq_max_tl = liq_raw if is_bist else liq_raw * usd_try_rate
            if tl > liq_max_tl:
                tl = round(liq_max_tl, 2)
                liq_capped = True

        entry: dict = {
            "ticker": tk,
            "tl_amount": tl,
            "composite_score": round(r["_composite"], 4),
            "rank": r["_rank"],
            "weight_pct": round(r["_weight"] * 100, 2),
            "f_score": _safe_float(r.get("f_score")),
            "z_score": _safe_float(r.get("z_score")),
            "peg": _safe_float(r.get("peg")),
            "momentum_6m": _safe_float(r.get("momentum_6m")),
            "sector": r.get("sector", ""),
            "is_illiquid": r.get("is_illiquid") in (True, "True"),
            "_is_new": is_new,
        }
        if liq_capped:
            entry["liquidity_capped"] = True
        if not is_bist:
            entry["usd_amount"] = round(tl / usd_try_rate, 2)
            if not is_new:
                entry["entry_price"] = next(
                    (h.get("entry_price") for h in holdings if h.get("ticker", "").upper() == tk), None
                )
            us_entries.append(entry)
        else:
            bist_entries.append(entry)

    # Komisyon — top-down pooling: en iyi US adayı önce, AUM cap, BIST'e kesinlikle geçmez
    us_entries.sort(key=lambda e: e["composite_score"], reverse=True)
    total_us_pool = round(sum(e["tl_amount"] for e in us_entries), 2)
    remaining_pool = total_us_pool
    confirmed_us: list[dict] = []
    pending_comm_tl = 0.0
    pending_us_tickers: list[str] = []

    for e in us_entries:
        if remaining_pool <= 0:
            break
        alloc = round(min(remaining_pool, max_tl_pos), 2)
        remaining_pool = round(remaining_pool - alloc, 2)
        e["tl_amount"] = alloc
        if "usd_amount" in e:
            e["usd_amount"] = round(alloc / usd_try_rate, 2)
        if alloc >= min_tl_us:
            confirmed_us.append(e)
        else:
            pending_comm_tl = round(pending_comm_tl + alloc, 2)
            pending_us_tickers.append(e["ticker"])

    pending_comm_tl = round(pending_comm_tl + remaining_pool, 2)

    if not dry_run:
        if pending_comm_tl > 0 or pending_pool_tl > 0:
            _save_pending_cash(pending_comm_tl, pending_pool_tl, PENDING_CASH_FILE)

    # Topup / new_buy ayrımı
    for e in bist_entries + confirmed_us:
        is_new = e.pop("_is_new", True)
        if is_new or is_first_month:
            new_buy_rows.append(e)
        else:
            topup_rows.append(e)

    topup_rows.sort(key=lambda x: x["composite_score"], reverse=True)
    new_buy_rows.sort(key=lambda x: x["composite_score"], reverse=True)
    total_tl = sum(e["tl_amount"] for e in topup_rows + new_buy_rows)

    # HARD INVARIANT — hiçbir pozisyon toplam AUM'un %10'unu aşamaz
    _assert_weight_cap(topup_rows + new_buy_rows, total_aum, _MAX_WEIGHT)

    # State kaydet — yalnızca dry_run=False ise
    if not dry_run:
        state["last_cycle"] = current_month
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            _json.dump(state, fh, ensure_ascii=False, indent=2)

        # Holdings güncelle: satılanları çıkar, yeni alımları/topup'ları ekle
        updated_holdings = [h for h in holdings if h.get("ticker", "").upper() not in sell_set]
        held_map = {h["ticker"].upper(): h for h in updated_holdings}
        for e in topup_rows + new_buy_rows:
            tk = e["ticker"]
            if tk in held_map:
                prev_tl = _safe_float(held_map[tk].get("entry_tl_amount") or held_map[tk].get("tl_amount")) or 0.0
                held_map[tk]["entry_tl_amount"] = round(prev_tl + e["tl_amount"], 2)
                if held_map[tk].get("status") == "confirmed":
                    held_map[tk]["status"] = "pending_execution"
            else:
                held_map[tk] = {
                    "ticker": tk,
                    "entry_tl_amount": e["tl_amount"],
                    "entry_date": current_month,
                    "sector": e.get("sector", ""),
                    "composite_score": e.get("composite_score"),
                    "shares": None,
                    "entry_price": None,
                    "status": "pending_execution",
                }
        with open(HOLDINGS_FILE, "w", encoding="utf-8") as fh:
            _json.dump(list(held_map.values()), fh, ensure_ascii=False, indent=2)

    result = {
        "cycle_month": current_month,
        "dry_run": dry_run,
        "amount_tl": amount,
        "effective_amount_tl": effective_amount,
        "pending_pool_tl": pending_pool_tl,
        "pool_ratio_pct": round(pool_ratio * 100, 1),
        "pool_note": (
            f"Havuz {len(qualified)}/{CONF['target_portfolio_size']} dolu → "
            f"{pool_ratio*100:.1f}% dağıtıldı, {pending_pool_tl:.0f}₺ nakitte"
        ) if pool_ratio < 1.0 else f"Havuz tam ({len(qualified)} aday)",
        "total_aum": total_aum,
        "max_position_tl": max_tl_pos,
        "total_pending_cash": total_pending_cash,
        "usd_try_rate": usd_try_rate,
        "is_first_month": is_first_month,
        "sell_signals": sell_signals,
        "topup": topup_rows,
        "new_buys": new_buy_rows,
        "pending_us_tl": round(pending_comm_tl, 2),
        "pending_us_tickers": pending_us_tickers,
        "total_allocated_tl": round(total_tl, 2),
        "commission_info": (
            f"ABD eşiği: ${_us_min_trade_usd():.0f} (~{min_tl_us:.0f}₺) | "
            f"Flat<${BROKER_CONFIG['US_FLAT_THRESHOLD_USD']:.0f}: ${BROKER_CONFIG['US_FLAT_COMMISSION_USD']:.2f} | "
            f"Oran: %{BROKER_CONFIG['US_PROPORTIONAL_RATE']*100:.1f}+BSMV"
        ),
        "summary": {
            "sat": len(sell_signals),
            "top_up": len(topup_rows),
            "yeni_alim": len(new_buy_rows),
            "beklemede_tl": round(pending_comm_tl, 2),
            "nakitte_tl": round(pending_pool_tl + pending_comm_tl, 2),
        },
        "market_regime": {
            # ── Aktif strateji bilgisi ────────────────────────────────────────
            "aktif_strateji":         "Composite (makro YOK) — tek aktif/canli strateji",
            "deployment_multiplier":  1.0,   # her zaman 1.0; filtreler karara girmiyor
            "regime_held_back_tl":    0.0,
            # ── Savunmaci filtre (DEVRE DISI — sadece gozlem) ────────────────
            "savunmaci_filtre": {
                "durum":                    "DEVRE DISI — deneysel, karara girmiyor",
                "risk_off_score":           market_regime.get("risk_off_score"),
                "deployment_multiplier_obs": _defensive_mult_obs,
                "regime":                   market_regime.get("regime", "bilinmiyor"),
                "bist_risk_off_score":      market_regime.get("bist_risk_off_score"),
                "bist_mult_obs":            _bist_mult_obs,
                "bist_regime":              market_regime.get("bist_regime", "bilinmiyor"),
            },
            # ── Kontraryen filtre (DEVRE DISI — sadece gozlem) ───────────────
            "kontraryen_filtre": {
                "durum":                   "DEVRE DISI — deneysel, karara girmiyor",
                "vix":                     _vix_val_obs,
                "fear_score":              _fear_score_obs,
                "contrarian_mult_obs":     _contrarian_mult_obs,
                "signal":                  _contrarian_signal_obs,
                "not": (
                    "VIX>30 (asiri korku) agresif alim mekanizmasi 2023-26 hic tetiklenmedi. "
                    "Karardan cikarildi; farkli/uzun bir donem test edilene kadar gozlemde."
                ),
            },
            # ── Ham gostergeler ───────────────────────────────────────────────
            "tcmb_status":        market_regime.get("tcmb_status"),
            "indicators": {
                k: {"score": v.get("score"), "note": v.get("note"), "ok": v.get("ok")}
                for k, v in (market_regime.get("indicators") or {}).items()
            },
            "skipped_sources":        market_regime.get("skipped_sources"),
            "economic_health_score":  market_regime.get("economic_health_score"),
        },
    }
    if not dry_run:
        _write_cycle_json(CYCLE_OUT, result)
    return result


def _write_cycle_json(path: str, data: dict) -> None:
    import json as _json
    with open(path, "w", encoding="utf-8") as fh:
        _json.dump(data, fh, ensure_ascii=False, indent=2, default=str)


# ── 15. confirm_purchase ──────────────────────────────────────────────────────
@mcp.tool()
def confirm_purchase(
    ticker: str,
    actual_shares: float,
    actual_price: float,
    actual_date: str | None = None,
    holdings_path: str | None = None,
) -> dict:
    """
    Broker'dan gelen kesin fiyat/adet bilgisini holdings.json'a yazar.
    ticker: ornek "MU" veya "THYAO.IS"
    actual_shares: Gercek adet (broker konfirmasyonundan)
    actual_price: Gercek islem fiyati (USD veya TL)
    actual_date: YYYY-MM-DD, None ise bugunun tarihi kullanilir
    """
    import os, json as _json
    from datetime import date as _date

    HERE = os.path.dirname(os.path.abspath(__file__))
    hpath = holdings_path or os.path.join(HERE, "holdings.json")

    if not os.path.exists(hpath):
        return {"error": f"holdings dosyasi bulunamadi: {hpath}"}

    with open(hpath, encoding="utf-8") as fh:
        holdings = _json.load(fh)

    tk = ticker.upper()
    match = next((h for h in holdings if h.get("ticker", "").upper() == tk), None)
    if match is None:
        return {"error": f"{tk} holdings'da bulunamadi."}
    if match.get("status") != "pending_execution":
        return {
            "error": f"{tk} zaten confirmed veya status tanimsiz: {match.get('status')}",
            "current": match,
        }

    conf_date = actual_date or _date.today().isoformat()
    match["shares"] = actual_shares
    match["entry_price"] = actual_price
    match["status"] = "confirmed"
    match["confirmed_date"] = conf_date

    with open(hpath, "w", encoding="utf-8") as fh:
        _json.dump(holdings, fh, ensure_ascii=False, indent=2)

    return {
        "status": "ok",
        "ticker": tk,
        "shares": actual_shares,
        "entry_price": actual_price,
        "confirmed_date": conf_date,
        "entry_tl_amount": match.get("entry_tl_amount"),
    }


# ── 16. list_pending_executions ───────────────────────────────────────────────
@mcp.tool()
def list_pending_executions(holdings_path: str | None = None) -> dict:
    """
    holdings.json'daki status='pending_execution' kayitlarini listeler.
    Kullanici gercek alimlari teker teker confirm_purchase ile onaylayabilir.
    """
    import os, json as _json

    HERE = os.path.dirname(os.path.abspath(__file__))
    hpath = holdings_path or os.path.join(HERE, "holdings.json")

    if not os.path.exists(hpath):
        return {"pending_count": 0, "confirmed_count": 0, "pending": [], "note": "holdings dosyasi bulunamadi."}

    with open(hpath, encoding="utf-8") as fh:
        holdings = _json.load(fh)

    pending = [h for h in holdings if h.get("status") == "pending_execution"]
    confirmed = [h for h in holdings if h.get("status") == "confirmed"]
    other = [h for h in holdings if h.get("status") not in ("pending_execution", "confirmed")]

    return {
        "pending_count": len(pending),
        "confirmed_count": len(confirmed),
        "other_count": len(other),
        "pending": pending,
    }


# ── 12. refresh_scan ─────────────────────────────────────────────────────────
@mcp.tool()
def refresh_scan(subset: str = "bist100") -> dict:
    """
    scanner.py'yi arka planda başlatır. Sonuçlar results.csv / results.json'a yazılır.
    subset: 'bist100' | 'sp500' | 'all'
    Not: Büyük taramalarda (all) 20-30 dakika sürebilir.
    """
    import subprocess
    import os

    valid = {"bist100", "sp500", "all"}
    if subset not in valid:
        return {"error": f"Geçersiz subset '{subset}'. Seçenekler: {valid}"}

    script = os.path.join(os.path.dirname(__file__), "scanner.py")
    if not os.path.exists(script):
        return {"error": "scanner.py bulunamadı."}

    proc = subprocess.Popen(
        ["python", "-X", "utf8", script, "--subset", subset],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=os.path.dirname(__file__),
    )

    return {
        "status": "started",
        "pid": proc.pid,
        "subset": subset,
        "message": (
            f"scanner.py başlatıldı (PID={proc.pid}, subset={subset}). "
            "Tamamlandığında sonuçlar results.csv ve results.json'a kaydedilecek. "
            "İlerlemeyi görmek için terminali açın."
        ),
        "output_files": ["results.csv", "results.json"],
    }


# ── TEFAS Fon Araçları ────────────────────────────────────────────────────────

@mcp.tool()
def track_my_funds(
    fund_weights: dict | None = None,
    dca_start: str = "2023-06-21",
    dca_monthly_tl: float = 20_000.0,
) -> dict:
    """
    TEFAS fon sepetini izle: güncel NAV, dönemsel getiriler, DCA geçmişi.

    Gerçek para-ağırlıklı getiriyi (XIRR) ve zaman-ağırlıklı getiriyi (TWR-CAGR)
    birlikte raporlar — ikisi farklı soruları yanıtlar (önceki analizde detaylandırıldı).
    Ayrıca korelasyon matrisi ve rebalans sapmasını gösterir.

    fund_weights: {'YAY': 0.45, 'GBG': 0.30, 'HBU': 0.25} gibi dict.
                 None ise varsayılan YAY/GBG/HBU 45/30/25 kullanılır.
    dca_start:   DCA başlangıç tarihi (YYYY-MM-DD).
    dca_monthly_tl: Aylık katkı (TL).
    """
    from tefas_tools import track_my_funds as _core
    return _core(
        fund_weights=fund_weights,
        dca_start=dca_start,
        dca_monthly_tl=dca_monthly_tl,
    )


@mcp.tool()
def suggest_next_contribution(
    monthly_amount: float = 20_000.0,
    fund_weights: dict | None = None,
    dca_start: str = "2023-06-21",
    correction_alpha: float = 1.0,
    min_floor_pct: float = 10.0,
    convergence_threshold_pp: float = 2.0,
) -> dict:
    """
    Satışsız (contribution-tilt) rebalans önerisi.

    Gelecek ayın katkısını hedefe en hızlı yaklaştıracak şekilde dağıtır.
    Hiçbir fon satılmaz; sadece yeni paranın dağılımı değiştirilir.
    Stopaj uyarısı ekler: satış yapılsaydı ne kadar vergi tetiklerdi.

    correction_alpha : 1.0 = tam drift düzeltmesi, 0.5 = daha yumuşak
    min_floor_pct    : Hiçbir fona bu %'nin altında para gitmesin (varsayılan 10)
    convergence_threshold_pp : Yakınsama eşiği pp cinsinden (varsayılan 2pp)
    """
    from tefas_tools import suggest_next_contribution as _core
    return _core(
        monthly_amount=monthly_amount,
        fund_weights=fund_weights,
        dca_start=dca_start,
        correction_alpha=correction_alpha,
        min_floor_pct=min_floor_pct,
        convergence_threshold_pp=convergence_threshold_pp,
    )


@mcp.tool()
def screen_tefas_funds(
    category: str | None = None,
    min_track_months: int = 24,
    top_n: int = 15,
    start_date: str = "2023-01-01",
    sort_by: str = "sharpe",
    require_split_consistent: bool = True,
) -> dict:
    """
    Tüm TEFAS fonlarını tara, performans ve risk metriklerine göre sırala.

    Verilen parametrelerle filtreler ve en iyi N fonu döner.
    Split validation uygular: her dönem yarısında da pozitif CAGR olan
    fonlar tutarlı performans göstermiş kabul edilir (tek dönemde parlayan
    fonları elee — backtest çalışmasında öğrenilen ders).

    category: None=tümü | "Yabancı Hisse Senedi" | "Hisse Senedi (TL)" |
              "Endeks (BIST)" | "Para Piyasası" | "Tahvil/Borçlanma" |
              "Altın/Kıymetli Maden" | "Fon Sepeti" | "Katılım" |
              "Karma/Değişken" | "Diğer/Serbest"
    min_track_months: en az kaç aylık geçmiş gerekli (varsayılan 24).
    top_n:   kaç fon listele (varsayılan 15).
    start_date: analiz başlangıcı (YYYY-MM-DD, maks 5 yıl gerisi).
    sort_by: "sharpe" | "cagr" | "max_dd" | "win_rate"
    require_split_consistent: True ise her yarı-dönemde CAGR>0 zorunlu.

    NOT: TER/yönetim ücreti pytefas API'sinde bulunmuyor — brüt getiriler.
    """
    from tefas_tools import screen_tefas_funds as _core
    return _core(
        category=category,
        min_track_months=min_track_months,
        top_n=top_n,
        start_date_str=start_date,
        sort_by=sort_by,
        require_split_consistent=require_split_consistent,
    )


@mcp.tool()
def screen_tax_exempt_funds(
    min_track_months: int = 24,
    top_n: int = 15,
    start_date: str = "2023-01-01",
    sort_by: str = "sharpe",
    require_split_consistent: bool = True,
    stock_pct_threshold: float = 80.0,
    foreign_pct_max: float = 20.0,
) -> dict:
    """
    Hisse senedi yoğun fon (%0 stopaj) evreni taraması.

    İsim/kategori etiketine bakmaksızın pytefas breakdown verisiyle tespit eder:
    stock_pct >= threshold VE foreign_stock_pct < foreign_max olan her fon
    GVK Geç.Md.67 kapsamında %0 stopajlı hisse senedi yoğun fondur.

    Parametreler:
    min_track_months    : En az kaç aylık geçmiş gerekli (varsayılan 24)
    top_n               : Kaç fon dönsün (varsayılan 15)
    start_date          : Analiz başlangıcı (YYYY-MM-DD, varsayılan 2023-01-01)
    sort_by             : sharpe | cagr | max_dd | win_rate
    require_split_consistent: Her iki yarı-dönemde de CAGR>0 zorunlu mu
    stock_pct_threshold : Minimum toplam hisse oranı (varsayılan 80.0)
    foreign_pct_max     : Maksimum yabancı hisse oranı (varsayılan 20.0)
    """
    from tefas_tools import screen_tax_exempt_funds as _core
    return _core(
        min_track_months=min_track_months,
        top_n=top_n,
        start_date_str=start_date,
        sort_by=sort_by,
        require_split_consistent=require_split_consistent,
        stock_pct_threshold=stock_pct_threshold,
        foreign_pct_max=foreign_pct_max,
    )


if __name__ == "__main__":
    mcp.run()
