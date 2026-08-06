"""
Twelve Data - Merkezi Veri Katmanı
====================================
• Rate limit : 55 istek/dakika
• Yerel DB   : twelve_data.db (SQLite)
• Strateji   : DB önce, API gerekirse

Kapsam:
  quote, time_series, exchange_rate
  statistics, earnings, balance_sheet
  rsi, macd, bbands, ema, beta
  key_executives, profile
  stocks (enstrüman listesi)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import socket
# Dış servislerin (TEFAS vb.) yavaş yanıt vermesi durumunda uygulamanın kilitlenmesini önlemek için global zaman aşımı
socket.setdefaulttimeout(8.0)

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Optional

import requests as _req
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

from cache import finance_cache as _fc

# ── Konfigürasyon ─────────────────────────────────────────────────────────────
API_KEY  = os.getenv("TWELVE_DATA_API_KEY", "")
BASE_URL = "https://api.twelvedata.com"
DB_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "twelve_data.db")

# TEFAS fon verisi için birincil kaynak. pytefas (unofficial scraping) eşzamanlı
# istek altında TEFAS sunucusunda ciddi yavaşlıyor (gözlemlenen: 8 fon paralel
# çekildiğinde 33-95sn/fon, 6sn timeout'u fazlasıyla aşıyor). Fonoloji resmi bir
# API sunuyor, fon verisi (BIST canlı fiyat verisinin aksine) yeniden-dağıtım
# kısıtına tabi değil, ve karşılaştırmalı testte pytefas ile birebir aynı fiyatı
# döndürdü. Anahtar yoksa (local dev / henüz ayarlanmamışsa) sessizce pytefas'a
# düşülür — bkz. get_tefas_current_price / get_tefas_nav.
FONOLOJI_API_KEY  = os.getenv("FONOLOJI_API_KEY", "")
FONOLOJI_BASE_URL = "https://fonoloji.com/v1"

# Cache TTL'ler (saniye)
TTL_QUOTE        =  5 * 60       # 5 dk  — anlık fiyat
TTL_RATE         =  1 * 3600     # 1 sa  — döviz kuru
TTL_TIME_SERIES  = 30 * 60       # 30 dk — OHLCV
TTL_STATISTICS   =  7 * 86400    # 7 gün — P/E, market cap
TTL_EARNINGS     = 30 * 86400    # 30 gün — EPS
TTL_BALANCE      = 30 * 86400    # 30 gün — bilanço
TTL_INDICATOR    = 24 * 3600     # 1 gün  — RSI, MACD vb.
TTL_PROFILE      = 30 * 86400    # 30 gün — şirket profili
TTL_EXECUTIVES   = 30 * 86400    # 30 gün — yöneticiler
TTL_INSTRUMENTS  = 14 * 86400    # 14 gün — enstrüman listesi
TTL_LOGO         = 30 * 86400    # 30 gün — şirket logosu
TTL_DIVIDENDS    =  7 * 86400    # 7 gün — temettüler
TTL_SPLITS       = 30 * 86400    # 30 gün — hisse bölünmeleri
TTL_TARGET       =  7 * 86400    # 7 gün — fiyat hedefleri
TTL_RECOMMENDATION = 3 * 86400   # 3 gün — analist tavsiyeleri
TTL_INSIDERS     =  7 * 86400    # 7 gün — içeriden alım/satımlar
TTL_HOLDERS      = 15 * 86400    # 15 gün — hissedarlar
TTL_MOVERS       =  4 * 3600     # 4 saat — günün hareketlileri
TTL_TEFAS_NAV    = 24 * 3600     # 1 gün — TEFAS fon fiyatı (NAV)

# ── Rate Limiter (55 istek/dakika) ───────────────────────────────────────────
_rate_lock  = threading.Lock()
_call_times: deque = deque()
RATE_LIMIT  = 55
RATE_WINDOW = 60.0

# Twelve Data'nın "speed limit"/429 döndüğü son an — /api/prices/{ticker} gibi
# rotaların, gerçekten var olmayan bir ticker (404) ile şu an rate-limit
# yüzünden geçici olarak veri alınamayan bir ticker'ı (429) ayırt edebilmesi için.
_last_rate_limit_ts = 0.0


def is_rate_limited() -> bool:
    """Son RATE_WINDOW saniye içinde Twelve Data'dan rate-limit hatası alındıysa True."""
    return (time.monotonic() - _last_rate_limit_ts) < RATE_WINDOW


def _clean_symbol(symbol: str) -> str:
    if not symbol:
        return ""
    sym = symbol.upper().strip()
    if sym.endswith("-USD"):
        return sym.replace("-USD", "/USD")
    if sym.endswith(".IS"):
        # XIST ücretsiz planda çalışmıyor; bare symbol kullan
        return sym.replace(".IS", "")
    if sym == "USDTRY=X":
        return "USD/TRY"
    if sym == "EURTRY=X":
        return "EUR/TRY"
    if sym == "GBPTRY=X":
        return "GBP/TRY"
    if sym == "GC=F":
        return "XAU/USD"
    if sym == "SI=F":
        return "XAG/USD"
    if sym in ("XU100.IS", "^XU100"):
        return "XU100:XIST"
    if sym == "^GSPC":
        return "SPX"
    if sym == "^VIX":
        return "VXX"
    if sym == "^TNX":
        return "IEF"
    if sym == "2YY=F":
        return "SHY"
    if sym == "^GDAXI":
        return "EWG"
    if sym == "^FTSE":
        return "EWU"
    if sym == "^FCHI":
        return "EWQ"
    if sym == "^STOXX50E":
        return "FEZ"
    # Hisse sınıfı ayırıcısı: BRK-B → BRK.B (Twelve Data nokta kullanır)
    # Kripto -USD zaten yukarıda ele alındı; kalan tire → nokta
    if "-" in sym and "/" not in sym and not sym.endswith("-USD"):
        sym = sym.replace("-", ".")
    return sym


def _yf_symbol(symbol: str) -> str:
    if not symbol:
        return ""
    sym = symbol.upper().strip()
    # Eger BIST semboluyse ve sonu .IS ile bitmiyorsa ekle
    if sym in ("ASELS", "CWENE", "GESAN", "GWIND", "PATEK", "SDTTR") or (sym.replace(".IS", "") in ("ASELS", "CWENE", "GESAN", "GWIND", "PATEK", "SDTTR")):
        if not sym.endswith(".IS"):
            return f"{sym.replace('.IS', '')}.IS"
    # Kripto: BTC/USD veya BTC → BTC-USD
    if "/" in sym:
        return sym.replace("/", "-")
    # ABD Hisse: BRK.B → BRK-B
    if sym == "BRK.B":
        return "BRK-B"
    return sym


def _throttle():
    with _rate_lock:
        now = time.monotonic()
        while _call_times and now - _call_times[0] > RATE_WINDOW:
            _call_times.popleft()
        if len(_call_times) >= RATE_LIMIT:
            wait = RATE_WINDOW - (now - _call_times[0]) + 0.05
            if wait > 0:
                time.sleep(wait)
            now = time.monotonic()
            while _call_times and now - _call_times[0] > RATE_WINDOW:
                _call_times.popleft()
        _call_times.append(time.monotonic())


def _api(endpoint: str, params: dict, timeout: int = 15) -> dict | list | None:
    """Rate-limited, hata-toleranslı GET."""
    global _last_rate_limit_ts
    if not API_KEY:
        return None
    _throttle()
    try:
        params = {**params, "apikey": API_KEY}
        r = _req.get(f"{BASE_URL}/{endpoint}", params=params, timeout=timeout)
        if not r.ok:
            sym_hint = params.get("symbol", params.get("symbols", ""))
            logging.warning("TD %s HTTP %s [symbol=%s]", endpoint, r.status_code, sym_hint)
            if r.status_code == 429:
                _last_rate_limit_ts = time.monotonic()
            return None
        data = r.json()
        if isinstance(data, dict) and data.get("status") == "error":
            msg = data.get("message", "")
            logging.warning("TD %s: %s", endpoint, msg[:100])
            if "speed limit" in msg.lower() or "rate limit" in msg.lower() or r.status_code == 429:
                # Not: burada senkron time.sleep(60) YAPMA — bu, isteği işleyen FastAPI worker
                # thread'ini bloke eder (Starlette'in paylaşımlı threadpool'unda bir slot kilitlenir),
                # ve 40+ pozisyonlu bir portföyde eş zamanlı çağrılar (örn. korelasyon matrisi)
                # bu yüzden dakikalarca "hesaplanıyor" gibi asılı kalırdı. _throttle() zaten
                # giden istekleri proaktif olarak sınırlıyor; burada sadece logla ve None dön,
                # çağıran taraf (DB cache / fallback) bunu zaten nazikçe idare ediyor.
                _last_rate_limit_ts = time.monotonic()
                logging.warning("[RATE LIMIT] Twelve Data speed limit hit for %s — atlaniyor.", endpoint)
            return None
        return data
    except Exception as e:
        logging.warning("TD %s exception: %s", endpoint, e)
        return None


# ── SQLite Bağlantısı ────────────────────────────────────────────────────────
_db_lock = threading.Lock()

# TEFAS istekleri için paylaşımlı thread havuzu. ÖNEMLİ: her çağrıda yeni bir
# `with ThreadPoolExecutor(...) as executor:` açıp future.result(timeout=X) ile
# zaman aşımına uğratmak İŞE YARAMIYORDU — `with` bloğundan çıkarken örtük
# executor.shutdown(wait=True) çağrılıyor ve bu, timeout'tan sonra bile arka
# plandaki yavaş isteğin GERÇEKTEN bitmesini bekliyordu (nominal 6sn yerine
# TEFAS'ın gerçek yanıt süresi kadar, gözlemlenen: ~60-70sn/fon). Paylaşılan,
# kapatılmayan bir havuz kullanıp zaman aşımında beklemeden vazgeçiyoruz.
_tefas_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tefas")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def _now() -> float:
    return time.time()


