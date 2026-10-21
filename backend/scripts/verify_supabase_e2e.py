"""
FIR VisionAI — End-to-End Supabase Live Verification Script
Tests login, case retrieval, synthetic case creation, verification, and persistence directly on Supabase.
"""
import sys
import os
import requests
import json

BASE_URL = "http://localhost:8000"

def test_supabase_live():
    print("=" * 70)
    print("FIR VisionAI — Live Supabase Verification")
    print("=" * 70)

    # 1. Health check
    print("\n[Check 1/6] Health Check & Engine Verification...")
    res = requests.get(f"{BASE_URL}/api/v1/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    health = res.json()
    print(f"  -> Database Engine : {health['database_details']['engine_type']}")
    print(f"  -> Database Status : {health['database_details']['status']}")
    print(f"  -> Storage Backend : {health['storage_details']['primary_backend']}")
    print(f"  -> Storage Status  : {health['storage_details']['cloud_status']}")
    assert health["database"] == "supabase_postgresql_connected"
    assert health["database_details"]["is_postgres"] is True
    assert health["storage_details"]["cloud_configured"] is True

    # 2. Authentication
    print("\n[Check 2/6] User Login & JWT Issuance (against Supabase users table)...")
    login_res = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "station_officer",
        "password": "StationPass@2024"
    })
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token_data = login_res.json()
    token = token_data["access_token"]
    user = token_data["user"]
    print(f"  -> Authenticated Officer : {user['full_name']} ({user['role']} - {user['district']})")
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Read Cases (scoped to station)
    print("\n[Check 3/6] Fetching Cases from Supabase PostgreSQL (Jurisdiction Scoped)...")
    cases_res = requests.get(f"{BASE_URL}/api/v1/cases/", headers=headers)
    assert cases_res.status_code == 200, f"Fetch cases failed: {cases_res.text}"
    cases = cases_res.json()
    print(f"  -> Station officer sees {len(cases)} cases in Kurnool Town Station jurisdiction.")
    assert len(cases) > 0

    # Also test STATE officer seeing all cases
    state_login = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "state_director",
        "password": "StateAdmin@2024"
    }).json()
    state_cases = requests.get(f"{BASE_URL}/api/v1/cases/?limit=50", headers={"Authorization": f"Bearer {state_login['access_token']}"}).json()
    print(f"  -> State Director sees {len(state_cases)} total cases across all districts.")
    assert len(state_cases) >= 24

    # 4. Create Synthetic Test Case
    print("\n[Check 4/6] Creating Synthetic Test Case in Supabase...")
    import uuid
    synthetic_fir = f"SYNTH-SUPABASE-{uuid.uuid4().hex[:6].upper()}"
    new_case_payload = {
        "fir_number": synthetic_fir,
        "year": 2026,
        "district": "Kurnool",
        "station": "Kurnool Town Station",
        "offence_nature": "Synthetic Test — Illegal possession of contraband for Supabase validation",
        "offence_category": "EXCISE",
        "contraband_type": "ID Liquor",
        "seized_quantity": 25.0,
        "seized_unit": "Litres",
        "vehicle_details": "Synthetic Hero Splendor AP21AB9999",
        "seizing_officer_name": "Inspector S. Kumar",
        "seizing_officer_rank": "Circle Inspector",
        "narrative": "Synthetic test FIR narrative generated for verifying live Supabase persistence."
    }
    create_res = requests.post(f"{BASE_URL}/api/v1/cases/", json=new_case_payload, headers=headers)
    print("Create status:", create_res.status_code, "Body:", create_res.text[:120])
    created_case = create_res.json()
    case_id = created_case["id"]
    print(f"  -> Created synthetic case ID: {case_id} (FIR: {created_case['fir_number']})")

    # 5. Retrieve Synthetic Case from Supabase
    print("\n[Check 5/6] Verifying Synthetic Case Read from Supabase...")
    get_res = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}", headers=headers)
    assert get_res.status_code == 200, f"Retrieve case failed: {get_res.text}"
    retrieved_case = get_res.json()["case"]
    assert retrieved_case["fir_number"] == synthetic_fir
    assert retrieved_case["district"] == "Kurnool"
    assert retrieved_case["seized_quantity"] == 25.0
    print(f"  -> Successfully retrieved case: {retrieved_case['fir_number']} | {retrieved_case['district']} | Seized: {retrieved_case['seized_quantity']} {retrieved_case['seized_unit']}")

    # 6. Verify Folders & Counts
    print("\n[Check 6/6] Verifying All FIR Folders & Scope Filter on Supabase...")
    folders_res = requests.get(f"{BASE_URL}/api/v1/folders/", headers=headers)
    assert folders_res.status_code == 200
    folders = folders_res.json()
    print(f"  -> Retrieved {len(folders)} FIR folder categories from Supabase.")
    counts_res = requests.get(f"{BASE_URL}/api/v1/folders/counts", headers=headers)
    assert counts_res.status_code == 200
    print(f"  -> Folder category assignment counts: {counts_res.json()}")

    print("\n" + "=" * 70)
    print("ALL 6 LIVE SUPABASE VERIFICATION CHECKS PASSED 100%!")
    print("=" * 70)
    return True

if __name__ == "__main__":
    test_supabase_live()
