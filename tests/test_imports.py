"""
Esnek CSV/Excel içe aktarıcı testleri (Faz 2, task #57).
Gerçek broker export formatına özel bir varsayım YOK — testler, sütun başlığı eş
anlamlı eşlemesinin ve Türkçe sayı/tarih ayrıştırmasının uçtan uca (preview -> confirm)
doğru pozisyon oluşturduğunu, ayrıştırılamayan satırların ise atlanıp nedeniyle
raporlandığını doğrular.
"""
import io

from conftest import register_user


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8-sig")


def test_import_preview_requires_auth(client):
    resp = client.post("/api/imports/preview", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert resp.status_code == 401


def test_import_preview_rejects_unsupported_extension(client, auth_headers):
    resp = client.post(
        "/api/imports/preview",
        files={"file": ("statement.pdf", b"%PDF-1.4", "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Desteklenmeyen" in resp.json()["detail"]


def test_import_preview_auto_maps_turkish_headers(client, auth_headers):
    csv_content = _csv_bytes("Sembol,Adet,Fiyat,Tarih\nTHYAO,100,\"245,30\",15.01.2024\n")
    resp = client.post(
        "/api/imports/preview",
        files={"file": ("ekstre.csv", csv_content, "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["row_count"] == 1
    assert data["suggested_mapping"]["ticker"] == "Sembol"
    assert data["suggested_mapping"]["quantity"] == "Adet"
    assert data["suggested_mapping"]["buy_price"] == "Fiyat"
    assert data["suggested_mapping"]["buy_date"] == "Tarih"
    assert data["import_id"]


def test_import_confirm_creates_positions_end_to_end(client):
    email = "import-e2e@example.com"
    data = register_user(client, email)
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    csv_content = _csv_bytes(
        "Sembol,Adet,Fiyat,Tarih\n"
        "THYAO,100,\"245,30\",15.01.2024\n"
        "AAPL,10,\"1.234,56\",2024-02-20\n"
    )
    preview = client.post(
        "/api/imports/preview",
        files={"file": ("ekstre.csv", csv_content, "text/csv")},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    import_id = preview.json()["import_id"]
    mapping = preview.json()["suggested_mapping"]

    confirm = client.post(
        "/api/imports/confirm",
        json={
            "import_id": import_id,
            "mapping": mapping,
            "asset_class_default": "BIST Hissesi",
            "buy_currency_default": "TRY",
        },
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text
    result = confirm.json()
    assert result["created"] == 2
    assert result["skipped"] == 0
    assert result["errors"] == []

    positions = client.get("/api/positions", headers=headers).json()
    tickers = {p["ticker"] for p in positions}
    assert {"THYAO", "AAPL"} <= tickers


def test_import_confirm_skips_unparseable_rows_with_reason(client):
    email = "import-skip@example.com"
    data = register_user(client, email)
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    # İkinci satırda adet sayı değil ("XX") — bu satır UYDURULMAMALI, atlanmalı.
    csv_content = _csv_bytes(
        "Sembol,Adet,Fiyat,Tarih\n"
        "THYAO,100,245.30,2024-01-15\n"
        "GARAN,XX,50.00,2024-01-16\n"
    )
    preview = client.post(
        "/api/imports/preview",
        files={"file": ("ekstre.csv", csv_content, "text/csv")},
        headers=headers,
    )
    import_id = preview.json()["import_id"]
    mapping = preview.json()["suggested_mapping"]

    confirm = client.post(
        "/api/imports/confirm",
        json={
            "import_id": import_id,
            "mapping": mapping,
            "asset_class_default": "BIST Hissesi",
        },
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text
    result = confirm.json()
    assert result["created"] == 1
    assert result["skipped"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 1


def test_import_confirm_without_asset_class_default_or_mapping_skips_all(client):
    """Varlık sınıfı ne eşlenmiş ne de varsayılan verilmişse, satır UYDURULMAMALI — atlanır."""
    email = "import-noclass@example.com"
    data = register_user(client, email)
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    csv_content = _csv_bytes("Sembol,Adet,Fiyat,Tarih\nTHYAO,100,245.30,2024-01-15\n")
    preview = client.post(
        "/api/imports/preview",
        files={"file": ("ekstre.csv", csv_content, "text/csv")},
        headers=headers,
    )
    import_id = preview.json()["import_id"]
    mapping = preview.json()["suggested_mapping"]

    confirm = client.post(
        "/api/imports/confirm",
        json={"import_id": import_id, "mapping": mapping},
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text
    result = confirm.json()
    assert result["created"] == 0
    assert result["skipped"] == 1
    assert "Varlık sınıfı" in result["errors"][0]["reason"]


def test_import_confirm_unknown_import_id_returns_404(client, auth_headers):
    resp = client.post(
        "/api/imports/confirm",
        json={"import_id": "does-not-exist", "mapping": {}, "asset_class_default": "Kripto"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_import_confirm_is_single_use(client):
    """Aynı import_id ikinci kez confirm edilirse (çift tıklama/yeniden gönderim), tekrar
    pozisyon oluşturmamalı — cache tek kullanımlık olduğundan 404 dönmeli."""
    email = "import-singleuse@example.com"
    data = register_user(client, email)
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    csv_content = _csv_bytes("Sembol,Adet,Fiyat,Tarih\nTHYAO,100,245.30,2024-01-15\n")
    preview = client.post(
        "/api/imports/preview",
        files={"file": ("ekstre.csv", csv_content, "text/csv")},
        headers=headers,
    )
    import_id = preview.json()["import_id"]
    mapping = preview.json()["suggested_mapping"]
    payload = {"import_id": import_id, "mapping": mapping, "asset_class_default": "BIST Hissesi"}

    first = client.post("/api/imports/confirm", json=payload, headers=headers)
    assert first.status_code == 200
    assert first.json()["created"] == 1

    second = client.post("/api/imports/confirm", json=payload, headers=headers)
    assert second.status_code == 404
