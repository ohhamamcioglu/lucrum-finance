"""
Kritik iş mantığı testleri: portföy/K-Z motoru (services.py) ve pozisyon
güncelleme (crud.py) — bu modüller daha önce hiç test edilmemişti.

Ağ çağrısı gerektiren fonksiyonlar (Twelve Data, TCMB vb.) monkeypatch ile
sahtelenir — testler internet erişimine bağımlı olmamalı (CI'da flaky olur).
"""
from datetime import date, timedelta

import crud
import services
from db_models import SessionLocal, DBUser
from models import PositionCreate, PositionUpdate

from conftest import register_user


def _user_id_for(email: str) -> int:
    session = SessionLocal()
    try:
        user = session.query(DBUser).filter(DBUser.email == email.lower().strip()).first()
        assert user is not None
        return user.id
    finally:
        session.close()


def _new_user(client) -> tuple[dict, int]:
    import uuid
    email = f"svc-test-{uuid.uuid4().hex[:10]}@example.com"
    data = register_user(client, email)
    return {"Authorization": f"Bearer {data['access_token']}"}, _user_id_for(email)


# ─────────────────────────────────────────────────────────────────────────
# get_price_currency — saf eşleme fonksiyonu
# ─────────────────────────────────────────────────────────────────────────

def test_get_price_currency_mapping():
    assert services.get_price_currency("TEFAS Fonu") == "TRY"
    assert services.get_price_currency("BIST Hissesi") == "TRY"
    assert services.get_price_currency("ABD Hisse/ETF") == "USD"
    assert services.get_price_currency("Kripto") == "USD"


# ─────────────────────────────────────────────────────────────────────────
# get_usd_try_rate — 730 günden eski tarih fallback'i (bkz. task #31 fix)
# ─────────────────────────────────────────────────────────────────────────

def test_usd_try_rate_older_than_730_days_uses_oldest_available_series(monkeypatch):
    """Twelve Data'nın 730 günlük penceresinde istenen TARİHTEN eski hiçbir eşleşme
    yoksa, eskiden kod sessizce BUGÜNÜN kuruna düşüyordu (3 yıl önceki bir alım için
    yanlış maliyet/TWRR). Artık çekilen serideki en eski kur kullanılmalı."""
    monkeypatch.setattr(services, "get_exchange_rate", lambda *a, **kw: None)
    monkeypatch.setattr(services, "save_exchange_rate", lambda *a, **kw: None)
    monkeypatch.setattr(services._svc_fc, "get", lambda *a, **kw: None)
    monkeypatch.setattr(services._svc_fc, "set", lambda *a, **kw: None)

    # Seri, istenen tarihten SONRAKİ günlerden oluşuyor (yani hiçbiri <= date_str değil) —
    # gerçek "730 günden eski istek" senaryosunu taklit eder.
    fake_series = [
        {"date": "2024-06-10", "close": 31.5},
        {"date": "2024-06-05", "close": 31.0},  # en eski = beklenen dönüş değeri
        {"date": "2024-06-15", "close": 32.0},
    ]
    monkeypatch.setattr(services.td, "get_time_series", lambda *a, **kw: fake_series)

    # _fetch_current_rates_fast/td.get_exchange_rate çağrılırsa test'in "bugünün kuruna
    # düştüğünü" yakalamak için belirgin, yanlış bir sentinel değer döndürsünler.
    monkeypatch.setattr(services, "_fetch_current_rates_fast", lambda: None)
    monkeypatch.setattr(services.td, "get_exchange_rate", lambda *a, **kw: 999.0)

    rate = services.get_usd_try_rate("2020-01-01")  # >730 gün önce

    assert rate == 31.0  # en eski seri değeri — ne 999.0 (bugünün kuru) ne 35.0 (hard fallback)


def test_usd_try_rate_exact_match_within_window_returns_that_date(monkeypatch):
    """Kontrol testi: istenen tarih pencerede GERÇEKTEN varsa, en eski değere değil
    doğru eşleşen güne düşülmeli."""
    monkeypatch.setattr(services, "get_exchange_rate", lambda *a, **kw: None)
    monkeypatch.setattr(services, "save_exchange_rate", lambda *a, **kw: None)
    monkeypatch.setattr(services._svc_fc, "get", lambda *a, **kw: None)
    monkeypatch.setattr(services._svc_fc, "set", lambda *a, **kw: None)

    fake_series = [
        {"date": "2024-06-15", "close": 32.0},
        {"date": "2024-06-10", "close": 31.5},  # istenen tarihle eşleşen (<=) en yeni gün
        {"date": "2024-06-05", "close": 31.0},
    ]
    monkeypatch.setattr(services.td, "get_time_series", lambda *a, **kw: fake_series)

    rate = services.get_usd_try_rate("2024-06-12")

    assert rate == 31.5


# ─────────────────────────────────────────────────────────────────────────
# crud.update_position — faizli nakitte ağırlıklı ortalama alım tarihi (task #30 fix)
# ─────────────────────────────────────────────────────────────────────────

