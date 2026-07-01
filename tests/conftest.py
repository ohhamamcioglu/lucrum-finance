"""
Pytest fixture'ları. Backend'i izole, geçici bir SQLite DB ile test eder —
gerçek portfolio.db/dev verisine hiçbir zaman dokunmaz.

DATABASE_URL ve diğer env değişkenleri, backend modülleri import edilmeden
ÖNCE set edilmeli (db_models.py engine'i import anında kurar).
"""
import os
import sys
import tempfile

import pytest

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND_DIR)

_db_fd, _db_path = tempfile.mkstemp(suffix=".db", prefix="lucrum_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-do-not-use-in-production"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000"
os.environ["RESEND_API_KEY"] = ""  # dev/no-op mod: email gönderilmez
os.environ["COOKIE_SECURE"] = "false"

from db_models import Base, engine  # noqa: E402
Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient  # noqa: E402
from app import app  # noqa: E402
from rate_limit import limiter  # noqa: E402


@pytest.fixture(scope="session")
def client():
    # Bilerek `with` kullanılmıyor: lifespan (scheduler/crawler, dış API çağrıları)
    # tetiklenmesin diye. Testler sadece route handler'larını çalıştırır.
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Her testten önce rate limit sayaçlarını sıfırla — testler birbirini etkilemesin."""
    limiter.reset()
    yield


def register_user(client, email: str, name: str = "Test User", password: str = "testpass123"):
    resp = client.post(
        "/api/users/register",
        json={"email": email, "name": name, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def auth_headers(client):
    """Yeni bir kullanıcı kaydeder ve Authorization header'ını döner."""
    import uuid
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    data = register_user(client, email)
    return {"Authorization": f"Bearer {data['access_token']}"}
