import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import List

from models import LemonSqueezyCheckoutRequest, CheckoutResponse, PaymentSummary
from crud import (
    create_payment_record, mark_payment_succeeded, list_user_payments,
    get_user_by_id,
)
from dependencies import get_current_user_id, get_db
from rate_limit import limiter
import payments as payment_svc

router = APIRouter(prefix="/api/payments", tags=["Payments"])

VALID_PLANS = ("PRO", "ENTERPRISE")


@router.post("/lemonsqueezy/checkout", response_model=CheckoutResponse)
@limiter.limit("10/minute")
def lemonsqueezy_checkout(
    request: Request,
    req: LemonSqueezyCheckoutRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Lemon Squeezy Checkout başlatır (tek seferlik ödeme, kart bilgisi hiçbir zaman bize gelmez)."""
    plan = req.plan.upper().strip()
    if plan not in VALID_PLANS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz plan seçimi.")

    if not payment_svc.lemonsqueezy_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ödeme sağlayıcısı yapılandırılmamış.")

    user = get_user_by_id(user_id, db=db)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    pricing_cents = payment_svc.PLAN_PRICING[plan]
    # provider_reference: UniqueConstraint(provider, provider_reference) çakışmasın diye
    # her checkout denemesinde benzersiz bir placeholder üretiyoruz — asıl korelasyon
    # webhook'a gömülen kendi DBPayment.id'imiz üzerinden yapılıyor, bu alan sadece
    # şema kısıtını karşılamak için var.
    payment = create_payment_record(
        user_id=user_id, provider="lemonsqueezy", provider_reference=secrets.token_urlsafe(16),
        plan_tier=plan, amount=pricing_cents / 100, currency="USD", db=db,
    )
    payment_id = payment["id"]

    checkout_url = payment_svc.create_lemonsqueezy_checkout(
        user_email=user["email"], user_id=user_id, plan=plan, payment_record_id=payment_id,
    )
    if not checkout_url:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Ödeme başlatılamadı, lütfen tekrar deneyin.")

    return {"checkout_url": checkout_url}


@router.post("/webhooks/lemonsqueezy")
async def lemonsqueezy_webhook(request: Request, db: Session = Depends(get_db)):
    """Lemon Squeezy'nin çağırdığı webhook — kullanıcı auth'u YOK, güvenlik X-Signature
    imza doğrulamasından geliyor. Payload MUTLAKA ham byte olarak okunmalı (imza
    bunun üzerinden hesaplanıyor, parse edilmiş body üzerinden değil)."""
    payload = await request.body()
    sig_header = request.headers.get("x-signature", "")

    if not payment_svc.verify_lemonsqueezy_webhook(payload, sig_header):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz webhook imzası.")

    event = json.loads(payload)

    event_name = event.get("meta", {}).get("event_name")
    custom_data = event.get("meta", {}).get("custom_data", {}) or {}
    order_status = event.get("data", {}).get("attributes", {}).get("status")

    if event_name == "order_created" and order_status == "paid":
        payment_record_id = custom_data.get("payment_record_id")
        if payment_record_id:
            try:
                mark_payment_succeeded(int(payment_record_id), db=db)
            except (ValueError, TypeError):
                pass

    return {"status": "ok"}


@router.get("/history", response_model=List[PaymentSummary])
def payment_history(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Giriş yapmış kullanıcının kendi ödeme geçmişi."""
    return list_user_payments(user_id, db=db)
