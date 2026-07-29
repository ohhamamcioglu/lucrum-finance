"""
Kritik iş mantığı testleri: portföy/K-Z motoru (services.py) ve pozisyon
güncelleme (crud.py) — bu modüller daha önce hiç test edilmemişti.

Ağ çağrısı gerektiren fonksiyonlar (Twelve Data, TCMB vb.) monkeypatch ile
sahtelenir — testler internet erişimine bağımlı olmamalı (CI'da flaky olur).
"""
from datetime import date, timedelta

import pytest

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


# ─────────────────────────────────────────────────────────────────────────
# bluelytics.py / services.get_ars_try_rate — Arjantin Blue Dollar (Faz 2,
# task #54). Kural: veri yoksa HİÇBİR ZAMAN tahmini/sabit bir değere
# düşülmez — None döner (kullanıcının açık talebi: yanlış/tahmini veri yok).
# ─────────────────────────────────────────────────────────────────────────

def test_bluelytics_get_latest_rates_returns_none_on_network_failure(monkeypatch):
    import bluelytics

    monkeypatch.setattr(bluelytics._fc, "get", lambda *a, **kw: None)
    monkeypatch.setattr(bluelytics._fc, "set", lambda *a, **kw: None)

    def _raise(*a, **kw):
        raise ConnectionError("simulated network failure")
    monkeypatch.setattr(bluelytics.requests, "get", _raise)

    assert bluelytics.get_latest_rates() is None
    assert bluelytics.get_blue_dollar_ars_per_usd() is None
    assert bluelytics.get_official_ars_per_usd() is None


def test_bluelytics_get_latest_rates_parses_real_shape(monkeypatch):
    import bluelytics

    monkeypatch.setattr(bluelytics._fc, "get", lambda *a, **kw: None)
    monkeypatch.setattr(bluelytics._fc, "set", lambda *a, **kw: None)

    fake_payload = {
        "oficial": {"value_avg": 1476.5, "value_sell": 1502.0, "value_buy": 1451.0},
        "blue": {"value_avg": 1513.5, "value_sell": 1530.0, "value_buy": 1497.0},
        "oficial_euro": {"value_avg": 1604.5},
        "blue_euro": {"value_avg": 1645.0},
        "last_update": "2026-07-17T19:45:54.009928-03:00",
    }

    class _FakeResp:
        def raise_for_status(self):
            pass
        def json(self):
            return fake_payload

    monkeypatch.setattr(bluelytics.requests, "get", lambda *a, **kw: _FakeResp())

    assert bluelytics.get_blue_dollar_ars_per_usd() == 1513.5
    assert bluelytics.get_official_ars_per_usd() == 1476.5


def test_ars_try_rate_derived_from_usd_try_and_blue_dollar(monkeypatch):
    """ars_try_rate = usd_try_rate / ars_per_usd_blue — canlı doğrulanan matematik
    (usd_try=47.17, ars_per_usd_blue=1513.5 -> ars_try≈0.031168)."""
    monkeypatch.setattr(services, "get_usd_try_rate", lambda *a, **kw: 47.172159)
    monkeypatch.setattr(services.bluelytics, "get_blue_dollar_ars_per_usd", lambda: 1513.5)
    monkeypatch.setattr(services, "save_exchange_rate", lambda *a, **kw: None)
    monkeypatch.setattr(services._svc_fc, "get", lambda *a, **kw: None)
    monkeypatch.setattr(services._svc_fc, "set", lambda *a, **kw: None)

    rate = services.get_ars_try_rate()

    # Kaynak fonksiyon 6 ondalığa yuvarlıyor — tolerans buna göre gevşetildi.
    assert rate == pytest.approx(47.172159 / 1513.5, rel=1e-4)


def test_ars_try_rate_returns_none_when_bluelytics_unavailable(monkeypatch):
    """Bluelytics çökerse (veya tarihsel veri hiç birikmemişse) sabit/tahmini bir
    kura DÜŞÜLMEMELİ — USD/EUR/GBP'nin aksine ARS için hiçbir hardcoded fallback yok."""
    monkeypatch.setattr(services._svc_fc, "get", lambda *a, **kw: None)
    monkeypatch.setattr(services.bluelytics, "get_blue_dollar_ars_per_usd", lambda: None)

    assert services.get_ars_try_rate() is None


