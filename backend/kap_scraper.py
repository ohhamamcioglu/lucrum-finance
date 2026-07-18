# -*- coding: utf-8 -*-
"""
kap_scraper.py — KAP (Kamuyu Aydınlatma Platformu) finansal veri çekici
=======================================================================
BIST hisseleri için yfinance'in eksik/gecikmeli bıraktığı finansal tablo
kalemlerini KAP'tan doğrudan çekerek tamamlar/doğrular.

Veri akışı:
1. pykap bundled veri → mkkMemberOid al (ağsız)
2. pykap disclosure API → son Finansal Rapor bildirimini bul
3. KAP bildirim sayfasını indir (HTML)
4. RSC __next_f.push script'indeki finansal tablo HTML'ini çıkar
5. BeautifulSoup ile gwt-Label satırlarını parse et → standart kalem dict döndür

Rate limit: KAP ~10 req/dk → istekler arası 2-3 sn bekleme zorunlu.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("lucrum.kap_scraper")

# ── Sabitler ──────────────────────────────────────────────────────────────────
_KAP_BASE  = "https://www.kap.org.tr"
_REQ_SLEEP = 2.5   # KAP rate limit koruma — request'ler arası minimum bekleme (sn)

_HERE          = os.path.dirname(os.path.abspath(__file__))
_KAP_CACHE_PATH = os.path.join(_HERE, "kap_cache.json")
_KAP_CACHE_TTL  = 7 * 24 * 3600  # 7 gün (saniye)


# ── KAP disk cache (kap_cache.json) ──────────────────────────────────────────
def _kap_cache_load() -> dict:
    try:
        with open(_KAP_CACHE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("KAP cache dosyası (%s) okunamadı, boş cache ile devam ediliyor: %s", _KAP_CACHE_PATH, e)
        return {}


def _kap_cache_save(cache: dict) -> None:
    try:
        with open(_KAP_CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.warning("KAP cache dosyası (%s) yazılamadı: %s", _KAP_CACHE_PATH, e)


def _kap_disk_get(clean: str) -> Optional[tuple[Optional[dict], Optional[dict]]]:
    """Disk cache'ten oku. TTL geçmişse ya da kayıt yoksa None döner."""
    cache = _kap_cache_load()
    entry = cache.get(clean)
    if not entry:
        return None
    try:
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at.replace(tzinfo=timezone.utc)).total_seconds()
        if age > _KAP_CACHE_TTL:
            return None
        data = entry["data"]
        return (data[0], data[1])
    except Exception as e:
        logger.warning("KAP disk cache girdisi ('%s') bozuk, atlanıyor: %s", clean, e)
        return None


def _kap_disk_set(clean: str, curr: Optional[dict], prev: Optional[dict]) -> None:
    """Disk cache'e yaz."""
    cache = _kap_cache_load()
    cache[clean] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data": [curr, prev],
    }
    _kap_cache_save(cache)

_PAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "tr-TR,tr;q=0.9",
    "Connection": "keep-alive",
}


# ── Yardımcı: ticker → mkkMemberOid (pykap bundled, ağsız) ───────────────────
def _get_member_oid(ticker: str) -> Optional[str]:
    """pykap bundled şirket listesinden mkkMemberOid döndür (ağ erişimi yok)."""
    try:
        import pykap
        clean = ticker.upper().replace(".IS", "")
        info = pykap.get_general_info(clean)
        return info.get("company_id") if info else None
    except Exception as e:
        logger.debug("pykap.get_general_info('%s') başarısız: %s", ticker, e)
        return None


