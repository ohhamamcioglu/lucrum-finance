"""
payments.py — Lemon Squeezy ödeme sağlayıcı entegrasyonu

Tek seferlik dönemsel ödeme (recurring/subscription API'leri değil): kullanıcı
öder, 30 günlük erişim açılır, süresi dolunca manuel yeniler
(bkz. tasks.downgrade_expired_subscriptions_task).

LEMONSQUEEZY_API_KEY / STORE_ID / variant ID'leri tanımlı değilse
lemonsqueezy_configured() False döner (router bunu 503'e çevirir) —
email_service.py'deki "boşsa no-op" deseniyle aynı, anahtarsız ortamda
uygulama asla çökmez.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger("lucrum.payments")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ── Plan fiyatları (statik — cent cinsinden USD liste fiyatı) ───────────────
# Lemon Squeezy alıcının ülkesine göre otomatik yerel para birimine çeviriyor,
# ayrı bir TRY fiyatı tutmaya gerek yok (Stripe+iyzico ikilisinden farklı olarak).
PLAN_PRICING = {
    "PRO": 1900,
    "ENTERPRISE": 9900,
}

LEMONSQUEEZY_API_BASE = "https://api.lemonsqueezy.com/v1"

LEMONSQUEEZY_API_KEY = os.getenv("LEMONSQUEEZY_API_KEY")
LEMONSQUEEZY_STORE_ID = os.getenv("LEMONSQUEEZY_STORE_ID")
LEMONSQUEEZY_WEBHOOK_SECRET = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET")

VARIANT_IDS = {
    "PRO": os.getenv("LEMONSQUEEZY_VARIANT_ID_PRO"),
    "ENTERPRISE": os.getenv("LEMONSQUEEZY_VARIANT_ID_ENTERPRISE"),
}


def lemonsqueezy_configured() -> bool:
    return bool(
        LEMONSQUEEZY_API_KEY
        and LEMONSQUEEZY_STORE_ID
        and VARIANT_IDS["PRO"]
        and VARIANT_IDS["ENTERPRISE"]
    )


def create_lemonsqueezy_checkout(
    user_email: str,
    user_id: int,
    plan: str,
    payment_record_id: int,
) -> Optional[str]:
    """Lemon Squeezy Checkout oluşturur, checkout_url döner.
    Yapılandırılmamışsa None döner.

    Korelasyon: checkout-id ile order-id eşleşmesi garanti değil (checkout != order,
    order sadece ödeme tamamlanınca oluşur). Bunun yerine kendi DBPayment.id'imizi
    checkout_data.custom içine gömüyoruz — webhook geldiğinde doğrudan bu ID ile
    ilgili kaydı buluyoruz, string eşleştirme/arama gerekmiyor.
    """
    if not lemonsqueezy_configured():
        return None

    try:
        resp = requests.post(
            f"{LEMONSQUEEZY_API_BASE}/checkouts",
            headers={
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
                "Authorization": f"Bearer {LEMONSQUEEZY_API_KEY}",
            },
            json={
                "data": {
                    "type": "checkouts",
                    "attributes": {
                        "checkout_data": {
                            "email": user_email,
                            "custom": {
                                "payment_record_id": str(payment_record_id),
                                "user_id": str(user_id),
                                "plan": plan,
                            },
                        },
                        "product_options": {
                            "redirect_url": f"{FRONTEND_URL}/pricing?payment=success",
                        },
                    },
                    "relationships": {
                        "store": {"data": {"type": "stores", "id": str(LEMONSQUEEZY_STORE_ID)}},
                        "variant": {"data": {"type": "variants", "id": str(VARIANT_IDS[plan])}},
                    },
                }
            },
            timeout=15,
        )
        if not resp.ok:
            logger.error("Lemon Squeezy checkout oluşturma başarısız: %s %s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        return data["data"]["attributes"]["url"]
    except Exception as e:
        logger.error("Lemon Squeezy checkout isteği başarısız: %s", e)
        return None


def verify_lemonsqueezy_webhook(payload: bytes, signature_header: str) -> bool:
    """X-Signature header'ını doğrular. LEMONSQUEEZY_WEBHOOK_SECRET tanımlı değilse
    veya imza uyuşmuyorsa False döner (router bunu 400'e çevirir)."""
    if not LEMONSQUEEZY_WEBHOOK_SECRET or not signature_header:
        return False
    expected = hmac.new(
        LEMONSQUEEZY_WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
