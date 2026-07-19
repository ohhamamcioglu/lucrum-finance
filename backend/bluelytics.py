"""
bluelytics.py — Bluelytics API istemcisi (Arjantin peso kurları)

Kaynak: https://api.bluelytics.com.ar/v2/latest — ücretsiz, anahtarsız, CORS açık.
Canlı doğrulandı (2026-07-18): {"oficial":{"value_avg","value_buy","value_sell"},
"blue":{...}, "oficial_euro":{...}, "blue_euro":{...}, "last_update"}.

Tarihsel endpoint YOK — geçmiş kur ancak zamanla DB'ye (exchange_rates.ars_try_rate)
biriktirilerek elde edilir (bkz. crud.save_exchange_rate), services.py'deki
USD/EUR/GBP kalıbıyla aynı.

"blue" (paralel piyasa / Blue Dollar) kuru esas alınır — Arjantinli yatırımcı için
ekonomik olarak anlamlı olan bu, resmi kur değil (bkz. strategic_product_roadmap.md,
Faz 2 pazar içgörüsü notu).
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from cache import finance_cache as _fc

logger = logging.getLogger("lucrum.bluelytics")

_API_URL = "https://api.bluelytics.com.ar/v2/latest"
_CACHE_KEY = "bluelytics_latest"
_CACHE_TTL = 3600  # 1 saat — USD/TRY güncel kur cache'iyle aynı taze tutma süresi


def get_latest_rates() -> Optional[dict]:
    """Bluelytics'in güncel oficial/blue (ve euro çeşitleri) kur setini döner.
    API erişilemezse None döner — HİÇBİR ZAMAN tahmini/sabit bir değere düşülmez
    (bkz. kullanıcı talebi: finansal veri asla tahmin edilmeyecek)."""
    cached = _fc.get(_CACHE_KEY, ttl=_CACHE_TTL)
    if cached is not None:
        return cached

    try:
        resp = requests.get(_API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("blue") or not data.get("oficial"):
            logger.warning("Bluelytics yanıtı beklenen alanları içermiyor: %s", data)
            return None
        _fc.set(_CACHE_KEY, data)
        return data
    except Exception as e:
        logger.warning("Bluelytics API isteği başarısız: %s", e)
        return None


def get_blue_dollar_ars_per_usd() -> Optional[float]:
    """1 USD kaç ARS (paralel/blue piyasa, alış-satış ortalaması). Veri yoksa None."""
    data = get_latest_rates()
    if not data:
        return None
    try:
        return float(data["blue"]["value_avg"])
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("Bluelytics blue.value_avg okunamadı: %s", e)
        return None


def get_official_ars_per_usd() -> Optional[float]:
    """1 USD kaç ARS (resmi kur, alış-satış ortalaması). Veri yoksa None."""
    data = get_latest_rates()
    if not data:
        return None
    try:
        return float(data["oficial"]["value_avg"])
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("Bluelytics oficial.value_avg okunamadı: %s", e)
        return None
