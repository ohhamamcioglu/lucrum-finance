"""
payments.py — Stripe + iyzico ödeme sağlayıcı entegrasyonu

Tek seferlik dönemsel ödeme (recurring/subscription API'leri değil): kullanıcı
öder, 30 günlük erişim açılır, süresi dolunca manuel yeniler
(bkz. tasks.downgrade_expired_subscriptions_task).

STRIPE_SECRET_KEY / IYZICO_API_KEY tanımlı değilse ilgili sağlayıcı fonksiyonları
None döner (router bunu 503'e çevirir) — email_service.py'deki "boşsa no-op"
deseniyle aynı, anahtarsız ortamda uygulama asla çökmez.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger("lucrum.payments")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ── Plan fiyatları (statik — MVP için canlı kur çevrimi yok) ─────────────────
PLAN_PRICING = {
    "PRO": {"usd_cents": 1900, "try": 650.0},
    "ENTERPRISE": {"usd_cents": 9900, "try": 3400.0},
}

# ── Stripe ────────────────────────────────────────────────────────────────
import stripe

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def stripe_configured() -> bool:
    return bool(STRIPE_SECRET_KEY)


def create_stripe_checkout(user_email: str, user_id: int, plan: str) -> Optional[str]:
    """Stripe Checkout Session (mode=payment, tek seferlik) oluşturur, checkout_url döner.
    STRIPE_SECRET_KEY tanımlı değilse None döner."""
    if not stripe_configured():
        return None
    pricing = PLAN_PRICING[plan]
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"Lucrum Finance {plan}"},
                "unit_amount": pricing["usd_cents"],
            },
            "quantity": 1,
        }],
        success_url=f"{FRONTEND_URL}/pricing?payment=success",
        cancel_url=f"{FRONTEND_URL}/pricing?payment=cancelled",
        customer_email=user_email,
        client_reference_id=str(user_id),
        metadata={"user_id": str(user_id), "plan": plan},
    )
    return session.id, session.url


def verify_stripe_webhook(payload: bytes, sig_header: str):
    """Stripe-Signature header'ını doğrular, geçerliyse stripe.Event döner.
    Geçersiz imza/payload durumunda ValueError fırlatır (router 400'e çevirir)."""
    if not STRIPE_WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET tanımlı değil.")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        raise ValueError(str(e))


# ── iyzico ────────────────────────────────────────────────────────────────
import iyzipay

IYZICO_API_KEY = os.getenv("IYZICO_API_KEY")
IYZICO_SECRET_KEY = os.getenv("IYZICO_SECRET_KEY")
IYZICO_BASE_URL = os.getenv("IYZICO_BASE_URL", "sandbox-api.iyzipay.com")


def iyzico_configured() -> bool:
    return bool(IYZICO_API_KEY and IYZICO_SECRET_KEY)


def _iyzico_options() -> dict:
    return {
        "api_key": IYZICO_API_KEY,
        "secret_key": IYZICO_SECRET_KEY,
        "base_url": IYZICO_BASE_URL,
    }


def create_iyzico_checkout(
    user_id: int,
    user_email: str,
    user_name: str,
    plan: str,
    identity_number: str,
    phone: str,
    address: str,
    city: str,
    country: str,
) -> Optional[tuple[str, str]]:
    """iyzico Checkout Form (Hosted Payment Page) başlatır.
    Döner: (checkout_url, token). IYZICO_API_KEY/SECRET_KEY tanımlı değilse None döner."""
    if not iyzico_configured():
        return None

    pricing = PLAN_PRICING[plan]
    price_str = f"{pricing['try']:.2f}"
    conversation_id = f"lucrum-{user_id}-{plan}-{int(datetime.utcnow().timestamp())}"
    name_parts = (user_name or "Lucrum Kullanıcısı").strip().split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else first_name

    request = {
        "locale": "tr",
        "conversationId": conversation_id,
        "price": price_str,
        "paidPrice": price_str,
        "currency": "TRY",
        "basketId": conversation_id,
        "paymentGroup": "PRODUCT",
        "callbackUrl": f"{BACKEND_URL}/api/payments/iyzico/callback",
        "enabledInstallments": [1],
        "buyer": {
            "id": str(user_id),
            "name": first_name,
            "surname": last_name,
            "identityNumber": identity_number,
            "email": user_email,
            "gsmNumber": phone,
            "registrationAddress": address,
            "city": city,
            "country": country,
        },
        "billingAddress": {
            "contactName": user_name or first_name,
            "address": address,
            "city": city,
            "country": country,
        },
        "basketItems": [{
            "id": f"plan-{plan.lower()}",
            "name": f"Lucrum Finance {plan} (30 gün)",
            "category1": "SaaS",
            "itemType": "VIRTUAL",
            "price": price_str,
        }],
    }

    checkout_form = iyzipay.CheckoutFormInitialize()
    result = checkout_form.create(request, _iyzico_options())
    parsed = json.loads(result.read().decode("utf-8")) if hasattr(result, "read") else result

    if parsed.get("status") != "success":
        logger.error("iyzico checkout başlatma başarısız: %s", parsed.get("errorMessage"))
        return None

    return parsed.get("paymentPageUrl"), parsed.get("token") or conversation_id


def retrieve_iyzico_payment(token: str) -> dict:
    """iyzico callback'inden gelen token'ı sunucu tarafında doğrular (asıl doğrulama adımı budur —
    ayrı bir imza kontrolü yok, klasik Checkout Form akışı bu retrieve çağrısına dayanır)."""
    request = {"locale": "tr", "conversationId": token, "token": token}
    checkout_form = iyzipay.CheckoutForm()
    result = checkout_form.retrieve(request, _iyzico_options())
    parsed = json.loads(result.read().decode("utf-8")) if hasattr(result, "read") else result
    return parsed


def iyzico_payment_succeeded(result: dict) -> bool:
    return result.get("status") == "success" and result.get("paymentStatus") == "SUCCESS"
