"""
Esnek CSV/Excel içe aktarma motoru (Faz 2, task #57).

Belirli bir borsacının export formatına göre YAZILMADI — hiçbir gerçek broker
export dosyası doğrulanmadan onun sütun düzenini "biliyormuş" gibi davranmak,
projedeki "asla tahmini veri üretme" kuralını ihlal eder. Bunun yerine sütun
başlıklarını eş anlamlı terimlerle otomatik eşlemeye çalışır (Türkçe/İngilizce),
kullanıcı önizleme ekranında eşlemeyi elle düzeltebilir. Bir satır/alan
ayrıştırılamazsa o satır atlanır ve nedeni raporlanır — asla varsayılan/tahmini
bir değerle doldurulmaz.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dateutil import parser as dateutil_parser

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_ROWS = 2000
SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls")

FIELD_SYNONYMS: Dict[str, List[str]] = {
    "ticker": ["ticker", "sembol", "symbol", "hisse", "hisse kodu", "kod", "fon kodu",
               "fon", "varlik", "instrument", "code", "enstruman"],
    "quantity": ["adet", "miktar", "quantity", "qty", "lot", "nominal", "pay adedi", "adedi"],
    "buy_price": ["fiyat", "price", "birim fiyat", "alis fiyati", "unit price",
                  "islem fiyati", "birim fiyati"],
    "buy_date": ["tarih", "date", "islem tarihi", "valor", "valor tarihi", "trade date",
                 "islem gunu"],
    "buy_currency": ["para birimi", "currency", "doviz", "kur birimi", "ccy", "para birim"],
    "asset_class": ["varlik turu", "varlik sinifi", "tur", "type", "asset class", "kategori"],
}

REQUIRED_FIELDS = ("ticker", "quantity", "buy_price", "buy_date")

# DashboardView'daki manuel "Yeni Varlık Ekle" formunun ürettiği taksonomiyle birebir
# aynı (bkz. frontend/src/components/DashboardView.tsx handleSymbolBlur/handleSubmitAdd) —
# başka bir sınıf UYDURULMADI, mevcut sistemin zaten kabul ettiği değerler kullanıldı.
VALID_ASSET_CLASSES = {
    "ABD Hisse/ETF", "BIST Hissesi", "Kripto", "TEFAS Fonu", "FixedIncome", "Nakit",
}
VALID_CURRENCIES = {"TRY", "USD", "EUR", "GBP"}


def _normalize_header(h: Any) -> str:
    s = str(h).strip().lower()
    for src, dst in (("ı", "i"), ("ğ", "g"), ("ü", "u"), ("ş", "s"), ("ö", "o"), ("ç", "c")):
        s = s.replace(src, dst)
    s = re.sub(r"[_\-/]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_file(filename: str, content: bytes) -> pd.DataFrame:
    """Ham dosya baytlarını DataFrame'e çevirir. Türkçe borsa export'ları genelde
    Windows-1254 veya UTF-8 karışık geldiğinden birden çok encoding sırayla denenir."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if filename and "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Desteklenmeyen dosya türü: {ext or 'uzantısız'}. CSV, XLSX veya XLS yükleyin.")
    if not content:
        raise ValueError("Dosya boş.")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError(f"Dosya çok büyük ({len(content) // 1024} KB). En fazla {MAX_FILE_BYTES // 1024 // 1024} MB desteklenir.")

    df: Optional[pd.DataFrame] = None
    if ext == ".csv":
        last_err: Optional[Exception] = None
        for encoding in ("utf-8-sig", "windows-1254", "iso-8859-9", "latin1"):
            try:
                df = pd.read_csv(io.BytesIO(content), encoding=encoding, sep=None, engine="python", dtype=str)
                break
            except Exception as e:
                last_err = e
                df = None
        if df is None:
            raise ValueError(f"CSV ayrıştırılamadı: {last_err}")
    else:
        try:
            df = pd.read_excel(io.BytesIO(content), dtype=str)
        except Exception as e:
            raise ValueError(f"Excel dosyası ayrıştırılamadı: {e}")

    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("Dosyada veri satırı bulunamadı.")
    if len(df) > MAX_ROWS:
        raise ValueError(f"Dosyada çok fazla satır var ({len(df)}). En fazla {MAX_ROWS} satır desteklenir.")

    df.columns = [str(c).strip() for c in df.columns]
    return df