def init_db():
    """Tüm tabloları oluştur. Uygulama başında bir kez çalışır."""
    with _db_lock:
        c = _conn()
        c.executescript("""
        -- Enstrüman listesi (BIST, US, ETF vb.)
        CREATE TABLE IF NOT EXISTS td_instruments (
            symbol      TEXT,
            exchange    TEXT,
            name        TEXT,
            currency    TEXT,
            type        TEXT,
            country     TEXT,
            mic_code    TEXT,
            figi_code   TEXT,
            fetched_at  REAL,
            PRIMARY KEY (symbol, exchange)
        );

        -- Anlık fiyat (batch quote)
        CREATE TABLE IF NOT EXISTS td_quotes (
            symbol         TEXT PRIMARY KEY,
            fetched_at     REAL,
            open           REAL, high REAL, low REAL, close REAL,
            volume         INTEGER,
            prev_close     REAL,
            change         REAL,
            change_pct     REAL,
            wk52_high      REAL,
            wk52_low       REAL,
            avg_volume     INTEGER,
            is_market_open INTEGER,
            currency       TEXT,
            exchange       TEXT
        );

        -- Döviz kurları
        CREATE TABLE IF NOT EXISTS td_exchange_rates (
            pair        TEXT PRIMARY KEY,
            rate        REAL,
            fetched_at  REAL
        );

        -- Tarihsel OHLCV
        CREATE TABLE IF NOT EXISTS td_time_series (
            symbol      TEXT,
            interval    TEXT,
            dt          TEXT,
            open        REAL, high REAL, low REAL, close REAL,
            volume      INTEGER,
            fetched_at  REAL,
            PRIMARY KEY (symbol, interval, dt)
        );

        -- Valuation & finansal istatistikler
        CREATE TABLE IF NOT EXISTS td_statistics (
            symbol           TEXT PRIMARY KEY,
            fetched_at       REAL,
            market_cap       REAL,
            enterprise_value REAL,
            pe_trailing      REAL,
            pe_forward       REAL,
            peg_ratio        REAL,
            ps_ratio         REAL,
            pb_ratio         REAL,
            ev_revenue       REAL,
            ev_ebitda        REAL,
            profit_margin    REAL,
            operating_margin REAL,
            roe              REAL,
            roa              REAL,
            revenue_ttm      REAL,
            eps_ttm          REAL,
            beta             REAL,
            shares_out       REAL,
            raw_json         TEXT
        );

        -- EPS / Kazanç
        CREATE TABLE IF NOT EXISTS td_earnings (
            symbol       TEXT,
            date         TEXT,
            eps_estimate REAL,
            eps_actual   REAL,
            surprise_pct REAL,
            fetched_at   REAL,
            PRIMARY KEY (symbol, date)
        );

        -- Bilanço (sadeleştirilmiş)
        CREATE TABLE IF NOT EXISTS td_balance_sheet (
            symbol             TEXT,
            fiscal_date        TEXT,
            period             TEXT,
            total_assets       REAL,
            total_liab         REAL,
            total_equity       REAL,
            retained_earnings  REAL,
            cash               REAL,
            total_debt         REAL,
            raw_json           TEXT,
            fetched_at         REAL,
            PRIMARY KEY (symbol, fiscal_date)
        );

        -- Teknik indikatörler (genel tablo)
        CREATE TABLE IF NOT EXISTS td_indicators (
            symbol     TEXT,
            indicator  TEXT,
            interval   TEXT,
            dt         TEXT,
            v1         REAL,   -- ana değer (rsi, ema, vb.)
            v2         REAL,   -- ikincil (macd signal, bb_middle)
            v3         REAL,   -- üçüncül (macd hist, bb_upper)
            v4         REAL,   -- dördüncül (bb_lower)
            raw_json   TEXT,   -- dinamik indikatör çıktısı (tüm anahtarlar)
            fetched_at REAL,
            PRIMARY KEY (symbol, indicator, interval, dt)
        );

        -- Şirket profili
        CREATE TABLE IF NOT EXISTS td_profiles (
            symbol      TEXT PRIMARY KEY,
            fetched_at  REAL,
            name        TEXT,
            sector      TEXT,
            industry    TEXT,
            description TEXT,
            exchange    TEXT,
            currency    TEXT,
            ceo         TEXT,
            website     TEXT,
            employees   INTEGER
        );

        -- Yöneticiler
        CREATE TABLE IF NOT EXISTS td_executives (
            symbol     TEXT,
            name       TEXT,
            title      TEXT,
            age        INTEGER,
            pay        REAL,
            fetched_at REAL,
            PRIMARY KEY (symbol, name)
        );

        -- Gelir Tablosu (çeyreklik)
        CREATE TABLE IF NOT EXISTS td_income_statements (
            symbol       TEXT,
            fiscal_date  TEXT,
            period       TEXT,
            sales        REAL,
            net_income   REAL,
            ebitda       REAL,
            op_income    REAL,
            gross_profit REAL,
            raw_json     TEXT,
            fetched_at   REAL,
            PRIMARY KEY (symbol, fiscal_date)
        );

        -- Nakit Akış Tablosu (çeyreklik)
        CREATE TABLE IF NOT EXISTS td_cash_flows (
            symbol       TEXT,
            fiscal_date  TEXT,
            period       TEXT,
            op_cashflow  REAL,
            free_cashflow REAL,
            raw_json     TEXT,
            fetched_at   REAL,
            PRIMARY KEY (symbol, fiscal_date)
        );

        -- Haber akışı
        CREATE TABLE IF NOT EXISTS td_news (
            id          TEXT PRIMARY KEY,
            symbol      TEXT,
            published   TEXT,
            title       TEXT,
            source      TEXT,
            url         TEXT,
            snippet     TEXT,
            fetched_at  REAL
        );

        -- Şirket logosu
        CREATE TABLE IF NOT EXISTS td_logos (
            symbol      TEXT PRIMARY KEY,
            logo_url    TEXT,
            fetched_at  REAL
        );

        -- Temettüler (Dividends)
        CREATE TABLE IF NOT EXISTS td_dividends (
            symbol      TEXT,
            date        TEXT,
            amount      REAL,
            frequency   INTEGER,
            description TEXT,
            fetched_at  REAL,
            PRIMARY KEY (symbol, date)
        );

        -- Bölünmeler (Splits)
        CREATE TABLE IF NOT EXISTS td_splits (
            symbol      TEXT,
            date        TEXT,
            from_factor REAL,
            to_factor   REAL,
            fetched_at  REAL,
            PRIMARY KEY (symbol, date)
        );

        -- Fiyat Hedefleri (Price Targets)
        CREATE TABLE IF NOT EXISTS td_price_targets (
            symbol      TEXT PRIMARY KEY,
            low         REAL,
            median      REAL,
            high        REAL,
            current     REAL,
            fetched_at  REAL
        );

        -- Analist Tavsiyeleri (Recommendations)
        CREATE TABLE IF NOT EXISTS td_recommendations (
            symbol      TEXT PRIMARY KEY,
            strong_buy  INTEGER,
            buy         INTEGER,
            hold        INTEGER,
            sell        INTEGER,
            strong_sell INTEGER,
            rating      REAL,
            rating_text TEXT,
            fetched_at  REAL
        );

        -- İçeriden Alım/Satım (Insider Transactions)
        CREATE TABLE IF NOT EXISTS td_insider_transactions (
            symbol           TEXT,
            date             TEXT,
            share_class      TEXT,
            owner_name       TEXT,
            relation         TEXT,
            transaction_type TEXT,
            shares           INTEGER,
            price            REAL,
            value            REAL,
            shares_held_after INTEGER,
            raw_json         TEXT,
            fetched_at       REAL,
            PRIMARY KEY (symbol, date, owner_name, shares)
        );

        -- Kurumsal Hissedarlar (Institutional Holders)
        CREATE TABLE IF NOT EXISTS td_institutional_holders (
            symbol      TEXT,
            entity_name TEXT,
            date        TEXT,
            shares      INTEGER,
            value       REAL,
            pct_held    REAL,
            change      INTEGER,
            change_pct  REAL,
            raw_json    TEXT,
            fetched_at  REAL,
            PRIMARY KEY (symbol, entity_name)
        );

        -- Fon Hissedarları (Fund Holders)
        CREATE TABLE IF NOT EXISTS td_fund_holders (
            symbol      TEXT,
            entity_name TEXT,
            date        TEXT,
            shares      INTEGER,
            value       REAL,
            pct_held    REAL,
            change      INTEGER,
            change_pct  REAL,
            raw_json    TEXT,
            fetched_at  REAL,
            PRIMARY KEY (symbol, entity_name)
        );

        -- Market Movers (Günün En Çok Kazandıran/Kaybettirenleri)
        CREATE TABLE IF NOT EXISTS td_market_movers (
            market      TEXT,
            direction   TEXT,
            symbol      TEXT,
            name        TEXT,
            last        REAL,
            change      REAL,
            percent_change REAL,
            fetched_at  REAL,
            PRIMARY KEY (market, direction, symbol)
        );

        -- TEFAS Fon listesi ve genel bilgileri
        CREATE TABLE IF NOT EXISTS td_tefas_funds (
            fund_code   TEXT PRIMARY KEY,
            fund_name   TEXT,
            kind        TEXT,
            fetched_at  REAL
        );

        -- TEFAS Fonlarının günlük fiyat (NAV) geçmişi
        CREATE TABLE IF NOT EXISTS td_tefas_nav (
            fund_code         TEXT,
            dt                TEXT,
            price             REAL,
            shares_outstanding REAL,
            investor_count    INTEGER,
            portfolio_size    REAL,
            fetched_at        REAL,
            PRIMARY KEY (fund_code, dt)
        );
        """)
        c.commit()

        # Mevcut DB kolon eklemeleri (migrations)
        try:
            c.execute("ALTER TABLE td_balance_sheet ADD COLUMN retained_earnings REAL")
            c.commit()
        except Exception:
            pass  # Zaten varsa ignore

        try:
            c.execute("ALTER TABLE td_indicators ADD COLUMN raw_json TEXT")
            c.commit()
        except Exception:
            pass  # Zaten varsa ignore

        try:
            # TEFAS fonları için Fonoloji'nin resmi SPK/KAP risk skoru (1-7)
            c.execute("ALTER TABLE td_instruments ADD COLUMN risk_score REAL")
            c.commit()
        except Exception:
            pass  # Zaten varsa ignore

        c.close()
    logging.info("TD DB hazır: %s", DB_PATH)


# ── Yardımcı: stale kontrol ──────────────────────────────────────────────────

def _fresh(fetched_at: float | None, ttl: float) -> bool:
    return bool(fetched_at and _now() - fetched_at < ttl)


# ═══════════════════════════════════════════════════════════════════════════
# 1. ENSTRÜMAN LİSTESİ
# ═══════════════════════════════════════════════════════════════════════════

def fetch_instruments(exchange: str) -> list[dict]:
    """Belirtilen borsa için tüm enstrüman listesini çek ve kaydet."""
    with _db_lock:
        c = _conn()
        row = c.execute(
            "SELECT MAX(fetched_at) fa FROM td_instruments WHERE exchange=?", (exchange,)
        ).fetchone()
        c.close()
    if _fresh(row["fa"] if row else None, TTL_INSTRUMENTS):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT * FROM td_instruments WHERE exchange=?", (exchange,)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    data = _api("stocks", {"exchange": exchange, "show_plan": "true"})
    if not data:
        return []
    instruments = data.get("data", []) if isinstance(data, dict) else data
    ts = _now()
    rows = [
        (
            item["symbol"], exchange,
            item.get("name"), item.get("currency"),
            item.get("type"), item.get("country"),
            item.get("mic_code"), item.get("figi_code"), ts
        )
        for item in instruments
    ]
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_instruments
            (symbol,exchange,name,currency,type,country,mic_code,figi_code,fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, rows)
        c.commit()
        c.close()
    return [dict(zip(
        ["symbol","exchange","name","currency","type","country","mic_code","figi_code","fetched_at"], r
    )) for r in rows]


def get_bist_instruments() -> list[dict]:
    return fetch_instruments("XIST")


def search_instruments(query: str, limit: int = 40) -> list[dict]:
    qu = query.upper()
    like = f"%{qu}%"
    prefix = f"{qu}%"
    with _db_lock:
        c = _conn()
        # Sembolü sorguyla BAŞLAYAN eşleşmeleri (ör. "BTC" -> "BTC/USD") önce getir,
        # sonra kısa sembolleri öne al — aksi halde binlerce kripto çapraz-paritesi
        # (ör. "ADX/BTC") gerçek eşleşmeyi LIMIT'in dışına itebiliyordu.
        rows = c.execute("""
            SELECT * FROM td_instruments
            WHERE symbol LIKE ? OR name LIKE ?
            ORDER BY (symbol LIKE ?) DESC, LENGTH(symbol) ASC
            LIMIT ?
        """, (like, like, prefix, limit)).fetchall()
        c.close()
    return [dict(r) for r in rows]


def _seed_etf_catalog(exchange: str) -> int:
    """Twelve Data'nın ETF/mutual fund listesini td_instruments'a kaydeder (TTL: 14 gün).
    fetch_instruments() sadece /stocks (adi hisse) endpoint'ini çekiyor, ETF'ler hiç
    kataloğa girmiyordu — bu yüzden bir ABD ETF'i, aynı 3 harfli koda sahip bir TEFAS
    fonuyla çakıştığında (ör. "PTF": hem TEFAS fonu hem NASDAQ'ta Invesco Dorsey
    Wright Technology ETF) arama sadece TEFAS'ı buluyor, ETF hiç seçenek olarak
    çıkmıyordu. type='ETF' ile ayrı TTL takip edilir (aynı borsanın stok taraması
    ile karışmasın diye)."""
    with _db_lock:
        c = _conn()
        row = c.execute(
            "SELECT MAX(fetched_at) fa FROM td_instruments WHERE exchange=? AND type='ETF'",
            (exchange,)
        ).fetchone()
        c.close()
    if _fresh(row["fa"] if row else None, TTL_INSTRUMENTS):
        return 0
    data = _api("etfs", {"exchange": exchange})
    items = (data or {}).get("data") or []
    if not items:
        return 0
    ts = _now()
    rows = [
        (
            item["symbol"], exchange,
            item.get("name"), item.get("currency"),
            "ETF", item.get("country"),
            item.get("mic_code"), item.get("figi_code"), ts
        )
        for item in items if item.get("symbol")
    ]
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_instruments
            (symbol,exchange,name,currency,type,country,mic_code,figi_code,fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, rows)
        c.commit()
        c.close()
    return len(rows)


def _seed_crypto_catalog() -> int:
    """Twelve Data kripto para listesini td_instruments'a kaydeder (TTL: 14 gün)."""
    with _db_lock:
        c = _conn()
        row = c.execute(
            "SELECT MAX(fetched_at) fa FROM td_instruments WHERE exchange='Digital Currency'"
        ).fetchone()
        c.close()
    if _fresh(row["fa"] if row else None, TTL_INSTRUMENTS):
        return 0
    data = _api("cryptocurrencies", {})
    items = (data or {}).get("data") or []
    if not items:
        return 0
    ts = _now()
    rows = [
        (
            item["symbol"], "Digital Currency",
            item.get("name"), item.get("currency_base"),
            "Digital Currency", "", "", "", ts
        )
        for item in items
    ]
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_instruments
            (symbol,exchange,name,currency,type,country,mic_code,figi_code,fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, rows)
        c.commit()
        c.close()
    return len(rows)


def seed_tefas_fund_catalog() -> int:
    """TEFAS fon kodu/adı kataloğunu td_instruments'a kaydeder (arama için).
    Birincil kaynak Fonoloji'nin /funds listesi (temiz UTF-8 isimler, sayfalanmış
    tam liste, trading_status ile aktif/pasif ayrımı). FONOLOJI_API_KEY tanımlı
    değilse veya istek başarısız olursa pytefas tabanlı
    tefas_tools._get_all_funds_snapshot'a düşülür (YAT+EMK+BYF, GYF/GSYF hariç;
    fon adlarında bilinen bir encoding kusuru var)."""
    with _db_lock:
        c = _conn()
        row = c.execute(
            "SELECT MAX(fetched_at) fa FROM td_instruments WHERE exchange='TEFAS'"
        ).fetchone()
        c.close()
    if _fresh(row["fa"] if row else None, TTL_INSTRUMENTS):
        return 0

    ts = _now()
    rows: list[tuple] = []

    if FONOLOJI_API_KEY:
        # BUGFIX: Fonoloji'nin canlı OpenAPI şeması (fonoloji.com/v1/openapi.json)
        # doğrulandı — /funds'ta limit artık en fazla 500 (eskiden burada 1000
        # isteniyordu, API'nin güncel sınırını aşıyordu). Ayrıca yeni bir kota sistemi
        # var: dönen HER FON KAYDI 1 kota düşer, kota tükenirse istek reddedilmez ama
        # `_meta.capped=true` ile eksik/kısıtlı sonuç döner — bu durumda `total`'a kadar
        # döngüye devam etmek (offset hep artarken items hep boş dönerdi) anlamsız,
        # kalan kotanın bittiğini görünce döngüden çıkılmalı.
        offset, page_size, total = 0, 500, None
        while total is None or offset < total:
            data = _fonoloji_api("/funds", {"limit": page_size, "offset": offset})
            if not data:
                break
            items = data.get("items") or []
            total = data.get("total", 0)
            for it in items:
                if it.get("trading_status") != "AKTİF":
                    continue
                code = (it.get("code") or "").upper().strip()
                if not code:
                    continue
                rows.append((
                    code, "TEFAS", it.get("name") or code, "TRY",
                    it.get("type") or "Fund", "TR", "", "", ts, it.get("risk_score")
                ))
            offset += page_size
            if not items or (data.get("_meta") or {}).get("capped"):
                if (data.get("_meta") or {}).get("capped"):
                    logging.warning("[CATALOG] Fonoloji /funds kota sınırına takıldı (_meta.capped) — "
                                     "katalog kısmi kalabilir, kalanı pytefas'a düşülecek.")
                break
        if not rows:
            logging.warning("[CATALOG] Fonoloji /funds boş/başarısız döndü, pytefas'a düşülüyor.")

    if not rows:
        try:
            from tefas_tools import _get_all_funds_snapshot
            from datetime import timedelta as _timedelta
            # Tek günlük pencere hafta sonuna denk gelip boş dönebiliyor; 6 günlük
            # pencere (dünle biten) en az birkaç iş gününü garantiler.
            snap = _get_all_funds_snapshot(date.today() - _timedelta(days=7))
        except Exception as e:
            logging.warning("[CATALOG] TEFAS fon listesi çekilemedi: %s", e)
            snap = None
        if snap is not None and not snap.empty:
            rows = [
                (
                    str(r["fund_code"]).upper(), "TEFAS",
                    r.get("fund_name") or str(r["fund_code"]), "TRY",
                    "Fund", "TR", "", "", ts, None
                )
                for _, r in snap.iterrows()
            ]

    if not rows:
        return 0
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_instruments
            (symbol,exchange,name,currency,type,country,mic_code,figi_code,fetched_at,risk_score)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, rows)
        c.commit()
        c.close()
    return len(rows)


