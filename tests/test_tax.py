"""
Almanya & UK vergi modülleri testleri (Faz 3, task #58).

Kur sorgulayan fonksiyonlar (get_usd_try_rate vb.) ve calculate_portfolio ağ
çağrısı içerdiğinden monkeypatch ile sabitlenir — testler deterministik ve hızlı
kalır. Sparerpauschbetrag/ISA/kripto lot hesaplamaları TAMAMEN gerçek işlem
geçmişinden türetildiğinden, buradaki testler gerçek aritmeti doğrular (tahmini
değer yok).
"""
import uuid
from datetime import date, timedelta

import routers.tax as tax_module
from conftest import register_user


def unique_email() -> str:
    return f"tax-test-{uuid.uuid4().hex[:10]}@example.com"


def _fixed_rates(monkeypatch):
    monkeypatch.setattr(tax_module, "get_usd_try_rate", lambda *a, **kw: 40.0)
    monkeypatch.setattr(tax_module, "get_eur_try_rate", lambda *a, **kw: 44.0)
    monkeypatch.setattr(tax_module, "get_gbp_try_rate", lambda *a, **kw: 50.0)


def _auth(client):
    email = unique_email()
    data = register_user(client, email)
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_germany_requires_auth(client):
    resp = client.get("/api/tax/germany")
    assert resp.status_code == 401


def test_uk_requires_auth(client):
    resp = client.get("/api/tax/uk")
    assert resp.status_code == 401


