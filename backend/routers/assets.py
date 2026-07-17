import time
import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from urllib.request import urlopen, Request
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
import requests

import twelve_data as td
import universe
from cache import finance_cache as _news_db
from crud import get_positions
from dependencies import get_current_user_id

router = APIRouter(prefix="/api", tags=["Assets"])

# Caches and TTLs
_NEWS_TTL = 1800  # 30 mins
_KAP_FUND_DISC_TTL = 3600 * 4  # 4 hours
_BREAKDOWN_TTL = 3600 * 6  # 6 hours
_TWELVE_DATA_NEWS_TTL = 1800  # 30 mins
OVERVIEW_CACHE_TTL = 43200  # 12 hours

_asset_overview_cache = {}
_tefas_name_cache: dict[str, str] = {}
_kap_fund_disc_cache: dict[str, tuple[float, dict]] = {}
_breakdown_cache: dict[str, tuple[float, dict]] = {}
_twelve_data_news_cache: dict = {}  # key → (timestamp, articles)
_fund_pys_cache: dict[str, str] = {}

# Constants
_TEFAS_TICKERS = {
    "JET","SAS","TI3","YAS","KZL","AFA","AFT","GO2","GO3","GO4",
    "YAY","AFV","BIH","HBU","AK1","MAC","TCD","GAF","YEF","GBG",
    "IPJ","ZZL","AKB","GAG","HEF","TI2","IYF","KBF","YKY","TYH",
}

_PYS_OID_MAP: dict[str, str] = {
    "AK":  "4028e4a240e8d16e0140e8f3623d0043",  # AK Portföy
    "AF":  "4028e4a240e8d16e0140e8f3623d0043",  # AK Portföy
    "YAY": "4028e4a140f2ed720141...",
    "JET": "4028e4a140e95bea0140e95c63f2000d",   # Ata Portföy
    "SAS": "4028e4a140e95bea0140e95c63f2000d",
    "TI":  "4028e4a140f2ed720141...",
    "HBU": "4028e4a140f2ed720141...",
    "BIH": "4028e4a140f2ed720141...",
    "GO":  "4028e4a1422d98690142...",
    "MAC": "4028e4a1422d98690142...",
}

POPULAR_ETFS = [
    {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "sector": "ETF"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "sector": "ETF"},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "sector": "ETF"},
    {"symbol": "IVV", "name": "iShares Core S&P 500 ETF", "sector": "ETF"},
    {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "sector": "ETF"},
    {"symbol": "VEA", "name": "Vanguard FTSE Developed Markets ETF", "sector": "ETF"},
    {"symbol": "VWO", "name": "Vanguard FTSE Emerging Markets ETF", "sector": "ETF"},
    {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "sector": "ETF"},
    {"symbol": "GLD", "name": "SPDR Gold Shares", "sector": "ETF"},
    {"symbol": "SLV", "name": "iShares Silver Trust", "sector": "ETF"},
    {"symbol": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "sector": "ETF"},
    {"symbol": "BND", "name": "Vanguard Total Bond Market ETF", "sector": "ETF"},
    {"symbol": "DIA", "name": "SPDR Dow Jones Industrial Average ETF Trust", "sector": "ETF"},
    {"symbol": "VT", "name": "Vanguard Total World Stock ETF", "sector": "ETF"},
    {"symbol": "IEFA", "name": "iShares Core MSCI EAFE ETF", "sector": "ETF"},
    {"symbol": "EFA", "name": "iShares MSCI EAFE ETF", "sector": "ETF"},
    {"symbol": "VUG", "name": "Vanguard Growth ETF", "sector": "ETF"},
    {"symbol": "VYM", "name": "Vanguard High Dividend Yield ETF", "sector": "ETF"},
    {"symbol": "XLK", "name": "Technology Select Sector SPDR Fund", "sector": "Technology ETF"},
    {"symbol": "XLF", "name": "Financial Select Sector SPDR Fund", "sector": "Financials ETF"},
    {"symbol": "XLV", "name": "Health Care Select Sector SPDR Fund", "sector": "Healthcare ETF"},
    {"symbol": "XLY", "name": "Consumer Discretionary Select Sector SPDR Fund", "sector": "Consumer ETF"},
    {"symbol": "XLP", "name": "Consumer Staples Select Sector SPDR Fund", "sector": "Consumer ETF"},
    {"symbol": "XLE", "name": "Energy Select Sector SPDR Fund", "sector": "Energy ETF"},
    {"symbol": "XLI", "name": "Industrial Select Sector SPDR Fund", "sector": "Industrials ETF"},
    {"symbol": "XLB", "name": "Materials Select Sector SPDR Fund", "sector": "Materials ETF"},
    {"symbol": "XLRE", "name": "Real Estate Select Sector SPDR Fund", "sector": "Real Estate ETF"},
    {"symbol": "XLU", "name": "Utilities Select Sector SPDR Fund", "sector": "Utilities ETF"},
]

