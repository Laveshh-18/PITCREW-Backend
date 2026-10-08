"""API tests that need no database. DB-backed tests belong in tests/api/ with a test Supabase project."""
import os

os.environ.setdefault("ADMIN_API_KEY", "a" * 40)
os.environ.setdefault("SENSOR_API_KEY", "s" * 40)
os.environ["DATABASE_URL"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.security import reset_security_state  # noqa: E402

client = TestClient(app)


def setup_function(_):
    reset_security_state()


def test_health_has_headers():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["version"] == "1.1.0"
    assert r.headers["X-Request-ID"] and r.headers["X-API-Version"] == "1.1.0"
    assert r.json()["time"].endswith("Z")


def test_request_id_is_echoed():
    assert client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"


def test_deep_health_without_db_is_503():
    r = client.get("/health?deep=true")
    assert r.status_code == 503 and r.json()["error"]["code"] == "DB_UNAVAILABLE"


def test_config_serves_constants():
    r = client.get("/v1/config")
    assert r.json()["FUSION_RADIUS_M"] == 20 and r.json()["MAX_CREWS"] == 3


def test_admin_requires_key():
    assert client.post("/v1/admin/seed").status_code == 401
    assert client.post("/v1/admin/seed", headers={"X-Admin-Key": "wrong"}).json()["error"]["code"] == "UNAUTHORIZED"
    assert client.patch("/v1/crews/crew-a", json={"shift_minutes": 400}).status_code == 401


def test_sensor_requires_key():
    assert client.post("/v1/sensor-events", json={}).status_code == 401


def test_fix_without_key_is_401():
    r = client.post("/v1/potholes/6f1c2a52-8f3e-4a53-9a55-0d1c8b5e7a10/fix", json={"crew_id": "crew-a"})
    assert r.status_code == 401


def test_validation_error_shape():
    r = client.get("/v1/potholes?limit=9999")
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_route_uses_error_format():
    assert client.get("/nope").json()["error"]["code"] == "NOT_FOUND"


def test_auth_failures_get_blocked_after_limit():
    for _ in range(10):
        client.post("/v1/admin/seed", headers={"X-Admin-Key": "wrong"})
    r = client.post("/v1/admin/seed", headers={"X-Admin-Key": "wrong"})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_evil_origin_gets_no_cors_header():
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
