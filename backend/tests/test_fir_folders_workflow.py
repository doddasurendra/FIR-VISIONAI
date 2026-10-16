import pytest
from httpx import AsyncClient
from app.services.classification import classify_case_text
from app.models.folder import FIRFolder


def test_classification_theft_not_liquor():
    """Verify that theft / property crime is never misclassified as liquor."""
    text = "The complainant stated that unidentified persons broke into the house and stole gold ornaments and cash."
    res = classify_case_text(full_text=text, offence_nature="House burglary and theft")
    assert res.folder_slug == "theft"
    assert res.confidence > 0.3
    assert "liquor" not in res.folder_slug


def test_classification_ndps_transport():
    """Verify that drug contraband classifies into NDPS / Drug Transport."""
    text = "During vehicle checking, officers intercepted a lorry transporting 120 kg of dried Ganja packets."
    res = classify_case_text(full_text=text, offence_nature="Unlawful possession and transport of Ganja")
    assert res.folder_slug == "ndps-transport"
    assert res.confidence > 0.3


def test_classification_road_accident():
    """Verify road accident reports classify into road-accident."""
    text = "A head-on collision between a bus and auto resulted in severe injuries and rash driving under MVA."
    res = classify_case_text(full_text=text, offence_nature="Road traffic accident with rash driving")
    assert res.folder_slug == "road-accident"
    assert res.confidence > 0.3


def test_classification_low_confidence_routes_to_pending():
    """Verify that text with no matching signals routes to pending-classification, never defaults to liquor."""
    text = "Routine administrative note with no offence details or criminal allegations."
    res = classify_case_text(full_text=text, offence_nature="General memo")
    assert res.folder_slug == "pending-classification"
    assert res.confidence < 0.25


def test_folders_list_endpoint(client, station_token):
    """Test that folders endpoint returns seeded categories."""
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/folders/", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 20
    slugs = [f["slug"] for f in data]
    assert "illicit-distillation" in slugs
    assert "ndps-transport" in slugs
    assert "theft" in slugs
    assert "cyber-crime" in slugs
    assert "pending-classification" in slugs


def test_folders_counts_endpoint(client, station_token):
    """Test folder counts endpoint for authenticated officer."""
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/folders/counts", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), dict)


def test_single_fir_persons_endpoint(client, station_token):
    """Test single-FIR persons listing endpoint."""
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/folders/persons/single-fir", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "persons" in data
    assert "total" in data


def test_multiple_fir_persons_endpoint(client, station_token):
    """Test multiple-FIR persons listing endpoint."""
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/folders/persons/multiple-fir", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "persons" in data
    assert "total" in data


def test_folder_cases_listing(client, station_token):
    """Test listing cases within a specific folder slug."""
    headers = {"Authorization": f"Bearer {station_token}"}
    res = client.get("/api/v1/folders/illicit-distillation/cases", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "folder" in data
    assert "cases" in data
    assert "total" in data
    assert data["folder"]["slug"] == "illicit-distillation"


def test_rule_based_fallback_extraction_no_liquor_assumption():
    """Verify fallback extraction parses real evidence without assuming liquor."""
    from app.services.gemini import GeminiService
    service = GeminiService()
    raw_fir = """
    CRIME NO: 88/2024
    POLICE STATION: Kurnool Town Station, Kurnool District
    OFFENCE: Theft of Two-Wheeler Motor Vehicle
    SEIZED PROPERTY: Hero Splendor Motorcycle AP21AB1234
    ACCUSED: Suresh Babu, S/o Venkatesh, aged 28 years
    SEIZING OFFICER: Sub-Inspector M. Krishna
    """
    extracted = service._rule_based_fallback_extraction(raw_fir)
    assert extracted["fir_number"] == "88/2024"
    assert extracted["district"] == "Kurnool"
    assert "Kurnool" in extracted["station"]
    assert "Theft" in extracted["offence_nature"]
    # Must NOT assume liquor
    assert extracted["contraband_type"] != "ID Liquor"
    assert extracted["offence_nature"] != "Illicit Distillation & Transport of Contraband"


def test_end_to_end_workflow_and_approval(client, station_token):
    """Test creating a case, automatic 6-stage workflow execution, and final officer approval."""
    import uuid
    headers = {"Authorization": f"Bearer {station_token}"}

    unique_num = f"Cr. No. {uuid.uuid4().hex[:6]}/2024"
    # 1. Create a case
    case_payload = {
        "fir_number": unique_num,
        "year": 2024,
        "district": "Kurnool",
        "station": "Kurnool Town Station",
        "offence_nature": "Burglary and Theft of Cash",
        "contraband_type": "Stolen Currency Notes",
        "seized_quantity": 50000.0,
        "seized_unit": "INR",
        "vehicle_details": "None",
        "accused_names": ["K. Rajesh", "P. Suresh"],
        "seizing_officer_name": "S.I. K. Raman",
        "seizing_officer_rank": "Sub-Inspector",
        "narrative": "Accused broke into commercial shop and committed burglary of cash."
    }
    create_res = client.post("/api/v1/cases/", json=case_payload, headers=headers)
    assert create_res.status_code in (200, 201)
    created_case = create_res.json()
    case_id = created_case["id"]
    assert created_case["status"] in ("DRAFT", "IN_REVIEW")

    # 2. Check workflow execution status (6 stages)
    wf_res = client.get(f"/api/v1/folders/workflow/{case_id}", headers=headers)
    assert wf_res.status_code == 200
    stages = wf_res.json()
    stage_names = [s["stage"] for s in stages]
    assert "INTAKE" in stage_names
    assert "CLASSIFICATION" in stage_names
    assert "ENTITY_EXTRACTION" in stage_names
    assert "AI_LEGAL" in stage_names
    assert "INVESTIGATION" in stage_names
    assert "ADMIN" in stage_names

    # 3. Check case approval endpoint
    approve_res = client.post(f"/api/v1/cases/{case_id}/approve", headers=headers)
    assert approve_res.status_code == 200
    approved_case = approve_res.json()["case"]
    assert approved_case["status"] == "APPROVED"