_BREAKDOWN_LABEL_MAP = {
    "stock_pct": "Hisse Senedi",
    "government_bond_pct": "Devlet Tahvili",
    "treasury_bill_pct": "Hazine Bonosu",
    "private_sector_bond_pct": "Özel Sektör Tahvili",
    "eurobond_pct": "Eurobond",
    "repo_pct": "Repo",
    "term_deposit_pct": "Vadeli Mevduat",
    "deposit_tl_pct": "TL Mevduat",
    "deposit_fx_pct": "Döviz Mevduat",
    "deposit_gold_pct": "Altın Mevduat",
    "participation_account_tl_pct": "TL Katılım Hesabı",
    "participation_account_fx_pct": "Döviz Katılım",
    "participation_account_gold_pct": "Altın Katılım",
    "precious_metals_pct": "Kıymetli Maden",
    "precious_metals_etf_pct": "Kıymetli Maden ETF",
    "government_lease_certificate_tl_pct": "Kira Sertifikası (TL)",
    "government_lease_certificate_fx_pct": "Kira Sertifikası (Döviz)",
    "private_sector_lease_certificate_pct": "Özel Sektör Sukuk",
    "foreign_stock_pct": "Yabancı Hisse",
    "foreign_etf_pct": "Yabancı ETF",
    "foreign_government_debt_pct": "Yabancı Devlet Tahvili",
    "foreign_private_sector_debt_pct": "Yabancı Özel Sektör Tahvili",
    "investment_fund_pct": "Yatırım Fonu",
    "etf_pct": "ETF",
    "derivative_pct": "Türev",
    "futures_cash_collateral_pct": "Vadeli İşlem Teminatı",
    "other_pct": "Diğer",
}

# Helpers
def _get_tefas_fund_name(fund_code: str) -> str:
    """TEFAS fon adını pytefas üzerinden çeker, cache'ler."""
    code = fund_code.upper()
    if code in _tefas_name_cache:
        return _tefas_name_cache[code]
    try:
        from pytefas import Crawler
        c = Crawler()
        today = date.today()
        df = c.fetch(today.isoformat(), today.isoformat(), kind="YAT", columns="info", fund_code=code)
        if df.empty:
            df = c.fetch(today.isoformat(), today.isoformat(), kind="EMK", columns="info", fund_code=code)
        if not df.empty:
            row = df[df["fund_code"] == code]
            name = row.iloc[0]["fund_name"] if not row.empty else df.iloc[0]["fund_name"]
            _tefas_name_cache[code] = name
            return name
    except Exception:
        pass
    return code

def _get_pys_oid_for_fund(fund_code: str) -> Optional[str]:
    code = fund_code.upper()
    if code in _fund_pys_cache:
        return _fund_pys_cache[code]

    fund_name = _get_tefas_fund_name(code)
    if not fund_name or fund_name == code:
        return None

    upper_name = fund_name.upper()
    pys_oid_lookup = {
        "AK PORTF":  "4028e4a240e8d16e0140e8f3623d0043",
        "ATA PORTF": "4028e4a140e95bea0140e95c63f2000d",
        "YAPI KRED": "4028e4a1413b7ef4014174f37a5f5e28",
        "DENIZ PORTF": "4028e4a140f2ed720141...",
        "GARANTI PORTF": "4028e4a1416e696301416f37201c5f35",
        "IS PORTF":  "4028e4a1413b7ef40141b0c7b7c77b2f",
        "TEB PORTF": "4028e4a140f2ed720141...",
        "FIBA PORTF": "4028e4a2422d9a780142...",
        "AZIMUT PORTF": "4028e4a1422d98690142...",
        "AKTIF PORTF": "8acae2c45835eb6601594aab49376642",
    }

    for prefix, oid in pys_oid_lookup.items():
        if prefix in upper_name and '...' not in oid:
            _fund_pys_cache[code] = oid
            return oid
    return None

def _slug_for_fund(fund_code: str, fund_name: str) -> str:
    import re as _re
    code = fund_code.lower()
    name_part = fund_name.lower()
    name_part = _re.sub(r'[^a-z0-9\s-]', '', name_part
                        .replace('ş', 's').replace('ç', 'c').replace('ğ', 'g')
                        .replace('ü', 'u').replace('ö', 'o').replace('ı', 'i')
                        .replace('İ', 'i').replace('Ş', 's').replace('Ç', 'c')
                        .replace('Ğ', 'g').replace('Ü', 'u').replace('Ö', 'o'))
    name_part = _re.sub(r'\s+', '-', name_part.strip())
    name_part = _re.sub(r'-+', '-', name_part)
    return f"{code}-{name_part}"

