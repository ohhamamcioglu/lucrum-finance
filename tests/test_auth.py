import uuid


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
