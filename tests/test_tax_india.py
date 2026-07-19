"""
Hindistan vergi modülü testleri (Faz 3.5, task #59).

mfapi.in ağ çağrısı içeren fonksiyonlar (india.py router) monkeypatch ile
sahtelenir. §80C/ELSS kilitlenme/LTCG-STCG sınıflandırması TAMAMEN gerçek işlem
geçmişinden türetildiğinden, buradaki testler gerçek aritmetiği doğrular.
"""
import uuid
from datetime import date, timedelta

import routers.india as india_module
from conftest import register_user


def unique_email() -> str:
    return f"india-test-{uuid.uuid4().hex[:10]}@example.com"


def _auth(client):
    email = unique_email()
    data = register_user(client, email)
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_india_tax_requires_auth(client):
    resp = client.get("/api/tax/india")
    assert resp.status_code == 401


def test_section_80c_counts_only_elss_buys_this_fy(client):
    headers = _auth(client)
    client.post(
        "/api/positions",
        json={
            "ticker": "AXISELSS", "asset_class": "AMFI Fonu",
            "quantity": 1000, "buy_price": 50.0,
            "buy_date": "2026-05-01", "buy_currency": "INR",
            "tax_wrapper": "ELSS",
        },
        headers=headers,
    )
    resp = client.get("/api/tax/india", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["section_80c"]["used_inr"] == 50000.0  # 1000 * 50
    assert data["section_80c"]["limit_inr"] == 150000.0
    assert data["section_80c"]["remaining_inr"] == 100000.0


def test_elss_lockin_reflects_real_buy_date(client):
    headers = _auth(client)
    recent_date = (date.today() - timedelta(days=100)).isoformat()
    client.post(
        "/api/positions",
        json={
            "ticker": "AXISELSS", "asset_class": "AMFI Fonu",
            "quantity": 1000, "buy_price": 50.0,
            "buy_date": recent_date, "buy_currency": "INR",
            "tax_wrapper": "ELSS",
        },
        headers=headers,
    )
    resp = client.get("/api/tax/india", headers=headers)
    lots = resp.json()["elss_lots"]
    assert len(lots) == 1
    assert lots[0]["locked"] is True
    assert lots[0]["ticker"] == "AXISELSS"


def test_ltcg_stcg_omitted_without_rates(client):
    """Kullanıcı LTCG/STCG oranlarını girmediyse ltcg_stcg None döner —
    sistem bu oranları ASLA kendiliğinden varsaymaz."""
    headers = _auth(client)
    resp = client.get("/api/tax/india", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ltcg_stcg"] is None


def test_ltcg_stcg_computed_from_real_sell_transaction(client):
    headers = _auth(client)
    old_date = (date.today() - timedelta(days=400)).isoformat()
    pos = client.post(
        "/api/positions",
        json={
            "ticker": "RELIANCE", "asset_class": "AMFI Fonu",
            "quantity": 100, "buy_price": 1000.0,
            "buy_date": old_date, "buy_currency": "INR",
        },
        headers=headers,
    )
    assert pos.status_code == 200, pos.text
    pos_id = pos.json()["id"]

    # Tamamını sat -> LTCG (400 gün > 365)
    upd = client.put(
        f"/api/positions/{pos_id}",
        json={"delta_quantity": -100, "delta_price": 1500.0},
        headers=headers,
    )
    assert upd.status_code == 200, upd.text

    resp = client.get(
        "/api/tax/india?ltcg_rate_pct=12.5&stcg_rate_pct=20&ltcg_exemption_inr=125000",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    ltcg_stcg = resp.json()["ltcg_stcg"]
    assert ltcg_stcg["ltcg_total_inr"] == 50000.0  # 100 * (1500-1000)
    assert ltcg_stcg["stcg_total_inr"] == 0.0
    assert ltcg_stcg["ltcg_taxable_inr"] == 0.0  # 50000 < 125000 muafiyet


def test_india_fund_search_requires_auth(client):
    resp = client.get("/api/india/funds/search?query=axis")
    assert resp.status_code == 401


def test_india_fund_search_returns_real_shaped_results(client, monkeypatch):
    headers = _auth(client)
    monkeypatch.setattr(
        india_module.mfapi, "search_funds",
        lambda query, limit=20: [{"schemeCode": 112323, "schemeName": "Axis ELSS Tax Saver Fund - Regular Plan - Growth"}],
    )
    resp = client.get("/api/india/funds/search?query=axis", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["schemeCode"] == 112323


def test_india_fund_detail_404_when_not_found(client, monkeypatch):
    headers = _auth(client)
    monkeypatch.setattr(india_module.mfapi, "get_fund_data", lambda scheme_code: None)
    resp = client.get("/api/india/funds/999999999", headers=headers)
    assert resp.status_code == 404