def _is_tefas(ticker: str) -> bool:
    t = ticker.upper()
    if t in _TEFAS_TICKERS:
        return True
    if len(t) == 3 and t.isalpha():
        name = _tefas_name_cache.get(t, "")
        if "PORTFÖY" in name or "PORTF" in name or "FON" in name:
            return True
    return False

def _fetch_yahoo_rss(ticker: str) -> list[dict]:
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote_plus(ticker)}&region=US&lang=en-US"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=8) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        items = root.findall(".//item")
        result = []
        for item in items[:6]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if title and link:
                result.append({
                    "ticker": ticker,
                    "title": title,
                    "summary": desc[:200],
                    "url": link,
                    "source": "Yahoo Finance RSS",
                    "published_at": pub,
                })
        return result
    except Exception:
        return []

def _fetch_google_news_rss(ticker: str, company_name: str = "") -> list[dict]:
    try:
        query = company_name if company_name else ticker
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}+stock&hl=en-US&gl=US&ceid=US:en"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=8) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        items = root.findall(".//item")
        result = []
        for item in items[:6]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = source_el.text if source_el is not None else "Google News"
            if title and link:
                result.append({
                    "ticker": ticker,
                    "title": title,
                    "summary": "",
                    "url": link,
                    "source": source or "Google News",
                    "published_at": pub,
                })
        return result
    except Exception:
        return []

def _fetch_google_news_rss_tr(query: str, ticker_label: str) -> list[dict]:
    """Google News'i Türkçe (hl=tr&gl=TR) arar — İngilizce '+stock' aramasının Türk şirket
    isimleri/BIST kodları için hiç sonuç getirmediği durumlar için (bkz. _get_news_for_ticker)."""
    try:
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=tr&gl=TR&ceid=TR:tr"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=8) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        items = root.findall(".//item")
        result = []
        for item in items[:5]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = source_el.text if source_el is not None else "Google News"
            if title and link:
                result.append({
                    "ticker": ticker_label,
                    "title": title,
                    "summary": "",
                    "url": link,
                    "source": source or "Google News TR",
                    "published_at": pub,
                })
        return result
    except Exception:
        return []

def _fetch_tefas_news(fund_code: str) -> list[dict]:
    fund_name = _get_tefas_fund_name(fund_code)
    articles = _fetch_google_news_rss(fund_code, fund_name)
    try:
        query_tr = fund_name if fund_name != fund_code else f"{fund_code} fonu"
        articles.extend(_fetch_google_news_rss_tr(query_tr, fund_code))
    except Exception:
        pass
    return articles

