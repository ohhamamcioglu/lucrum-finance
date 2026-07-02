import hashlib
import hmac
import json
import time
import uuid

import payments as payments_module
from db_models import SessionLocal, DBUser, DBPayment
from crud import create_payment_record

from conftest import register_user


def unique_email() -> str:
    return f"pay-test-{uuid.uuid4().hex[:10]}@example.com"


def _user_id_for(email: str) -> int:
    session = SessionLocal()
    try:
        user = session.query(DBUser).filter(DBUser.email == email.lower().strip()).first()
        return user.id
    finally:
        session.close()


def _get_payment(provider: str, provider_reference: str):
    session = SessionLocal()
    try:
        return session.query(DBPayment).filter(
            DBPayment.provider == provider,
            DBPayment.provider_reference == provider_reference,
        ).first()
    finally:
        session.close()


def _get_user(email: str) -> DBUser:
    session = SessionLocal()
    try:
        user = session.query(DBUser).filter(DBUser.email == email.lower().strip()).first()
        session.expunge(user)
        return user
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# Anahtarsız (dev) ortamda güvenli düşüş
# ─────────────────────────────────────────────────────────────────────────────

def test_stripe_checkout_503_when_unconfigured(client, auth_headers):
    resp = client.post("/api/payments/stripe/checkout", json={"plan": "PRO"}, headers=auth_headers)
    assert resp.status_code == 503