def refresh_instrument_catalog() -> dict:
    """BIST, NASDAQ, NYSE (hisse+ETF), Kripto ve TEFAS arama kataloğunu tazeler.
    Her kaynak kendi TTL'ine göre (14 gün) ağa gerçek istek atar; taze olan
    kaynaklar için hiçbir API çağrısı yapılmaz."""
    counts: dict[str, int] = {}
    for label, fn in (
        ("XIST", lambda: len(get_bist_instruments())),
        ("NASDAQ", lambda: len(fetch_instruments("NASDAQ"))),
        ("NYSE", lambda: len(fetch_instruments("NYSE"))),
        ("NASDAQ_ETF", lambda: _seed_etf_catalog("NASDAQ")),
        ("NYSE_ETF", lambda: _seed_etf_catalog("NYSE")),
        ("CRYPTO", _seed_crypto_catalog),
        ("TEFAS", seed_tefas_fund_catalog),
    ):
        try:
            counts[label] = fn()
        except Exception as e:
            logging.warning("[CATALOG] %s tohumlama başarısız: %s", label, e)
            counts[label] = -1
    logging.info("[CATALOG] Enstrüman kataloğu tazelendi: %s", counts)
    return counts


# ═══════════════════════════════════════════════════════════════════════════
# 2. ANLLIK FİYAT (BATCH QUOTE)
# ═══════════════════════════════════════════════════════════════════════════

def _save_quote(sym: str, raw: dict):
    fw = raw.get("fifty_two_week") or {}
    with _db_lock:
        c = _conn()
        c.execute("""
            INSERT OR REPLACE INTO td_quotes
            (symbol,fetched_at,open,high,low,close,volume,prev_close,change,change_pct,
             wk52_high,wk52_low,avg_volume,is_market_open,currency,exchange)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            sym.upper(), _now(),
            _f(raw.get("open")), _f(raw.get("high")),
            _f(raw.get("low")),  _f(raw.get("close")),
            _i(raw.get("volume")), _f(raw.get("previous_close")),
            _f(raw.get("change")), _f(raw.get("percent_change")),
            _f(fw.get("high")), _f(fw.get("low")),
            _i(raw.get("average_volume")),
            1 if raw.get("is_market_open") else 0,
            raw.get("currency", "USD"), raw.get("exchange", ""),
        ))
        c.commit()
        c.close()


def batch_quotes(symbols: list[str]) -> dict[str, dict]:
    """
    Toplu anlık fiyat. Cache'de tazeyse API çağrısı yapmaz.
    Returns {SYMBOL: quote_dict}
    """
    if not symbols:
        return {}
    
    # Eşleme tutalım: {cleaned_symbol: original_symbol_uppercase}
    sym_map = { _clean_symbol(s): s.upper() for s in symbols }
    cleaned_symbols = list(sym_map.keys())
    
    result: dict[str, dict] = {}
    missing: list[str] = []

    with _db_lock:
        c = _conn()
        for cs in cleaned_symbols:
            row = c.execute("SELECT * FROM td_quotes WHERE symbol=?", (cs,)).fetchone()
            if row and _fresh(row["fetched_at"], TTL_QUOTE):
                orig = sym_map[cs]
                result[orig] = dict(row)
                result[orig]["symbol"] = orig # Orijinal sembolü koru
            else:
                missing.append(cs)
        c.close()

    for i in range(0, len(missing), 20):
        chunk = missing[i:i + 20]
        raw = _api("quote", {"symbol": ",".join(chunk)})
        if not raw:
            # Batch başarısız — tek tek dene
            for cs in chunk:
                single = _api("quote", {"symbol": cs})
                if not single or not isinstance(single, dict) or "close" not in single:
                    continue
                cs_upper = cs.upper()
                _save_quote(cs_upper, single)
                orig = sym_map.get(cs_upper, cs_upper)
                loaded = _load_quote(cs_upper)
                if loaded:
                    result[orig] = dict(loaded)
                    result[orig]["symbol"] = orig
            continue
        # Tek sembol → dict, çoklu → {sym: dict}
        if isinstance(raw, dict) and "close" in raw:
            raw = {chunk[0]: raw}
        for cs, data in raw.items():
            if not isinstance(data, dict):
                continue
            cs_upper = cs.upper()
            _save_quote(cs_upper, data)
            orig = sym_map.get(cs_upper, cs_upper)
            loaded = _load_quote(cs_upper)
            if loaded:
                result[orig] = dict(loaded)
                result[orig]["symbol"] = orig
    return result



def get_quote(symbol: str) -> Optional[dict]:
    q = batch_quotes([symbol])
    return q.get(symbol.upper())


def get_price(symbol: str) -> Optional[float]:
    q = get_quote(symbol)
    return q["close"] if q else None


def _load_quote(sym: str) -> Optional[sqlite3.Row]:
    with _db_lock:
        c = _conn()
        row = c.execute("SELECT * FROM td_quotes WHERE symbol=?", (sym.upper(),)).fetchone()
        c.close()
    return row


# ═══════════════════════════════════════════════════════════════════════════
# 3. DÖVİZ KURLARI
# ═══════════════════════════════════════════════════════════════════════════

def get_exchange_rate(pair: str) -> Optional[float]:
    """
    Döviz kuru. Örn: get_exchange_rate('USD/TRY')
    1 saatlik cache.
    """
    pair = pair.upper()
    with _db_lock:
        c = _conn()
        row = c.execute("SELECT * FROM td_exchange_rates WHERE pair=?", (pair,)).fetchone()
        c.close()
    if row and _fresh(row["fetched_at"], TTL_RATE):
        return row["rate"]

    data = _api("exchange_rate", {"symbol": pair})
    if not data or "rate" not in data:
        return None
    rate = float(data["rate"])
    with _db_lock:
        c = _conn()
        c.execute(
            "INSERT OR REPLACE INTO td_exchange_rates (pair,rate,fetched_at) VALUES (?,?,?)",
            (pair, rate, _now())
        )
        c.commit()
        c.close()
    return rate


def get_all_rates() -> dict[str, float]:
    """Portföy için gereken tüm kurları tek seferde döndür."""
    pairs = ["USD/TRY", "EUR/TRY", "GBP/TRY", "BTC/USD", "ETH/USD"]
    rates = {}
    for pair in pairs:
        r = get_exchange_rate(pair)
        if r:
            rates[pair] = r
    return rates


# ═══════════════════════════════════════════════════════════════════════════
# 4. TARİHSEL OHLCV (TIME SERIES)
# ═══════════════════════════════════════════════════════════════════════════

def _get_earliest_timestamp(symbol: str, interval: str) -> Optional[str]:
    """Twelve Data en eski veri tarihini sorgular."""
    raw = _api("earliest_timestamp", {"symbol": symbol, "interval": interval})
    if raw and isinstance(raw, dict) and "datetime" in raw:
        return raw["datetime"]
    return None


def get_time_series(symbol: str, days: int = 90, interval: str = "1day") -> list[dict]:
    """
    Tarihsel OHLCV.
    - İlk çalıştırmada en eski tarihten başlayarak tüm geçmişi çeker (Full Backfill, maks 5000 bar).
    - Sonraki çalıştırmalarda sadece son tarihten sonrasını çeker (Incremental Update).
    Returns: [{"date", "open", "high", "low", "close", "volume"}]
    """
    sym = _clean_symbol(symbol)
    
    # Veritabanındaki durumu kontrol et
    with _db_lock:
        c = _conn()
        meta = c.execute(
            "SELECT MAX(dt) max_dt, COUNT(*) cnt, MAX(fetched_at) fa FROM td_time_series WHERE symbol=? AND interval=?",
            (sym, interval)
        ).fetchone()
        c.close()
        
    max_dt = meta["max_dt"] if meta else None
    cnt = meta["cnt"] if meta else 0
    fa = meta["fa"] if meta else None
    
    # Eğer önbellek taze ise doğrudan DB'den dön
    if cnt > 0 and _fresh(fa, TTL_TIME_SERIES) and cnt >= days:
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT dt date, open, high, low, close, volume FROM td_time_series "
                "WHERE symbol=? AND interval=? ORDER BY dt DESC LIMIT ?",
                (sym, interval, days)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    # API'den veri çekme kararı
    values = []
    ts = _now()
    
    if cnt == 0:
        # 1. Senaryo: Veritabanında hiç veri yok -> FULL BACKFILL
        earliest = _get_earliest_timestamp(sym, interval)
        params = {"symbol": sym, "interval": interval, "outputsize": 5000}
        if earliest:
            params["start_date"] = earliest
            
        raw = _api("time_series", params)
        if raw and not raw.get("status") == "error":
            values = raw.get("values", [])
    else:
        # 2. Senaryo: Artımlı güncelleme -> INCREMENTAL UPDATE
        raw = _api("time_series", {"symbol": sym, "interval": interval, "start_date": max_dt})
        if raw and not raw.get("status") == "error":
            values = raw.get("values", [])

    if values:
        with _db_lock:
            c = _conn()
            # Yeni verileri kaydet veya eskilerini güncelle
            c.executemany("""
                INSERT OR REPLACE INTO td_time_series
                (symbol,interval,dt,open,high,low,close,volume,fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, [
                (sym, interval, v["datetime"],
                 _f(v.get("open")), _f(v.get("high")),
                 _f(v.get("low")),  _f(v.get("close")),
                 _i(v.get("volume")), ts)
                for v in values
            ])
            # Tüm serinin fetched_at tarihini güncelle ki cache yenilenmiş olsun
            c.execute(
                "UPDATE td_time_series SET fetched_at=? WHERE symbol=? AND interval=?",
                (ts, sym, interval)
            )
            c.commit()
            c.close()

    # Sonuçları veritabanından çek ve döndür (böylece her zaman sıralı ve temiz gelir)
    with _db_lock:
        c = _conn()
        rows = c.execute(
            "SELECT dt date, open, high, low, close, volume FROM td_time_series "
            "WHERE symbol=? AND interval=? ORDER BY dt DESC LIMIT ?",
            (sym, interval, days)
        ).fetchall()
        c.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# 5. İSTATİSTİKLER (P/E, Market Cap, vb.)
# ═══════════════════════════════════════════════════════════════════════════

def get_statistics(symbol: str) -> Optional[dict]:
    """Valuation ve finansal istatistikler. 7 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return None
    with _db_lock:
        c = _conn()
        row = c.execute("SELECT * FROM td_statistics WHERE symbol=?", (sym,)).fetchone()
        c.close()
    if row and _fresh(row["fetched_at"], TTL_STATISTICS):
        d = dict(row)
        d["symbol"] = symbol.upper()
        return d

    raw = _api("statistics", {"symbol": sym})
    if not raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            info = ticker.info
            if info and "marketCap" in info:
                data = {
                    "symbol": sym, "fetched_at": _now(),
                    "market_cap":       _f(info.get("marketCap")),
                    "enterprise_value": _f(info.get("enterpriseValue")),
                    "pe_trailing":      _f(info.get("trailingPE")),
                    "pe_forward":       _f(info.get("forwardPE")),
                    "peg_ratio":        _f(info.get("pegRatio")),
                    "ps_ratio":         _f(info.get("priceToSalesTrailing12Months")),
                    "pb_ratio":         _f(info.get("priceToBook")),
                    "ev_revenue":       _f(info.get("enterpriseToRevenue")),
                    "ev_ebitda":        _f(info.get("enterpriseToEbitda")),
                    "profit_margin":    _f(info.get("profitMargins")),
                    "operating_margin": _f(info.get("operatingMargins")),
                    "roe":              _f(info.get("returnOnEquity")),
                    "roa":              _f(info.get("returnOnAssets")),
                    "revenue_ttm":      _f(info.get("totalRevenue")),
                    "eps_ttm":          _f(info.get("trailingEps")),
                    "beta":             _f(info.get("beta")),
                    "shares_out":       _f(info.get("sharesOutstanding")),
                    "raw_json":         json.dumps(info),
                }
                with _db_lock:
                    c = _conn()
                    c.execute("""
                        INSERT OR REPLACE INTO td_statistics
                        (symbol,fetched_at,market_cap,enterprise_value,pe_trailing,pe_forward,
                         peg_ratio,ps_ratio,pb_ratio,ev_revenue,ev_ebitda,profit_margin,
                         operating_margin,roe,roa,revenue_ttm,eps_ttm,beta,shares_out,raw_json)
                        VALUES (:symbol,:fetched_at,:market_cap,:enterprise_value,:pe_trailing,:pe_forward,
                         :peg_ratio,:ps_ratio,:pb_ratio,:ev_revenue,:ev_ebitda,:profit_margin,
                         :operating_margin,:roe,:roa,:revenue_ttm,:eps_ttm,:beta,:shares_out,:raw_json)
                    """, data)
                    c.commit()
                    c.close()
                data["symbol"] = symbol.upper()
                return data
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Statistics fetch failed for %s: %s", sym, e)
        return None
    stats = raw.get("statistics", {})
    vm = stats.get("valuations_metrics", {})
    fin = stats.get("financials", {})
    inc = fin.get("income_statement", {})
    bs  = fin.get("balance_sheet", {})
    data = {
        "symbol": sym, "fetched_at": _now(),
        "market_cap":       _f(vm.get("market_capitalization")),
        "enterprise_value": _f(vm.get("enterprise_value")),
        "pe_trailing":      _f(vm.get("trailing_pe")),
        "pe_forward":       _f(vm.get("forward_pe")),
        "peg_ratio":        _f(vm.get("peg_ratio")),
        "ps_ratio":         _f(vm.get("price_to_sales_ttm")),
        "pb_ratio":         _f(vm.get("price_to_book_mrq")),
        "ev_revenue":       _f(vm.get("enterprise_to_revenue")),
        "ev_ebitda":        _f(vm.get("enterprise_to_ebitda")),
        "profit_margin":    _f(fin.get("profit_margin")),
        "operating_margin": _f(fin.get("operating_margin")),
        "roe":              _f(fin.get("return_on_equity_ttm")),
        "roa":              _f(fin.get("return_on_assets_ttm")),
        "revenue_ttm":      _f(inc.get("revenue_ttm")),
        "eps_ttm":          _f(inc.get("diluted_eps_ttm")),
        "beta":             _f(stats.get("stock_price_summary", {}).get("beta")),
        "shares_out":       _f(stats.get("stock_statistics", {}).get("shares_outstanding")),
        "raw_json":         json.dumps(stats),
    }
    with _db_lock:
        c = _conn()
        c.execute("""
            INSERT OR REPLACE INTO td_statistics
            (symbol,fetched_at,market_cap,enterprise_value,pe_trailing,pe_forward,
             peg_ratio,ps_ratio,pb_ratio,ev_revenue,ev_ebitda,profit_margin,
             operating_margin,roe,roa,revenue_ttm,eps_ttm,beta,shares_out,raw_json)
            VALUES (:symbol,:fetched_at,:market_cap,:enterprise_value,:pe_trailing,:pe_forward,
             :peg_ratio,:ps_ratio,:pb_ratio,:ev_revenue,:ev_ebitda,:profit_margin,
             :operating_margin,:roe,:roa,:revenue_ttm,:eps_ttm,:beta,:shares_out,:raw_json)
        """, data)
        c.commit()
        c.close()
    data["symbol"] = symbol.upper()
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 6. EPS / KAZANÇ
# ═══════════════════════════════════════════════════════════════════════════

def get_earnings(symbol: str, periods: int = 8) -> list[dict]:
    """Son N EPS açıklaması. 30 günlük cache."""
    sym = _clean_symbol(symbol)
    with _db_lock:
        c = _conn()
        meta = c.execute(
            "SELECT MAX(fetched_at) fa, COUNT(*) cnt FROM td_earnings WHERE symbol=?", (sym,)
        ).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_EARNINGS) and meta["cnt"] >= 1:
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT date,eps_estimate,eps_actual,surprise_pct FROM td_earnings "
                "WHERE symbol=? ORDER BY date DESC LIMIT ?", (sym, periods)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    raw = _api("earnings", {"symbol": sym, "outputsize": periods})
    if not raw:
        return []
    items = raw.get("earnings", [])
    ts = _now()
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_earnings
            (symbol,date,eps_estimate,eps_actual,surprise_pct,fetched_at)
            VALUES (?,?,?,?,?,?)
        """, [
            (sym, item["date"], _f(item.get("eps_estimate")),
             _f(item.get("eps_actual")), _f(item.get("surprise_prc")), ts)
            for item in items
        ])
        c.commit()
        c.close()
    return [{"date": i["date"], "eps_estimate": _f(i.get("eps_estimate")),
             "eps_actual": _f(i.get("eps_actual")), "surprise_pct": _f(i.get("surprise_prc"))}
            for i in items[:periods]]


