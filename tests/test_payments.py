import hashlib
import hmac
import json
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


def _get_payment_by_id(payment_id: int) -> DBPayment:
    session = SessionLocal()
    try:
        payment = session.query(DBPayment).filter(DBPayment.id == payment_id).first()
        session.expunge(payment)
        return payment
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


def _make_pending_payment(user_id: int, plan: str, amount: float) -> int:
    payment = create_payment_record(
        user_id, "lemonsqueezy", f"placeholder-{uuid.uuid4().hex[:10]}", plan, amount, "USD"
    )
    return payment["id"]


# ─────────────────────────────────────────────────────────────────────────────
# Anahtarsız (dev) ortamda güvenli düşüş
# ─────────────────────────────────────────────────────────────────────────────

def test_lemonsqueezy_checkout_503_when_unconfigured(client, auth_headers):
    resp = client.post("/api/payments/lemonsqueezy/checkout", json={"plan": "PRO"}, headers=auth_headers)
    assert resp.status_code == 503


def test_checkout_rejects_invalid_plan(client, auth_headers):
    resp = client.post("/api/payments/lemonsqueezy/checkout", json={"plan": "GOLD"}, headers=auth_headers)
    assert resp.status_code == 400


def test_checkout_requires_auth(client):
    resp = client.post("/api/payments/lemonsqueezy/checkout", json={"plan": "PRO"})
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
# Lemon Squeezy webhook — imza doğrulama + idempotency (gerçek hesap gerekmez,
# Lemon Squeezy'nin dokümante edilmiş HMAC-SHA256 algoritmasıyla elle imzalanıyor)
# ─────────────────────────────────────────────────────────────────────────────

def _sign_lemonsqueezy_payload(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _lemonsqueezy_order_payload(payment_record_id: int, user_id: int, plan: str) -> bytes:
    event = {
        "meta": {
            "event_name": "order_created",
            "custom_data": {
                "payment_record_id": str(payment_record_id),
                "user_id": str(user_id),
                "plan": plan,
            },
        },
        "data": {
            "type": "orders",
            "id": "order_" + uuid.uuid4().hex[:10],
            "attributes": {"status": "paid"},
        },
    }
    return json.dumps(event).encode("utf-8")


def test_lemonsqueezy_webhook_valid_signature_activates_subscription(client, monkeypatch):
    monkeypatch.setattr(payments_module, "LEMONSQUEEZY_WEBHOOK_SECRET", "ls_test_secret")

    email = unique_email()
    register_user(client, email)
    user_id = _user_id_for(email)

    payment_id = _make_pending_payment(user_id, "PRO", 19.0)

    payload = _lemonsqueezy_order_payload(payment_id, user_id, "PRO")
    sig_header = _sign_lemonsqueezy_payload(payload, "ls_test_secret")

    resp = client.post(
        "/api/payments/webhooks/lemonsqueezy",
        content=payload,
        headers={"x-signature": sig_header, "content-type": "application/json"},
    )
    assert resp.status_code == 200

    payment = _get_payment_by_id(payment_id)
    assert payment.status == "succeeded"
    assert payment.completed_at is not None

    user = _get_user(email)
    assert user.subscription_tier == "PRO"
    assert user.subscription_ends_at is not None


def test_lemonsqueezy_webhook_invalid_signature_rejected(client, monkeypatch):
    monkeypatch.setattr(payments_module, "LEMONSQUEEZY_WEBHOOK_SECRET", "ls_test_secret")

    email = unique_email()
    register_user(client, email)
    user_id = _user_id_for(email)

    payment_id = _make_pending_payment(user_id, "PRO", 19.0)

    payload = _lemonsqueezy_order_payload(payment_id, user_id, "PRO")
    bad_sig_header = _sign_lemonsqueezy_payload(payload, "ls_WRONG_secret")

    resp = client.post(
        "/api/payments/webhooks/lemonsqueezy",
        content=payload,
        headers={"x-signature": bad_sig_header, "content-type": "application/json"},
    )
    assert resp.status_code == 400

    # State değişmemeli — güvenlik regresyonu olmadığının kanıtı
    payment = _get_payment_by_id(payment_id)
    assert payment.status == "pending"
    user = _get_user(email)
    assert user.subscription_tier == "FREE"


def test_lemonsqueezy_webhook_idempotent_on_replay(client, monkeypatch):
    monkeypatch.setattr(payments_module, "LEMONSQUEEZY_WEBHOOK_SECRET", "ls_test_secret")

    email = unique_email()
    register_user(client, email)
    user_id = _user_id_for(email)

    payment_id = _make_pending_payment(user_id, "PRO", 19.0)

    payload = _lemonsqueezy_order_payload(payment_id, user_id, "PRO")
    sig_header = _sign_lemonsqueezy_payload(payload, "ls_test_secret")

    r1 = client.post("/api/payments/webhooks/lemonsqueezy", content=payload,
                      headers={"x-signature": sig_header, "content-type": "application/json"})
    assert r1.status_code == 200
    completed_at_first = _get_payment_by_id(payment_id).completed_at

    # Aynı webhook tekrar teslim edilirse (gerçek dünyada olabileceği gibi)
    # tier ikinci kez uygulanmamalı / completed_at değişmemeli.
    r2 = client.post("/api/payments/webhooks/lemonsqueezy", content=payload,
                      headers={"x-signature": sig_header, "content-type": "application/json"})
    assert r2.status_code == 200
    assert _get_payment_by_id(payment_id).completed_at == completed_at_first

    user = _get_user(email)
    assert user.subscription_tier == "PRO"


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

    _make_pending_payment(user_id_a, "PRO", 19.0)
    _make_pending_payment(user_id_b, "PRO", 19.0)

    resp = client.get("/api/payments/history", headers=headers_a)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["plan_tier"] == "PRO"
