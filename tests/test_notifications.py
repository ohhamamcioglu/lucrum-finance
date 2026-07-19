"""
Dashboard bildirim akışı (/api/notifications/news) testleri — Faz 2, task #56.

Bug: TEFAS pozisyonları bu akıştan tamamen atlanıyordu (bkz. routers/notifications.py
fetch_ticker_news eski hali: `if _is_tefas(ticker): return []`). Bu, kullanıcının
BIST hisseleri için zil ikonunda gerçek KAP bildirimlerini görürken TEFAS fonları
için HİÇBİR ŞEY görmemesi anlamına geliyordu — halbuki görev açıkça "BIST hisselerine
VE TEFAS fonlarına özel KAP haberlerini dashboard'a yansıtma" diyordu.

Ağ çağrısı gerektiren fonksiyonlar (KAP, Google News RSS) monkeypatch ile sahtelenir.
"""
import uuid

import routers.notifications as notif_module

from conftest import register_user


def unique_email() -> str:
    return f"notif-test-{uuid.uuid4().hex[:10]}@example.com"


def test_notifications_news_requires_auth(client):
    resp = client.get("/api/notifications/news")
    assert resp.status_code == 401


def test_tefas_position_gets_real_kap_disclosures_not_skipped(client, monkeypatch):
    """Asıl regresyon testi: TEFAS pozisyonu artık boş liste değil, gerçek KAP
    fon bildirimlerini (_get_fund_disclosures_data üzerinden) dashboard bildirim
    akışına dahil ediyor."""
    monkeypatch.setattr(notif_module, "_fetch_google_news_rss", lambda *a, **kw: [])

    fake_disclosures = {
        "fund_code": "BIH",
        "fund_name": "Test Portföy BIH Fonu",
        "kap_page": "https://www.kap.org.tr/tr/fon-bildirimleri/test-bih",
        "pys_oid_found": True,
        "disclosures": [
            {
                "index": 12345,
                "title": "Portföy Dağılım Değişikliği",
                "subject": "Fon portföy dağılımında değişiklik yapılmıştır.",
                "publish_date": "2026-07-15T10:00:00",
                "year": 2026,
                "url": "https://www.kap.org.tr/tr/Bildirim/12345",
            },
        ],
        "note": "",
    }
    monkeypatch.setattr(notif_module, "_get_fund_disclosures_data", lambda *a, **kw: fake_disclosures)

    email = unique_email()
    data = register_user(client, email)
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    pos = client.post(
        "/api/positions",
        json={
            "ticker": "BIH", "asset_class": "TEFAS Fonu",
            "quantity": 100, "buy_price": 8.0,
            "buy_date": "2026-01-01", "buy_currency": "TRY",
        },
        headers=headers,
    )
    assert pos.status_code == 200

    resp = client.get("/api/notifications/news", headers=headers)
    assert resp.status_code == 200
    items = resp.json()

    kap_items = [i for i in items if i.get("ticker") == "BIH" and i.get("source") == "KAP"]
    assert len(kap_items) == 1
    assert kap_items[0]["title"] == "Portföy Dağılım Değişikliği"
    assert kap_items[0]["url"] == "https://www.kap.org.tr/tr/Bildirim/12345"
    assert kap_items[0]["tag"] == "portfolio"


def test_tefas_position_with_no_disclosures_does_not_crash(client, monkeypatch):
    """_get_fund_disclosures_data boş/hata dönerse endpoint 500 patlamamalı,
    sadece o pozisyon için haber olmadan devam etmeli."""
    monkeypatch.setattr(notif_module, "_fetch_google_news_rss", lambda *a, **kw: [])
    monkeypatch.setattr(notif_module, "_get_fund_disclosures_data", lambda *a, **kw: {"disclosures": []})

    email = unique_email()
    data = register_user(client, email)
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    client.post(
        "/api/positions",
        json={
            "ticker": "YAS", "asset_class": "TEFAS Fonu",
            "quantity": 50, "buy_price": 10.0,
            "buy_date": "2026-01-01", "buy_currency": "TRY",
        },
        headers=headers,
    )

    resp = client.get("/api/notifications/news", headers=headers)
    assert resp.status_code == 200