def extract_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """DataFrame'i cache'e yazılabilir, JSON/pickle güvenli ham satır listesine çevirir."""
    return df.where(pd.notnull(df), None).to_dict(orient="records")  # type: ignore[return-value]


def suggest_mapping(columns: List[str]) -> Dict[str, Optional[str]]:
    """Sütun başlıklarını eş anlamlı terim sözlüğüyle alanlara eşlemeye çalışır.
    Belirsizse (eşleşme yoksa) o alan için None döner — kullanıcı elle seçer."""
    normalized = {col: _normalize_header(col) for col in columns}
    mapping: Dict[str, Optional[str]] = {}
    used_columns: set = set()
    for field, synonyms in FIELD_SYNONYMS.items():
        best_col = None
        for col, norm in normalized.items():
            if col in used_columns:
                continue
            if norm in synonyms:
                best_col = col
                break
        if best_col is None:
            for col, norm in normalized.items():
                if col in used_columns:
                    continue
                if any(syn in norm for syn in synonyms):
                    best_col = col
                    break
        mapping[field] = best_col
        if best_col:
            used_columns.add(best_col)
    return mapping


def parse_number(raw: Any) -> Optional[float]:
    """'1.234,56' (TR), '1,234.56' (US) ya da '1234.56' biçimlerini kabul eder.
    Gerçek bir sayıya ayrıştıramazsa None döner — asla tahmini bir değer üretmez."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw == raw else None  # NaN guard
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "-"):
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s or s == "-":
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_date_value(raw: Any) -> Optional[date]:
    """Kullanıcının dosyasındaki GERÇEK tarih string'ini ayrıştırır — tahmini/varsayılan
    tarih ÜRETMEZ, ayrıştıramazsa None döner."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, pd.Timestamp):
        return raw.to_pydatetime().date()
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    try:
        dt = dateutil_parser.parse(s, dayfirst=True)
        return dt.date()
    except (ValueError, OverflowError, TypeError):
        return None


def build_position_fields(
    row: Dict[str, Any],
    mapping: Dict[str, Optional[str]],
    asset_class_default: Optional[str],
    buy_currency_default: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Bir satırı Position alanlarına çevirir. Ayrıştırılamayan/eksik bir alan varsa
    (None, hata_nedeni) döner — eksik veri asla tahminle doldurulmaz."""
    ticker_col = mapping.get("ticker")
    ticker_raw = row.get(ticker_col) if ticker_col else None
    ticker = str(ticker_raw).strip().upper() if ticker_raw not in (None, "") else None
    if not ticker:
        return None, "Sembol/ticker boş veya eşlenmemiş"

    qty_col = mapping.get("quantity")
    quantity = parse_number(row.get(qty_col)) if qty_col else None
    if quantity is None or quantity <= 0:
        return None, "Adet/miktar ayrıştırılamadı veya sıfır"

    price_col = mapping.get("buy_price")
    buy_price = parse_number(row.get(price_col)) if price_col else None
    if buy_price is None or buy_price <= 0:
        return None, "Fiyat ayrıştırılamadı veya sıfır"

    date_col = mapping.get("buy_date")
    buy_date = parse_date_value(row.get(date_col)) if date_col else None
    if buy_date is None:
        return None, "Tarih ayrıştırılamadı"

    currency_col = mapping.get("buy_currency")
    buy_currency = None
    if currency_col:
        raw_cur = row.get(currency_col)
        if raw_cur:
            buy_currency = str(raw_cur).strip().upper()
    if not buy_currency:
        buy_currency = buy_currency_default
    if buy_currency not in VALID_CURRENCIES:
        return None, f"Bilinmeyen para birimi: {buy_currency}"

    asset_class_col = mapping.get("asset_class")
    asset_class = None
    if asset_class_col:
        raw_ac = row.get(asset_class_col)
        if raw_ac:
            asset_class = str(raw_ac).strip()
    if not asset_class:
        asset_class = asset_class_default
    if not asset_class:
        return None, "Varlık sınıfı belirlenemedi (eşlenmemiş ve varsayılan seçilmemiş)"
    if asset_class not in VALID_ASSET_CLASSES:
        return None, f"Bilinmeyen varlık sınıfı: {asset_class}"

    return {
        "ticker": ticker,
        "quantity": quantity,
        "buy_price": buy_price,
        "buy_date": buy_date,
        "buy_currency": buy_currency,
        "asset_class": asset_class,
    }, None
