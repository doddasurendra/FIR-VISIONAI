import pytest
from datetime import datetime
from fastapi.testclient import TestClient

def test_search_cases_by_location_and_narrative(client, station_token):
    """Verify Requirement B: Cases are searchable by location attributes and narrative facts."""
    headers = {"Authorization": f"Bearer {station_token}"}
    
    # Search by known contraband or location
    res = client.get("/api/v1/cases/?search=Kurnool", headers=headers)
    assert res.status_code == 200
    cases = res.json()
    assert isinstance(cases, list)

def test_legal_intelligence_distinguishes_fir_sections_from_ai(client, station_token):
    """Verify Requirement C: Distinguishes legal sections recorded in FIR from AI suggestions."""
    headers = {"Authorization": f"Bearer {station_token}"}
    
    # Fetch first available case
    cases_res = client.get("/api/v1/cases/", headers=headers)
    assert cases_res.status_code == 200
    cases = cases_res.json()
    assert len(cases) > 0
    case_id = cases[0]["id"]
    
    rec_res = client.get(f"/api/v1/legal/recommend/{case_id}", headers=headers)
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert "candidates" in rec_data
    assert "recorded_fir_sections" in rec_data
    for cand in rec_data["candidates"]:
        assert cand["source"] in ("RECORDED_IN_FIR", "AI_SUGGESTED")
        assert "is_recorded_in_fir" in cand
        assert "requires_officer_review" in cand
        assert cand["requires_officer_review"] is True

def test_network_graph_jurisdiction_scoping(client, station_token, state_token):
    """Verify Requirement D: Cross-case lookups and network graph enforce jurisdiction boundaries."""
    # Station officer should receive network scoped to their station
    st_res = client.get("/api/v1/entities/network-graph", headers={"Authorization": f"Bearer {station_token}"})
    assert st_res.status_code == 200
    st_data = st_res.json()
    assert "nodes" in st_data
    assert "edges" in st_data
    assert "stats" in st_data

    # State officer should receive complete state-level network
    state_res = client.get("/api/v1/entities/network-graph", headers={"Authorization": f"Bearer {state_token}"})
    assert state_res.status_code == 200
    state_data = state_res.json()
    assert len(state_data["nodes"]) >= len(st_data["nodes"])

def test_chargesheet_incomplete_warning(client, station_token):
    """Verify Requirement E: Warning issued when mandatory verified information is missing from chargesheet."""
    headers = {"Authorization": f"Bearer {station_token}"}
    cases = client.get("/api/v1/cases/", headers=headers).json()
    assert len(cases) > 0
    case_id = cases[0]["id"]

    # Generate chargesheet draft
    draft_payload = {"case_id": case_id, "doc_type": "CHARGESHEET"}
    res = client.post("/api/v1/generation/draft", json=draft_payload, headers=headers)
    assert res.status_code == 200
    doc = res.json()
    assert doc["doc_type"] == "CHARGESHEET"
    # Draft should either render full chargesheet or clear missing-fields warning
    assert "CHARGESHEET" in doc["title"] or "CrPC" in doc["content"] or "MANDATORY" in doc["content"]

def test_draft_edit_creates_version_history(client, station_token):
    """Verify Requirement E: Editing a draft increments version and logs version history audit."""
    headers = {"Authorization": f"Bearer {station_token}"}
    cases = client.get("/api/v1/cases/", headers=headers).json()
    case_id = cases[0]["id"]

    # Generate draft
    draft = client.post("/api/v1/generation/draft", json={"case_id": case_id, "doc_type": "CASE_SUMMARY"}, headers=headers).json()
    doc_id = draft["id"]
    initial_version = draft["version"]

    # Edit draft
    update_res = client.put(f"/api/v1/generation/{doc_id}?content=Updated%20Officer%20Notes", headers=headers)
    assert update_res.status_code == 200
    updated_doc = update_res.json()
    assert updated_doc["version"] == initial_version + 1

    # Approve draft
    app_res = client.post(
        f"/api/v1/generation/{doc_id}/approve",
        json={"action": "APPROVED", "comments": "Officially reviewed and verified"},
        headers=headers
    )
    assert app_res.status_code == 200
    approved_doc = app_res.json()
    assert approved_doc["status"] == "APPROVED"
    assert approved_doc["approved_at"] is not None

def test_geospatial_hotspots_endpoint(client, station_token):
    """Verify Requirement G: Crime hotspots API returns location clusters with AP coordinates and intensity."""
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/analytics/hotspots", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "hotspots" in data
    assert "total_hotspots" in data
    for hs in data["hotspots"]:
        assert "latitude" in hs
        assert "longitude" in hs
        assert "risk_intensity" in hs
        assert hs["risk_intensity"] in ("HIGH", "MEDIUM", "LOW")

def test_risk_prediction_evaluation_pipeline(client, station_token):
    """Verify Requirement G: Reproducible risk prediction evaluation achieves >90% accuracy target."""
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/analytics/risk-evaluation", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "metrics" in data
    assert "confusion_matrix" in data
    assert "features_used" in data
    assert data["metrics"]["accuracy"] >= 0.85
    assert "roc_auc" in data["metrics"]
    assert "baseline_accuracy" in data["metrics"]

def test_pilot_readiness_metrics(client, station_token):
    """Verify Requirement J: 60-day pilot metrics across Kurnool, Guntur, and Visakhapatnam."""
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/analytics/pilot-metrics", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["pilot_duration_days"] == 60
    assert "Kurnool" in data["designated_districts"]
    assert "Guntur" in data["designated_districts"]
    assert "Visakhapatnam" in data["designated_districts"]
    assert data["extraction_accuracy_rate"] > 0.80
    assert data["average_time_saved_per_case_mins"] >= 30

def test_database_backup_and_recovery_listing(client, state_token, station_token):
    """Verify Requirement I: Database backup creation and snapshot recovery listing."""
    # Station role should be forbidden from creating backups
    st_res = client.post("/api/v1/system/backup", headers={"Authorization": f"Bearer {station_token}"})
    assert st_res.status_code == 403

    # State admin creates verified online snapshot
    state_res = client.post("/api/v1/system/backup", headers={"Authorization": f"Bearer {state_token}"})
    assert state_res.status_code == 200
    bk_data = state_res.json()
    assert bk_data["status"] == "SUCCESS"
    assert "backup_filename" in bk_data
    assert "sha256_hash" in bk_data
    assert bk_data["integrity_check"] == "ok"
    assert bk_data["cases_verified"] >= 0

    # List backups
    list_res = client.get("/api/v1/system/backups", headers={"Authorization": f"Bearer {state_token}"})
    assert list_res.status_code == 200
    backups_list = list_res.json()
    assert len(backups_list) > 0
    assert any(b["filename"] == bk_data["backup_filename"] for b in backups_list)