# ═══════════════════════════════════════════════════════════════════════════
# 7. BİLANÇO
# ═══════════════════════════════════════════════════════════════════════════

def get_balance_sheet(symbol: str) -> list[dict]:
    """Son 4 çeyreklik bilanço. 30 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return []
    with _db_lock:
        c = _conn()
        meta = c.execute(
            "SELECT MAX(fetched_at) fa FROM td_balance_sheet WHERE symbol=?", (sym,)
        ).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_BALANCE):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT fiscal_date,period,total_assets,total_liab,total_equity,retained_earnings,cash,total_debt "
                "FROM td_balance_sheet WHERE symbol=? ORDER BY fiscal_date DESC LIMIT 4", (sym,)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    raw = _api("balance_sheet", {"symbol": sym, "outputsize": 4}, timeout=20)
    if not raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            df = ticker.quarterly_balance_sheet
            if df is not None and not df.empty:
                ts = _now()
                results = []
                with _db_lock:
                    c = _conn()
                    for col in df.columns[:4]:
                        fiscal_date = str(col)[:10]
                        col_data = df[col].to_dict()
                        # yfinance'in quarterly_balance_sheet DataFrame'i satır etiketlerini boşluklu
                        # Title Case kullanır (örn. "Total Assets"), bitişik-yazım anahtarlar hiç eşleşmiyordu.
                        cash = col_data.get("Cash And Cash Equivalents") or col_data.get("Cash Cash Equivalents And Short Term Investments") or col_data.get("CashAndCashEquivalents")
                        total_assets = col_data.get("Total Assets") or col_data.get("TotalAssets")
                        total_liab = col_data.get("Total Liabilities Net Minority Interest") or col_data.get("TotalLiabilitiesNetMinInterest")
                        total_equity = col_data.get("Stockholders Equity") or col_data.get("StockholdersEquity")
                        retained_earnings = col_data.get("Retained Earnings") or col_data.get("RetainedEarnings")
                        total_debt = col_data.get("Total Debt") or col_data.get("Long Term Debt") or col_data.get("TotalDebt")
                        
                        row = {
                            "fiscal_date":      fiscal_date,
                            "period":           "Quarterly",
                            "total_assets":     _f(total_assets),
                            "total_liab":       _f(total_liab),
                            "total_equity":     _f(total_equity),
                            "retained_earnings":_f(retained_earnings),
                            "cash":             _f(cash),
                            "total_debt":       _f(total_debt),
                            "raw_json":         json.dumps(col_data),
                            "fetched_at":       ts,
                        }
                        c.execute("""
                            INSERT OR REPLACE INTO td_balance_sheet
                            (symbol,fiscal_date,period,total_assets,total_liab,total_equity,retained_earnings,cash,total_debt,raw_json,fetched_at)
                            VALUES (:sym,:fiscal_date,:period,:total_assets,:total_liab,:total_equity,:retained_earnings,:cash,:total_debt,:raw_json,:fetched_at)
                        """, {"sym": sym, **row})
                        results.append({k: v for k, v in row.items() if k != "raw_json"})
                    c.commit()
                    c.close()
                if results:
                    return results
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Balance sheet fetch failed for %s: %s", sym, e)
        return []
    items = raw.get("balance_sheet", [])
    ts = _now()
    results = []
    with _db_lock:
        c = _conn()
        for item in items:
            assets   = item.get("assets", {})
            liab     = item.get("liabilities", {})
            equity   = item.get("shareholders_equity", {})
            cur_a    = assets.get("current_assets", {})
            cur_l    = liab.get("current_liabilities", {})
            noncur_l = liab.get("non_current_liabilities", {})
            row = {
                "fiscal_date":      item.get("fiscal_date", ""),
                "period":           raw.get("meta", {}).get("period", "Annual"),
                "total_assets":     _f(assets.get("total_assets")),
                "total_liab":       _f(liab.get("total_liabilities")),
                "total_equity":     _f(equity.get("total_shareholders_equity")),
                "retained_earnings":_f(equity.get("retained_earnings")),
                "cash":             _f(cur_a.get("cash_and_cash_equivalents")),
                "total_debt":       _f(noncur_l.get("long_term_debt") or cur_l.get("short_term_debt")),
                "raw_json":         json.dumps(item),
                "fetched_at":       ts,
            }
            c.execute("""
                INSERT OR REPLACE INTO td_balance_sheet
                (symbol,fiscal_date,period,total_assets,total_liab,total_equity,retained_earnings,cash,total_debt,raw_json,fetched_at)
                VALUES (:sym,:fiscal_date,:period,:total_assets,:total_liab,:total_equity,:retained_earnings,:cash,:total_debt,:raw_json,:fetched_at)
            """, {"sym": sym, **row})
            results.append({k: v for k, v in row.items() if k != "raw_json"})
        c.commit()
        c.close()
    return results


# ═══════════════════════════════════════════════════════════════════════════
# 8. TEKNİK İNDİKATÖRLER
# ═══════════════════════════════════════════════════════════════════════════

_INDICATOR_FIELDS = {
    "rsi":    (["rsi"],            ["v1"]),
    "macd":   (["macd","macd_signal","macd_hist"], ["v1","v2","v3"]),
    "bbands": (["upper_band","middle_band","lower_band"], ["v1","v2","v3"]),
    "ema":    (["ema"],            ["v1"]),
    "sma":    (["sma"],            ["v1"]),
    "beta":   (["beta"],           ["v1"]),
    "atr":    (["atr"],            ["v1"]),
    "adx":    (["adx"],            ["v1"]),
    "stoch":  (["slow_k","slow_d"],["v1","v2"]),
}


def get_indicator(
    symbol: str,
    indicator: str,
    interval: str = "1day",
    periods: int = 30,
    **extra_params
) -> list[dict]:
    """
    Herhangi bir teknik indikatör. 1 günlük cache.
    Örn: get_indicator('AAPL', 'rsi', time_period=14)
    Returns: [{"dt", "v1", ...}] veya dinamik çıktı içeren dict listesi.
    """
    sym  = _clean_symbol(symbol)
    ind  = indicator.lower()
    with _db_lock:
        c = _conn()
        meta = c.execute(
            "SELECT MAX(fetched_at) fa, COUNT(*) cnt FROM td_indicators "
            "WHERE symbol=? AND indicator=? AND interval=?", (sym, ind, interval)
        ).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_INDICATOR) and meta["cnt"] >= 1:
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT dt, v1, v2, v3, v4, raw_json FROM td_indicators "
                "WHERE symbol=? AND indicator=? AND interval=? ORDER BY dt DESC LIMIT ?",
                (sym, ind, interval, periods)
            ).fetchall()
            c.close()
        
        results = []
        for r in rows:
            dt = r["dt"]
            if r["raw_json"]:
                try:
                    data = json.loads(r["raw_json"])
                    results.append({"dt": dt, **data})
                    continue
                except Exception:
                    pass
            # Geriye dönük uyumluluk: raw_json yoksa field_map ile eşle
            field_map = _INDICATOR_FIELDS.get(ind, (["v1"], ["v1"]))
            src_fields, dst_fields = field_map
            item = {"dt": dt}
            for i, df in enumerate(dst_fields):
                val_key = f"v{i+1}"
                item[df] = r[val_key]
            results.append(item)
        return results

    params = {"symbol": sym, "interval": interval, "outputsize": max(periods, 20), **extra_params}
    if ind == "rsi" and "time_period" not in params:
        params["time_period"] = 14
    if ind == "beta" and "time_period" not in params:
        params["time_period"] = 252

    raw = _api(ind, params)
    if not raw:
        return []
    values = raw.get("values", [])
    if not values:
        return []

    field_map = _INDICATOR_FIELDS.get(ind, ([list(values[0].keys())[-1]], ["v1"]))
    src_fields, dst_fields = field_map

    ts = _now()
    db_rows = []
    results = []
    for v in values:
        vals = [_f(v.get(sf)) for sf in src_fields]
        while len(vals) < 4:
            vals.append(None)
        
        # Datetime hariç tüm çiftleri topla ve sakla
        raw_data = {k: _f(val) for k, val in v.items() if k != "datetime"}
        raw_json_str = json.dumps(raw_data)
        
        db_rows.append((sym, ind, interval, v["datetime"], *vals[:4], raw_json_str, ts))
        results.append({"dt": v["datetime"], **raw_data})

    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_indicators
            (symbol,indicator,interval,dt,v1,v2,v3,v4,raw_json,fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, db_rows)
        c.commit()
        c.close()
    return results[:periods]


def get_rsi(symbol: str, period: int = 14, interval: str = "1day", n: int = 30) -> list[dict]:
    return get_indicator(symbol, "rsi", interval, n, time_period=period)

def get_macd(symbol: str, interval: str = "1day", n: int = 30) -> list[dict]:
    return get_indicator(symbol, "macd", interval, n)

def get_bbands(symbol: str, period: int = 20, interval: str = "1day", n: int = 30) -> list[dict]:
    return get_indicator(symbol, "bbands", interval, n, time_period=period)

def get_ema(symbol: str, period: int = 20, interval: str = "1day", n: int = 30) -> list[dict]:
    return get_indicator(symbol, "ema", interval, n, time_period=period)

def get_beta_value(symbol: str) -> Optional[float]:
    """Güncel Beta değeri (risk skoru için).
    get_indicator() taze API yanıtında sağlayıcının ham alan adını ("beta"),
    eski formatlı cache'den okurken kanonik adı ("v1") döndürebiliyor — ikisini
    de dene."""
    data = get_indicator(symbol, "beta", "1day", 1, time_period=252)
    if not data:
        return None
    row = data[0]
    return row.get("beta") if row.get("beta") is not None else row.get("v1")


# ═══════════════════════════════════════════════════════════════════════════
# 9. ŞİRKET PROFİLİ & YÖNETİCİLER
# ═══════════════════════════════════════════════════════════════════════════

def get_profile(symbol: str) -> Optional[dict]:
    """Şirket profili. 30 günlük cache."""
    sym = _clean_symbol(symbol)
    with _db_lock:
        c = _conn()
        row = c.execute("SELECT * FROM td_profiles WHERE symbol=?", (sym,)).fetchone()
        c.close()
    if row and _fresh(row["fetched_at"], TTL_PROFILE):
        d = dict(row)
        d["symbol"] = symbol.upper()
        return d

    raw = _api("profile", {"symbol": sym})
    if not raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            info = ticker.info
            if info and ("longName" in info or "shortName" in info):
                officers = info.get("companyOfficers", [{}])
                ceo_name = officers[0].get("name", "") if officers else ""
                data = {
                    "symbol": sym, "fetched_at": _now(),
                    "name": info.get("longName") or info.get("shortName") or sym,
                    "sector": info.get("sector") or "N/A",
                    "industry": info.get("industry") or "N/A",
                    "description": info.get("longBusinessSummary") or "N/A",
                    "exchange": info.get("exchange") or "N/A",
                    "currency": info.get("currency") or "USD",
                    "ceo": ceo_name,
                    "website": info.get("website") or "",
                    "employees": _i(info.get("fullTimeEmployees")),
                }
                with _db_lock:
                    c = _conn()
                    c.execute("""
                        INSERT OR REPLACE INTO td_profiles
                        (symbol,fetched_at,name,sector,industry,description,exchange,currency,ceo,website,employees)
                        VALUES (:symbol,:fetched_at,:name,:sector,:industry,:description,:exchange,:currency,:ceo,:website,:employees)
                    """, data)
                    c.commit()
                    c.close()
                data["symbol"] = symbol.upper()
                return data
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Profile fetch failed for %s: %s", sym, e)
        return None

    data = {
        "symbol": sym, "fetched_at": _now(),
        "name": raw.get("name"), "sector": raw.get("sector"),
        "industry": raw.get("industry"), "description": raw.get("description"),
        "exchange": raw.get("exchange"), "currency": raw.get("currency"),
        "ceo": raw.get("CEO"), "website": raw.get("website"),
        "employees": _i(raw.get("employees")),
    }
    with _db_lock:
        c = _conn()
        c.execute("""
            INSERT OR REPLACE INTO td_profiles
            (symbol,fetched_at,name,sector,industry,description,exchange,currency,ceo,website,employees)
            VALUES (:symbol,:fetched_at,:name,:sector,:industry,:description,:exchange,:currency,:ceo,:website,:employees)
        """, data)
        c.commit()
        c.close()
    data["symbol"] = symbol.upper()
    return data


def get_executives(symbol: str) -> list[dict]:
    """Yöneticiler. 30 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return []
    with _db_lock:
        c = _conn()
        meta = c.execute(
            "SELECT MAX(fetched_at) fa FROM td_executives WHERE symbol=?", (sym,)
        ).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_EXECUTIVES):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT name,title,age,pay FROM td_executives WHERE symbol=?", (sym,)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    raw = _api("key_executives", {"symbol": sym})
    if not raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            info = ticker.info
            officers = info.get("companyOfficers")
            if officers:
                ts = _now()
                rows = []
                results = []
                for i, off in enumerate(officers):
                    row = (sym, off.get("name", ""), off.get("title", ""), _i(off.get("age")), _f(off.get("totalPay")), ts)
                    rows.append(row)
                    results.append({"name": off.get("name"), "title": off.get("title"), "age": _i(off.get("age")), "pay": _f(off.get("totalPay"))})
                with _db_lock:
                    c = _conn()
                    c.executemany("""
                        INSERT OR REPLACE INTO td_executives (symbol,name,title,age,pay,fetched_at)
                        VALUES (?,?,?,?,?,?)
                    """, rows)
                    c.commit()
                    c.close()
                return results
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Executives fetch failed for %s: %s", sym, e)
        return []
    items = raw.get("key_executives", [])
    ts = _now()
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_executives (symbol,name,title,age,pay,fetched_at)
            VALUES (?,?,?,?,?,?)
        """, [(sym, i.get("name",""), i.get("title",""), _i(i.get("age")), _f(i.get("pay")), ts)
              for i in items])
        c.commit()
        c.close()
    return [{"name": i.get("name"), "title": i.get("title"),
             "age": _i(i.get("age")), "pay": _f(i.get("pay"))} for i in items]


# ═══════════════════════════════════════════════════════════════════════════
# 10. HABER AKIŞI
# ═══════════════════════════════════════════════════════════════════════════

TTL_NEWS = 6 * 3600  # 6 saat


def get_news(symbol: str, output_size: int = 20) -> list[dict]:
    """Sembol haberleri. 6 saatlik cache."""
    sym = _clean_symbol(symbol)
    ts = _now()
    with _db_lock:
        c = _conn()
        meta = c.execute(
            "SELECT MAX(fetched_at) fa FROM td_news WHERE symbol=?", (sym,)
        ).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_NEWS):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT * FROM td_news WHERE symbol=? ORDER BY published DESC LIMIT ?",
                (sym, output_size)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    raw = _api("news", {"symbol": sym, "outputsize": output_size})
    if not raw:
        return []
    items = raw.get("data", []) if isinstance(raw, dict) else raw
    if not items:
        return []
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_news (id, symbol, published, title, source, url, snippet, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                f"{sym}_{item.get('published_at', '')}_{i}",
                sym,
                item.get("published_at", ""),
                item.get("title", ""),
                item.get("source", ""),
                item.get("url", ""),
                item.get("snippet", ""),
                ts,
            )
            for i, item in enumerate(items)
        ])
        c.commit()
        c.close()
    return [{"symbol": sym, "published": it.get("published_at"), "title": it.get("title"),
             "source": it.get("source"), "url": it.get("url"), "snippet": it.get("snippet")}
            for it in items]


# ═══════════════════════════════════════════════════════════════════════════
# 10. TOPLU YENİLEME (Portföy için)
# ═══════════════════════════════════════════════════════════════════════════

def refresh_portfolio_quotes(us_symbols: list[str]) -> dict[str, dict]:
    """Portföydeki US sembolleri için anlık fiyat toplu güncelle."""
    return batch_quotes(us_symbols)


def enrich_symbol(symbol: str, interval: str = "1day") -> dict[str, Any]:
    """
    Bir sembol için ulaşılabilecek HER şeyi çek ve DB'ye kaydet.
    Portföy varlıkları için arka planda çalışır.
    Returns: summary of what was fetched.
    """
    sym = symbol.upper()
    result: dict[str, Any] = {"symbol": sym}

    result["quote"]      = get_quote(sym)
    result["profile"]    = get_profile(sym)
    result["statistics"] = get_statistics(sym)
    result["earnings"]   = get_earnings(sym, 8)
    result["balance"]    = get_balance_sheet(sym)
    result["time_series"]= get_time_series(sym, 365, interval)
    result["rsi"]        = get_rsi(sym, 14, interval, 60)
    result["macd"]       = get_macd(sym, interval, 60)
    result["bbands"]     = get_bbands(sym, 20, interval, 60)
    result["ema_20"]     = get_ema(sym, 20, interval, 60)
    result["ema_50"]     = get_ema(sym, 50, interval, 60)
    result["executives"] = get_executives(sym)
    
    # Yeni Analiz Verileri
    result["logo"]            = get_logo(sym)
    result["dividends"]       = get_dividends(sym)
    result["splits"]          = get_splits(sym)
    result["price_target"]    = get_price_target(sym)
    result["recommendations"] = get_recommendations(sym)
    result["insiders"]        = get_insider_transactions(sym)
    result["institutional"]   = get_institutional_holders(sym)
    result["fund_holders"]    = get_fund_holders(sym)

    return {k: (len(v) if isinstance(v, list) else bool(v)) for k, v in result.items()}


import queue

class TwelveDataCrawler:
    def __init__(self):
        self.queue = queue.Queue()
        self.running = False
        self.thread = None
        self.last_api_call = 0
        # Crawler ve canlı kullanıcı istekleri (fiyat çekme) AYNI paylaşımlı Twelve Data
        # rate-limit kotasını (_throttle(), 55 çağrı/60sn) kullanıyor. 1.8sn'de bir (dakikada
        # ~33 çağrı) crawler TEK BAŞINA kotanın çoğunu tüketebiliyordu — canlıda ölçüldü:
        # bir kullanıcı giriş yapıp portföyünü çektiği anda crawler'ın arka planda bilanço/
        # gelir tablosu çekmesi yüzünden kullanıcının TEK istekli toplu fiyat çağrısı bile
        # 429 (rate limit) hatası alıyordu. Crawler düşük öncelikli bir zenginleştirme
        # görevi — canlı kullanıcı deneyimini ASLA aç bırakmamalı, bu yüzden çok daha yavaş.
        self.api_delay = 10.0  # dakikada en fazla ~6 çağrı — kotanın büyük kısmı canlı istekler için kalır
        self.registered_symbols: dict[str, str] = {}  # sym → asset_class
        # ETF'ler/fonlar için "statistics" 403/404 ile kalıcı olarak başarısız olur, ama başarısızlık
        # DB'ye yazılmadığından _is_stale() hep True döner ve crawler her 5sn'lik boş-kuyruk taramasında
        # aynı sembolü sonsuza dek yeniden dener — API kotasını tüketip gerçek kullanıcı isteklerini
        # (örn. korelasyon matrisi) aç bırakır. Bu sembolleri süreç ömrü boyunca hafızada işaretleyip atla.
        self._fundamentals_unavailable: set[str] = set()
        # Hangi semboller için Redis'teki "fundamentals_unavailable" bayrağı bu süreç
        # ömründe ZATEN kontrol edildi — bkz. _supports_fundamentals'taki kritik not.
        self._fundamentals_redis_checked: set[str] = set()

    def _supports_fundamentals(self, sym: str) -> bool:
        """Twelve Data fundamentals (statistics, balance, profile) only work for US stocks."""
        if "/" in sym or ":" in sym:
            return False
        if sym in self._fundamentals_unavailable:
            return False
        ac = self.registered_symbols.get(sym, "")
        if ac in ("BIST Hissesi", "Kripto"):
            return False
        # KRİTİK: bu fonksiyon, boş-kuyruk tarandığında HER 5 SANİYEDE BİR, kayıtlı HER
        # sembol için çağrılıyor (_crawl_symbol_stale_data). Redis kontrolünü (aşağıda)
        # her çağrıda yapmak — "fundamentals destekleniyor" olan (yani hiç unavailable
        # olmayan) semboller için bile — günde yüz binlerce gereksiz Redis isteğine yol
        # açtı ve Upstash'in aylık kotasını (500.000) birkaç güne tüketti (canlıda
        # ResponseError: max requests limit exceeded olarak gözlemlendi). Artık Redis'e
        # süreç ömrü boyunca sembol başına SADECE BİR KEZ soruluyor.
        if sym not in self._fundamentals_redis_checked:
            self._fundamentals_redis_checked.add(sym)
            # Railway gibi ephemeral disk'li ortamlarda her redeploy süreç belleğini
            # sıfırlıyor — bu Redis kontrolü, ETF/fon gibi fundamentals'ı hiç olmayan
            # sembollerin HER deploy sonrası yeniden keşfedilmesini (onlarca başarısız
            # API çağrısını) önlemek için var.
            if _fc.get(f"td_fund_unavail:{sym}", _fc.TTL_FINANCIALS):
                self._fundamentals_unavailable.add(sym)
                return False
        return True

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logging.info("TwelveDataCrawler started.")
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
            logging.info("TwelveDataCrawler stopped.")
            
    def register_symbols(self, symbols: list[str], asset_classes: dict[str, str] | None = None):
        """Yeni sembolleri crawler listesine ekler. asset_classes: {original_sym → asset_class}"""
        for s in symbols:
            clean = _clean_symbol(s)
            ac = (asset_classes or {}).get(s, "")
            if clean and clean not in self.registered_symbols:
                self.registered_symbols[clean] = ac
                self.queue.put((clean, "all"))
                logging.info("[CRAWLER] Registered symbol for background crawl: %s (%s)", clean, ac or "US")
                
    def register_symbol(self, symbol: str, asset_class: str = ""):
        """Tek sembol kaydet (asset_class ile birlikte)."""
        self.register_symbols([symbol], {symbol: asset_class})

    def trigger_priority_fetch(self, symbol: str, target: str = "all"):
        """Kullanıcının anlık tıkladığı bir sembolü en öncelikli şekilde sıraya sokar."""
        clean = _clean_symbol(symbol)
        if clean:
            self.queue.put((clean, target))
            logging.info("[CRAWLER] Priority fetch queued for %s (%s)", clean, target)
            
    def _enforce_delay(self):
        """API istekleri arasına 1.3 saniye gecikme koyar, limit aşımını %100 önler."""
        now = time.monotonic()
        elapsed = now - self.last_api_call
        if elapsed < self.api_delay:
            time.sleep(self.api_delay - elapsed)
        self.last_api_call = time.monotonic()
        
    def _run_loop(self):
        # Deploy sonrası ilk saniyelerde uygulama az önce trafik almaya başlar — crawler'ın
        # hemen aynı anda API çağrısı bombardımanına başlaması, paylaşılan rate-limit kotasını
        # gerçek kullanıcı isteklerinden (örn. portföy fiyat çekme) önce tüketip onları dakikalarca
        # bekletiyordu (canlıda ölçüldü: 3+ dakika). İlk kullanıcı isteklerine öncelik vermek için
        # kısa bir bekleme payı.
        time.sleep(45)
        while self.running:
            try:
                try:
                    symbol, target = self.queue.get(timeout=5)
                except queue.Empty:
                    # Kuyruk boşsa, kayıtlı tüm sembolleri tekrar gözden geçir (stale olanları tara)
                    if self.registered_symbols:
                        for sym in list(self.registered_symbols):
                            if not self.running:
                                break
                            self._crawl_symbol_stale_data(sym)
                            time.sleep(1)
                    continue
                
                # Görevi işle
                self._process_task(symbol, target)
                self.queue.task_done()
                
            except Exception as e:
                logging.error("[CRAWLER] Error in loop: %s", e)
                time.sleep(5)
                
    def _crawl_symbol_stale_data(self, sym: str):
        """Sembolün veritabanındaki verilerini kontrol eder, stale olanları sıraya alır."""
        if self._is_stale("td_quotes", sym, TTL_QUOTE):
            self._process_task(sym, "quote")
        if self._is_stale("td_news", sym, TTL_NEWS):
            self._process_task(sym, "news")
        if self._supports_fundamentals(sym):
            if self._is_stale("td_profiles", sym, TTL_PROFILE):
                self._process_task(sym, "profile")
            if self._is_stale("td_statistics", sym, TTL_STATISTICS):
                self._process_task(sym, "statistics")
            if self._is_stale("td_balance_sheet", sym, TTL_BALANCE):
                self._process_task(sym, "balance")
            if self._is_stale("td_income_statements", sym, TTL_BALANCE):
                self._process_task(sym, "income")
            if self._is_stale("td_cash_flows", sym, TTL_BALANCE):
                self._process_task(sym, "cashflow")
            if self._is_stale("td_executives", sym, TTL_EXECUTIVES):
                self._process_task(sym, "executives")
            
            # Yeni tabloların stale kontrolü
            if self._is_stale("td_logos", sym, TTL_LOGO):
                self._process_task(sym, "logo")
            if self._is_stale("td_dividends", sym, TTL_DIVIDENDS):
                self._process_task(sym, "dividends")
            if self._is_stale("td_splits", sym, TTL_SPLITS):
                self._process_task(sym, "splits")
            if self._is_stale("td_price_targets", sym, TTL_TARGET):
                self._process_task(sym, "price_target")
            if self._is_stale("td_recommendations", sym, TTL_RECOMMENDATION):
                self._process_task(sym, "recommendations")
            if self._is_stale("td_insider_transactions", sym, TTL_INSIDERS):
                self._process_task(sym, "insider")
            if self._is_stale("td_institutional_holders", sym, TTL_HOLDERS):
                self._process_task(sym, "institutional")
            if self._is_stale("td_fund_holders", sym, TTL_HOLDERS):
                self._process_task(sym, "fund_holder")
            
    def _is_stale(self, table: str, symbol: str, ttl: float) -> bool:
        try:
            with _db_lock:
                c = _conn()
                row = c.execute(f"SELECT MAX(fetched_at) fa FROM {table} WHERE symbol=?", (symbol,)).fetchone()
                c.close()
            if not row or not row["fa"]:
                return True
            return not _fresh(row["fa"], ttl)
        except Exception:
            return True
            
    def _process_task(self, symbol: str, target: str):
        if not self.running:
            return
            
        logging.info("[CRAWLER] Processing task: fetch %s for %s", target, symbol)
        
        fundamentals_ok = self._supports_fundamentals(symbol)
        try:
            if target in ("all", "quote"):
                self._enforce_delay()
                get_quote(symbol)

            if target in ("all", "news"):
                self._enforce_delay()
                get_news(symbol)

            if fundamentals_ok:
                if target in ("all", "profile"):
                    self._enforce_delay()
                    get_profile(symbol)

                if target in ("all", "statistics"):
                    self._enforce_delay()
                    stats_result = get_statistics(symbol)
                    if not stats_result:
                        # ETF/fon gibi fundamentals'ı olmayan bir sembol — bir daha deneme.
                        # Redis'e de yazılıyor ki redeploy sonrası süreç belleği sıfırlansa bile
                        # bu bilgi kalıcı kalsın (bkz. _supports_fundamentals'taki not).
                        self._fundamentals_unavailable.add(symbol)
                        _fc.set(f"td_fund_unavail:{symbol}", True)

                if target in ("all", "balance"):
                    self._enforce_delay()
                    get_balance_sheet(symbol)

                if target in ("all", "income"):
                    self._enforce_delay()
                    get_income_statement(symbol)

                if target in ("all", "cashflow"):
                    self._enforce_delay()
                    get_cash_flow(symbol)

                if target in ("all", "executives"):
                    self._enforce_delay()
                    get_executives(symbol)
                    
                # Yeni veriler için fetch işlemleri
                if target in ("all", "logo"):
                    self._enforce_delay()
                    get_logo(symbol)
                    
                if target in ("all", "dividends"):
                    self._enforce_delay()
                    get_dividends(symbol)
                    
                if target in ("all", "splits"):
                    self._enforce_delay()
                    get_splits(symbol)
                    
                if target in ("all", "price_target"):
                    self._enforce_delay()
                    get_price_target(symbol)
                    
                if target in ("all", "recommendations"):
                    self._enforce_delay()
                    get_recommendations(symbol)
                    
                if target in ("all", "insider"):
                    self._enforce_delay()
                    get_insider_transactions(symbol)
                    
                if target in ("all", "institutional"):
                    self._enforce_delay()
                    get_institutional_holders(symbol)
                    
                if target in ("all", "fund_holder"):
                    self._enforce_delay()
                    get_fund_holders(symbol)

            if target == "all":
                self._enforce_delay()
                get_rsi(symbol, 14, "1day", 60)
                self._enforce_delay()
                get_macd(symbol, "1day", 60)
                self._enforce_delay()
                get_time_series(symbol, 365, "1day")

        except Exception as e:
            logging.error("[CRAWLER] Fetch failed for %s (%s): %s", symbol, target, e)

# Global Crawler Instance
crawler = TwelveDataCrawler()


# ── Tip dönüşüm yardımcıları ─────────────────────────────────────────────────
def _f(v: Any) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None

def _i(v: Any) -> Optional[int]:
    try:
        return int(float(v)) if v not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


# ── DB Başlatma ───────────────────────────────────────────────────────────────
init_db()


# ═══════════════════════════════════════════════════════════════════════════
# 11. GELİR TABLOSU & NAKİT AKIŞ TABLOSU (MCP için)
# ═══════════════════════════════════════════════════════════════════════════

def get_income_statement(symbol: str) -> dict:
    """Son 4 çeyreklik gelir tablosu. 30 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return {}
    with _db_lock:
        c = _conn()
        meta = c.execute(
            "SELECT MAX(fetched_at) fa FROM td_income_statements WHERE symbol=?", (sym,)
        ).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_BALANCE):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT fiscal_date,period,sales,net_income,ebitda,op_income,gross_profit,raw_json "
                "FROM td_income_statements WHERE symbol=? ORDER BY fiscal_date DESC LIMIT 4", (sym,)
            ).fetchall()
            c.close()
        if rows:
            return {
                "meta": {"symbol": symbol.upper(), "period": rows[0]["period"]},
                "income_statement": [json.loads(r["raw_json"]) for r in rows]
            }

    raw = _api("income_statement", {"symbol": sym, "outputsize": 4}, timeout=20)
    if not raw or "income_statement" not in raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            df = ticker.quarterly_income_stmt
            if df is not None and not df.empty:
                ts = _now()
                with _db_lock:
                    c = _conn()
                    for col in df.columns[:4]:
                        fiscal_date = str(col)[:10]
                        col_data = df[col].to_dict()
                        # yfinance'in quarterly_income_stmt DataFrame'i satır etiketlerini boşluklu
                        # Title Case kullanır (örn. "Total Revenue"), bitişik-yazım anahtarlar hiç eşleşmiyordu.
                        sales = col_data.get("Total Revenue") or col_data.get("Operating Revenue") or col_data.get("TotalRevenue")
                        net_inc = col_data.get("Net Income") or col_data.get("NetIncome")
                        ebitda = col_data.get("EBITDA") or col_data.get("Normalized EBITDA")
                        op_inc = col_data.get("Operating Income") or col_data.get("OperatingIncome")
                        gross_prof = col_data.get("Gross Profit") or col_data.get("GrossProfit")
                        row = {
                            "fiscal_date": fiscal_date,
                            "period":      "Quarterly",
                            "sales":        _f(sales),
                            "net_income":   _f(net_inc),
                            "ebitda":       _f(ebitda),
                            "op_income":    _f(op_inc),
                            "gross_profit": _f(gross_prof),
                            "raw_json":     json.dumps(col_data),
                            "fetched_at":   ts,
                        }
                        c.execute("""
                            INSERT OR REPLACE INTO td_income_statements
                            (symbol,fiscal_date,period,sales,net_income,ebitda,op_income,gross_profit,raw_json,fetched_at)
                            VALUES (:sym,:fiscal_date,:period,:sales,:net_income,:ebitda,:op_income,:gross_profit,:raw_json,:fetched_at)
                        """, {"sym": sym, **row})
                    c.commit()
                    c.close()
                return get_income_statement(symbol)
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Income statement fetch failed for %s: %s", sym, e)
        return {}
    items = raw.get("income_statement", [])
    ts = _now()
    with _db_lock:
        c = _conn()
        for item in items:
            row = {
                "fiscal_date": item.get("fiscal_date", ""),
                "period":      raw.get("meta", {}).get("period", "Annual"),
                "sales":        _f(item.get("sales") or item.get("revenue")),
                "net_income":   _f(item.get("net_income")),
                "ebitda":       _f(item.get("ebitda")),
                "op_income":    _f(item.get("operating_income")),
                "gross_profit": _f(item.get("gross_profit")),
                "raw_json":     json.dumps(item),
                "fetched_at":   ts,
            }
            c.execute("""
                INSERT OR REPLACE INTO td_income_statements
                (symbol,fiscal_date,period,sales,net_income,ebitda,op_income,gross_profit,raw_json,fetched_at)
                VALUES (:sym,:fiscal_date,:period,:sales,:net_income,:ebitda,:op_income,:gross_profit,:raw_json,:fetched_at)
            """, {"sym": sym, **row})
        c.commit()
        c.close()
    return raw