# ── Yardımcı: pykap ile disclosure listesi çek ────────────────────────────────
def _get_disclosure_list(ticker: str) -> list[dict]:
    """
    pykap BISTCompany.get_historical_disclosure_list() → FR bildirim listesi.
    Fallback: doğrudan KAP API.
    """
    clean = ticker.upper().replace(".IS", "")

    # 1) pykap yolu (en güvenilir)
    try:
        from pykap.bist import BISTCompany
        company = BISTCompany(clean)
        disclosures = company.get_historical_disclosure_list()
        if disclosures:
            return disclosures
    except Exception as e:
        logger.debug("pykap BISTCompany('%s').get_historical_disclosure_list() başarısız, API fallback'e geçiliyor: %s", clean, e)

    time.sleep(_REQ_SLEEP)

    # 2) Doğrudan API fallback
    member_oid = _get_member_oid(ticker)
    if not member_oid:
        return []

    from datetime import date, timedelta
    payload_base = {
        "fromDate": (date.today() - timedelta(days=800)).isoformat(),
        "toDate": date.today().isoformat(),
        "disclosureClass": "FR",
        "mkkMemberOidList": [member_oid],
        "inactiveMkkMemberOidList": [],
        "bdkMemberOidList": [],
        "fromSrc": False,
        "disclosureIndexList": [],
    }

    for subject_list in [
        ["4028328c594bfdca01594c0af9aa0057"],
        ["8aca490d502dd03b01502deede79010a"],
        [],
    ]:
        try:
            payload = {**payload_base, "subjectList": subject_list}
            r = requests.post(
                f"{_KAP_BASE}/tr/api/disclosure/members/byCriteria",
                json=payload, timeout=20,
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    return data
        except Exception as e:
            logger.debug("KAP disclosure/byCriteria isteği (subject_list=%s) başarısız: %s", subject_list, e)
        time.sleep(_REQ_SLEEP)

    return []


# ── Yardımcı: RSC __next_f.push script'inden finansal tablo HTML'ini çıkar ───
def _decode_rsc_script(sc: str) -> Optional[str]:
    """RSC script içindeki JSON-encoded HTML string'i decode et."""
    # Yöntem 1: JSON string parse (en güvenli — \\uXXXX Unicode kaçışları için)
    try:
        decoded = json.loads(f'"{sc}"')
        if "<table" in decoded:
            return decoded
    except Exception as e:
        logger.debug("RSC script decode Yöntem 1 (JSON parse) başarısız: %s", e)

    # Yöntem 2: raw_unicode_escape
    try:
        decoded = sc.encode("raw_unicode_escape").decode("unicode_escape")
        if "<table" in decoded:
            return decoded
    except Exception as e:
        logger.debug("RSC script decode Yöntem 2 (raw_unicode_escape) başarısız: %s", e)

    # Yöntem 3: manuel unescape
    try:
        decoded = (
            sc.replace("\\u003c", "<").replace("\\u003e", ">")
              .replace("\\u0026", "&").replace('\\"', '"')
              .replace("\\n", "\n").replace("\\t", "\t")
              .replace("\\\\", "\\")
        )
        if "<table" in decoded:
            return decoded
    except Exception as e:
        logger.debug("RSC script decode Yöntem 3 (manuel unescape) başarısız: %s", e)

    return None


def _extract_financial_html(page_html: str) -> Optional[str]:
    """
    KAP Next.js bildirim sayfasındaki TÜM RSC script payload'larını tara.
    Birden fazla finansal tablo (bilanço, gelir tablosu, nakit akış) olabilir —
    hepsini birleştirerek döndür.

    KAP, her finansal tabloyu ayrı bir RSC script olarak gömer:
      self.__next_f.push([1,"...<table class=\\"financial-table tbl_general_role_XXXXXX\\"..."])
    """
    rsc_scripts = re.findall(
        r'self\.__next_f\.push\(\[1,"(.*?)"\]\)',
        page_html, re.S
    )

    html_parts: list[str] = []
    for sc in rsc_scripts:
        if "financial-table" not in sc and "gwt-Label" not in sc:
            continue
        decoded = _decode_rsc_script(sc)
        if decoded and "<table" in decoded:
            html_parts.append(decoded)

    if html_parts:
        return "\n\n".join(html_parts)

    # Fallback: eski KAP formatı — doğrudan DOM'da tablo var mı?
    if "financial-header-table" in page_html or (
        "gwt-Label" in page_html and "taxonomy-context-value" in page_html
    ):
        return page_html

    return None


# ── Yardımcı: birim tespiti (Bin TL vs Milyon TL) ─────────────────────────────
def _detect_unit_multiplier(html: str) -> int:
    """
    KAP finansal tablo birimini tespit et.
    Dönüş: 1_000 (Bin TL) veya 1_000_000 (Milyon TL).
    Türk IFRS raporlarının büyük çoğunluğu 'Bin TL' kullanır.
    """
    low = html.lower()
    if "milyon tl" in low or "tl milyon" in low or "million tl" in low:
        return 1_000_000
    return 1_000  # Default: Bin TL


# ── Yardımcı: finansal tablo HTML parse ───────────────────────────────────────
def _parse_financial_html(html: str) -> dict[str, Optional[float]]:
    """
    gwt-Label / taxonomy-context-value satırlarını parse et.
    Sol sütun = kalem adı (Türkçe), sağ sütun = güncel dönem değeri.
    """
    soup = BeautifulSoup(html, "html5lib")
    label_class = "gwt-Label multi-language-content content-tr"
    value_class_re = re.compile(r"taxonomy-context-value.*")
    row_class_re = re.compile(r".*_role_.*data-input-row.*presentation-enabled")

    result: dict[str, Optional[float]] = {}
    seen: set[str] = set()

    for row in soup.find_all("tr", {"class": row_class_re}):
        label_el = row.find(True, {"class": label_class})
        if label_el is None:
            continue

        label = label_el.get_text(strip=True)
        if not label:
            continue

        # Duplicate handling
        base_label = label
        n = 1
        while label in seen:
            n += 1
            label = f"{base_label}{n}"
        seen.add(label)

        value: Optional[float] = None
        value_el = row.find("td", {"class": value_class_re})
        if value_el is not None:
            raw = value_el.get_text(strip=True)
            if raw:
                try:
                    value = float(raw.replace(".", "").replace(",", "."))
                except ValueError:
                    pass

        result[label] = value

    return result


# ── Standart kalem eşleştirme tablosu ─────────────────────────────────────────
_KALEM_MAP: dict[str, list[str]] = {
    # Bilanço
    "working_capital_components": [],  # hesaplanır
    "current_assets":       ["Dönen Varlıklar", "Toplam Dönen Varlıklar",
                             "TOPLAM DÖNEN VARLIKLAR"],
    "total_assets":         ["Toplam Varlıklar", "TOPLAM VARLIKLAR", "Varlıklar Toplamı",
                             "Varlık Toplamı"],
    "current_liabilities":  ["Kısa Vadeli Yükümlülükler", "Kısa Vadeli Borçlar",
                             "Toplam Kısa Vadeli Yükümlülükler",
                             "TOPLAM KISA VADELİ YÜKÜMLÜLÜKLER"],
    "total_liabilities":    ["Toplam Yükümlülükler", "Toplam Borçlar",
                             "Yükümlülükler Toplamı", "TOPLAM YÜKÜMLÜLÜKLER"],
    "equity":               ["Özkaynaklar", "Ana Ortaklığa Ait Özkaynaklar",
                             "Toplam Özkaynaklar", "Özsermaye",
                             "ANA ORTAKLIĞA AİT ÖZKAYNAKLAR"],
    "retained_earnings":    ["Geçmiş Yıllar Kârları/Zararları", "Dağıtılmamış Kârlar",
                             "Geçmiş Yıllar Karları",
                             "Geçmiş Yıllar Karları veya Zararları",
                             "Geçmiş Yıllar Kârları veya Zararları"],
    "cash":                 ["Nakit ve Nakit Benzerleri"],
    # Gelir tablosu
    "revenue":              ["Hasılat", "Net Satışlar", "Satışlardan Gelirler",
                             "Satış Gelirleri"],
    "gross_profit":         ["Brüt Kâr/Zarar", "Brüt Kâr (Zarar)", "Brüt Kâr",
                             "BRÜT KAR (ZARAR)", "TİCARİ FAALİYETLERDEN BRÜT KAR (ZARAR)"],
    "operating_income":     ["Esas Faaliyet Kârı/Zararı", "Faaliyet Kârı/Zararı",
                             "Faaliyet Kârı", "ESAS FAALİYET KARI (ZARARI)",
                             "FAALİYET KARI (ZARARI)"],
    "net_income":           ["Dönem Kârı/Zararı", "Net Dönem Kârı/Zararı",
                             "Net Kâr/Zarar", "Dönem Net Kârı",
                             "DÖNEM KARI (ZARARI)",
                             "SÜRDÜRÜLEN FAALİYETLER DÖNEM KARI (ZARARI)"],
    # Nakit akış
    "operating_cash_flow":  ["İşletme Faaliyetlerinden Nakit Akışları",
                             "Esas Faaliyetlerden Kaynaklanan Net Nakit",
                             "İşletme Faaliyetlerinden Sağlanan Nakit Akışları",
                             "İŞLETME FAALİYETLERİNDEN NAKİT AKIŞLARI"],
}


def _map_items(raw: dict[str, Optional[float]]) -> dict[str, Optional[float]]:
    """Ham kalem adlarını standart anahtarlara dönüştür (büyük/küçük harf duyarsız)."""
    # Case-insensitive lookup: lowercase_key → (original_key, value)
    raw_ci: dict[str, tuple[str, Optional[float]]] = {
        k.lower(): (k, v) for k, v in raw.items()
    }

    out: dict[str, Optional[float]] = {}
    for std_key, aliases in _KALEM_MAP.items():
        if not aliases:
            continue
        for alias in aliases:
            # Exact match first
            if alias in raw and raw[alias] is not None:
                out[std_key] = raw[alias]
                break
            # Case-insensitive fallback
            al = alias.lower()
            if al in raw_ci:
                _, val = raw_ci[al]
                if val is not None:
                    out[std_key] = val
                    break
        if std_key not in out:
            out[std_key] = None

    # Çalışma sermayesi hesapla
    ca = out.get("current_assets")
    cl = out.get("current_liabilities")
    if ca is not None and cl is not None:
        out["working_capital"] = ca - cl
    else:
        out["working_capital"] = None

    return out


# ── Ana fonksiyonlar ──────────────────────────────────────────────────────────
_annual_pair_cache: dict[str, tuple] = {}


def _is_annual_disclosure(d: dict) -> bool:
    """Bildirim yıllık mı? ruleType alanına göre kontrol."""
    rt = (d.get("ruleType") or "").lower()
    if any(kw in rt for kw in ("yıllık", "yillik", "12 aylık", "12 aylik", "annual")):
        return True
    # 3/6/9 aylık = ara dönem
    if any(kw in rt for kw in ("3 aylık", "6 aylık", "9 aylık", "3 aylik", "6 aylik", "9 aylik")):
        return False
    # Bilinmeyen: "aylık" geçmiyorsa yıllık kabul et
    return "aylık" not in rt and "aylik" not in rt


def _fetch_kap_disc(disc: dict) -> Optional[dict]:
    """Tek bir bildirim dict'i için HTTP fetch + parse. get_kap_financials alt yordamı."""
    disc_idx = disc.get("disclosureIndex")
    if not disc_idx:
        return None

    time.sleep(_REQ_SLEEP)
    url = f"{_KAP_BASE}/tr/Bildirim/{disc_idx}"
    r = requests.get(url, headers=_PAGE_HEADERS, timeout=30)
    if r.status_code == 429:
        time.sleep(30)
        r = requests.get(url, headers=_PAGE_HEADERS, timeout=30)
    if r.status_code != 200:
        return None

    time.sleep(_REQ_SLEEP)
    fin_html = _extract_financial_html(r.text)
    if fin_html is None:
        return None

    raw_items = _parse_financial_html(fin_html)
    if not raw_items:
        return None

    unit_multiplier = _detect_unit_multiplier(r.text)
    mapped = _map_items(raw_items)
    mapped.pop("working_capital_components", None)

    return {
        **mapped,
        "raw_items": raw_items,
        "disclosure_index": disc_idx,
        "period": disc.get("ruleType", ""),
        "year": disc.get("year"),
        "publish_date": disc.get("publishDate", ""),
        "unit_multiplier": unit_multiplier,
        "unit_label": "Milyon TL" if unit_multiplier == 1_000_000 else "Bin TL",
        "data_source": "KAP",
    }


def get_kap_financials(ticker: str) -> Optional[dict]:
    """
    BIST ticker için KAP'tan son finansal raporu çek (quarterly veya annual).

    Returns dict with keys:
      current_assets, total_assets, current_liabilities, total_liabilities,
      equity, retained_earnings, cash, revenue, gross_profit,
      operating_income, net_income, operating_cash_flow, working_capital,
      raw_items, disclosure_index, period, year, publish_date,
      unit_multiplier, unit_label, data_source
    Hata/veri yoksa None döner.
    """
    try:
        disclosures = _get_disclosure_list(ticker)
        if not disclosures:
            return None
        disclosures.sort(
            key=lambda d: (d.get("year", 0), d.get("period", 0)),
            reverse=True,
        )
        return _fetch_kap_disc(disclosures[0])
    except Exception as e:
        logger.warning("get_kap_financials('%s') başarısız: %s", ticker, e)
        return None


def _get_disclosure_list_extended(ticker: str, days: int = 900) -> list[dict]:
    """
    Doğrudan KAP API'sini kullanarak genişletilmiş geçmiş bildirim listesi çek.
    pykap'ın kısa penceresi yetmediğinde ikinci yıllık bildirimi bulmak için kullanılır.
    """
    from datetime import date, timedelta

    clean = ticker.upper().replace(".IS", "")
    member_oid = _get_member_oid(ticker)
    if not member_oid:
        return []

    payload_base = {
        "fromDate": (date.today() - timedelta(days=days)).isoformat(),
        "toDate": date.today().isoformat(),
        "disclosureClass": "FR",
        "mkkMemberOidList": [member_oid],
        "inactiveMkkMemberOidList": [],
        "bdkMemberOidList": [],
        "fromSrc": False,
        "disclosureIndexList": [],
    }
    for subject_list in [
        ["4028328c594bfdca01594c0af9aa0057"],
        ["8aca490d502dd03b01502deede79010a"],
        [],
    ]:
        try:
            payload = {**payload_base, "subjectList": subject_list}
            r = requests.post(
                f"{_KAP_BASE}/tr/api/disclosure/members/byCriteria",
                json=payload, timeout=20,
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    return data
        except Exception as e:
            logger.debug("KAP genişletilmiş disclosure isteği (subject_list=%s) başarısız: %s", subject_list, e)
        time.sleep(_REQ_SLEEP)

    return []


def get_kap_financials_annual_pair(ticker: str) -> tuple[Optional[dict], Optional[dict]]:
    """
    Piotroski F-Score YoY karşılaştırması için son iki yıllık bildirimi çek.

    Aynı session içinde tekrar çağrılırsa cache'ten döner (Z+F score aynı ticker için
    ikişer kez çağırdığında KAP HTTP isteği tekrarlanmaz).

    pykap kısa pencereli döndürürse ikinci yıllık için 900-günlük extended API'ye düşer.

    Returns:
        (curr_annual, prev_annual) — her biri get_kap_financials ile aynı yapıda
        Veri yoksa ilgili slot None döner.
    """
    clean = ticker.upper().replace(".IS", "")
    if clean in _annual_pair_cache:
        return _annual_pair_cache[clean]

    # Disk cache kontrolü (kap_cache.json, TTL=7 gün)
    cached = _kap_disk_get(clean)
    if cached is not None:
        _annual_pair_cache[clean] = cached
        return cached

    result: tuple[Optional[dict], Optional[dict]] = (None, None)
    try:
        disclosures = _get_disclosure_list(ticker)

        annuals = sorted(
            [d for d in disclosures if _is_annual_disclosure(d)],
            key=lambda d: (d.get("year", 0), d.get("period", 0)),
            reverse=True,
        )

        # pykap yeterli tarihçe döndürmezse doğrudan API'den genişlet
        if len(annuals) < 2:
            ext = _get_disclosure_list_extended(ticker, days=900)
            if ext:
                seen = {d.get("disclosureIndex") for d in disclosures}
                for d in ext:
                    if d.get("disclosureIndex") not in seen:
                        disclosures.append(d)
                        seen.add(d.get("disclosureIndex"))
                annuals = sorted(
                    [d for d in disclosures if _is_annual_disclosure(d)],
                    key=lambda d: (d.get("year", 0), d.get("period", 0)),
                    reverse=True,
                )

        curr = _fetch_kap_disc(annuals[0]) if len(annuals) >= 1 else None
        prev = _fetch_kap_disc(annuals[1]) if len(annuals) >= 2 else None
        result = (curr, prev)
    except Exception as e:
        logger.warning("get_kap_financials_annual_pair('%s') başarısız: %s", ticker, e)

    _annual_pair_cache[clean] = result
    # Disk cache'e yaz (refresh_kap_data.py ile önceden doldurulabilir)
    _kap_disk_set(clean, result[0], result[1])
    return result


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    tickers = sys.argv[1:] or ["ASELS.IS", "THYAO.IS", "EREGL.IS"]
    for tk in tickers:
        print(f"\n{'='*60}")
        print(f"KAP verisi: {tk}")
        print(f"{'='*60}")
        result = get_kap_financials(tk)
        if result:
            print(f"Disclosure : {result['disclosure_index']} | {result['year']} {result['period']}")
            print(f"Yayın      : {result['publish_date']}")
            print(f"\nStandart kalemler:")
            for k, v in result.items():
                if k not in ("raw_items", "data_source", "disclosure_index", "period", "year", "publish_date"):
                    val_str = f"{v:>20,.0f}" if isinstance(v, (int, float)) else str(v)
                    print(f"  {k:<25}: {val_str}")
            print(f"\nHam kalemler (ilk 12):")
            for label, val in list(result.get("raw_items", {}).items())[:12]:
                val_str = f"{val:>20,.0f}" if isinstance(val, (int, float)) else str(val)
                print(f"  {label:<50}: {val_str}")
        else:
            print("Veri bulunamadı")
        time.sleep(5)
