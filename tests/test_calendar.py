"""
Portföy temettü takvimi testleri (Faz 3, task #58).

twelve_data.get_dividends() ağ çağrısı içerdiğinden monkeypatch ile sahtelenir.
total_amount = gerçek pay başı temettü × kullanıcının gerçekten sahip olduğu adet
olduğu, ve tarihsiz/eksik kayıtların UYDURULMADAN atlandığı doğrulanır.
"""
import uuid

import routers.calendar as calendar_module
from conftest import register_user


def unique_email() -> str:
    return f"calendar-test-{uuid.uuid4().hex[:10]}@example.com"


def _auth(client):
    email = unique_email()
    data = register_user(client, email)
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_dividend_calendar_requires_auth(client):
    resp = client.get("/api/calendar/dividends")
    assert resp.status_code == 401


def test_dividend_calendar_computes_real_total_from_holding_quantity(client, monkeypatch):
    headers = _auth(client)
    client.post(
        "/api/positions",
        json={
            "ticker": "AAPL", "asset_class": "ABD Hisse/ETF",
            "quantity": 150, "buy_price": 180.0,
            "buy_date": "2024-01-01", "buy_currency": "USD",
        },
        headers=headers,
    )

    monkeypatch.setattr(
        calendar_module.td, "get_dividends",
        lambda ticker: [{"date": "2026-05-11", "amount": 0.27, "frequency": None, "description": None}],
    )

    resp = client.get("/api/calendar/dividends", headers=headers)
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    assert len(events) == 1
    assert events[0]["ticker"] == "AAPL"
    assert events[0]["quantity_held"] == 150
    assert events[0]["total_amount"] == 40.5  # 0.27 * 150 -- gerçek aritmetik, tahmin değil


def test_dividend_calendar_skips_entries_without_date(client, monkeypatch):
    """Twelve Data'nın bozuk/tarihsiz dönebildiği kayıtlar (bkz. twelve_data.py'deki
    ex_date bugfix'i) sessizce atlanmalı — asla uydurma bir tarihle doldurulmamalı."""
    headers = _auth(client)
    client.post(
        "/api/positions",
        json={
            "ticker": "GARAN.IS", "asset_class": "BIST Hissesi",
            "quantity": 50, "buy_price": 90.0,
            "buy_date": "2024-01-01", "buy_currency": "TRY",
        },
        headers=headers,
    )

    monkeypatch.setattr(
        calendar_module.td, "get_dividends",
        lambda ticker: [{"date": None, "amount": 5.0, "frequency": None, "description": None}],
    )

    resp = client.get("/api/calendar/dividends", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["events"] == []


def test_dividend_calendar_excludes_non_dividend_asset_classes(client, monkeypatch):
    """TEFAS fonları ve kripto için klasik temettü kavramı yok — bu ticker'lar için
    get_dividends hiç çağrılmamalı."""
    headers = _auth(client)
    client.post(
        "/api/positions",
        json={
            "ticker": "BTC", "asset_class": "Kripto",
            "quantity": 1, "buy_price": 30000.0,
            "buy_date": "2024-01-01", "buy_currency": "USD",
        },
        headers=headers,
    )

    calls = []
    monkeypatch.setattr(calendar_module.td, "get_dividends", lambda ticker: calls.append(ticker) or [])

    resp = client.get("/api/calendar/dividends", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["events"] == []
    assert calls == []
