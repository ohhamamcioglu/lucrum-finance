# -*- coding: utf-8 -*-
"""
historical_db.py — Kalici zaman serisi veritabani

Amac:
  TTL cache'in aksine, once cekilmis veriyi sonsuza kadar saklar.
  Her ay yeni veri eklenir, eskisi korunur; boylece 3 yil sonra
  yfinance'in 4-5 yil siniriyla sinirli olmayan kendi tarihimiz olur.

Tablo tasarimi:
  financial_records : ticker basina yillik finansal kayit (JSON)
  price_snapshots   : ticker basina aylik kapаnis fiyati

Look-ahead guvenlik:
  financial_records.available_from  = fiscal_end + 4 ay
  get_historical_snapshot()         = available_from <= as_of_date kosulu
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

_HERE   = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_HERE, "historical_data.db")

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS financial_records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT    NOT NULL,
    fiscal_end     DATE    NOT NULL,
    available_from DATE    NOT NULL,
    source         TEXT    NOT NULL DEFAULT 'yfinance',
    record_json    TEXT    NOT NULL,
    fetched_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, fiscal_end, source)
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    price_date  DATE    NOT NULL,
    close_price REAL,
    source      TEXT    NOT NULL DEFAULT 'yfinance',
    fetched_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, price_date)
);

CREATE INDEX IF NOT EXISTS idx_fin_ticker  ON financial_records(ticker);
CREATE INDEX IF NOT EXISTS idx_fin_avail   ON financial_records(ticker, available_from);
CREATE INDEX IF NOT EXISTS idx_px_ticker   ON price_snapshots(ticker);
CREATE INDEX IF NOT EXISTS idx_px_date     ON price_snapshots(ticker, price_date);
"""

_LOCK = threading.Lock()


