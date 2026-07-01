"""
Çok kiracılı (multi-tenant) izolasyon testleri: bir kullanıcının diğer
kullanıcının verisine hiçbir şekilde erişememesi/etkileyememesi gerekir.
"""
import uuid


def _register(client, password="testpass123"):
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    resp = client.post("/api/users/register", json={"email": email, "name": "Test", "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_user_cannot_list_other_users_positions(client):
    headers_a = _register(client)
    headers_b = _register(client)

    created = client.post(
        "/api/positions",
        json={
            "ticker": "AAPL",
            "asset_class": "ABD Hisse/ETF",
            "quantity": 10,
            "buy_price": 100.0,
            "buy_date": "2026-01-01",
            "buy_currency": "USD",
        },
        headers=headers_a,
    )
    assert created.status_code == 200

    list_as_b = client.get("/api/positions", headers=headers_b)
    assert list_as_b.status_code == 200
    assert list_as_b.json() == []

    list_as_a = client.get("/api/positions", headers=headers_a)
    assert len(list_as_a.json()) == 1


def test_user_cannot_read_or_delete_other_users_position(client):
    headers_a = _register(client)
    headers_b = _register(client)

    created = client.post(
        "/api/positions",
        json={
            "ticker": "MSFT",
            "asset_class": "ABD Hisse/ETF",
            "quantity": 5,
            "buy_price": 200.0,
            "buy_date": "2026-01-01",
            "buy_currency": "USD",
        },
        headers=headers_a,
    )
    position_id = created.json()["id"]

    get_as_b = client.get(f"/api/positions/{position_id}", headers=headers_b)
    assert get_as_b.status_code == 404

    delete_as_b = client.delete(f"/api/positions/{position_id}", headers=headers_b)
    assert delete_as_b.status_code == 404

    # Pozisyon hâlâ sahibinde duruyor olmalı
    get_as_a = client.get(f"/api/positions/{position_id}", headers=headers_a)
    assert get_as_a.status_code == 200


def test_user_cannot_access_other_users_liabilities(client):
    headers_a = _register(client)
    headers_b = _register(client)

    created = client.post(
        "/api/liabilities",
        json={"name": "Kredi Kartı", "liability_type": "credit_card", "amount": 5000.0, "currency": "TRY"},
        headers=headers_a,
    )
    assert created.status_code == 200
    item_id = created.json()["id"]

    list_as_b = client.get("/api/liabilities", headers=headers_b)
    assert list_as_b.json() == []

    update_as_b = client.put(f"/api/liabilities/{item_id}", json={"amount": 1.0}, headers=headers_b)
    assert update_as_b.status_code == 404

    delete_as_b = client.delete(f"/api/liabilities/{item_id}", headers=headers_b)
    assert delete_as_b.status_code == 404


def test_free_tier_position_limit_enforced(client):
    headers = _register(client)
    payload = {
        "asset_class": "ABD Hisse/ETF",
        "quantity": 1,
        "buy_price": 10.0,
        "buy_date": "2026-01-01",
        "buy_currency": "USD",
    }
    for i in range(5):
        resp = client.post("/api/positions", json={**payload, "ticker": f"SYM{i}"}, headers=headers)
        assert resp.status_code == 200, resp.text

    over_limit = client.post("/api/positions", json={**payload, "ticker": "SYM99"}, headers=headers)
    assert over_limit.status_code == 403
