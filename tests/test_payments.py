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

# ─────────────────────────────────────────────────────────────────────────────
# order_refunded / subscription_* iptal event'leri (task #37 — eskiden sadece
# order_created işleniyordu, iade/iptal durumunda kullanıcı süre dolana kadar
# ücretli limitlerde kalabiliyordu)
# ─────────────────────────────────────────────────────────────────────────────

def _lemonsqueezy_refund_payload(payment_record_id: int, user_id: int) -> bytes:
    event = {
        "meta": {
            "event_name": "order_refunded",
            "custom_data": {"payment_record_id": str(payment_record_id), "user_id": str(user_id)},
        },
        "data": {"type": "orders", "id": "order_" + uuid.uuid4().hex[:10], "attributes": {"status": "refunded"}},
    }
    return json.dumps(event).encode("utf-8")


def _lemonsqueezy_subscription_event_payload(event_name: str, user_id: int) -> bytes:
    event = {
        "meta": {
            "event_name": event_name,
            "custom_data": {"user_id": str(user_id)},
        },
        "data": {"type": "subscriptions", "id": "sub_" + uuid.uuid4().hex[:10], "attributes": {"status": event_name}},
    }
    return json.dumps(event).encode("utf-8")


def test_lemonsqueezy_order_refunded_downgrades_user_immediately(client, monkeypatch):
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
    assert _get_user(email).subscription_tier == "PRO"

    refund_payload = _lemonsqueezy_refund_payload(payment_id, user_id)
    refund_sig = _sign_lemonsqueezy_payload(refund_payload, "ls_test_secret")
    r2 = client.post("/api/payments/webhooks/lemonsqueezy", content=refund_payload,
                      headers={"x-signature": refund_sig, "content-type": "application/json"})
    assert r2.status_code == 200

    payment = _get_payment_by_id(payment_id)
    assert payment.status == "refunded"

    user = _get_user(email)
    assert user.subscription_tier == "FREE"
    assert user.subscription_status == "refunded"
    assert user.subscription_ends_at is None


def test_lemonsqueezy_subscription_cancelled_downgrades_user(client, monkeypatch):
    monkeypatch.setattr(payments_module, "LEMONSQUEEZY_WEBHOOK_SECRET", "ls_test_secret")

    email = unique_email()
    register_user(client, email)
    user_id = _user_id_for(email)

    payment_id = _make_pending_payment(user_id, "PRO", 19.0)
    payload = _lemonsqueezy_order_payload(payment_id, user_id, "PRO")
    sig_header = _sign_lemonsqueezy_payload(payload, "ls_test_secret")
    client.post("/api/payments/webhooks/lemonsqueezy", content=payload,
                headers={"x-signature": sig_header, "content-type": "application/json"})
    assert _get_user(email).subscription_tier == "PRO"

    cancel_payload = _lemonsqueezy_subscription_event_payload("subscription_cancelled", user_id)
    cancel_sig = _sign_lemonsqueezy_payload(cancel_payload, "ls_test_secret")
    resp = client.post("/api/payments/webhooks/lemonsqueezy", content=cancel_payload,
                        headers={"x-signature": cancel_sig, "content-type": "application/json"})
    assert resp.status_code == 200

    user = _get_user(email)
    assert user.subscription_tier == "FREE"
    assert user.subscription_status == "cancelled"


def test_lemonsqueezy_subscription_payment_failed_downgrades_user(client, monkeypatch):
    monkeypatch.setattr(payments_module, "LEMONSQUEEZY_WEBHOOK_SECRET", "ls_test_secret")

    email = unique_email()
    register_user(client, email)
    user_id = _user_id_for(email)

    payment_id = _make_pending_payment(user_id, "ENTERPRISE", 99.0)
    payload = _lemonsqueezy_order_payload(payment_id, user_id, "ENTERPRISE")
    sig_header = _sign_lemonsqueezy_payload(payload, "ls_test_secret")
    client.post("/api/payments/webhooks/lemonsqueezy", content=payload,
                headers={"x-signature": sig_header, "content-type": "application/json"})
    assert _get_user(email).subscription_tier == "ENTERPRISE"

    failed_payload = _lemonsqueezy_subscription_event_payload("subscription_payment_failed", user_id)
    failed_sig = _sign_lemonsqueezy_payload(failed_payload, "ls_test_secret")
    resp = client.post("/api/payments/webhooks/lemonsqueezy", content=failed_payload,
                        headers={"x-signature": failed_sig, "content-type": "application/json"})
    assert resp.status_code == 200

    user = _get_user(email)
    assert user.subscription_tier == "FREE"
    assert user.subscription_status == "payment_failed"


def test_lemonsqueezy_refund_without_payment_record_id_is_ignored_not_500(client, monkeypatch):
    """custom_data.payment_record_id eksikse (beklenmeyen payload şekli) endpoint
    500 patlamak yerine sessizce 200 dönüp loglamalı — webhook'lar tekrar denenmeye
    devam etmesin diye Lemon Squeezy'e her zaman 200 döneriz."""
    monkeypatch.setattr(payments_module, "LEMONSQUEEZY_WEBHOOK_SECRET", "ls_test_secret")

    event = {
        "meta": {"event_name": "order_refunded", "custom_data": {}},
        "data": {"type": "orders", "id": "order_x", "attributes": {"status": "refunded"}},
    }
    payload = json.dumps(event).encode("utf-8")
    sig_header = _sign_lemonsqueezy_payload(payload, "ls_test_secret")

    resp = client.post("/api/payments/webhooks/lemonsqueezy", content=payload,
                        headers={"x-signature": sig_header, "content-type": "application/json"})
    assert resp.status_code == 200


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
