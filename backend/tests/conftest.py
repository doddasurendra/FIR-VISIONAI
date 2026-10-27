import pytest
import os
import sys
from fastapi.testclient import TestClient

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# The suite creates users, drafts and approvals. Never let it run against the live Supabase database.
from app.database import is_postgres  # noqa: E402
if is_postgres and os.getenv("FIR_ALLOW_TESTS_ON_POSTGRES") != "1":
    pytest.exit(
        "Refusing to run tests: the configured database is PostgreSQL (Supabase), so the tests would write "
        "test users and documents into live data. Run .\\run_tests.ps1, which uses a temporary SQLite database.",
        returncode=2,
    )

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def station_token(client):
    res = client.post("/api/v1/auth/login", json={"username": "station_officer", "password": "StationPass@2024"})
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture
def district_token(client):
    res = client.post("/api/v1/auth/login", json={"username": "district_admin", "password": "DistrictPass@2024"})
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture
def state_token(client):
    res = client.post("/api/v1/auth/login", json={"username": "state_director", "password": "StateAdmin@2024"})
    assert res.status_code == 200
    return res.json()["access_token"]