def test_ars_try_rate_historical_date_without_db_cache_returns_none(monkeypatch):
    """Bluelytics'in tarihsel endpoint'i yok — DB'de o tarih için birikmiş gerçek
    bir kayıt yoksa None dönmeli, ASLA en yakın/tahmini bir değere düşülmemeli
    (get_usd_try_rate'teki 'en eski mevcut kuru kullan' fallback'i burada YOK)."""
    monkeypatch.setattr(services, "get_ars_exchange_rate", lambda *a, **kw: None)
    monkeypatch.setattr(services._svc_fc, "get", lambda *a, **kw: None)
    monkeypatch.setattr(services._svc_fc, "set", lambda *a, **kw: None)

    assert services.get_ars_try_rate("2024-01-15") is None


def test_ars_try_rate_historical_date_uses_db_cache_when_available(monkeypatch):
    monkeypatch.setattr(services, "get_ars_exchange_rate", lambda *a, **kw: 0.028)
    monkeypatch.setattr(services._svc_fc, "get", lambda *a, **kw: None)
    monkeypatch.setattr(services._svc_fc, "set", lambda *a, **kw: None)

    assert services.get_ars_try_rate("2024-01-15") == 0.028


def test_ticker_historical_prices_for_tefas_fund_uses_real_nav_not_flat_fallback(monkeypatch):
    """BUGFIX regresyon testi: TEFAS fonları (asset_type='fund') için performans grafiği
    düz bir çizgi (statik alım fiyatı) çiziyordu, çünkü get_ticker_historical_prices genel
    Yahoo/Twelve Data yolunu deniyordu — bu yol TEFAS'ın 3-4 harfli kodlarını (ör. "AFA")
    hiç tanımıyor (gerçek küresel ticker'lar değiller), her zaman boş/404 dönüyordu.
    Artık TEFAS'ın kendi gerçek NAV kaynağı (get_tefas_nav) doğrudan kullanılmalı."""
    import pandas as pd

    fake_nav = pd.Series(
        [1.10, 1.12, 1.09, 1.15],
        index=pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"]),
    )
    monkeypatch.setattr(services.td, "get_tefas_nav", lambda *a, **kw: fake_nav)

    result = services.get_ticker_historical_prices("AFA", "fund", date(2026, 7, 1), date(2026, 7, 4))

    assert result == {
        date(2026, 7, 1): 1.10,
        date(2026, 7, 2): 1.12,
        date(2026, 7, 3): 1.09,
        date(2026, 7, 4): 1.15,
    }
    # Değerler AYNI DEĞİL — asıl düzeltilen bug, tüm günlerin tek bir statik fiyata düşmesiydi.
    assert len(set(result.values())) > 1


def test_ticker_historical_prices_for_tefas_fund_returns_empty_on_failure(monkeypatch):
    """get_tefas_nav başarısız olursa (ağ hatası/boş sonuç), sessizce boş dict dönmeli —
    çağıran taraf (calculate_twrr_and_metrics) zaten statik alım fiyatına düşen bir
    fallback'e sahip; burada UYDURMA bir fiyat serisi üretilmemeli."""
    import pandas as pd

    monkeypatch.setattr(services.td, "get_tefas_nav", lambda *a, **kw: pd.Series(dtype=float))
    assert services.get_ticker_historical_prices("ZZZ", "fund", date(2026, 7, 1), date(2026, 7, 4)) == {}

    def _raise(*a, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(services.td, "get_tefas_nav", _raise)
    assert services.get_ticker_historical_prices("ZZZ", "fund", date(2026, 7, 1), date(2026, 7, 4)) == {}


def test_ticker_historical_prices_for_tefas_fund_never_blocks_on_live_fetch(monkeypatch):
    """REGRESYON: ilk düzeltme get_tefas_nav'ı live_fetch=True (varsayılan) ile çağırıyordu —
    bu, pytefas'ın 27 günlük parçalar halindeki SENKRON scrape'ini (parça başına ~6sn'ye
    kadar) HTTP isteğinin içine soktu ve performans grafiğini kullanılamayacak kadar
    yavaşlattı (production'da canlı olarak gözlemlendi). get_ticker_historical_prices
    ARTIK live_fetch=False geçmeli — sadece önbellekten okumalı, asla canlı ağ isteği
    tetiklememeli. Önbellek ayrı bir arka plan görevi ile doldurulur (bkz. tasks.py
    refresh_tefas_nav_task / scheduler.py refresh_tefas_nav_cache_job)."""
    captured_kwargs = {}

    def fake_get_tefas_nav(ticker, start, end, **kwargs):
        captured_kwargs.update(kwargs)
        import pandas as pd
        return pd.Series(dtype=float)

    monkeypatch.setattr(services.td, "get_tefas_nav", fake_get_tefas_nav)
    services.get_ticker_historical_prices("AFA", "fund", date(2026, 7, 1), date(2026, 7, 4))

    assert captured_kwargs.get("live_fetch") is False