def get_cash_flow(symbol: str) -> dict:
    """Son 4 çeyreklik nakit akış tablosu. 30 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return {}
    with _db_lock:
        c = _conn()
        meta = c.execute(
            "SELECT MAX(fetched_at) fa FROM td_cash_flows WHERE symbol=?", (sym,)
        ).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_BALANCE):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT fiscal_date,period,op_cashflow,free_cashflow,raw_json "
                "FROM td_cash_flows WHERE symbol=? ORDER BY fiscal_date DESC LIMIT 4", (sym,)
            ).fetchall()
            c.close()
        if rows:
            return {
                "meta": {"symbol": symbol.upper(), "period": rows[0]["period"]},
                "cash_flow": [json.loads(r["raw_json"]) for r in rows]
            }

    raw = _api("cash_flow", {"symbol": sym, "outputsize": 4}, timeout=20)
    if not raw or "cash_flow" not in raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            df = ticker.quarterly_cashflow
            if df is not None and not df.empty:
                ts = _now()
                with _db_lock:
                    c = _conn()
                    for col in df.columns[:4]:
                        fiscal_date = str(col)[:10]
                        col_data = df[col].to_dict()
                        # yfinance'in quarterly_cashflow DataFrame'i satır etiketlerini boşluklu
                        # Title Case kullanır (örn. "Operating Cash Flow"), bitişik-yazım anahtarlar hiç eşleşmiyordu.
                        op_cf = col_data.get("Operating Cash Flow") or col_data.get("Cash Flow From Continuing Operating Activities") or col_data.get("OperatingCashFlow")
                        free_cf = col_data.get("Free Cash Flow") or col_data.get("FreeCashFlow")
                        row = {
                            "fiscal_date": fiscal_date,
                            "period":      "Quarterly",
                            "op_cashflow":  _f(op_cf),
                            "free_cashflow": _f(free_cf),
                            "raw_json":     json.dumps(col_data),
                            "fetched_at":   ts,
                        }
                        c.execute("""
                            INSERT OR REPLACE INTO td_cash_flows
                            (symbol,fiscal_date,period,op_cashflow,free_cashflow,raw_json,fetched_at)
                            VALUES (:sym,:fiscal_date,:period,:op_cashflow,:free_cashflow,:raw_json,:fetched_at)
                        """, {"sym": sym, **row})
                    c.commit()
                    c.close()
                return get_cash_flow(symbol)
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Cash flow fetch failed for %s: %s", sym, e)
        return {}
    items = raw.get("balance_sheet", [])
    ts = _now()
    with _db_lock:
        c = _conn()
        for item in items:
            row = {
                "fiscal_date": item.get("fiscal_date", ""),
                "period":      raw.get("meta", {}).get("period", "Annual"),
                "op_cashflow":  _f(item.get("operating_cash_flow") or item.get("cash_flow_from_operating_activities")),
                "free_cashflow": _f(item.get("free_cash_flow")),
                "raw_json":     json.dumps(item),
                "fetched_at":   ts,
            }
            c.execute("""
                INSERT OR REPLACE INTO td_cash_flows
                (symbol,fiscal_date,period,op_cashflow,free_cashflow,raw_json,fetched_at)
                VALUES (:sym,:fiscal_date,:period,:op_cashflow,:free_cashflow,:raw_json,:fetched_at)
            """, {"sym": sym, **row})
        c.commit()
        c.close()
    return raw


# ═══════════════════════════════════════════════════════════════════════════
# 12. YENİ BİLGİ VE ANALİZ SERVİSLERİ
# ═══════════════════════════════════════════════════════════════════════════

def get_logo(symbol: str) -> Optional[str]:
    """Şirket logosu URL'sini döner. 30 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return None
    with _db_lock:
        c = _conn()
        row = c.execute("SELECT logo_url, fetched_at FROM td_logos WHERE symbol=?", (sym,)).fetchone()
        c.close()
    if row and _fresh(row["fetched_at"], TTL_LOGO):
        return row["logo_url"]

    raw = _api("logo", {"symbol": sym})
    if not raw or "url" not in raw:
        return None
    logo_url = raw["url"]
    with _db_lock:
        c = _conn()
        c.execute("INSERT OR REPLACE INTO td_logos (symbol, logo_url, fetched_at) VALUES (?, ?, ?)",
                  (sym, logo_url, _now()))
        c.commit()
        c.close()
    return logo_url