def _conn(path: str = _DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(path, check_same_thread=False, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _init(path: str = _DB_PATH) -> None:
    with _conn(path) as con:
        con.executescript(_DDL)


_init()  # modül yüklenince şemayı oluştur/doğrula


# ─────────────────────────────────────────────────────────────────────────────
# YAZMA
# ─────────────────────────────────────────────────────────────────────────────

def write_financials(ticker: str, records: list[dict],
                     source: str = "yfinance",
                     path: str = _DB_PATH) -> int:
    """
    Finansal kayıtları DB'ye yazar (UPSERT).
    records: _yf_financials() çıktısı, her dict'te fiscal_end ve available_from
    Döner: yazılan/güncellenen kayıt sayısı
    """
    if not records:
        return 0
    fetched_at = datetime.utcnow().isoformat(timespec="seconds")
    rows = []
    for r in records:
        fe = r.get("fiscal_end")
        af = r.get("available_from")
        if fe is None or af is None:
            continue
        # date nesneleri ISO string'e çevir (JSON-safe hale getir)
        serialisable = {
            k: (v.isoformat() if isinstance(v, date) else v)
            for k, v in r.items()
        }
        rows.append((
            ticker.upper(),
            fe.isoformat() if isinstance(fe, date) else str(fe),
            af.isoformat() if isinstance(af, date) else str(af),
            source,
            json.dumps(serialisable, ensure_ascii=False),
            fetched_at,
        ))
    if not rows:
        return 0
    sql = """
        INSERT INTO financial_records(ticker, fiscal_end, available_from, source, record_json, fetched_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(ticker, fiscal_end, source) DO UPDATE SET
            available_from = excluded.available_from,
            record_json    = excluded.record_json,
            fetched_at     = excluded.fetched_at
    """
    with _LOCK:
        with _conn(path) as con:
            con.executemany(sql, rows)
    return len(rows)


def write_prices(ticker: str, price_series: pd.Series,
                 source: str = "yfinance",
                 path: str = _DB_PATH) -> int:
    """
    Fiyat serisinden aylık snapshot'ları DB'ye yazar (UPSERT).
    Simülasyon aylarıyla uyumlu: her ayın 1.'si veya en yakın işlem günü.
    Tüm günlük veriler kaydedilir — daily kapanış nokta nokta.
    """
    if price_series is None or price_series.empty:
        return 0
    fetched_at = datetime.utcnow().isoformat(timespec="seconds")
    rows = []
    for ts, px in price_series.items():
        if pd.isna(px):
            continue
        rows.append((
            ticker.upper(),
            pd.Timestamp(ts).date().isoformat(),
            float(px),
            source,
            fetched_at,
        ))
    if not rows:
        return 0
    sql = """
        INSERT INTO price_snapshots(ticker, price_date, close_price, source, fetched_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(ticker, price_date) DO UPDATE SET
            close_price = excluded.close_price,
            fetched_at  = excluded.fetched_at
    """
    with _LOCK:
        with _conn(path) as con:
            con.executemany(sql, rows)
    return len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# OKUMA
# ─────────────────────────────────────────────────────────────────────────────

def load_financials(ticker: str, path: str = _DB_PATH) -> list[dict]:
    """
    Ticker'ın tüm yıllık finansal kayıtlarını DB'den yükler.
    Döner: backtest_composite._yf_financials() çıktısıyla uyumlu list[dict]
    """
    sql = """
        SELECT record_json FROM financial_records
        WHERE ticker = ? ORDER BY fiscal_end
    """
    with _conn(path) as con:
        rows = con.execute(sql, (ticker.upper(),)).fetchall()
    records = []
    for row in rows:
        try:
            d = json.loads(row["record_json"])
            # ISO string'leri date nesnesine geri çevir
            for key in ("fiscal_end", "available_from"):
                if key in d and isinstance(d[key], str):
                    try:
                        d[key] = date.fromisoformat(d[key])
                    except ValueError:
                        pass
            records.append(d)
        except Exception:
            pass
    return records


def load_prices(ticker: str,
                date_from: Optional[date] = None,
                date_to:   Optional[date] = None,
                path: str = _DB_PATH) -> pd.Series:
    """
    Ticker'ın fiyat serisini DB'den yükler.
    Döner: DatetimeIndex'li pd.Series (yfinance çıktısıyla uyumlu)
    """
    params: list = [ticker.upper()]
    where  = "WHERE ticker = ?"
    if date_from:
        where += " AND price_date >= ?"
        params.append(date_from.isoformat())
    if date_to:
        where += " AND price_date <= ?"
        params.append(date_to.isoformat())
    sql = f"SELECT price_date, close_price FROM price_snapshots {where} ORDER BY price_date"
    with _conn(path) as con:
        rows = con.execute(sql, params).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    dates  = pd.to_datetime([r["price_date"] for r in rows])
    prices = [r["close_price"] for r in rows]
    return pd.Series(prices, index=dates, dtype=float)


# ─────────────────────────────────────────────────────────────────────────────
# MEVCUT VERİ KONTROLÜ
# ─────────────────────────────────────────────────────────────────────────────

def tickers_with_financials(path: str = _DB_PATH) -> set[str]:
    with _conn(path) as con:
        rows = con.execute("SELECT DISTINCT ticker FROM financial_records").fetchall()
    return {r["ticker"] for r in rows}


def tickers_with_prices(path: str = _DB_PATH) -> set[str]:
    with _conn(path) as con:
        rows = con.execute("SELECT DISTINCT ticker FROM price_snapshots").fetchall()
    return {r["ticker"] for r in rows}


def has_price_coverage(ticker: str, from_date: date, to_date: date,
                        min_points: int = 30, path: str = _DB_PATH) -> bool:
    """
    Ticker'ın from_date–to_date arasında yeterli fiyat noktası var mı?
    min_points: genellikle 30 işlem günü (~6 hafta) yeterli kabul edilir.
    """
    sql = """
        SELECT COUNT(*) AS cnt FROM price_snapshots
        WHERE ticker = ? AND price_date BETWEEN ? AND ?
    """
    with _conn(path) as con:
        row = con.execute(sql, (ticker.upper(),
                                from_date.isoformat(),
                                to_date.isoformat())).fetchone()
    return (row["cnt"] if row else 0) >= min_points


# ─────────────────────────────────────────────────────────────────────────────
# SORGU TOOL'U (point-in-time, look-ahead safe)
# ─────────────────────────────────────────────────────────────────────────────

def get_historical_snapshot(ticker: str, as_of: date,
                             path: str = _DB_PATH) -> dict:
    """
    O tarihte GERCEKTEN bilinebilecek en son finansal veriyi + fiyatı döner.
    Look-ahead safe: sadece available_from <= as_of olan kayıtlar.

    Döner: {
        "ticker": ...,
        "as_of": ...,
        "financials": {most_recent_available_dict},  # None if none available
        "price": float | None,
        "price_6m_ago": float | None,  # momentum için
        "momentum_6m_pct": float | None,
    }
    """
    # Finansal: available_from <= as_of, en son
    sql_fin = """
        SELECT record_json FROM financial_records
        WHERE ticker = ? AND available_from <= ?
        ORDER BY fiscal_end DESC LIMIT 1
    """
    with _conn(path) as con:
        row_fin = con.execute(sql_fin, (ticker.upper(), as_of.isoformat())).fetchone()

    financials = None
    if row_fin:
        try:
            d = json.loads(row_fin["record_json"])
            for key in ("fiscal_end", "available_from"):
                if key in d and isinstance(d[key], str):
                    try:
                        d[key] = date.fromisoformat(d[key])
                    except ValueError:
                        pass
            financials = d
        except Exception:
            pass

    # Fiyat: as_of veya en yakın önceki işlem günü
    sql_px = """
        SELECT close_price FROM price_snapshots
        WHERE ticker = ? AND price_date <= ?
        ORDER BY price_date DESC LIMIT 1
    """
    # 6 ay öncesi fiyat (momentum)
    ago_6m = (date(as_of.year, as_of.month, 1) -
               timedelta(days=180)).replace(day=1)

    with _conn(path) as con:
        row_px    = con.execute(sql_px, (ticker.upper(), as_of.isoformat())).fetchone()
        row_px_6m = con.execute(sql_px, (ticker.upper(), ago_6m.isoformat())).fetchone()

    price     = row_px["close_price"]    if row_px    else None
    price_6m  = row_px_6m["close_price"] if row_px_6m else None
    momentum  = None
    if price and price_6m and price_6m != 0:
        momentum = round((price / price_6m - 1) * 100, 2)

    return {
        "ticker":         ticker.upper(),
        "as_of":          as_of.isoformat(),
        "financials":     financials,
        "price":          price,
        "price_6m_ago":   price_6m,
        "momentum_6m_pct": momentum,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ISTATISTIK
# ─────────────────────────────────────────────────────────────────────────────

def stats(path: str = _DB_PATH) -> dict:
    sql_fin = """
        SELECT COUNT(*) AS total_records,
               COUNT(DISTINCT ticker) AS tickers_fin,
               MIN(fiscal_end) AS oldest_fin,
               MAX(fiscal_end) AS newest_fin
        FROM financial_records
    """
    sql_px = """
        SELECT COUNT(*) AS total_prices,
               COUNT(DISTINCT ticker) AS tickers_px,
               MIN(price_date) AS oldest_px,
               MAX(price_date) AS newest_px
        FROM price_snapshots
    """
    with _conn(path) as con:
        fin_row = con.execute(sql_fin).fetchone()
        px_row  = con.execute(sql_px).fetchone()
    db_mb = os.path.getsize(path) / 1_048_576 if os.path.exists(path) else 0.0
    return {
        "financial_records":  dict(fin_row) if fin_row else {},
        "price_snapshots":    dict(px_row)  if px_row  else {},
        "db_size_mb":         round(db_mb, 2),
        "db_path":            path,
    }


if __name__ == "__main__":
    s = stats()
    print(f"historical_data.db istatistikleri:")
    print(f"  Finansal kayit: {s['financial_records'].get('total_records', 0)}"
          f" ({s['financial_records'].get('tickers_fin', 0)} ticker)")
    print(f"  Fiyat noktasi : {s['price_snapshots'].get('total_prices', 0)}"
          f" ({s['price_snapshots'].get('tickers_px', 0)} ticker)")
    print(f"  DB boyutu     : {s['db_size_mb']} MB")