def test_iyzico_checkout_503_when_unconfigured(client, auth_headers):
    resp = client.post(
        "/api/payments/iyzico/checkout",
        json={
            "plan": "PRO", "identity_number": "12345678901", "phone": "5551234567",
            "address": "Test Adres No:1", "city": "İstanbul", "country": "Türkiye",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 503


def test_checkout_rejects_invalid_plan(client, auth_headers):
    resp = client.post("/api/payments/stripe/checkout", json={"plan": "GOLD"}, headers=auth_headers)
    assert resp.status_code == 400


def test_checkout_requires_auth(client):
    resp = client.post("/api/payments/stripe/checkout", json={"plan": "PRO"})
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Mock subscribe bypass'ı kapandı mı
# ─────────────────────────────────────────────────────────────────────────────

def test_subscribe_rejects_paid_plans(client, auth_headers):
    resp = client.post("/api/users/subscribe", json={"plan": "PRO"}, headers=auth_headers)
    assert resp.status_code == 400

    resp2 = client.post("/api/users/subscribe", json={"plan": "ENTERPRISE"}, headers=auth_headers)
    assert resp2.status_code == 400


def test_subscribe_still_allows_free_downgrade(client, auth_headers):
    resp = client.post("/api/users/subscribe", json={"plan": "FREE"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["subscription_tier"] == "FREE"


# ─────────────────────────────────────────────────────────────────────────────
# Stripe webhook — imza doğrulama + idempotency (gerçek hesap gerekmez,
# Stripe'ın dokümante edilmiş HMAC algoritmasıyla elle imzalanıyor)
# ─────────────────────────────────────────────────────────────────────────────

def _sign_stripe_payload(payload_bytes: bytes, secret: str) -> str:
    ts = str(int(time.time()))
    signed_payload = f"{ts}.{payload_bytes.decode('utf-8')}"
    sig = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _stripe_event_payload(session_id: str, user_id: int, plan: str) -> bytes:
    event = {
        "id": "evt_test_" + uuid.uuid4().hex[:10],
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "payment_status": "paid",
                "client_reference_id": str(user_id),
                "metadata": {"user_id": str(user_id), "plan": plan},
            }
        },
    }
    return json.dumps(event).encode("utf-8")


def test_stripe_webhook_valid_signature_activates_subscription(client, monkeypatch):
    monkeypatch.setattr(payments_module, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")

    email = unique_email()
    register_user(client, email)
    user_id = _user_id_for(email)

    session_id = "cs_test_" + uuid.uuid4().hex[:10]
    create_payment_record(user_id, "stripe", session_id, "PRO", 19.0, "USD")

    payload = _stripe_event_payload(session_id, user_id, "PRO")
    sig_header = _sign_stripe_payload(payload, "whsec_test_secret")

    resp = client.post(
        "/api/payments/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": sig_header, "content-type": "application/json"},
    )
    assert resp.status_code == 200

    payment = _get_payment("stripe", session_id)
    assert payment.status == "succeeded"
    assert payment.completed_at is not None

    user = _get_user(email)
    assert user.subscription_tier == "PRO"
    assert user.subscription_ends_at is not None


def test_stripe_webhook_invalid_signature_rejected(client, monkeypatch):
    monkeypatch.setattr(payments_module, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")

    email = unique_email()
    register_user(client, email)
    user_id = _user_id_for(email)

    session_id = "cs_test_" + uuid.uuid4().hex[:10]
    create_payment_record(user_id, "stripe", session_id, "PRO", 19.0, "USD")

    payload = _stripe_event_payload(session_id, user_id, "PRO")
    bad_sig_header = _sign_stripe_payload(payload, "whsec_WRONG_secret")

    resp = client.post(
        "/api/payments/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": bad_sig_header, "content-type": "application/json"},
    )
    assert resp.status_code == 400

    # State değişmemeli — güvenlik regresyonu olmadığının kanıtı
    payment = _get_payment("stripe", session_id)
    assert payment.status == "pending"
    user = _get_user(email)
    assert user.subscription_tier == "FREE"


def test_stripe_webhook_idempotent_on_replay(client, monkeypatch):
    monkeypatch.setattr(payments_module, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")

    email = unique_email()
    register_user(client, email)
    user_id = _user_id_for(email)

    session_id = "cs_test_" + uuid.uuid4().hex[:10]
    create_payment_record(user_id, "stripe", session_id, "PRO", 19.0, "USD")

    payload = _stripe_event_payload(session_id, user_id, "PRO")
    sig_header = _sign_stripe_payload(payload, "whsec_test_secret")

    r1 = client.post("/api/payments/webhooks/stripe", content=payload,
                      headers={"stripe-signature": sig_header, "content-type": "application/json"})
    assert r1.status_code == 200
    payment_after_first = _get_payment("stripe", session_id)
    completed_at_first = payment_after_first.completed_at

    # Aynı webhook tekrar teslim edilirse (Stripe'ın gerçek dünyada yaptığı gibi)
    # tier ikinci kez uygulanmamalı / completed_at değişmemeli.
    r2 = client.post("/api/payments/webhooks/stripe", content=payload,
                      headers={"stripe-signature": sig_header, "content-type": "application/json"})
    assert r2.status_code == 200
    payment_after_second = _get_payment("stripe", session_id)
    assert payment_after_second.completed_at == completed_at_first

    user = _get_user(email)
    assert user.subscription_tier == "PRO"


# ─────────────────────────────────────────────────────────────────────────────
# iyzico callback (gerçek hesap gerekmez — retrieve_iyzico_payment monkeypatch'lenir)
# ─────────────────────────────────────────────────────────────────────────────

def test_iyzico_callback_success_activates_subscription(client, monkeypatch):
    monkeypatch.setattr(
        payments_module, "retrieve_iyzico_payment",
        lambda token: {"status": "success", "paymentStatus": "SUCCESS"},
    )

    email = unique_email()
    register_user(client, email)
    user_id = _user_id_for(email)

    token = "iyz-token-" + uuid.uuid4().hex[:10]
    create_payment_record(user_id, "iyzico", token, "ENTERPRISE", 3400.0, "TRY")

    resp = client.post("/api/payments/iyzico/callback", data={"token": token}, follow_redirects=False)
    assert resp.status_code == 302
    assert "payment=success" in resp.headers["location"]

    payment = _get_payment("iyzico", token)
    assert payment.status == "succeeded"
    user = _get_user(email)
    assert user.subscription_tier == "ENTERPRISE"


def test_iyzico_callback_failure_does_not_activate_subscription(client, monkeypatch):
    monkeypatch.setattr(
        payments_module, "retrieve_iyzico_payment",
        lambda token: {"status": "success", "paymentStatus": "FAILURE"},
    )

    email = unique_email()
    register_user(client, email)
    user_id = _user_id_for(email)

    token = "iyz-token-" + uuid.uuid4().hex[:10]
    create_payment_record(user_id, "iyzico", token, "PRO", 650.0, "TRY")

    resp = client.post("/api/payments/iyzico/callback", data={"token": token}, follow_redirects=False)
    assert resp.status_code == 302
    assert "payment=failed" in resp.headers["location"]

    payment = _get_payment("iyzico", token)
    assert payment.status == "failed"
    user = _get_user(email)
    assert user.subscription_tier == "FREE"


# ─────────────────────────────────────────────────────────────────────────────
# Ödeme geçmişi — tenant isolation
# ─────────────────────────────────────────────────────────────────────────────

def test_payment_history_only_shows_own_payments(client):
    email_a = unique_email()
    data_a = register_user(client, email_a)
    headers_a = {"Authorization": f"Bearer {data_a['access_token']}"}
    user_id_a = _user_id_for(email_a)

    email_b = unique_email()
    register_user(client, email_b)
    user_id_b = _user_id_for(email_b)

    ref_a = "cs_" + uuid.uuid4().hex[:10]
    ref_b = "cs_" + uuid.uuid4().hex[:10]
    create_payment_record(user_id_a, "stripe", ref_a, "PRO", 19.0, "USD")
    create_payment_record(user_id_b, "stripe", ref_b, "PRO", 19.0, "USD")

    resp = client.get("/api/payments/history", headers=headers_a)
    assert resp.status_code == 200
    refs = [p["provider"] for p in resp.json()]
    assert len(resp.json()) == 1
    assert resp.json()[0]["plan_tier"] == "PRO"