def get_dividends(symbol: str) -> list[dict]:
    """Şirket temettü geçmişini döner. 7 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return []
    with _db_lock:
        c = _conn()
        meta = c.execute("SELECT MAX(fetched_at) fa FROM td_dividends WHERE symbol=?", (sym,)).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_DIVIDENDS):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT date, amount, frequency, description FROM td_dividends "
                "WHERE symbol=? ORDER BY date DESC", (sym,)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    raw = _api("dividends", {"symbol": sym})
    if not raw or not isinstance(raw, dict) or "dividends" not in raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                ts = _now()
                rows = []
                results = []
                for dt_index, val in divs.items():
                    dt_str = str(dt_index)[:10]
                    rows.append((sym, dt_str, float(val), 1, "Quarterly", ts))
                    results.append({"date": dt_str, "amount": float(val), "frequency": 1, "description": "Quarterly"})
                with _db_lock:
                    c = _conn()
                    c.executemany("INSERT OR REPLACE INTO td_dividends (symbol, date, amount, frequency, description, fetched_at) VALUES (?, ?, ?, ?, ?, ?)", rows)
                    c.commit()
                    c.close()
                return results
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Dividends fetch failed for %s: %s", sym, e)
        return []
    items = raw.get("dividends", [])
    ts = _now()
    # Twelve Data'nın gerçek yanıt anahtarı "ex_date" — "date" değil (bkz. canlı yanıt
    # örneği: {"ex_date": "2026-05-11", "amount": 0.27}, frequency/description alanları
    # hiç dönmüyor). Eskiden burada "date" okunuyordu, bu da her zaman None'a düşüp
    # td_dividends tablosuna tarihsiz kayıt yazıyordu — temettü takvimi gibi tarihe
    # dayalı hiçbir özellik bu veriyle çalışamazdı.
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_dividends (symbol, date, amount, frequency, description, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [(sym, i.get("ex_date"), _f(i.get("amount")), _i(i.get("frequency")), i.get("description"), ts)
              for i in items])
        c.commit()
        c.close()
    return [{"date": i.get("ex_date"), "amount": _f(i.get("amount")),
             "frequency": _i(i.get("frequency")), "description": i.get("description")} for i in items]


def get_splits(symbol: str) -> list[dict]:
    """Hisse bölünme geçmişini döner. 30 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return []
    with _db_lock:
        c = _conn()
        meta = c.execute("SELECT MAX(fetched_at) fa FROM td_splits WHERE symbol=?", (sym,)).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_SPLITS):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT date, from_factor, to_factor FROM td_splits "
                "WHERE symbol=? ORDER BY date DESC", (sym,)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    raw = _api("splits", {"symbol": sym})
    if not raw or not isinstance(raw, dict) or "splits" not in raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            splits = ticker.splits
            if splits is not None and not splits.empty:
                ts = _now()
                rows = []
                results = []
                for dt_index, val in splits.items():
                    dt_str = str(dt_index)[:10]
                    val_float = float(val)
                    if val_float > 0:
                        if val_float >= 1.0:
                            to_factor = val_float
                            from_factor = 1.0
                        else:
                            to_factor = 1.0
                            from_factor = 1.0 / val_float
                    else:
                        to_factor = 1.0
                        from_factor = 1.0
                    rows.append((sym, dt_str, from_factor, to_factor, ts))
                    results.append({"date": dt_str, "from_factor": from_factor, "to_factor": to_factor})
                with _db_lock:
                    c = _conn()
                    c.executemany("INSERT OR REPLACE INTO td_splits (symbol, date, from_factor, to_factor, fetched_at) VALUES (?, ?, ?, ?, ?)", rows)
                    c.commit()
                    c.close()
                return results
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Splits fetch failed for %s: %s", sym, e)
        return []
    items = raw.get("splits", [])
    ts = _now()
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_splits (symbol, date, from_factor, to_factor, fetched_at)
            VALUES (?, ?, ?, ?, ?)
        """, [(sym, i.get("date"), _f(i.get("from_factor")), _f(i.get("to_factor")), ts)
              for i in items])
        c.commit()
        c.close()
    return [{"date": i.get("date"), "from_factor": _f(i.get("from_factor")),
             "to_factor": _f(i.get("to_factor"))} for i in items]


def get_price_target(symbol: str) -> Optional[dict]:
    """Analist hedef fiyat tahminlerini döner. 7 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return None
    with _db_lock:
        c = _conn()
        row = c.execute("SELECT low, median, high, current, fetched_at FROM td_price_targets WHERE symbol=?", (sym,)).fetchone()
        c.close()
    if row and _fresh(row["fetched_at"], TTL_TARGET):
        return {"low": row["low"], "median": row["median"], "high": row["high"], "current": row["current"]}

    raw = _api("price_target", {"symbol": sym})
    if not raw or not isinstance(raw, dict) or "price_target" not in raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            info = ticker.info
            if info and "targetMeanPrice" in info:
                data = {
                    "symbol": sym, "fetched_at": _now(),
                    "low": _f(info.get("targetLowPrice")), "median": _f(info.get("targetMedianPrice")),
                    "high": _f(info.get("targetHighPrice")), "current": _f(info.get("targetMeanPrice"))
                }
                with _db_lock:
                    c = _conn()
                    c.execute("""
                        INSERT OR REPLACE INTO td_price_targets (symbol, low, median, high, current, fetched_at)
                        VALUES (:symbol, :low, :median, :high, :current, :fetched_at)
                    """, data)
                    c.commit()
                    c.close()
                return {"low": data["low"], "median": data["median"], "high": data["high"], "current": data["current"]}
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Price target fetch failed for %s: %s", sym, e)
        return None
    pt = raw["price_target"]
    data = {
        "symbol": sym, "fetched_at": _now(),
        "low": _f(pt.get("low")), "median": _f(pt.get("median")),
        "high": _f(pt.get("high")), "current": _f(pt.get("current"))
    }
    with _db_lock:
        c = _conn()
        c.execute("""
            INSERT OR REPLACE INTO td_price_targets (symbol, low, median, high, current, fetched_at)
            VALUES (:symbol, :low, :median, :high, :current, :fetched_at)
        """, data)
        c.commit()
        c.close()
    return {"low": data["low"], "median": data["median"], "high": data["high"], "current": data["current"]}


