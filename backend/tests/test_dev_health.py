"""
Health and readiness endpoints used by start_all.ps1 / diagnose.ps1, and the secret scrubbing of
the error text they report.
"""
import asyncio

from app.services import health


def test_health_has_app_marker(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    # start_all.ps1 relies on this marker to tell FIR VisionAI apart from another app on the same port
    assert res.json()["app"] == "fir-visionai"


def test_readiness_reports_database_and_storage(client):
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["app"] == "fir-visionai"
    assert body["status"] == "ready"
    assert body["checks"]["database"]["ok"] is True
    assert isinstance(body["checks"]["database"]["latency_ms"], int)
    assert body["checks"]["storage"]["ok"] is True


def test_readiness_returns_503_when_database_fails(client, monkeypatch):
    def broken():
        raise RuntimeError("could not connect to postgresql://admin:hunter2@db.example.co:5432/postgres")
    monkeypatch.setattr(health, "_select_one", broken)
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    db = body["checks"]["database"]
    assert db["ok"] is False
    assert "RuntimeError" in db["error"]
    assert "hunter2" not in res.text


def test_readiness_times_out_instead_of_hanging(monkeypatch):
    def slow():
        import time
        time.sleep(2)
    monkeypatch.setattr(health, "_select_one", slow)
    monkeypatch.setattr(health, "DB_TIMEOUT_SECONDS", 0.2)
    result = asyncio.run(health.check_database())
    assert result["ok"] is False
    assert "did not answer" in result["error"]


def test_safe_error_removes_credentials_and_tokens():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.c2lnbmF0dXJl"
    msg = health.safe_error(ValueError(f"postgresql://postgres:s3cret@host:5432/db failed; Bearer {jwt}"))
    assert "s3cret" not in msg
    assert jwt not in msg
    assert msg.startswith("ValueError: postgresql://***@host")
