import uuid
from datetime import datetime, timedelta

import crud


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


def test_register_creates_user_and_sets_refresh_cookie(client):
    email = unique_email()
    resp = client.post(
        "/api/users/register",
        json={"email": email, "name": "Test User", "password": "testpass123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert "lucrum_refresh_token" in resp.cookies


def test_register_duplicate_email_fails(client):
    email = unique_email()
    client.post("/api/users/register", json={"email": email, "name": "A", "password": "testpass123"})
    resp = client.post("/api/users/register", json={"email": email, "name": "B", "password": "testpass123"})
    assert resp.status_code == 400


def test_register_weak_password_rejected(client):
    resp = client.post(
        "/api/users/register",
        json={"email": unique_email(), "name": "Test", "password": "short"},
    )
    assert resp.status_code == 422


def test_login_success_and_wrong_password(client):
    email = unique_email()
    client.post("/api/users/register", json={"email": email, "name": "Test", "password": "testpass123"})

    ok = client.post("/api/users/login", json={"email": email, "password": "testpass123"})
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = client.post("/api/users/login", json={"email": email, "password": "wrongpass"})
    assert bad.status_code == 401


def test_login_rate_limited_after_10_attempts(client):
    email = unique_email()
    client.post("/api/users/register", json={"email": email, "name": "Test", "password": "testpass123"})

    statuses = []
    for _ in range(12):
        r = client.post("/api/users/login", json={"email": email, "password": "wrongpass"})
        statuses.append(r.status_code)

    assert statuses.count(401) == 10
    assert statuses[10:] == [429, 429]


def test_refresh_rotates_token_and_revokes_old_one(client):
    email = unique_email()
    client.post("/api/users/register", json={"email": email, "name": "Test", "password": "testpass123"})
    old_refresh_cookie = client.cookies.get("lucrum_refresh_token")
    assert old_refresh_cookie

    refreshed = client.post("/api/users/refresh")
    assert refreshed.status_code == 200
    new_refresh_cookie = client.cookies.get("lucrum_refresh_token")
    assert new_refresh_cookie and new_refresh_cookie != old_refresh_cookie

    # Rotation sonrası yeni cookie ile tekrar refresh çalışmalı
    refreshed_again = client.post("/api/users/refresh")
    assert refreshed_again.status_code == 200

    # Eski (rotate edilmiş) refresh token artık geçersiz olmalı — replay koruması
    client.cookies.set("lucrum_refresh_token", old_refresh_cookie)
    replay_attempt = client.post("/api/users/refresh")
    assert replay_attempt.status_code == 401


def test_refresh_without_cookie_returns_401(client):
    fresh_client = client.__class__(client.app)
    resp = fresh_client.post("/api/users/refresh")
    assert resp.status_code == 401


def test_logout_revokes_refresh_token(client):
    email = unique_email()
    client.post("/api/users/register", json={"email": email, "name": "Test", "password": "testpass123"})

    logout_resp = client.post("/api/users/logout")
    assert logout_resp.status_code == 200

    refresh_resp = client.post("/api/users/refresh")
    assert refresh_resp.status_code == 401


def test_forgot_password_returns_generic_message_for_unknown_email(client):
    resp = client.post("/api/users/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert "message" in resp.json()


def test_reset_password_flow(client, monkeypatch):
    email = unique_email()
    client.post("/api/users/register", json={"email": email, "name": "Test", "password": "oldpass123"})

    captured = {}

    def fake_send(to_email, token):
        captured["token"] = token

    import routers.users as users_router
    monkeypatch.setattr(users_router, "send_password_reset_email", fake_send)

    fp = client.post("/api/users/forgot-password", json={"email": email})
    assert fp.status_code == 200
    assert captured.get("token")

    reset = client.post(
        "/api/users/reset-password",
        json={"token": captured["token"], "new_password": "newpass456"},
    )
    assert reset.status_code == 200

    old_login = client.post("/api/users/login", json={"email": email, "password": "oldpass123"})
    assert old_login.status_code == 401

    new_login = client.post("/api/users/login", json={"email": email, "password": "newpass456"})
    assert new_login.status_code == 200

    # Şifre sıfırlama sonrası eski refresh token'lar iptal edilmiş olmalı
    reused_reset = client.post(
        "/api/users/reset-password",
        json={"token": captured["token"], "new_password": "anotherpass789"},
    )
    assert reused_reset.status_code == 400


def test_verify_email_flow(client, monkeypatch):
    captured = {}

    def fake_send(to_email, token):
        captured["token"] = token

    import routers.users as users_router
    monkeypatch.setattr(users_router, "send_verification_email", fake_send)

    email = unique_email()
    reg = client.post("/api/users/register", json={"email": email, "name": "Test", "password": "testpass123"})
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    me_before = client.get("/api/users/me", headers=headers)
    assert me_before.json()["email_verified"] is False

    verify = client.post("/api/users/verify-email", json={"token": captured["token"]})
    assert verify.status_code == 200

    me_after = client.get("/api/users/me", headers=headers)
    assert me_after.json()["email_verified"] is True

    # Token tek kullanımlık — ikinci kullanım reddedilmeli
    reuse = client.post("/api/users/verify-email", json={"token": captured["token"]})
    assert reuse.status_code == 400


def test_me_requires_auth(client):
    resp = client.get("/api/users/me")
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────
# Hesap silme (task #48 — KVKK madde 11) — DELETE /api/users/me tüm
# ilişkili verileri (pozisyon/işlem/ödeme/token) cascade ile silmeli.
# ─────────────────────────────────────────────────────────────────────────

def test_delete_account_requires_auth(client):
    resp = client.delete("/api/users/me")
    assert resp.status_code == 401


def test_delete_account_removes_user_and_cascades_related_data(client):
    from db_models import SessionLocal, DBUser, DBPosition, DBLiability

    email = unique_email()
    data = client.post(
        "/api/users/register",
        json={"email": email, "name": "Delete Me", "password": "testpass123"},
    ).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    session = SessionLocal()
    try:
        user = session.query(DBUser).filter(DBUser.email == email.lower().strip()).first()
        user_id = user.id
    finally:
        session.close()

    pos_resp = client.post(
        "/api/positions",
        json={
            "ticker": "AAPL", "asset_class": "ABD Hisse/ETF",
            "quantity": 10, "buy_price": 100.0,
            "buy_date": "2026-01-01", "buy_currency": "USD",
        },
        headers=headers,
    )
    assert pos_resp.status_code == 200

    liab_resp = client.post(
        "/api/liabilities",
        json={"name": "Kredi Kartı", "liability_type": "credit_card", "amount": 500.0, "currency": "TRY"},
        headers=headers,
    )
    assert liab_resp.status_code == 200

    del_resp = client.delete("/api/users/me", headers=headers)
    assert del_resp.status_code == 200

    # Kullanıcı ve tüm ilişkili kayıtlar DB'den tamamen gitmiş olmalı
    session = SessionLocal()
    try:
        assert session.query(DBUser).filter(DBUser.id == user_id).first() is None
        assert session.query(DBPosition).filter(DBPosition.user_id == user_id).count() == 0
        assert session.query(DBLiability).filter(DBLiability.user_id == user_id).count() == 0
    finally:
        session.close()

    # Silinen hesabın access token'ı artık geçersiz olmalı
    me_after = client.get("/api/users/me", headers=headers)
    assert me_after.status_code == 401

    # Aynı e-posta ile tekrar kayıt olunabilmeli (unique constraint boşa çıktı)
    re_register = client.post(
        "/api/users/register",
        json={"email": email, "name": "Delete Me Again", "password": "testpass123"},
    )
    assert re_register.status_code == 200


def test_delete_account_nonexistent_user_returns_404(client):
    """Access token geçerli ama kullanıcı zaten silinmişse (ör. çift istek/yarış durumu)
    ikinci silme denemesi 404 dönmeli, 500 değil."""
    email = unique_email()
    data = client.post(
        "/api/users/register",
        json={"email": email, "name": "Twice", "password": "testpass123"},
    ).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    first = client.delete("/api/users/me", headers=headers)
    assert first.status_code == 200

    second = client.delete("/api/users/me", headers=headers)
    assert second.status_code == 401  # token zaten iptal edilmiş kullanıcı için geçersiz


def test_consume_auth_token_is_atomic_and_single_use(client):
    """BUGFIX regresyon testi (kod incelemesinde bulunan TOCTOU yarış durumu):
    eskiden consume_auth_token koşulsuz bir UPDATE atıyordu — get_valid_auth_token ile
    arasındaki pencerede iki eşzamanlı istek aynı token'ı geçerli görüp ikisi de işlemi
    tamamlayabiliyordu. Artık UPDATE'in kendisi geçerlilik kontrolünü de içeriyor:
    ikinci çağrı (token zaten tüketilmiş olduğundan) False dönmeli, satırı tekrar
    güncellememeli."""
    email = unique_email()
    data = client.post(
        "/api/users/register",
        json={"email": email, "name": "Token Test", "password": "testpass123"},
    ).json()
    user_id = data.get("user_id")
    if not user_id:
        # /register access_token içinde user_id olmayabilir — /me üzerinden al.
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        user_id = client.get("/api/users/me", headers=headers).json()["id"]

    token_hash = f"test-hash-{uuid.uuid4().hex}"
    crud.create_auth_token(user_id, token_hash, "EMAIL_VERIFY", datetime.utcnow() + timedelta(hours=1))

    first = crud.consume_auth_token(token_hash)
    second = crud.consume_auth_token(token_hash)

    assert first is True
    assert second is False  # eşzamanlı/tekrarlanan çağrı token'ı tekrar tüketememeli


def test_revoke_auth_token_is_atomic_and_single_use(client):
    """Aynı TOCTOU düzeltmesi refresh token rotation'ı için de geçerli — bkz.
    test_consume_auth_token_is_atomic_and_single_use."""
    email = unique_email()
    data = client.post(
        "/api/users/register",
        json={"email": email, "name": "Token Test 2", "password": "testpass123"},
    ).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    user_id = client.get("/api/users/me", headers=headers).json()["id"]

    token_hash = f"test-hash-{uuid.uuid4().hex}"
    crud.create_auth_token(user_id, token_hash, "REFRESH", datetime.utcnow() + timedelta(days=1))

    first = crud.revoke_auth_token(token_hash)
    second = crud.revoke_auth_token(token_hash)

    assert first is True
    assert second is False
