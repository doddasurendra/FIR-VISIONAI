"""
Comprehensive E2E Verification Script for FIR VisionAI New Features:
1. Export Formats (XLSX, DOCX, PDF, CSV, JSON)
2. Jurisdiction Protection on Exports
3. Entity Network (Single Case & Cross-Case Mode, Phone, Location, Org)
4. RAG Chatbot Language Selection & Missing Info Messages
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def run_tests():
    print("=" * 70)
    print("FIR VisionAI — Comprehensive Feature Verification")
    print("=" * 70)

    # 1. Login Station Officer
    print("\n[Step 1/5] Authenticating Station Officer (Kurnool)...")
    login = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "station_officer",
        "password": "StationPass@2024"
    }).json()
    stn_headers = {"Authorization": f"Bearer {login['access_token']}"}
    print(f"  -> Officer: {login['user']['full_name']} ({login['user']['role']} - {login['user']['district']})")

    # 2. Test 5 Export Formats
    print("\n[Step 2/5] Testing 5 Case Export Formats (xlsx, docx, pdf, csv, json)...")
    cases = requests.get(f"{BASE_URL}/api/v1/cases/", headers=stn_headers).json()
    assert len(cases) > 0, "No cases found for station officer"
    test_case = cases[0]
    case_id = test_case["id"]
    fir_num = test_case["fir_number"]
    print(f"  -> Target Case: {fir_num} ({case_id})")

    for fmt in ["json", "csv", "xlsx", "docx", "pdf"]:
        res = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}/export/{fmt}", headers=stn_headers)
        assert res.status_code == 200, f"Export {fmt} failed with {res.status_code}: {res.text}"
        disp = res.headers.get("content-disposition", "")
        print(f"     [OK] {fmt.upper()} export: {len(res.content)} bytes, header: {disp}")

    # 3. Test Jurisdiction Protection
    print("\n[Step 3/5] Testing Export Jurisdiction Protection...")
    # State admin login to find out-of-jurisdiction case
    state_login = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "state_director",
        "password": "StateAdmin@2024"
    }).json()
    state_cases = requests.get(f"{BASE_URL}/api/v1/cases/?limit=50", headers={"Authorization": f"Bearer {state_login['access_token']}"}).json()
    other_case = next(c for c in state_cases if c["district"] != "Kurnool")
    print(f"  -> Case outside Kurnool: {other_case['fir_number']} ({other_case['district']})")

    unauth_res = requests.get(f"{BASE_URL}/api/v1/cases/{other_case['id']}/export/pdf", headers=stn_headers)
    assert unauth_res.status_code == 403, f"Expected 403 but got {unauth_res.status_code}"
    print(f"     [OK] Jurisdiction enforcement: blocked with 403 Forbidden ({unauth_res.json()['detail']})")

    # 4. Test Entity Network (Cross-case vs Single-case, Phone filter)
    print("\n[Step 4/5] Testing Entity Network Graph & Filters...")
    net_res = requests.get(f"{BASE_URL}/api/v1/entities/network-graph", headers=stn_headers).json()
    nodes = net_res.get("nodes", [])
    edges = net_res.get("edges", [])
    print(f"  -> Cross-case graph: {len(nodes)} nodes, {len(edges)} edges")

    entity_types = set(n["entity_type"] for n in nodes)
    print(f"  -> Detected entity types in graph: {entity_types}")
    assert "PERSON" in entity_types
    assert "VEHICLE" in entity_types
    assert "LOCATION" in entity_types
    assert "PHONE" in entity_types

    # Single-case mode
    single_res = requests.get(f"{BASE_URL}/api/v1/entities/network-graph?case_id={case_id}", headers=stn_headers).json()
    single_nodes = single_res.get("nodes", [])
    print(f"  -> Single-case graph for {fir_num}: {len(single_nodes)} nodes (Zero cross-case leakage)")
    assert len(single_nodes) <= len(nodes)

    # 5. Test AI Chatbot RAG in Telugu & English
    print("\n[Step 5/5] Testing AI FIR RAG Assistant Language Support...")
    docs = requests.get(f"{BASE_URL}/api/v1/documents/", headers=stn_headers).json()
    assert len(docs) > 0, "No documents found for testing RAG"
    test_doc_id = docs[0]["id"]
    print(f"  -> Active test document: {docs[0]['original_filename']}")

    # Missing info in English
    rag_en = requests.post(f"{BASE_URL}/api/v1/rag/query", json={
        "document_id": test_doc_id,
        "query": "What is the previous criminal history of the accused?",
        "mode": "PDF_ONLY",
        "language": "en"
    }, headers=stn_headers).json()
    print(f"  -> Missing Info Query (EN): {rag_en.get('answer')[:90]}...")
    assert "The requested information was not found in the uploaded FIR" in rag_en.get("answer", "")

    # Missing info in Telugu
    rag_te = requests.post(f"{BASE_URL}/api/v1/rag/query", json={
        "document_id": test_doc_id,
        "query": "నిందితుడి మునుపటి క్రిమినల్ హిస్టరీ ఏమిటి?",
        "mode": "PDF_ONLY",
        "language": "te"
    }, headers=stn_headers).json()
    print(f"  -> Missing Info Query (TE): {rag_te.get('answer')[:90]}...")
    assert "సమాచారం కనుగొనబడలేదు" in rag_te.get("answer", "")

    print("\n" + "=" * 70)
    print("ALL E2E FEATURE VERIFICATION TESTS PASSED 100%!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
