from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import List

from models import (
    StripeCheckoutRequest, IyzicoCheckoutRequest, CheckoutResponse, PaymentSummary,
)
from crud import (
    create_payment_record, get_payment_by_reference,
    mark_payment_succeeded, mark_payment_failed, list_user_payments,
    get_user_by_id,
)
from dependencies import get_current_user_id, get_db
from rate_limit import limiter
import payments as payment_svc

router = APIRouter(prefix="/api/payments", tags=["Payments"])

VALID_PLANS = ("PRO", "ENTERPRISE")


@router.post("/stripe/checkout", response_model=CheckoutResponse)
@limiter.limit("10/minute")
def stripe_checkout(
    request: Request,
    req: StripeCheckoutRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Stripe Checkout Session başlatır (tek seferlik ödeme, kart bilgisi hiçbir zaman bize gelmez)."""
    plan = req.plan.upper().strip()
    if plan not in VALID_PLANS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz plan seçimi.")

    if not payment_svc.stripe_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe yapılandırılmamış.")

    user = get_user_by_id(user_id, db=db)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    session_id, checkout_url = payment_svc.create_stripe_checkout(user["email"], user_id, plan)
    pricing = payment_svc.PLAN_PRICING[plan]
    create_payment_record(
        user_id=user_id, provider="stripe", provider_reference=session_id,
        plan_tier=plan, amount=pricing["usd_cents"] / 100, currency="USD", db=db,
    )
    return {"checkout_url": checkout_url}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe'ın çağırdığı webhook — kullanıcı auth'u YOK, güvenlik Stripe-Signature
    imza doğrulamasından geliyor. Payload MUTLAKA ham byte olarak okunmalı (imza
    bunun üzerinden hesaplanıyor, parse edilmiş body üzerinden değil)."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = payment_svc.verify_stripe_webhook(payload, sig_header)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz webhook imzası.")

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        if session_obj["payment_status"] == "paid":
            payment = get_payment_by_reference("stripe", session_obj["id"], db=db)
            if payment:
                mark_payment_succeeded(payment.id, db=db)

    return {"status": "ok"}


@router.post("/iyzico/checkout", response_model=CheckoutResponse)
@limiter.limit("10/minute")
def iyzico_checkout(
    request: Request,
    req: IyzicoCheckoutRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """iyzico Checkout Form (hosted payment page) başlatır."""
    plan = req.plan.upper().strip()
    if plan not in VALID_PLANS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz plan seçimi.")

    if not payment_svc.iyzico_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="iyzico yapılandırılmamış.")

    user = get_user_by_id(user_id, db=db)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    result = payment_svc.create_iyzico_checkout(
        user_id=user_id,
        user_email=user["email"],
        user_name=user["name"],
        plan=plan,
        identity_number=req.identity_number,
        phone=req.phone,
        address=req.address,
        city=req.city,
        country=req.country,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Ödeme başlatılamadı, lütfen tekrar deneyin.")

    checkout_url, token = result
    pricing = payment_svc.PLAN_PRICING[plan]
    create_payment_record(
        user_id=user_id, provider="iyzico", provider_reference=token,
        plan_tier=plan, amount=pricing["try"], currency="TRY", db=db,
    )
    return {"checkout_url": checkout_url}


@router.post("/iyzico/callback")
async def iyzico_callback(token: str = Form(...), db: Session = Depends(get_db)):
    """iyzico'nun ödeme sonrası tarayıcıyı yönlendirdiği callback — form-encoded 'token'
    içerir. Asıl doğrulama burada DEĞİL, retrieve_iyzico_payment'ın sunucu-taraflı
    API çağrısında gerçekleşir (klasik Checkout Form akışı budur, ayrı bir imza yok)."""
    result = payment_svc.retrieve_iyzico_payment(token)
    payment = get_payment_by_reference("iyzico", token, db=db)

    if payment and payment_svc.iyzico_payment_succeeded(result):
        mark_payment_succeeded(payment.id, db=db)
        return RedirectResponse(f"{payment_svc.FRONTEND_URL}/pricing?payment=success", status_code=302)

    if payment:
        mark_payment_failed(payment.id, db=db)
    return RedirectResponse(f"{payment_svc.FRONTEND_URL}/pricing?payment=failed", status_code=302)


@router.get("/history", response_model=List[PaymentSummary])
def payment_history(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Giriş yapmış kullanıcının kendi ödeme geçmişi."""
    return list_user_payments(user_id, db=db)
