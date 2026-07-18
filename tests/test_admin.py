import uuid

from db_models import SessionLocal, DBUser

from conftest import register_user


def unique_email() -> str:
    return f"admin-test-{uuid.uuid4().hex[:10]}@example.com"


def _make_admin(email: str) -> None:
    session = SessionLocal()
    try:
        user = session.query(DBUser).filter(DBUser.email == email.lower().strip()).first()
        assert user is not None
        user.is_admin = True
        session.commit()
    finally:
        session.close()


def _admin_headers(client):
    """Yeni bir kullanıcı kaydeder, DB'de is_admin=True yapar, header döner."""
    email = unique_email()
    data = register_user(client, email)
    _make_admin(email)
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_non_admin_cannot_list_users(client, auth_headers):
    resp = client.get("/api/admin/users", headers=auth_headers)
    assert resp.status_code == 403


def test_non_admin_cannot_view_stats(client, auth_headers):
    resp = client.get("/api/admin/stats", headers=auth_headers)
    assert resp.status_code == 403


def test_admin_can_list_and_search_users(client):
    admin_headers = _admin_headers(client)
    email = unique_email()
    register_user(client, email, name="Aranan Kullanici")

    listed = client.get("/api/admin/users?page=1&page_size=50", headers=admin_headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 2
    assert any(u["email"] == email for u in body["items"])

    searched = client.get(f"/api/admin/users?search={email}", headers=admin_headers)
    assert searched.status_code == 200
    search_body = searched.json()
    assert search_body["total"] == 1
    assert search_body["items"][0]["email"] == email


def test_admin_can_update_subscription_tier(client):
    admin_headers = _admin_headers(client)
    email = unique_email()
    data = register_user(client, email)
    target_headers = {"Authorization": f"Bearer {data['access_token']}"}

    me = client.get("/api/users/me", headers=target_headers)
    user_id = me.json()["id"]

    patched = client.patch(
        f"/api/admin/users/{user_id}",
        json={"subscription_tier": "PRO"},
        headers=admin_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["subscription_tier"] == "PRO"

    me_after = client.get("/api/users/me", headers=target_headers)
    assert me_after.json()["subscription_tier"] == "PRO"


def test_admin_update_rejects_invalid_tier(client):
    admin_headers = _admin_headers(client)
    email = unique_email()
    data = register_user(client, email)
    user_id = client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    ).json()["id"]

    resp = client.patch(
        f"/api/admin/users/{user_id}",
        json={"subscription_tier": "GOLD"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_admin_can_disable_user_and_login_blocked(client):
    admin_headers = _admin_headers(client)
    email = unique_email()
    data = register_user(client, email, password="testpass123")
    user_id = client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    ).json()["id"]

    disabled = client.patch(
        f"/api/admin/users/{user_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False

    blocked_login = client.post("/api/users/login", json={"email": email, "password": "testpass123"})
    assert blocked_login.status_code == 403


def test_admin_cannot_disable_self(client):
    admin_headers = _admin_headers(client)
    me = client.get("/api/users/me", headers=admin_headers)
    admin_id = me.json()["id"]

    resp = client.patch(
        f"/api/admin/users/{admin_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_admin_update_requires_at_least_one_field(client):
    admin_headers = _admin_headers(client)
    me = client.get("/api/users/me", headers=admin_headers)
    admin_id = me.json()["id"]

    resp = client.patch(f"/api/admin/users/{admin_id}", json={}, headers=admin_headers)
    assert resp.status_code == 400


def test_admin_stats_endpoint_shape(client):
    admin_headers = _admin_headers(client)
    resp = client.get("/api/admin/stats", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    for key in ("total_users", "active_users", "verified_users", "admin_users", "tier_breakdown"):
        assert key in body
    assert body["total_users"] >= 1
    assert isinstance(body["tier_breakdown"], dict)


# ─────────────────────────────────────────────────────────────────────────────
# Audit log (task #53) — tier/aktiflik değişimi otomatik kaydediliyor mu
# ─────────────────────────────────────────────────────────────────────────────

def test_non_admin_cannot_view_audit_log(client, auth_headers):
    resp = client.get("/api/admin/audit-log", headers=auth_headers)
    assert resp.status_code == 403


def test_tier_change_creates_audit_log_entry(client):
    admin_headers = _admin_headers(client)
    email = unique_email()
    data = register_user(client, email)
    user_id = client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    ).json()["id"]

    client.patch(f"/api/admin/users/{user_id}", json={"subscription_tier": "PRO"}, headers=admin_headers)

    log_resp = client.get("/api/admin/audit-log", headers=admin_headers)
    assert log_resp.status_code == 200
    entries = log_resp.json()["items"]
    match = next((e for e in entries if e["action"] == "tier_change" and e["target_user_id"] == user_id), None)
    assert match is not None
    assert match["target_email"] == email
    assert "PRO" in match["details"]


def test_toggle_active_creates_audit_log_entry(client):
    admin_headers = _admin_headers(client)
    email = unique_email()
    data = register_user(client, email)
    user_id = client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    ).json()["id"]

    client.patch(f"/api/admin/users/{user_id}", json={"is_active": False}, headers=admin_headers)

    log_resp = client.get("/api/admin/audit-log", headers=admin_headers)
    entries = log_resp.json()["items"]
    match = next((e for e in entries if e["action"] == "toggle_active" and e["target_user_id"] == user_id), None)
    assert match is not None


def test_audit_log_survives_target_user_deletion(client):
    """Hedef kullanıcı sonradan hesabını silse bile (bkz. DELETE /api/users/me),
    audit log kaydı kaybolmamalı — DBAuditLog, DBUser üzerinde ORM cascade
    ilişkisi olarak TANIMLANMADI (kasıtlı: audit geçmişi kullanıcı silinince
    silinmemeli), bu yüzden session.delete(user) audit_logs'a dokunmaz.
    Not: FK'lerin ondelete='SET NULL' olması Postgres'te (prod) sütunu
    gerçekten null'lar ama SQLite (test DB'si) varsayılan olarak FK
    enforcement'ı kapalı tuttuğundan bu davranışı burada doğrulayamıyoruz —
    asıl garanti ettiğimiz şey (kaydın e-posta ile hâlâ bulunabilir olması)
    her iki backend'de de doğru."""
    admin_headers = _admin_headers(client)
    email = unique_email()
    data = register_user(client, email)
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    user_id = client.get("/api/users/me", headers=headers).json()["id"]

    client.patch(f"/api/admin/users/{user_id}", json={"subscription_tier": "PRO"}, headers=admin_headers)
    client.delete("/api/users/me", headers=headers)

    log_resp = client.get("/api/admin/audit-log", headers=admin_headers)
    entries = log_resp.json()["items"]
    match = next((e for e in entries if e["action"] == "tier_change" and e["target_email"] == email), None)
    assert match is not None


# ─────────────────────────────────────────────────────────────────────────────
# Destek amaçlı portföy görüntüleme (task #53) — calculate_portfolio ağ çağrısı
# yaptığından burada monkeypatch ile sahtelenir (bkz. test_services.py'deki not).
# ─────────────────────────────────────────────────────────────────────────────

def test_non_admin_cannot_view_other_users_portfolio(client, auth_headers):
    resp = client.get("/api/admin/users/1/portfolio", headers=auth_headers)
    assert resp.status_code == 403


def test_admin_view_portfolio_returns_404_for_unknown_user(client):
    admin_headers = _admin_headers(client)
    resp = client.get("/api/admin/users/999999999/portfolio", headers=admin_headers)
    assert resp.status_code == 404


def test_admin_view_portfolio_returns_data_and_logs_access(client, monkeypatch):
    import routers.admin as admin_router

    fake_portfolio = {"totalValue": 12345.0, "holdings": []}
    monkeypatch.setattr(admin_router, "calculate_portfolio", lambda user_id: fake_portfolio)

    admin_headers = _admin_headers(client)
    email = unique_email()
    data = register_user(client, email)
    user_id = client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    ).json()["id"]

    resp = client.get(f"/api/admin/users/{user_id}/portfolio", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == fake_portfolio

    log_resp = client.get("/api/admin/audit-log", headers=admin_headers)
    entries = log_resp.json()["items"]
    match = next((e for e in entries if e["action"] == "view_portfolio" and e["target_user_id"] == user_id), None)
    assert match is not None
    assert match["target_email"] == email