def _fetch_kap_news(ticker: str) -> list[dict]:
    try:
        clean = ticker.upper().replace(".IS", "")
        url = "https://www.kap.org.tr/tr/api/memberDisclosureQuery"
        payload = {
            "isAudit": False,
            "orderBy": "DESC",
            "orderByColumn": "STARTDATE",
            "pageNumber": 0,
            "pageSize": 8,
            "term": clean,
            "disclosureTypes": [],
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://www.kap.org.tr",
            "Referer": "https://www.kap.org.tr/",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if not resp.ok:
            return []
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", [])
        result = []
        for item in items[:8]:
            title = item.get("title", "") or item.get("disclosureTitle", "") or item.get("basicSubjectDesc", "")
            disc_id = item.get("disclosureIndex", "") or item.get("id", "")
            link = f"https://www.kap.org.tr/tr/Bildirim/{disc_id}" if disc_id else "https://www.kap.org.tr"
            pub = item.get("startDate", "") or item.get("publishDate", "")
            if title:
                result.append({
                    "ticker": ticker,
                    "title": title,
                    "summary": item.get("basicSubjectDesc", "")[:200],
                    "url": link,
                    "source": "KAP",
                    "published_at": str(pub),
                })
        return result
    except Exception:
        return []

def _get_news_for_ticker(ticker: str, asset_class: str = "") -> list[dict]:
    cache_key = f"news_{ticker.upper()}"
    cached = _news_db.get(cache_key, ttl=_NEWS_TTL)
    if cached is not None:
        return cached

    t = ticker.upper()
    # asset_class (gerçek pozisyon verisi) önce kontrol edilir — sadece ticker suffix'ine
    # bakmak, ".IS" uzantısı olmadan kayıtlı gerçek BIST pozisyonlarını (GESAN, ASELS vb.)
    # hiç yakalamıyordu, KAP/Türkçe haberler asla tetiklenmiyordu.
    is_bist = asset_class == "BIST Hissesi" or (not asset_class and t.endswith(".IS"))
    is_tefas = not is_bist and (asset_class == "TEFAS Fonu" or (not asset_class and _is_tefas(t)))
    articles: list[dict] = []

    if is_tefas:
        articles += _fetch_tefas_news(t)
    elif is_bist:
        clean_ticker = t.replace(".IS", "")
        articles += _fetch_kap_news(ticker)
        # Türkçe arama — İngilizce "+stock" sorgusu Türk hisseleri/BIST kodları için
        # neredeyse hiç sonuç getirmiyordu.
        articles += _fetch_google_news_rss_tr(f"{clean_ticker} hisse", clean_ticker)
    else:
        articles += _fetch_yahoo_rss(ticker)
        if len(articles) < 5:
            articles += _fetch_google_news_rss(ticker)
        if len(articles) < 8:
            articles += _fetch_google_news_rss(ticker)

    seen_urls: set[str] = set()
    unique: list[dict] = []
    for a in articles:
        if a["url"] not in seen_urls:
            seen_urls.add(a["url"])
            unique.append(a)

    _news_db.set(cache_key, unique)
    return unique

def _fetch_twelve_data_news(us_tickers: list[str]) -> list[dict]:
    TWELVE_DATA_API_KEY = td.API_KEY
    if not TWELVE_DATA_API_KEY or not us_tickers:
        return []

    all_articles: list[dict] = []
    for i in range(0, len(us_tickers), 20):
        chunk = us_tickers[i:i + 20]
        cache_key = ",".join(sorted(chunk))
        cached = _twelve_data_news_cache.get(cache_key)
        if cached and time.time() - cached[0] < _TWELVE_DATA_NEWS_TTL:
            all_articles.extend(cached[1])
            continue

        try:
            resp = requests.get(
                "https://api.twelvedata.com/news",
                params={"symbol": ",".join(chunk), "apikey": TWELVE_DATA_API_KEY},
                timeout=10,
            )
            if not resp.ok:
                continue
            data = resp.json()
            if data.get("status") == "error":
                logging.warning("Twelve Data news error: %s", data.get("message", ""))
                continue

            raw = data.get("data", [])
            chunk_set = set(t.upper() for t in chunk)
            articles: list[dict] = []
            for art in raw:
                related = [t.upper() for t in (art.get("tickers") or [])]
                ticker = next((t for t in related if t in chunk_set), related[0] if related else chunk[0])
                pub = art.get("datetime", "")
                articles.append({
                    "ticker": ticker,
                    "title": art.get("title", ""),
                    "summary": (art.get("summary") or "")[:200],
                    "url": art.get("url", ""),
                    "source": (art.get("publisher") or {}).get("name", "Twelve Data"),
                    "published_at": pub,
                })
            _twelve_data_news_cache[cache_key] = (time.time(), articles)
            all_articles.extend(articles)
        except Exception as e:
            logging.warning("Twelve Data news fetch failed: %s", e)

    return all_articles


# Routes
@router.get("/assets/search")
def search_assets(query: str = Query(..., min_length=1)):
    """Arama sorgusuna uyan varliklari listele"""
    q = query.upper().strip()
    results = []
    
    # 1. BIST 100 search
    for ticker in universe.BIST_100:
        clean_ticker = ticker.replace(".IS", "")
        metadata = universe.BIST_100_METADATA.get(clean_ticker)
        name = metadata["name"] if metadata else f"{clean_ticker} BIST Hissesi"
        sector = metadata["sector"] if metadata else "BIST"
        
        if q in clean_ticker or q in name.upper():
            results.append({
                "symbol": clean_ticker,
                "name": name,
                "category": "Equity",
                "asset_class": "BIST Hissesi",
                "sector": sector,
                "riskScore": 5.5
            })
            
    # 2. S&P 500 search
    for ticker in universe.SP500:
        metadata = universe.SP500_METADATA.get(ticker)
        name = metadata["name"] if metadata else f"{ticker} S&P 500 Stock"
        sector = metadata["sector"] if metadata else "S&P 500"
        
        if q in ticker or q in name.upper():
            results.append({
                "symbol": ticker,
                "name": name,
                "category": "Equity",
                "asset_class": "ABD Hisse/ETF",
                "sector": sector,
                "riskScore": 5.5
            })
            
    # 3. Crypto search
    POPULAR_CRYPTOS = [
        {"symbol": "BTC", "name": "Bitcoin"},
        {"symbol": "ETH", "name": "Ethereum"},
        {"symbol": "SOL", "name": "Solana"},
        {"symbol": "XRP", "name": "Ripple"},
        {"symbol": "ADA", "name": "Cardano"},
        {"symbol": "DOGE", "name": "Dogecoin"},
        {"symbol": "DOT", "name": "Polkadot"},
        {"symbol": "LINK", "name": "Chainlink"},
        {"symbol": "AVAX", "name": "Avalanche"},
        {"symbol": "MATIC", "name": "Polygon"},
        {"symbol": "LTC", "name": "Litecoin"},
        {"symbol": "UNI", "name": "Uniswap"},
        {"symbol": "ATOM", "name": "Cosmos"},
        {"symbol": "TRX", "name": "TRON"}
    ]
    for crypto in POPULAR_CRYPTOS:
        if q in crypto["symbol"] or q in crypto["name"].upper():
            results.append({
                "symbol": crypto["symbol"],
                "name": crypto["name"],
                "category": "Crypto",
                "asset_class": "Kripto",
                "sector": "Cryptocurrency",
                "riskScore": 9.0
            })
            
    # 4. TEFAS search
    for ticker in _TEFAS_TICKERS:
        cached_name = _tefas_name_cache.get(ticker, "")
        name = cached_name if cached_name else f"{ticker} TEFAS Fonu"
        
        if q in ticker or q in name.upper():
            results.append({
                "symbol": ticker,
                "name": name,
                "category": "FixedIncome",
                "asset_class": "TEFAS Fonu",
                "sector": "TEFAS",
                "riskScore": 2.5
            })
            
    # 5. US ETF search
    for etf in POPULAR_ETFS:
        if q in etf["symbol"] or q in etf["name"].upper():
            results.append({
                "symbol": etf["symbol"],
                "name": etf["name"],
                "category": "Equity",
                "asset_class": "ABD Hisse/ETF",
                "sector": etf["sector"],
                "riskScore": 4.5
            })
            
    seen = set()
    unique_results = []
    for r in results:
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            unique_results.append(r)
            if len(unique_results) >= 15:
                break
    return unique_results

@router.get("/assets/{ticker}/overview")
def get_asset_overview(
    ticker: str,
    asset_class: str = Query(...),
):
    """Varlık için genel bilgi ve temel analiz verilerini al (Caching entegre edilmiştir)"""
    t_code = ticker.upper()
    cache_key = (t_code, asset_class)
    now = time.time()
    
    if cache_key in _asset_overview_cache:
        ts, cached_data = _asset_overview_cache[cache_key]
        if now - ts < OVERVIEW_CACHE_TTL:
            return cached_data
            
    try:
        # 1. TEFAS Fonu
        if asset_class == "TEFAS Fonu":
            try:
                breakdown = get_fund_breakdown(t_code)
                result = {
                    "type": "fund",
                    "name": breakdown.get("fund_name", t_code),
                    "price": breakdown.get("price"),
                    "portfolio_size": breakdown.get("portfolio_size"),
                    "investor_count": breakdown.get("investor_count"),
                    "allocation": breakdown.get("allocation", []),
                    "description": f"{t_code} kodlu TEFAS Yatırım Fonu."
                }
                _asset_overview_cache[cache_key] = (now, result)
                return result
            except Exception:
                result = {
                    "type": "fund",
                    "name": t_code,
                    "description": f"{t_code} kodlu TEFAS Yatırım Fonu."
                }
                _asset_overview_cache[cache_key] = (now, result)
                return result
                
        # 2. US, BIST, Kripto → Twelve Data
        is_bist = asset_class == "BIST Hissesi"
        is_crypto = asset_class == "Kripto"
        
        td_ticker = t_code
        if is_bist:
            td_ticker = f"{t_code}.IS"
        elif is_crypto:
            td_ticker = f"{t_code}-USD"
            
        with ThreadPoolExecutor(max_workers=3) as _ex:
            _fq = _ex.submit(td.batch_quotes, [td_ticker])
            _fp = _ex.submit(td.get_profile, td_ticker)
            _fs = _ex.submit(td.get_statistics, td_ticker)
            quotes  = _fq.result(timeout=15)
            profile = _fp.result(timeout=15)
            stats   = _fs.result(timeout=15)
            
        q = quotes.get(td_ticker.upper()) or {}
        s = stats or {}
        p = profile or {}
        
        if q.get("close"):
            if is_crypto:
                result = {
                    "type": "crypto",
                    "name": p.get("name") or q.get("name") or t_code,
                    "current_price": q.get("close"),
                    "market_cap": s.get("market_cap"),
                    "volume_24h": q.get("volume"),
                    "fifty_two_week_high": q.get("wk52_high"),
                    "fifty_two_week_low": q.get("wk52_low"),
                    "description": p.get("description") or f"{t_code} Kripto Para Birimi.",
                    "data_source": "Twelve Data"
                }
            else:
                metadata = None
                if is_bist:
                    metadata = universe.BIST_100_METADATA.get(t_code)
                else:
                    metadata = universe.SP500_METADATA.get(t_code) or next(
                        ({"name": e["name"], "sector": e["sector"]} for e in POPULAR_ETFS if e["symbol"] == t_code), None
                    )
                default_name = metadata["name"] if metadata else f"{t_code} Stock"
                default_sector = metadata["sector"] if metadata else "N/A"
                
                result = {
                    "type": "stock",
                    "name": p.get("name") or q.get("name") or default_name,
                    "sector": p.get("sector") or default_sector,
                    "industry": p.get("industry") or "N/A",
                    "current_price": q.get("close"),
                    "change_pct": q.get("change_pct"),
                    "market_cap": s.get("market_cap"),
                    "enterprise_value": s.get("enterprise_value"),
                    "pe_ratio": s.get("pe_trailing"),
                    "pe_forward": s.get("pe_forward"),
                    "pb_ratio": s.get("pb_ratio"),
                    "peg_ratio": s.get("peg_ratio"),
                    "ps_ratio": s.get("ps_ratio"),
                    "ev_ebitda": s.get("ev_ebitda"),
                    "dividend_yield": None,
                    "profit_margin": s.get("profit_margin"),
                    "operating_margin": s.get("operating_margin"),
                    "roe": s.get("roe"),
                    "eps_ttm": s.get("eps_ttm"),
                    "revenue_ttm": s.get("revenue_ttm"),
                    "beta": s.get("beta"),
                    "shares_out": s.get("shares_out"),
                    "fifty_two_week_high": q.get("wk52_high"),
                    "fifty_two_week_low": q.get("wk52_low"),
                    "volume_24h": q.get("volume"),
                    "avg_volume": q.get("avg_volume"),
                    "is_market_open": bool(q.get("is_market_open")),
                    "description": p.get("description") or f"{default_name} şirketi.",
                    "data_source": "Twelve Data",
                }
            _asset_overview_cache[cache_key] = (now, result)
            return result
        else:
            raise HTTPException(status_code=404, detail=f"Price data not found for symbol: {t_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/assets/{ticker}/fundamentals")
def get_asset_fundamentals(
    ticker: str,
    asset_class: str = Query(...),
):
    """US hisseleri için temel analiz: profil, istatistikler, temettüler, bölünmeler, hedefler, hissedarlar."""
    t_code = ticker.upper()
    if asset_class not in ("ABD Hisse/ETF", "BIST Hissesi"):
        raise HTTPException(status_code=400, detail="Fundamentals yalnızca ABD Hisse/ETF ve BIST Hisseleri için")

    # ÖNEMLİ: eskiden her alt-çağrının sonucu SIRAYLA .result(timeout=X) ile bekleniyordu —
    # bu, tüm timeout'ların TOPLAMI kadar (13 çağrı × 15-25sn ≈ birkaç dakika) beklenebileceği
    # anlamına geliyordu ve bir tek alt-çağrı (örn. rate-limit'e takılan Twelve Data isteği)
    # yavaşladığında "Temel Analiz" sekmesi kullanıcıya sonsuza dek yükleniyormuş gibi
    # görünüyordu. wait(..., timeout=20) TÜM çağrılar için TEK bir toplam üst sınır koyar;
    # süre dolduğunda henüz bitmeyenler için None döner (arka planda çalışmaya devam ederler,
    # sonuçları zaten kullanılmayacağı için beklenmez) — endpoint her zaman ~20sn içinde,
    # elindeki kısmi veriyle yanıt verir.
    with ThreadPoolExecutor(max_workers=13) as ex:
        futures = {
            "statistics": ex.submit(td.get_statistics, t_code),
            "earnings": ex.submit(td.get_earnings, t_code, 8),
            "balance_sheet": ex.submit(td.get_balance_sheet, t_code),
            "executives": ex.submit(td.get_executives, t_code),
            "profile": ex.submit(td.get_profile, t_code),
            "logo": ex.submit(td.get_logo, t_code),
            "dividends": ex.submit(td.get_dividends, t_code),
            "splits": ex.submit(td.get_splits, t_code),
            "price_target": ex.submit(td.get_price_target, t_code),
            "recommendations": ex.submit(td.get_recommendations, t_code),
            "insiders": ex.submit(td.get_insider_transactions, t_code),
            "institutional_holders": ex.submit(td.get_institutional_holders, t_code),
            "fund_holders": ex.submit(td.get_fund_holders, t_code),
        }
        done, _pending = wait(futures.values(), timeout=20)
        results = {}
        for key, fut in futures.items():
            if fut in done:
                try:
                    results[key] = fut.result()
                except Exception:
                    results[key] = None
            else:
                results[key] = None

    return {
        "symbol": t_code,
        **results,
    }

@router.get("/assets/{ticker}/indicators")
def get_asset_indicators(
    ticker: str,
    asset_class: str = Query(...),
    interval: str = Query("1day"),
    periods: int = Query(60, ge=10, le=200),
):
    """Teknik indikatörler: RSI(14), MACD, Bollinger Bands(20). (US Hisseleri, BIST ve Kripto destekler)"""
    t_code = ticker.upper()
    if asset_class not in ("ABD Hisse/ETF", "BIST Hissesi", "Kripto"):
        raise HTTPException(status_code=400, detail="Teknik indikatörler yalnızca Hisse, BIST ve Kripto için desteklenmektedir")

    # Aynı toplam-üst-sınır mantığı fundamentals uç noktasındaki gibi: sıralı .result(timeout=X)
    # yerine tek bir wait() ile en fazla 20sn'de yanıt veriyoruz.
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_rsi  = ex.submit(td.get_rsi,    t_code, 14, interval, periods)
        f_macd = ex.submit(td.get_macd,   t_code, interval, periods)
        f_bb   = ex.submit(td.get_bbands, t_code, 20, interval, periods)
        done, _pending = wait([f_rsi, f_macd, f_bb], timeout=20)

        def _safe(fut):
            if fut not in done:
                return []
            try:
                return fut.result()
            except Exception:
                return []

        rsi  = _safe(f_rsi)
        macd = _safe(f_macd)
        bb   = _safe(f_bb)

    return {
        "symbol": t_code,
        "interval": interval,
        "rsi": rsi,
        "macd": macd,
        "bbands": bb,
    }

@router.get("/assets/{ticker}/enrich")
def enrich_asset(
    ticker: str,
    asset_class: str = Query(...),
):
    """Sembolün tüm fundamental verilerini çeker ve DB cache'ini ısıtır."""
    t_code = ticker.upper()
    if asset_class not in ("ABD Hisse/ETF", "BIST Hissesi", "Kripto"):
        raise HTTPException(status_code=400, detail="Yalnızca Hisse, BIST ve Kripto için desteklenmektedir")
    summary = td.enrich_symbol(t_code)
    return {"symbol": t_code, "fetched": summary}

@router.get("/market/movers")
def get_market_movers_endpoint(
    market: str = Query("US"),
    direction: str = Query("gainers"),
):
    """Günün en çok kazandıran/kaybettirenlerini getirir. Twelve Data Grow planında kısıtlıdır."""
    movers = td.get_market_movers(market, direction)
    return {"market": market, "direction": direction, "movers": movers}

@router.get("/news")
def get_news(
    tickers: Optional[str] = Query(None, description="Comma-separated ticker list; omit for all portfolio tickers"),
    user_id: int = Depends(get_current_user_id),
):
    """Portföydeki varlıklar için haber toplar: US → Twelve Data (batch), BIST → KAP, TEFAS → KAP."""
    if tickers:
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        positions = get_positions(user_id)
        ticker_list = list({p["ticker"].upper() for p in positions})

    if not ticker_list:
        return {"generated_at": datetime.now().isoformat(), "tickers": [], "articles": []}

    positions = get_positions(user_id)
    asset_class_map = {p["ticker"].upper(): p.get("asset_class", "") for p in positions}

    # ÖNEMLİ: gerçek pozisyonlardaki BIST ticker'ları (GESAN, ASELS vb.) veritabanında ".IS"
    # uzantısı OLMADAN kayıtlı — sadece t.endswith(".IS") kontrolü bu yüzden hiçbir zaman
    # eşleşmiyor ve BIST haberleri KAP/Türkçe kaynak yerine yanlışlıkla ABD hissesi gibi
    # Twelve Data'dan aranıyordu (boş/alakasız sonuç). asset_class_map (gerçek pozisyon verisi)
    # önce kontrol edilir, ticker suffix'i sadece asset_class bilinmediğinde yedek olarak kullanılır.
    def _classify_ticker(t: str) -> str:
        ac = asset_class_map.get(t, "")
        if ac == "BIST Hissesi" or (not ac and t.endswith(".IS")):
            return "bist"
        if ac == "TEFAS Fonu" or (not ac and _is_tefas(t) and not t.endswith(".IS")):
            return "tefas"
        if ac in ("Nakit", "Cash"):
            return "cash"
        return "us"

    us_tickers = [t for t in ticker_list if _classify_ticker(t) == "us"]
    bist_tickers = [t for t in ticker_list if _classify_ticker(t) == "bist"]
    tefas_tickers_list = [t for t in ticker_list if _classify_ticker(t) == "tefas"]

    all_articles: list[dict] = []

    def fetch_ticker_news(t):
        try:
            return _get_news_for_ticker(t, asset_class_map.get(t, ""))
        except Exception:
            return []

    def _parallel_fetch(tickers, max_workers, timeout_sec):
        if not tickers:
            return []
        collected: list[dict] = []
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = {executor.submit(fetch_ticker_news, t): t for t in tickers}
            for future in as_completed(futures, timeout=timeout_sec):
                try:
                    collected.extend(future.result())
                except Exception:
                    pass
        except TimeoutError:
            pass
        except Exception:
            pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return collected

    td_articles = _fetch_twelve_data_news(us_tickers) if us_tickers else []
    if td_articles:
        all_articles.extend(td_articles)
    elif us_tickers:
        all_articles.extend(_parallel_fetch(us_tickers[:15], max_workers=10, timeout_sec=10.0))

    all_articles.extend(_parallel_fetch(bist_tickers + tefas_tickers_list, max_workers=8, timeout_sec=10.0))

    def _parse_pub(pub: str):
        if not pub:
            return datetime.min
        try:
            return datetime.fromisoformat(pub.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(pub).replace(tzinfo=None)
        except Exception:
            pass
        return datetime.min

    all_articles.sort(key=lambda a: _parse_pub(a.get("published_at", "")), reverse=True)

    return {
        "generated_at": datetime.now().isoformat(),
        "tickers": ticker_list,
        "articles": all_articles,
    }

@router.get("/funds/{fund_code}/disclosures")
def get_fund_disclosures(
    fund_code: str,
    days: int = Query(180, ge=30, le=730),
):
    """TEFAS fonu için KAP bildirimlerini döner (yönetim şirketi üzerinden)."""
    code = fund_code.upper()
    cache_key = f"{code}_{days}"
    now = time.time()
    if cache_key in _kap_fund_disc_cache:
        ts, cached = _kap_fund_disc_cache[cache_key]
        if now - ts < _KAP_FUND_DISC_TTL:
            return cached

    fund_name = _get_tefas_fund_name(code)
    pys_oid = _get_pys_oid_for_fund(code)
    kap_url = f"https://www.kap.org.tr/tr/fon-bildirimleri/{_slug_for_fund(code, fund_name)}"

    disclosures: list[dict] = []

    if pys_oid:
        from datetime import timedelta
        today = date.today()
        from_date = today - timedelta(days=days)

        session = requests.Session()
        session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
        )

        for dc in ("FR", "DG"):
            payload = {
                "fromDate": str(from_date),
                "toDate": str(today),
                "disclosureClass": dc,
                "subjectList": [],
                "mkkMemberOidList": [pys_oid],
                "inactiveMkkMemberOidList": [],
                "bdkMemberOidList": [],
                "fromSrc": False,
                "disclosureIndexList": [],
            }
            try:
                r = session.post(
                    "https://www.kap.org.tr/tr/api/disclosure/members/byCriteria",
                    json=payload, timeout=20
                )
                if not r.ok:
                    continue
                items = r.json()
                for item in items:
                    title = item.get("summary") or item.get("subject") or ""
                    if code in title.upper() or (fund_name and any(
                        w in title.upper() for w in fund_name.upper().split()[:3] if len(w) > 3
                    )):
                        disclosures.append({
                            "index": item.get("disclosureIndex"),
                            "title": title,
                            "subject": item.get("subject"),
                            "publish_date": item.get("publishDate"),
                            "year": item.get("year"),
                            "url": f"https://www.kap.org.tr/tr/Bildirim/{item.get('disclosureIndex')}",
                        })
            except Exception:
                pass

    result = {
        "fund_code": code,
        "fund_name": fund_name,
        "kap_page": kap_url,
        "pys_oid_found": bool(pys_oid),
        "disclosures": disclosures,
        "note": "Fon bildirimleri için KAP sayfasını ziyaret edin" if not disclosures else "",
    }
    _kap_fund_disc_cache[cache_key] = (now, result)
    return result

@router.get("/funds/{fund_code}/breakdown")
def get_fund_breakdown(fund_code: str):
    """TEFAS fonu için portföy dağılımını (breakdown) döner."""
    code = fund_code.upper()
    now = time.time()
    if code in _breakdown_cache:
        ts, cached = _breakdown_cache[code]
        if now - ts < _BREAKDOWN_TTL:
            return cached

    try:
        from pytefas import Crawler
        c = Crawler()
        today = date.today()
        for kind in ("YAT", "EMK", "BYF"):
            df = c.fetch(today.isoformat(), today.isoformat(), kind=kind, columns="breakdown", fund_code=code)
            if not df.empty:
                sub = df[df["fund_code"] == code]
                if sub.empty:
                    sub = df
                row = sub.sort_values("date").iloc[-1].to_dict()

                info_df = c.fetch(today.isoformat(), today.isoformat(), kind=kind, columns="info", fund_code=code)
                info_row: dict = {}
                if not info_df.empty:
                    info_sub = info_df[info_df["fund_code"] == code]
                    info_row = (info_sub if not info_sub.empty else info_df).sort_values("date").iloc[-1].to_dict()

                allocation = []
                for col, label in _BREAKDOWN_LABEL_MAP.items():
                    val = float(row.get(col, 0) or 0)
                    if val > 0:
                        allocation.append({"label": label, "pct": round(val, 2)})
                allocation.sort(key=lambda x: x["pct"], reverse=True)

                result = {
                    "fund_code": code,
                    "fund_name": row.get("fund_name", code),
                    "date": str(row.get("date", today)),
                    "price": info_row.get("price"),
                    "portfolio_size": info_row.get("portfolio_size"),
                    "investor_count": info_row.get("investor_count"),
                    "allocation": allocation,
                }
                _breakdown_cache[code] = (now, result)
                return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TEFAS veri çekme hatası: {e}")

    raise HTTPException(status_code=404, detail=f"Fon bulunamadı: {fund_code}")
