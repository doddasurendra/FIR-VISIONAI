import requests
import json
import uuid

BASE = "http://localhost:8000/api/v1"

def run_verification():
    print("==================================================")
    print("   FIR SAHAYAK — FULL SYSTEM LIVE VERIFICATION    ")
    print("==================================================")

    # 1. Jurisdictions
    print("\n[1] JURISDICTION MASTER DATA (26 AP DISTRICTS)")
    r = requests.get(f"{BASE}/jurisdictions/districts")
    districts = r.json()
    print(f"[PASS] Total AP Districts: {len(districts)}")
    assert len(districts) == 26
    
    r2 = requests.get(f"{BASE}/jurisdictions/stations?district=Kurnool")
    k_stations = r2.json()
    print(f"[PASS] Kurnool Stations ({len(k_stations)}): {k_stations[:3]}...")
    assert len(k_stations) >= 5

    # 2. Authentication (All 4 Demo Accounts)
    print("\n[2] AUTHENTICATION — ALL 4 DEMO ACCOUNTS")
    accounts = [
        ("developer_test", "DevPass@2024", "STATE (Lead Dev / Architect)"),
        ("station_officer", "StationPass@2024", "STATION (Kurnool Town)"),
        ("district_admin", "DistrictPass@2024", "DISTRICT (Kurnool Superintendent)"),
        ("state_director", "StateAdmin@2024", "STATE (Commissioner Headquarters)")
    ]
    tokens = {}
    for u, p, desc in accounts:
        lr = requests.post(f"{BASE}/auth/login", json={"username": u, "password": p})
        assert lr.status_code == 200, f"Login failed for {u}: {lr.text}"
        data = lr.json()
        tokens[u] = data["access_token"]
        print(f"[PASS] {u:<16} | Role: {data['user']['role']:<8} | District: {data['user']['district']:<22} | {desc}")

    # 3. Self-Registration Workflow
    print("\n[3] SELF-REGISTRATION WORKFLOW & ROLE GOVERNANCE")
    # A. Station officer self-registers -> Activated automatically
    su = f"station_rep_{uuid.uuid4().hex[:5]}"
    reg_res = requests.post(f"{BASE}/auth/register", json={
        "username": su,
        "email": f"{su}@apexcise.gov.in",
        "password": "OfficerPass@2024",
        "confirm_password": "OfficerPass@2024",
        "full_name": "Sub-Inspector Rep Officer",
        "role": "STATION",
        "district": "Kurnool",
        "station": "Kurnool Town Station",
        "badge_number": "EXC-KNL-505",
        "designation": "Excise Sub-Inspector"
    })
    assert reg_res.status_code == 200
    print(f"[PASS] Station Registration: {reg_res.json()['approval_status']} (is_active={reg_res.json()['is_active']})")
    
    sl_res = requests.post(f"{BASE}/auth/login", json={"username": su, "password": "OfficerPass@2024"})
    assert sl_res.status_code == 200
    print("[PASS] Immediate login for station officer: SUCCESS")

    # B. District officer self-registers -> Requires Admin Approval
    du = f"dist_rep_{uuid.uuid4().hex[:5]}"
    reg_dist = requests.post(f"{BASE}/auth/register", json={
        "username": du,
        "email": f"{du}@apexcise.gov.in",
        "password": "DistPass@2024",
        "confirm_password": "DistPass@2024",
        "full_name": "District Admin Applicant",
        "role": "DISTRICT",
        "district": "Guntur",
        "station": None,
        "badge_number": "EXC-GNT-101",
        "designation": "Superintendent of Excise"
    })
    assert reg_dist.status_code == 200
    print(f"[PASS] Privileged District Registration: {reg_dist.json()['approval_status']} (is_active={reg_dist.json()['is_active']})")
    
    # Attempted login before approval MUST return 403
    dl_res = requests.post(f"{BASE}/auth/login", json={"username": du, "password": "DistPass@2024"})
    assert dl_res.status_code == 403
    print(f"[PASS] Login before approval blocked (403): {dl_res.json()['detail']}")

    # 4. Admin Approval & Password Reset
    print("\n[4] ADMINISTRATIVE ACCOUNT MANAGEMENT & RESET")
    admin_headers = {"Authorization": f"Bearer {tokens['state_director']}"}
    dist_user_id = reg_dist.json()["user_id"]
    
    app_res = requests.post(f"{BASE}/employees/{dist_user_id}/approve", headers=admin_headers)
    assert app_res.status_code == 200
    print(f"[PASS] Admin approval: {app_res.json()['message']}")

    dl_res2 = requests.post(f"{BASE}/auth/login", json={"username": du, "password": "DistPass@2024"})
    assert dl_res2.status_code == 200
    print("[PASS] Login after approval: SUCCESS")

    reset_res = requests.post(
        f"{BASE}/employees/{dist_user_id}/reset-password",
        json={"new_password": "NewResetPassword@2024"},
        headers=admin_headers
    )
    assert reset_res.status_code == 200
    print(f"[PASS] Admin password reset: {reset_res.json()['message']}")

    dl_res3 = requests.post(f"{BASE}/auth/login", json={"username": du, "password": "NewResetPassword@2024"})
    assert dl_res3.status_code == 200
    print("[PASS] Login with newly reset password: SUCCESS")

    # 5. PDF Upload and Grounded RAG with Citations
    print("\n[5] EVIDENCE PDF UPLOAD & GROUNDED RAG WITH EXACT PAGE CITATIONS")
    st_headers = {"Authorization": f"Bearer {tokens['station_officer']}"}
    with open("C:/Users/LENOVO/Desktop/FIR-Sahayak/data/evidence/FIR-2024-KNL-0042_Official.pdf", "rb") as f:
        up_res = requests.post(
            f"{BASE}/documents/upload",
            files={"file": ("FIR-2024-KNL-0042_Official.pdf", f, "application/pdf")},
            headers=st_headers
        )
    assert up_res.status_code == 200
    up_data = up_res.json()
    doc_id = up_data["id"]
    print(f"[PASS] PDF Upload: ID={doc_id} | Pages={up_data['physical_page_count']} | Status={up_data['status']}")

    # Query RAG: Seized quantity (Grounded fact present on Page 2)
    rag_res = requests.post(f"{BASE}/rag/query", json={
        "query": "What quantity of contraband was seized in this FIR?",
        "mode": "PDF_ONLY",
        "document_id": doc_id,
        "language": "en"
    }, headers=st_headers)
    assert rag_res.status_code == 200
    rag_data = rag_res.json()
    print(f"[PASS] Grounded RAG Answer: {rag_data['answer']}")
    print(f"[PASS] Validated Citations: {rag_data['citations']}")
    assert len(rag_data['citations']) > 0

    # Query RAG: Missing Information (Mandatory phrase check)
    rag_miss = requests.post(f"{BASE}/rag/query", json={
        "query": "What is the past criminal history of the accused?",
        "mode": "PDF_ONLY",
        "document_id": doc_id,
        "language": "en"
    }, headers=st_headers)
    assert rag_miss.status_code == 200
    print(f"[PASS] Missing Info Answer: {rag_miss.json()['answer']}")
    assert "The requested information was not found in the uploaded FIR PDF." in rag_miss.json()['answer']

    # 6. Audit Chain Hash Integrity
    print("\n[6] SECTION 15: SHA-256 TAMPER-EVIDENT AUDIT HASH CHAIN")
    audit_res = requests.get(f"{BASE}/audit/verify-integrity", headers=admin_headers)
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    print(f"[PASS] Audit Chain Status: {audit_data['verification_status']}")
    print(f"[PASS] Verified Entries: {audit_data['verified_entries_count']}")
    print(f"[PASS] Algorithm: {audit_data['algorithm']}")
    assert audit_data['verification_status'] == "SECURE_AND_VERIFIED"
    assert audit_data['is_chain_intact'] is True

    print("\n==================================================")
    print("   [SUCCESS] ALL 6 LIVE VERIFICATION CHECKS PASSED! ")
    print("==================================================")

if __name__ == "__main__":
    run_verification()
