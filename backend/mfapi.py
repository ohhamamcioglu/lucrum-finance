"""
mfapi.in istemcisi — AMFI (Association of Mutual Funds in India) yatırım fonu
verilerini saran, ücretsiz, anahtarsız bir topluluk REST API'si (Faz 3.5, task #59).

DOĞRULANDI (önceki oturumda canlı test edildi): AMFI'nin ham NAVAll.txt dosyasına
bu ortamdan erişim ECONNREFUSED ile başarısız oluyordu (coğrafi kısıtlama olabilir).
mfapi.in gerçek AMFI verisini JSON olarak sunuyor ve çalışıyor — bu oturumda tekrar
canlı doğrulandı: GET https://api.mfapi.in/mf (75.340 fonun tam kod+isim listesi) ve
GET https://api.mfapi.in/mf/{scheme_code} (fon evi/kategori/ISIN metadata'sı + tam
tarihsel NAV serisi, en yeni kayıt ilk sırada, tarih formatı DD-MM-YYYY).
"""
from typing import Any, Dict, List, Optional

import requests

from cache import finance_cache

_BASE_URL = "https://api.mfapi.in"
_TTL_FUND_LIST = 7 * 24 * 3600  # 7 gün — fon listesi nadiren değişir
_TTL_FUND_DATA = 1 * 24 * 3600  # 1 gün — NAV günlük güncellenir


def get_fund_list() -> List[Dict[str, Any]]:
    """Tüm AMFI fonlarının kod+isim listesini döner (~75.000 fon). Ağ hatasında
    boş liste döner — asla eski/uydurma bir liste üretmez."""
    cached = finance_cache.get("mfapi_fund_list", ttl=_TTL_FUND_LIST)
    if cached is not None:
        return cached
    try:
        r = requests.get(f"{_BASE_URL}/mf", timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    if isinstance(data, list):
        finance_cache.set("mfapi_fund_list", data)
        return data
    return []


def search_funds(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Fon adında/kodunda GEÇEN (büyük/küçük harf duyarsız alt dize) fonları döner."""
    if not query or len(query.strip()) < 2:
        return []
    q = query.strip().lower()
    all_funds = get_fund_list()
    matches = [
        f for f in all_funds
        if q in str(f.get("schemeName", "")).lower() or q == str(f.get("schemeCode", ""))
    ]
    return matches[:limit]


def get_fund_data(scheme_code: str) -> Optional[Dict[str, Any]]:
    """Belirli bir fonun metadata'sını (fon evi, kategori, ISIN) ve tam tarihsel
    NAV serisini döner. Bulunamazsa/ağ hatasında None döner."""
    cache_key = f"mfapi_fund_{scheme_code}"
    cached = finance_cache.get(cache_key, ttl=_TTL_FUND_DATA)
    if cached is not None:
        return cached
    try:
        r = requests.get(f"{_BASE_URL}/mf/{scheme_code}", timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    if not isinstance(data, dict) or "meta" not in data:
        return None
    finance_cache.set(cache_key, data)
    return data


def get_latest_nav(scheme_code: str) -> Optional[Dict[str, str]]:
    """En güncel NAV kaydını ({"date": "DD-MM-YYYY", "nav": "..."})  döner."""
    data = get_fund_data(scheme_code)
    if not data:
        return None
    nav_series = data.get("data") or []
    if not nav_series:
        return None
    return nav_series[0]  # mfapi.in en yeni kaydı ilk sırada döner


def is_equity_oriented(scheme_code: str) -> Optional[bool]:
    """Fonun 'scheme_category' alanına göre hisse-ağırlıklı (equity-oriented) olup
    olmadığını söyler — LTCG/STCG 12 aylık eşiği SADECE hisse-ağırlıklı fonlara
    uygulanır (borç fonları 2023 vergi değişikliğinden beri tamamen farklı, çok daha
    karmaşık kurallara tabi — bu modül onları KAPSAMAZ). Kategori bilgisi yoksa/fon
    bulunamazsa None döner (True/False UYDURULMAZ)."""
    data = get_fund_data(scheme_code)
    if not data:
        return None
    category = (data.get("meta") or {}).get("scheme_category") or ""
    if not category:
        return None
    return "equity" in category.lower()