def test_interest_bearing_cash_topup_recalculates_weighted_average_buy_date(client):
    """1000 birim, 100 gün önce alınmış faizli nakit pozisyona 500 birim top-up
    yapılınca (yeni toplam 1500), buy_date artık:
        avg_days_held = round(1000 * 100 / 1500) = 67 gün önce olmalı.
    Bu, top-up'ın kendi sıfır gün faiz kazanmış payını doğru şekilde harmanlar —
    eskiden buy_date değişmediği için yeni eklenen tutar da retroaktif faiz kazanıyordu."""
    _, user_id = _new_user(client)

    old_buy_date = date.today() - timedelta(days=100)
    created = crud.create_position(user_id, PositionCreate(
        ticker="TRY-MEVDUAT",
        asset_class="Nakit",
        quantity=1000,
        buy_price=1.0,
        buy_date=old_buy_date,
        buy_currency="TRY",
        asset_type="cash",
        interest_rate=10.0,
    ))

    updated = crud.update_position(user_id, created.id, PositionUpdate(
        quantity=1500,
        delta_quantity=500,
        delta_price=1.0,
    ))

    assert updated is not None
    expected_days = round(1000 * 100 / 1500)  # 67
    expected_date = date.today() - timedelta(days=expected_days)
    assert updated["buy_date"] == expected_date


def test_partial_sell_does_not_recalculate_buy_date(client):
    """Kısmi satış (delta_quantity negatif) top-up değildir — orijinal alım tarihi
    hiç değişmemeli (fonksiyon sadece delta_quantity > 0 iken tetiklenir)."""
    _, user_id = _new_user(client)

    old_buy_date = date.today() - timedelta(days=50)
    created = crud.create_position(user_id, PositionCreate(
        ticker="TRY-MEVDUAT-2",
        asset_class="Nakit",
        quantity=1000,
        buy_price=1.0,
        buy_date=old_buy_date,
        buy_currency="TRY",
        asset_type="cash",
        interest_rate=10.0,
    ))

    updated = crud.update_position(user_id, created.id, PositionUpdate(
        quantity=600,
        delta_quantity=-400,
        delta_price=1.0,
    ))

    assert updated["buy_date"] == old_buy_date


def test_explicit_buy_date_override_is_respected(client):
    """Frontend top-up sırasında AÇIKÇA bir buy_date gönderirse, otomatik ağırlıklı
    ortalama hesaplaması devre dışı kalmalı (kullanıcının açık isteği önceliklidir)."""
    _, user_id = _new_user(client)

    old_buy_date = date.today() - timedelta(days=100)
    explicit_date = date.today() - timedelta(days=10)
    created = crud.create_position(user_id, PositionCreate(
        ticker="TRY-MEVDUAT-3",
        asset_class="Nakit",
        quantity=1000,
        buy_price=1.0,
        buy_date=old_buy_date,
        buy_currency="TRY",
        asset_type="cash",
        interest_rate=10.0,
    ))

    updated = crud.update_position(user_id, created.id, PositionUpdate(
        quantity=1500,
        delta_quantity=500,
        delta_price=1.0,
        buy_date=explicit_date,
    ))

    assert updated["buy_date"] == explicit_date


def test_non_interest_bearing_cash_topup_does_not_shift_buy_date(client):
    """interest_rate yoksa/0 ise ağırlıklı ortalama mantığı hiç tetiklenmemeli —
    faiz olmayan bir pozisyon için alım tarihinin anlamı yok, dokunmaya gerek yok."""
    _, user_id = _new_user(client)

    old_buy_date = date.today() - timedelta(days=100)
    created = crud.create_position(user_id, PositionCreate(
        ticker="USD-NAKIT",
        asset_class="Nakit",
        quantity=1000,
        buy_price=1.0,
        buy_date=old_buy_date,
        buy_currency="USD",
        asset_type="cash",
        interest_rate=None,
    ))

    updated = crud.update_position(user_id, created.id, PositionUpdate(
        quantity=1500,
        delta_quantity=500,
        delta_price=1.0,
    ))

    assert updated["buy_date"] == old_buy_date


# ─────────────────────────────────────────────────────────────────────────
# Input validation (task #25/#26) — API seviyesinde regresyon testleri
# ─────────────────────────────────────────────────────────────────────────

def test_negative_position_quantity_rejected(client, auth_headers):
    resp = client.post(
        "/api/positions",
        json={
            "ticker": "AAPL", "asset_class": "ABD Hisse/ETF",
            "quantity": -10, "buy_price": 100.0,
            "buy_date": "2026-01-01", "buy_currency": "USD",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_zero_position_buy_price_rejected(client, auth_headers):
    resp = client.post(
        "/api/positions",
        json={
            "ticker": "AAPL", "asset_class": "ABD Hisse/ETF",
            "quantity": 10, "buy_price": 0,
            "buy_date": "2026-01-01", "buy_currency": "USD",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_target_allocations_must_sum_to_100(client, auth_headers):
    resp = client.post(
        "/api/portfolio/targets",
        json=[
            {"asset_class": "ABD Hisse/ETF", "target_pct": 50},
            {"asset_class": "BIST Hissesi", "target_pct": 20},
        ],  # toplam %70 — reddedilmeli
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_target_allocations_summing_to_100_accepted(client, auth_headers):
    resp = client.post(
        "/api/portfolio/targets",
        json=[
            {"asset_class": "ABD Hisse/ETF", "target_pct": 60},
            {"asset_class": "BIST Hissesi", "target_pct": 40},
        ],
        headers=auth_headers,
    )
    assert resp.status_code == 200