def get_recommendations(symbol: str) -> Optional[dict]:
    """Analist alım/satım tavsiyelerini döner. 3 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return None
    with _db_lock:
        c = _conn()
        row = c.execute("SELECT strong_buy, buy, hold, sell, strong_sell, rating, rating_text, fetched_at FROM td_recommendations WHERE symbol=?", (sym,)).fetchone()
        c.close()
    if row and _fresh(row["fetched_at"], TTL_RECOMMENDATION):
        return {
            "strong_buy": row["strong_buy"], "buy": row["buy"], "hold": row["hold"],
            "sell": row["sell"], "strong_sell": row["strong_sell"],
            "rating": row["rating"], "rating_text": row["rating_text"]
        }

    raw = _api("recommendations", {"symbol": sym})
    if not raw or not isinstance(raw, dict) or "rating" not in raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            info = ticker.info
            if info and "recommendationMean" in info:
                rating_val = _f(info.get("recommendationMean"))
                key = str(info.get("recommendationKey") or "")
                
                # Format key to human readable text
                rating_text = ""
                if "strong_buy" in key or key == "strong buy": rating_text = "Strong Buy"
                elif "buy" in key: rating_text = "Buy"
                elif "hold" in key: rating_text = "Hold"
                elif "sell" in key: rating_text = "Sell"
                elif "strong_sell" in key or key == "strong sell": rating_text = "Strong Sell"
                else: rating_text = key.replace("_", " ").title()
                
                data = {
                    "symbol": sym, "fetched_at": _now(),
                    "strong_buy": None, "buy": None, "hold": None, "sell": None, "strong_sell": None,
                    "rating": rating_val, "rating_text": rating_text
                }
                with _db_lock:
                    c = _conn()
                    c.execute("""
                        INSERT OR REPLACE INTO td_recommendations (symbol, strong_buy, buy, hold, sell, strong_sell, rating, rating_text, fetched_at)
                        VALUES (:symbol, :strong_buy, :buy, :hold, :sell, :strong_sell, :rating, :rating_text, :fetched_at)
                    """, data)
                    c.commit()
                    c.close()
                return {
                    "strong_buy": data["strong_buy"], "buy": data["buy"], "hold": data["hold"],
                    "sell": data["sell"], "strong_sell": data["strong_sell"],
                    "rating": data["rating"], "rating_text": data["rating_text"]
                }
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Recommendations fetch failed for %s: %s", sym, e)
        return None
    
    trends_list = raw.get("trends")
    if isinstance(trends_list, list) and trends_list:
        trends = trends_list[0]
    elif isinstance(trends_list, dict):
        trends = trends_list
    else:
        trends = {}
        
    rating = raw.get("rating")
    rating_val = None
    rating_text = ""
    if isinstance(rating, dict):
        rating_val = _f(rating.get("decimal"))
        rating_text = rating.get("text") or ""
    elif isinstance(rating, (int, float)):
        rating_val = _f(rating)
        if rating_val is not None:
            if rating_val < 1.5: rating_text = "Strong Buy"
            elif rating_val < 2.5: rating_text = "Buy"
            elif rating_val < 3.5: rating_text = "Hold"
            elif rating_val < 4.5: rating_text = "Sell"
            else: rating_text = "Strong Sell"
    elif isinstance(rating, str):
        try:
            rating_val = float(rating)
            if rating_val < 1.5: rating_text = "Strong Buy"
            elif rating_val < 2.5: rating_text = "Buy"
            elif rating_val < 3.5: rating_text = "Hold"
            elif rating_val < 4.5: rating_text = "Sell"
            else: rating_text = "Strong Sell"
        except ValueError:
            rating_text = rating

    data = {
        "symbol": sym, "fetched_at": _now(),
        "strong_buy": _i(trends.get("strong_buy")), "buy": _i(trends.get("buy")),
        "hold": _i(trends.get("hold")), "sell": _i(trends.get("sell")),
        "strong_sell": _i(trends.get("strong_sell")),
        "rating": rating_val, "rating_text": rating_text
    }
    with _db_lock:
        c = _conn()
        c.execute("""
            INSERT OR REPLACE INTO td_recommendations (symbol, strong_buy, buy, hold, sell, strong_sell, rating, rating_text, fetched_at)
            VALUES (:symbol, :strong_buy, :buy, :hold, :sell, :strong_sell, :rating, :rating_text, :fetched_at)
        """, data)
        c.commit()
        c.close()
    return {
        "strong_buy": data["strong_buy"], "buy": data["buy"], "hold": data["hold"],
        "sell": data["sell"], "strong_sell": data["strong_sell"],
        "rating": data["rating"], "rating_text": data["rating_text"]
    }


def get_insider_transactions(symbol: str) -> list[dict]:
    """İçeriden yapılan alım/satım işlemlerini döner. 7 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return []
    with _db_lock:
        c = _conn()
        meta = c.execute("SELECT MAX(fetched_at) fa FROM td_insider_transactions WHERE symbol=?", (sym,)).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_INSIDERS):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT date, share_class, owner_name, relation, transaction_type, shares, price, value, shares_held_after, raw_json "
                "FROM td_insider_transactions WHERE symbol=? ORDER BY date DESC", (sym,)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    raw = _api("insider_transactions", {"symbol": sym})
    if not raw or not isinstance(raw, dict) or "insider_transactions" not in raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            df = ticker.insider_transactions
            if df is not None and not df.empty:
                ts = _now()
                rows = []
                results = []
                for idx, r in df.iterrows():
                    dt_str = str(r.get("Start Date") or r.get("Transaction Date") or "")[:10]
                    if not dt_str or dt_str == "NaT":
                        dt_str = date.today().isoformat()
                    shares = _i(r.get("Shares"))
                    value = _f(r.get("Value"))
                    owner = str(r.get("Text") or r.get("Owner") or "Insider")
                    
                    # Convert pandas Timestamps to strings in dict
                    raw_dict = {}
                    for k, v in r.to_dict().items():
                        if hasattr(v, "isoformat"):
                            raw_dict[k] = v.isoformat()
                        else:
                            raw_dict[k] = v
                            
                    row = {
                        "symbol": sym, "date": dt_str, "share_class": "Common",
                        "owner_name": owner, "relation": "Officer/Director",
                        "transaction_type": "Buy" if (shares and shares > 0) else "Sell",
                        "shares": abs(shares) if shares else 0, "price": (value / abs(shares)) if (value and shares) else 0.0,
                        "value": value or 0.0, "shares_held_after": 0, "raw_json": json.dumps(raw_dict),
                        "fetched_at": ts
                    }
                    rows.append((row["symbol"], row["date"], row["share_class"], row["owner_name"], row["relation"],
                                 row["transaction_type"], row["shares"], row["price"], row["value"],
                                 row["shares_held_after"], row["raw_json"], row["fetched_at"]))
                    results.append({
                        "date": row["date"], "share_class": row["share_class"], "owner_name": row["owner_name"],
                        "relation": row["relation"], "transaction_type": row["transaction_type"],
                        "shares": row["shares"], "price": row["price"], "value": row["value"],
                        "shares_held_after": row["shares_held_after"]
                    })
                with _db_lock:
                    c = _conn()
                    c.executemany("""
                        INSERT OR REPLACE INTO td_insider_transactions
                        (symbol, date, share_class, owner_name, relation, transaction_type, shares, price, value, shares_held_after, raw_json, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, rows)
                    c.commit()
                    c.close()
                return results
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Insider transactions fetch failed for %s: %s", sym, e)
        return []
    items = raw.get("insider_transactions") or []
    ts = _now()
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_insider_transactions
            (symbol, date, share_class, owner_name, relation, transaction_type, shares, price, value, shares_held_after, raw_json, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [(sym, i.get("date"), i.get("share_class"), i.get("owner_name"), i.get("relation"),
               i.get("transaction_type"), _i(i.get("shares")), _f(i.get("price")), _f(i.get("value")),
               _i(i.get("shares_held_after")), json.dumps(i), ts)
              for i in items if isinstance(i, dict)])
        c.commit()
        c.close()
    return [{"date": i.get("date"), "share_class": i.get("share_class"), "owner_name": i.get("owner_name"),
             "relation": i.get("relation"), "transaction_type": i.get("transaction_type"),
             "shares": _i(i.get("shares")), "price": _f(i.get("price")), "value": _f(i.get("value")),
             "shares_held_after": _i(i.get("shares_held_after"))} for i in items if isinstance(i, dict)]


def get_institutional_holders(symbol: str) -> list[dict]:
    """Kurumsal hissedarları döner. 15 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return []
    with _db_lock:
        c = _conn()
        meta = c.execute("SELECT MAX(fetched_at) fa FROM td_institutional_holders WHERE symbol=?", (sym,)).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_HOLDERS):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT entity_name, date, shares, value, pct_held, change, change_pct, raw_json "
                "FROM td_institutional_holders WHERE symbol=?", (sym,)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    raw = _api("institutional_holders", {"symbol": sym})
    if not raw or not isinstance(raw, dict) or "institutional_holders" not in raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            df = ticker.institutional_holders
            if df is not None and not df.empty:
                ts = _now()
                rows = []
                results = []
                for idx, r in df.iterrows():
                    dt_str = str(r.get("Date Reported") or "")[:10]
                    if not dt_str or dt_str == "NaT":
                        dt_str = date.today().isoformat()
                    entity = str(r.get("Holder") or "Institution")
                    shares = _i(r.get("Shares"))
                    val = _f(r.get("Value"))
                    pct = _f(r.get("pctChange"))
                    
                    # Convert pandas Timestamps to strings in dict
                    raw_dict = {}
                    for k, v in r.to_dict().items():
                        if hasattr(v, "isoformat"):
                            raw_dict[k] = v.isoformat()
                        else:
                            raw_dict[k] = v
                            
                    row = {
                        "symbol": sym, "entity_name": entity, "date": dt_str,
                        "shares": shares or 0, "value": val or 0.0, "pct_held": pct or 0.0,
                        "change": 0, "change_pct": pct or 0.0, "raw_json": json.dumps(raw_dict),
                        "fetched_at": ts
                    }
                    rows.append((row["symbol"], row["entity_name"], row["date"], row["shares"], row["value"],
                                 row["pct_held"], row["change"], row["change_pct"], row["raw_json"], row["fetched_at"]))
                    results.append({
                        "entity_name": row["entity_name"], "date": row["date"], "shares": row["shares"],
                        "value": row["value"], "pct_held": row["pct_held"], "change": row["change"],
                        "change_pct": row["change_pct"]
                    })
                with _db_lock:
                    c = _conn()
                    c.executemany("""
                        INSERT OR REPLACE INTO td_institutional_holders
                        (symbol, entity_name, date, shares, value, pct_held, change, change_pct, raw_json, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, rows)
                    c.commit()
                    c.close()
                return results
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Institutional holders fetch failed for %s: %s", sym, e)
        return []
    items = raw.get("institutional_holders") or []
    ts = _now()
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_institutional_holders
            (symbol, entity_name, date, shares, value, pct_held, change, change_pct, raw_json, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [(sym, i.get("entity_name"), i.get("date"), _i(i.get("shares")), _f(i.get("value")),
               _f(i.get("percent_held")), _i(i.get("change")), _f(i.get("change_percent")), json.dumps(i), ts)
              for i in items if isinstance(i, dict)])
        c.commit()
        c.close()
    return [{"entity_name": i.get("entity_name"), "date": i.get("date"), "shares": _i(i.get("shares")),
             "value": _f(i.get("value")), "pct_held": _f(i.get("percent_held")), "change": _i(i.get("change")),
             "change_pct": _f(i.get("change_percent"))} for i in items if isinstance(i, dict)]


def get_fund_holders(symbol: str) -> list[dict]:
    """Hissedar yatırım fonlarını döner. 15 günlük cache."""
    sym = _clean_symbol(symbol)
    if ":" in sym or "/" in sym:
        return []
    with _db_lock:
        c = _conn()
        meta = c.execute("SELECT MAX(fetched_at) fa FROM td_fund_holders WHERE symbol=?", (sym,)).fetchone()
        c.close()
    if meta and _fresh(meta["fa"], TTL_HOLDERS):
        with _db_lock:
            c = _conn()
            rows = c.execute(
                "SELECT entity_name, date, shares, value, pct_held, change, change_pct, raw_json "
                "FROM td_fund_holders WHERE symbol=?", (sym,)
            ).fetchall()
            c.close()
        return [dict(r) for r in rows]

    raw = _api("fund_holders", {"symbol": sym})
    if not raw or not isinstance(raw, dict) or "fund_holders" not in raw:
        # yfinance Fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(_yf_symbol(symbol))
            df = ticker.mutualfund_holders
            if df is not None and not df.empty:
                ts = _now()
                rows = []
                results = []
                for idx, r in df.iterrows():
                    dt_str = str(r.get("Date Reported") or "")[:10]
                    if not dt_str or dt_str == "NaT":
                        dt_str = date.today().isoformat()
                    entity = str(r.get("Holder") or "Mutual Fund")
                    shares = _i(r.get("Shares"))
                    val = _f(r.get("Value"))
                    pct = _f(r.get("pctChange"))
                    
                    # Convert pandas Timestamps to strings in dict
                    raw_dict = {}
                    for k, v in r.to_dict().items():
                        if hasattr(v, "isoformat"):
                            raw_dict[k] = v.isoformat()
                        else:
                            raw_dict[k] = v
                            
                    row = {
                        "symbol": sym, "entity_name": entity, "date": dt_str,
                        "shares": shares or 0, "value": val or 0.0, "pct_held": pct or 0.0,
                        "change": 0, "change_pct": pct or 0.0, "raw_json": json.dumps(raw_dict),
                        "fetched_at": ts
                    }
                    rows.append((row["symbol"], row["entity_name"], row["date"], row["shares"], row["value"],
                                 row["pct_held"], row["change"], row["change_pct"], row["raw_json"], row["fetched_at"]))
                    results.append({
                        "entity_name": row["entity_name"], "date": row["date"], "shares": row["shares"],
                        "value": row["value"], "pct_held": row["pct_held"], "change": row["change"],
                        "change_pct": row["change_pct"]
                    })
                with _db_lock:
                    c = _conn()
                    c.executemany("""
                        INSERT OR REPLACE INTO td_fund_holders
                        (symbol, entity_name, date, shares, value, pct_held, change, change_pct, raw_json, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, rows)
                    c.commit()
                    c.close()
                return results
        except Exception as e:
            logging.warning("[YFINANCE FALLBACK] Fund holders fetch failed for %s: %s", sym, e)
        return []
    items = raw.get("fund_holders") or []
    ts = _now()
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_fund_holders
            (symbol, entity_name, date, shares, value, pct_held, change, change_pct, raw_json, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [(sym, i.get("entity_name"), i.get("date"), _i(i.get("shares")), _f(i.get("value")),
               _f(i.get("percent_held")), _i(i.get("change")), _f(i.get("change_percent")), json.dumps(i), ts)
              for i in items if isinstance(i, dict)])
        c.commit()
        c.close()
    return [{"entity_name": i.get("entity_name"), "date": i.get("date"), "shares": _i(i.get("shares")),
             "value": _f(i.get("value")), "pct_held": _f(i.get("percent_held")), "change": _i(i.get("change")),
             "change_pct": _f(i.get("change_percent"))} for i in items if isinstance(i, dict)]


def get_market_movers(market: str, direction: str = "gainers") -> list[dict]:
    """
    Günün en çok kazandıran/kaybettirenlerini getirir.
    Plana göre /market_movers API'si 403 döndüğü için boş döner.
    """
    return []


def _fonoloji_api(path: str, params: dict | None = None, timeout: int = 10) -> dict | None:
    """Fonoloji.com TEFAS API için basit GET. Anahtar tanımlı değilse veya istek
    başarısız olursa None döner — çağıran taraf zaten pytefas'a düşüyor."""
    if not FONOLOJI_API_KEY:
        return None
    try:
        r = _req.get(
            f"{FONOLOJI_BASE_URL}{path}",
            headers={"X-API-Key": FONOLOJI_API_KEY},
            params=params or {},
            timeout=timeout,
        )
        if not r.ok:
            logging.warning("Fonoloji %s HTTP %s", path, r.status_code)
            return None
        return r.json()
    except Exception as e:
        logging.warning("Fonoloji %s exception: %s", path, e)
        return None


def _save_tefas_nav_rows(code: str, rows: list[tuple]) -> None:
    if not rows:
        return
    with _db_lock:
        c = _conn()
        c.executemany("""
            INSERT OR REPLACE INTO td_tefas_nav
            (fund_code, dt, price, shares_outstanding, investor_count, portfolio_size, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)
        c.commit()
        c.close()


def _compute_missing_ranges(db_data: dict, start_date: date, end_date: date) -> list[tuple]:
    """[start_date, end_date] aralığındaki hafta içi günlerden db_data'da olmayanları,
    ardışık aralıklar halinde döner."""
    from datetime import timedelta
    missing_ranges = []
    curr = start_date
    range_start = None
    while curr <= end_date:
        is_weekend = curr.weekday() >= 5
        date_str = curr.isoformat()
        if not is_weekend and date_str not in db_data:
            if range_start is None:
                range_start = curr
        else:
            if range_start is not None:
                missing_ranges.append((range_start, curr - timedelta(days=1)))
                range_start = None
        curr += timedelta(days=1)
    if range_start is not None:
        missing_ranges.append((range_start, end_date))
    return missing_ranges


# ═══════════════════════════════════════════════════════════════════════════
# 13. TEFAS FON VERİTABANI ÖNBELLEĞİ
# ═══════════════════════════════════════════════════════════════════════════

def get_tefas_nav(fund_code: str, start_date: date, end_date: date, live_fetch: bool = True) -> Any:
    """
    TEFAS fonunun günlük fiyat (NAV) serisini döner.
    - Önce veritabanındaki kayıtları tarar.
    - Eksik tarihler varsa önce Fonoloji API'den (bkz. FONOLOJI_API_KEY yorumu),
      hâlâ eksik kalırsa pytefas ile çeker ve veritabanına ekler (Incremental Sync).
    Returns: pandas.Series (index=DatetimeIndex normalize, values=price)

    live_fetch=False: SADECE veritabanındaki mevcut kayıtları döner, Fonoloji/pytefas'a
    ASLA ağ isteği atmaz. pytefas yolu 27 günlük parçalar halinde SENKRON scrape yapıyor
    (parça başına 6sn'ye kadar bekleme) — bu, tek bir kullanıcı isteği içinde BİRDEN FAZLA
    fon için çağrıldığında (ör. performans grafiği) isteği dakikalarca bloke edebiliyordu.
    Canlı HTTP istek yolundaki çağıranlar (services.get_ticker_historical_prices)
    live_fetch=False kullanmalı; önbellek arka planda ayrıca doldurulur (bkz.
    scheduler.py refresh_tefas_nav_cache_job)."""
    import pandas as pd
    from datetime import timedelta

    code = fund_code.upper().strip()

    # 1. Veritabanından mevcut kayıtları sorgula
    with _db_lock:
        c = _conn()
        rows = c.execute(
            "SELECT dt, price FROM td_tefas_nav WHERE fund_code=? AND dt BETWEEN ? AND ? ORDER BY dt ASC",
            (code, start_date.isoformat(), end_date.isoformat())
        ).fetchall()
        c.close()

    db_data = {r["dt"]: r["price"] for r in rows}

    missing_ranges = _compute_missing_ranges(db_data, start_date, end_date)

    # 2. Eksik varsa önce Fonoloji'den dene — tek çağrıda fonun TÜM geçmişini
    # döner (pytefas'ın aksine hızlı ve eşzamanlı isteklerde tıkanmıyor).
    if missing_ranges and FONOLOJI_API_KEY and live_fetch:
        try:
            data = _fonoloji_api(f"/funds/{code}/history", {"period": "all"})
            points = (data or {}).get("points") or []
            if points:
                ts = _now()
                db_rows = []
                for p in points:
                    dt_str = p.get("date")
                    price = p.get("price")
                    if not dt_str or price is None:
                        continue
                    db_data[dt_str] = _f(price)
                    db_rows.append((
                        code, dt_str, _f(price), None,
                        _i(p.get("investor_count")), _f(p.get("total_value")), ts
                    ))
                _save_tefas_nav_rows(code, db_rows)
                missing_ranges = _compute_missing_ranges(db_data, start_date, end_date)
        except Exception as e:
            logging.warning("[TEFAS CACHE] Fonoloji fetch failed for %s: %s", code, e)

    # 3. Fonoloji sonrası hâlâ eksik varsa pytefas ile çek ve veritabanına kaydet
    from tefas_tools import _TEFAS_OK, _crawler, _fund_kind

    if missing_ranges and _TEFAS_OK and _crawler is not None and live_fetch:
        ts = _now()
        kind = _fund_kind(code)
        
        for m_start, m_end in missing_ranges:
            try:
                c_curr = m_start
                while c_curr <= m_end:
                    c_end = min(c_curr + timedelta(days=27), m_end)

                    future = _tefas_executor.submit(
                        _crawler.fetch,
                        c_curr.isoformat(), c_end.isoformat(),
                        kind=kind, columns="info", fund_code=code
                    )
                    # TimeoutError burada yakalanmıyor — aşağıdaki dıştaki except zaten
                    # loglayıp bu fonun kalan aralıklarını atlayarak bir sonraki fona geçiyor.
                    # Arka plandaki yavaş istek pool'da kendi başına bitmeye devam eder,
                    # sonucu zaten kullanılmayacağı için beklenmiyor.
                    df = future.result(timeout=6.0)

                    if df is not None and not df.empty:
                        db_rows = []
                        for _, row in df.iterrows():
                            dt_val = row["date"]
                            if hasattr(dt_val, "strftime"):
                                dt_str = dt_val.strftime("%Y-%m-%d")
                            else:
                                dt_str = str(dt_val)[:10]
                                
                            db_rows.append((
                                code, dt_str,
                                _f(row["price"]), _f(row.get("shares_outstanding")),
                                _i(row.get("investor_count")), _f(row.get("portfolio_size")), ts
                            ))
                            db_data[dt_str] = _f(row["price"])
                            
                        if db_rows:
                            with _db_lock:
                                c = _conn()
                                c.executemany("""
                                    INSERT OR REPLACE INTO td_tefas_nav
                                    (fund_code, dt, price, shares_outstanding, investor_count, portfolio_size, fetched_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, db_rows)
                                c.commit()
                                c.close()
                                
                    c_curr = c_end + timedelta(days=1)
                    time.sleep(0.3)
            except Exception as e:
                logging.warning("[TEFAS CACHE] Fetch failed for %s: %s", code, e)
                
    if not db_data:
        return pd.Series(dtype=float)

    sorted_dates = sorted(db_data.keys())
    series = pd.Series(
        [db_data[d] for d in sorted_dates],
        index=pd.to_datetime(sorted_dates)
    )
    # Fonoloji "period=all" ile fonun TÜM geçmişini döndürüyor (db_data bu yüzden
    # istenen aralığın dışına taşabiliyor) — çağıranın istediği [start_date, end_date]
    # sözleşmesini bozmamak için burada kırpılıyor.
    return series[
        (series.index >= pd.Timestamp(start_date)) & (series.index <= pd.Timestamp(end_date))
    ]


def get_tefas_risk_score(fund_code: str) -> Optional[float]:
    """TEFAS fonunun Fonoloji üzerinden SPK/KAP resmi risk seviyesini (1-7) döner.
    Anahtar tanımlı değilse veya istek başarısız olursa None — çağıran taraf
    sabit bir varsayılana düşer."""
    data = _fonoloji_api(f"/funds/{fund_code.upper().strip()}")
    fund = (data or {}).get("fund") or {}
    risk = fund.get("risk_score")
    return float(risk) if risk is not None else None


def get_tefas_current_price(fund_code: str) -> Optional[float]:
    """TEFAS fonunun en güncel fiyatını döner. 1 günlük cache."""
    from datetime import timedelta
    code = fund_code.upper().strip()
    today = date.today()
    yesterday = today - timedelta(days=5)
    
    with _db_lock:
        c = _conn()
        row = c.execute(
            "SELECT price, fetched_at FROM td_tefas_nav WHERE fund_code=? ORDER BY dt DESC LIMIT 1",
            (code,)
        ).fetchone()
        c.close()
        
    if row and _fresh(row["fetched_at"], TTL_TEFAS_NAV):
        return row["price"]
        
    series = get_tefas_nav(code, yesterday, today)
    if not series.empty:
        return float(series.iloc[-1])

    return row["price"] if row else None


def get_tefas_indicators(fund_code: str, periods: int = 60) -> dict:
    """TEFAS fonu için RSI(14)/MACD/Bollinger Bands(20) yerel olarak NAV serisinden
    hesaplanır. Twelve Data TEFAS fonlarını tanımadığı için (get_time_series/get_indicator
    genel sembol uzayında yok) tek veri kaynağı kendi biriktirdiğimiz td_tefas_nav
    tablosudur (bkz. get_tefas_nav). Dönen şekil get_rsi/get_macd/get_bbands ile
    aynı alan adlarını kullanır (rsi / macd,macd_signal,macd_hist / upper_band,
    middle_band,lower_band) — frontend hiçbir değişiklik gerektirmeden tüketebilsin diye."""
    import pandas as pd
    from datetime import timedelta

    code = fund_code.upper().strip()
    end_date = date.today()
    # MACD(26,9) ve BBands(20) ısınma payı + istenen periyot kadar işlem günü —
    # hafta sonları/tatiller yüzünden takvim gününde bolca pay bırakılıyor.
    start_date = end_date - timedelta(days=int(periods * 2.2) + 90)
    series = get_tefas_nav(code, start_date, end_date)
    if series.empty or len(series) < 20:
        return {"rsi": [], "macd": [], "bbands": []}

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = (100 - (100 / (1 + rs))).fillna(100)

    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line

    sma20 = series.rolling(window=20).mean()
    std20 = series.rolling(window=20).std()
    upper_band = sma20 + 2 * std20
    lower_band = sma20 - 2 * std20

    def _rows(cols: dict) -> list[dict]:
        out = []
        for i in range(len(series.index) - 1, -1, -1):
            row = {"dt": series.index[i].strftime("%Y-%m-%d")}
            ok = True
            for key, s in cols.items():
                v = s.iloc[i]
                if pd.isna(v):
                    ok = False
                    break
                row[key] = round(float(v), 4)
            if ok:
                out.append(row)
            if len(out) >= periods:
                break
        return out

    return {
        "rsi": _rows({"rsi": rsi}),
        "macd": _rows({"macd": macd_line, "macd_signal": signal_line, "macd_hist": macd_hist}),
        "bbands": _rows({"upper_band": upper_band, "middle_band": sma20, "lower_band": lower_band}),
    }


def get_tefas_daily_change_pct(fund_code: str) -> Optional[float]:
    """TEFAS fonunun son iki işlem gününün NAV'ından günlük değişim yüzdesini
    hesaplar (Twelve Data quote'larındaki change_pct ile aynı birim: 2.34 = %2.34).
    Ekstra bir API çağrısı gerektirmez — get_tefas_current_price zaten td_tefas_nav
    önbelleğini doldurmuş olur, burada sadece son iki satır okunur."""
    code = fund_code.upper().strip()
    with _db_lock:
        c = _conn()
        rows = c.execute(
            "SELECT price FROM td_tefas_nav WHERE fund_code=? ORDER BY dt DESC LIMIT 2",
            (code,)
        ).fetchall()
        c.close()
    if len(rows) < 2:
        return None
    latest, prev = rows[0]["price"], rows[1]["price"]
    if not latest or not prev:
        return None
    return round((latest / prev - 1) * 100, 2)

