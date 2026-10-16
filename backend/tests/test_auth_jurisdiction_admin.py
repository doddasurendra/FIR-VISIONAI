import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_jurisdictions_master_data():
    """Verify official Andhra Pradesh master data endpoints."""
    # 1. Districts list
    res = client.get("/api/v1/jurisdictions/districts")
    assert res.status_code == 200
    districts = res.json()
    assert len(districts) == 26
    assert "Kurnool" in districts
    assert "Guntur" in districts
    assert "Visakhapatnam" in districts

    # 2. Stations list for a district
    s_res = client.get("/api/v1/jurisdictions/stations?district=Kurnool")
    assert s_res.status_code == 200
    stations = s_res.json()
    assert "Kurnool Town Station" in stations

    # 3. Invalid district returns 404
    bad_res = client.get("/api/v1/jurisdictions/stations?district=NonExistentDistrict")
    assert bad_res.status_code == 404

    # 4. Jurisdiction summary
    sum_res = client.get("/api/v1/jurisdictions/summary")
    assert sum_res.status_code == 200
    summary = sum_res.json()
    assert summary["total_districts"] == 26
    assert summary["total_stations"] > 100

    # 5. Reverse geocode location matching
    geo_res = client.get("/api/v1/jurisdictions/reverse-geocode?latitude=15.82&longitude=78.03")
    assert geo_res.status_code == 200
    geo_data = geo_res.json()
    assert geo_data["detected_district"] == "Kurnool"
    assert "Kurnool Town Station" in geo_data["candidate_stations"]
    assert "disclaimer" in geo_data
    assert geo_data["confidence"] == "HIGH"


def test_self_registration_station_role():
    """Station officers self-register and are activated for testing."""
    unique_user = f"station_test_{uuid.uuid4().hex[:6]}"
    reg_payload = {
        "username": unique_user,
        "email": f"{unique_user}@apexcise.gov.in",
        "password": "TestOfficer@2024",
        "confirm_password": "TestOfficer@2024",
        "full_name": "Test Station Officer",
        "role": "STATION",
        "district": "Guntur",
        "station": "Guntur-1 Station",
        "badge_number": "EXC-GNT-999",
        "designation": "Excise Sub-Inspector"
    }

    res = client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["approval_status"] == "APPROVED"
    assert data["is_active"] is True

    # Immediate login should succeed
    login_res = client.post("/api/v1/auth/login", json={
        "username": unique_user,
        "password": "TestOfficer@2024"
    })
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

def test_self_registration_privileged_role_requires_approval():
    """Privileged roles (DISTRICT, STATE) self-registration must require admin approval."""
    unique_user = f"district_test_{uuid.uuid4().hex[:6]}"
    reg_payload = {
        "username": unique_user,
        "email": f"{unique_user}@apexcise.gov.in",
        "password": "PrivPass@2024",
        "confirm_password": "PrivPass@2024",
        "full_name": "Test District Applicant",
        "role": "DISTRICT",
        "district": "Visakhapatnam",
        "station": None,
        "badge_number": "AP-VSP-888",
        "designation": "Assistant Superintendent"
    }

    res = client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["approval_status"] == "PENDING_APPROVAL"
    assert data["is_active"] is False

    # Attempted login before approval MUST return 403 Forbidden
    login_res = client.post("/api/v1/auth/login", json={
        "username": unique_user,
        "password": "PrivPass@2024"
    })
    assert login_res.status_code == 403
    assert "pending administrative review" in login_res.json()["detail"].lower()

def test_duplicate_registration_prevention():
    """Duplicate username and email registrations must be rejected with 400."""
    payload = {
        "username": "station_officer", # Existing user
        "email": "unique_email_test@apexcise.gov.in",
        "password": "Password@2024",
        "confirm_password": "Password@2024",
        "full_name": "Duplicate User",
        "role": "STATION",
        "district": "Kurnool",
        "station": "Kurnool Town Station"
    }
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 400
    assert "already registered" in res.json()["detail"]

def test_admin_approval_and_password_reset_workflow():
    """State admin approves pending user and can reset password."""
    # 1. Register a pending district officer
    unique_user = f"pending_officer_{uuid.uuid4().hex[:6]}"
    reg_res = client.post("/api/v1/auth/register", json={
        "username": unique_user,
        "email": f"{unique_user}@apexcise.gov.in",
        "password": "InitialPass@2024",
        "confirm_password": "InitialPass@2024",
        "full_name": "Officer Pending Approval",
        "role": "DISTRICT",
        "district": "Kurnool",
        "station": None
    })
    emp_id = reg_res.json()["user_id"]

    # 2. Login as state_director
    admin_login = client.post("/api/v1/auth/login", json={
        "username": "state_director",
        "password": "StateAdmin@2024"
    })
    admin_token = admin_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 3. Approve the officer
    app_res = client.post(f"/api/v1/employees/{emp_id}/approve", headers=headers)
    assert app_res.status_code == 200

    # 4. Now login as the approved officer succeeds
    user_login = client.post("/api/v1/auth/login", json={
        "username": unique_user,
        "password": "InitialPass@2024"
    })
    assert user_login.status_code == 200

    # 5. Admin resets officer password
    reset_res = client.post(
        f"/api/v1/employees/{emp_id}/reset-password",
        json={"new_password": "NewResetPassword@2024"},
        headers=headers
    )
    assert reset_res.status_code == 200

    # 6. Login with new password succeeds
    login_new = client.post("/api/v1/auth/login", json={
        "username": unique_user,
        "password": "NewResetPassword@2024"
    })
    assert login_new.status_code == 200

def test_token_refresh_rotation():
    """Verify refresh token endpoint issues new access and rotated refresh token."""
    login_res = client.post("/api/v1/auth/login", json={
        "username": "developer_test",
        "password": "DevPass@2024"
    })
    assert login_res.status_code == 200
    ref_token = login_res.json()["refresh_token"]

    ref_res = client.post("/api/v1/auth/refresh", json={"refresh_token": ref_token})
    assert ref_res.status_code == 200
    ref_data = ref_res.json()
    assert "access_token" in ref_data
    assert "refresh_token" in ref_data
    assert ref_data["user"]["username"] == "developer_test"