def test_sparerpauschbetrag_default_exemption_is_single(client, monkeypatch):
    _fixed_rates(monkeypatch)
    headers = _auth(client)
    resp = client.get("/api/tax/germany", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sparerpauschbetrag"]["exemption_eur"] == 1000.0
    assert data["sparerpauschbetrag"]["married"] is False


def test_sparerpauschbetrag_married_doubles_exemption(client, monkeypatch):
    _fixed_rates(monkeypatch)
    headers = _auth(client)
    resp = client.get("/api/tax/germany?married=true", headers=headers)
    assert resp.json()["sparerpauschbetrag"]["exemption_eur"] == 2000.0


def test_sparerpauschbetrag_computes_realized_gain_from_real_transactions(client, monkeypatch):
    """Sparerpauschbetrag'ın gerçekleşmiş kazancı, GERÇEK BUY+SELL işlem çiftinden
    hesaplanmalı — uydurulmuş bir değer değil."""
    _fixed_rates(monkeypatch)
    headers = _auth(client)

    # EUR cinsinden pozisyon aç (buy_currency=EUR -> çevrim gerektirmez, doğrulaması kolay).
    pos = client.post(
        "/api/positions",
        json={
            "ticker": "SAP.DE", "asset_class": "ABD Hisse/ETF",
            "quantity": 10, "buy_price": 100.0,
            "buy_date": "2025-01-01", "buy_currency": "EUR",
        },
        headers=headers,
    )
    assert pos.status_code == 200, pos.text
    pos_id = pos.json()["id"]

    # Bu yıl 4 adet 150 EUR'dan sat (gerçekleşmiş kazanç = 4 * (150-100) = 200 EUR).
    today = date.today().isoformat()
    upd = client.put(
        f"/api/positions/{pos_id}",
        json={"delta_quantity": -4, "delta_price": 150.0},
        headers=headers,
    )
    assert upd.status_code == 200, upd.text

    resp = client.get("/api/tax/germany", headers=headers)
    assert resp.status_code == 200, resp.text
    summary = resp.json()["sparerpauschbetrag"]
    assert summary["realized_gain_eur"] == 200.0
    assert summary["remaining_eur"] == 800.0
    assert summary["used_pct"] == 20.0


def test_crypto_lot_older_than_one_year_is_tax_free(client, monkeypatch):
    _fixed_rates(monkeypatch)
    headers = _auth(client)

    old_date = (date.today() - timedelta(days=400)).isoformat()
    pos = client.post(
        "/api/positions",
        json={
            "ticker": "BTC", "asset_class": "Kripto",
            "quantity": 1.0, "buy_price": 20000.0,
            "buy_date": old_date, "buy_currency": "USD",
        },
        headers=headers,
    )
    assert pos.status_code == 200, pos.text

    resp = client.get("/api/tax/germany", headers=headers)
    lots = resp.json()["crypto_lots"]
    assert len(lots) == 1
    assert lots[0]["ticker"] == "BTC"
    assert lots[0]["tax_free"] is True
    assert lots[0]["days_until_tax_free"] == 0


def test_crypto_lot_younger_than_one_year_is_taxable(client, monkeypatch):
    _fixed_rates(monkeypatch)
    headers = _auth(client)

    recent_date = (date.today() - timedelta(days=30)).isoformat()
    client.post(
        "/api/positions",
        json={
            "ticker": "ETH", "asset_class": "Kripto",
            "quantity": 2.0, "buy_price": 1000.0,
            "buy_date": recent_date, "buy_currency": "USD",
        },
        headers=headers,
    )

    resp = client.get("/api/tax/germany", headers=headers)
    lots = resp.json()["crypto_lots"]
    assert len(lots) == 1
    assert lots[0]["tax_free"] is False
    assert lots[0]["days_until_tax_free"] == 335


def test_vorabpauschale_caps_at_actual_gain():
    """value_end_eur verildiğinde, Vorabpauschale gerçek değer artışını AŞMAMALI
    (§18 Abs. 1 Satz 3 InvStG) — fon değeri düşse bile matrah negatif olmamalı."""
    import tax_germany
    result = tax_germany.vorabpauschale_base(
        value_start_eur=10000, basiszins_pct=2.53, fund_type="equity",
        months_held=12, value_end_eur=9500,  # fon DEĞER KAYBETTİ
    )
    assert result["vorabpauschale_gross_eur"] == 0.0
    assert result["taxable_base_eur"] == 0.0
    assert result["capped_by_actual_gain"] is True


def test_vorabpauschale_endpoint_requires_auth(client):
    resp = client.post("/api/tax/germany/vorabpauschale", json={
        "value_start_eur": 10000, "basiszins_pct": 2.53,
    })
    assert resp.status_code == 401


def test_vorabpauschale_endpoint_returns_taxable_base(client):
    headers = _auth(client)
    resp = client.post(
        "/api/tax/germany/vorabpauschale",
        json={"value_start_eur": 10000, "basiszins_pct": 2.53, "fund_type": "equity", "months_held": 12},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["basisertrag_prorated_eur"] == 177.1
    assert data["teilfreistellung_pct"] == 30.0
    assert data["taxable_base_eur"] == 123.97


def test_isa_allowance_counts_only_current_uk_tax_year(client, monkeypatch):
    _fixed_rates(monkeypatch)
    headers = _auth(client)

    pos = client.post(
        "/api/positions",
        json={
            "ticker": "VWRL.L", "asset_class": "ABD Hisse/ETF",
            "quantity": 100, "buy_price": 50.0,
            "buy_date": "2020-01-01", "buy_currency": "GBP",
            "tax_wrapper": "ISA",
        },
        headers=headers,
    )
    assert pos.status_code == 200, pos.text
    pos_id = pos.json()["id"]

    # UK vergi yılı içinde bir top-up yap (bugünün tarihiyle GERÇEK bir BUY işlemi oluşur).
    upd = client.put(
        f"/api/positions/{pos_id}",
        json={"delta_quantity": 20, "delta_price": 55.0},
        headers=headers,
    )
    assert upd.status_code == 200, upd.text

    resp = client.get("/api/tax/uk", headers=headers)
    assert resp.status_code == 200, resp.text
    isa = resp.json()["isa_allowance"]
    assert isa["used_gbp"] == 1100.0  # 20 * 55.0
    assert isa["allowance_gbp"] == 20000.0
    assert isa["remaining_gbp"] == 18900.0


def test_bed_and_isa_uses_calculate_portfolio_unrealized_gain(client, monkeypatch):
    """calculate_portfolio ağ çağrısı içerdiğinden sahte bir portföy sonucu enjekte edilir —
    testin doğruladığı şey, endpoint'in bu veriyi doğru filtreleyip karşılaştırdığı."""
    _fixed_rates(monkeypatch)
    headers = _auth(client)

    pos = client.post(
        "/api/positions",
        json={
            "ticker": "LGEN.L", "asset_class": "ABD Hisse/ETF",
            "quantity": 500, "buy_price": 2.0,
            "buy_date": "2023-01-01", "buy_currency": "GBP",
            "tax_wrapper": "GIA",
        },
        headers=headers,
    )
    assert pos.status_code == 200, pos.text

    fake_portfolio = {"holdings": [
        {"ticker": "LGEN.L", "tax_wrapper": "GIA", "gross_return_gbp": 3500.0},
    ]}
    monkeypatch.setattr(tax_module, "calculate_portfolio", lambda *a, **kw: fake_portfolio)

    resp = client.get("/api/tax/uk?cgt_allowance_gbp=3000", headers=headers)
    assert resp.status_code == 200, resp.text
    bed = resp.json()["bed_and_isa"]
    assert bed["total_gia_unrealized_gain_gbp"] == 3500.0
    assert bed["exceeds_allowance"] is True
    assert bed["excess_gbp"] == 500.0


def test_bed_and_isa_omitted_without_cgt_allowance(client, monkeypatch):
    """Kullanıcı CGT muafiyet tutarını girmediyse bed_and_isa None döner —
    sistem bu tutarı ASLA kendiliğinden tahmin etmez."""
    _fixed_rates(monkeypatch)
    headers = _auth(client)
    resp = client.get("/api/tax/uk", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["bed_and_isa"] is None
