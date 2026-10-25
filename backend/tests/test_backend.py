import pytest
import os
import sys
from fastapi.testclient import TestClient

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.services.rag_engine import NOT_FOUND

DEMO_FIR_FILENAME = "FIR-2024-KNL-0042_Official.pdf"

def get_demo_fir_document(client, headers):
    """Return the seeded 3-page demo FIR from the paginated documents list (newest-first order)."""
    res = client.get("/api/v1/documents/", params={"search": DEMO_FIR_FILENAME}, headers=headers)
    assert res.status_code == 200
    docs = res.json()["documents"]
    matches = [d for d in docs if d["original_filename"] == DEMO_FIR_FILENAME]
    assert matches, f"Seeded demo document {DEMO_FIR_FILENAME} is missing; run scripts/seed_demo_data.py"
    return matches[0]

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

# 1. Health and System Status
def test_health_check(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
    assert res.json()["database"] == "sqlite3_fts5_connected"

# 2. Authentication & Scoped Case Access (Section 5)
def test_station_role_data_scoping(client, station_token):
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/cases/", headers=headers)
    assert res.status_code == 200
    cases = res.json()
    assert len(cases) > 0
    # Every case returned must strictly belong to Kurnool district
    for c in cases:
        assert c["district"].lower() == "kurnool"

def test_state_role_sees_all_cases(client, state_token):
    headers = {"Authorization": f"Bearer {state_token}"}
    res = client.get("/api/v1/cases/", headers=headers)
    assert res.status_code == 200
    cases = res.json()
    districts = set([c["district"].lower() for c in cases])
    # STATE user sees across multiple districts
    assert len(districts) >= 2

# 3. Field Verification & Override (Section 6)
def test_field_override_persists(client, station_token):
    headers = {"Authorization": f"Bearer {station_token}"}
    cases = client.get("/api/v1/cases/", headers=headers).json()
    c_id = cases[0]["id"]
    detail = client.get(f"/api/v1/cases/{c_id}", headers=headers).json()
    fields = detail["fields"]
    if fields:
        f_id = fields[0]["id"]
        override_res = client.post(
            f"/api/v1/cases/{c_id}/fields/{f_id}/override",
            json={"human_override_value": "Verified 50.0 Litres", "verification_status": "OVERRIDDEN"},
            headers=headers
        )
        assert override_res.status_code == 200
        assert override_res.json()["human_override_value"] == "Verified 50.0 Litres"

# 4. Section 26: PDF-Only Grounded RAG with Exact Physical Page Citations
def test_pdf_only_grounded_rag_with_citations(client, station_token):
    headers = {"Authorization": f"Bearer {station_token}"}
    target_doc = get_demo_fir_document(client, headers)

    # Query factual information present in PDF
    query_payload = {
        "query": "What quantity of contraband was seized in this FIR?",
        "mode": "PDF_ONLY",
        "document_id": target_doc["id"],
        "language": "en"
    }
    res = client.post("/api/v1/rag/query", json=query_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "45.0" in data["answer"] or "Litres" in data["answer"] or "seized" in data["answer"].lower()
    assert len(data["citations"]) > 0
    assert any(c["physical_page_number"] == 2 for c in data["citations"])
    page2 = next(c for c in data["citations"] if c["physical_page_number"] == 2)
    assert "Page 2" in page2["source_label"]
    assert page2["document_id"] == target_doc["id"]
    assert page2["evidence_excerpt"]

def test_pdf_only_missing_information_returns_mandatory_phrase(client, station_token):
    headers = {"Authorization": f"Bearer {station_token}"}
    target_doc = get_demo_fir_document(client, headers)

    # Query absent information: Criminal history
    query_payload = {
        "query": "What is the previous criminal history of the accused person?",
        "mode": "PDF_ONLY",
        "document_id": target_doc["id"],
        "language": "en"
    }
    res = client.post("/api/v1/rag/query", json=query_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == NOT_FOUND["en"]
    assert data["citations"] == []
    assert data["not_found"] is True
    assert data["can_expand_scope"] is True

def test_pdf_only_telugu_missing_phrase(client, station_token):
    headers = {"Authorization": f"Bearer {station_token}"}
    target_doc = get_demo_fir_document(client, headers)

    query_payload = {
        "query": "నిందితుడి గత నేర చరిత్ర ఏమిటి?",
        "mode": "PDF_ONLY",
        "document_id": target_doc["id"],
        "language": "te"
    }
    res = client.post("/api/v1/rag/query", json=query_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == NOT_FOUND["te"]
    assert data["citations"] == []

# 5. Section 27: Case Facts -> Candidate Sections Workflow
def test_legal_section_recommendation_and_date_regime(client, station_token):
    headers = {"Authorization": f"Bearer {station_token}"}
    cases = client.get("/api/v1/cases/", headers=headers).json()
    target_case = [c for c in cases if c["fir_number"] == "FIR-2024-KNL-0042"][0]

    rec_res = client.get(f"/api/v1/legal/recommend/{target_case['id']}", headers=headers)
    assert rec_res.status_code == 200
    rec = rec_res.json()
    assert "Bharatiya Nyaya Sanhita" in rec["applicable_regime"]
    candidates = rec["candidates"]
    assert len(candidates) >= 1
    sec34 = [c for c in candidates if "Section 34(a)" in c["section_number"]][0]
    assert len(sec34["matched_facts"]) > 0

# 6. Section 15: Tamper-Evident SHA-256 Audit Trail Verification
def test_audit_hash_chain_integrity(client, station_token):
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/audit/verify-integrity", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["is_chain_intact"] is True
    assert data["verification_status"] == "SECURE_AND_VERIFIED"
    assert data["verified_entries_count"] >= 3

# 7. Component 4: Entity Resolution & Network Graph
def test_network_graph_generation(client, station_token):
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/entities/network-graph", headers=headers)
    assert res.status_code == 200
    graph = res.json()
    assert len(graph["nodes"]) > 0
    assert len(graph["edges"]) > 0
    assert "stats" in graph
    assert graph["stats"]["total_entities"] > 0
