import io
import json
import hashlib
import pytest
from PIL import Image
from fastapi.testclient import TestClient


def _create_test_image(text_overlay: str = "Test FIR") -> io.BytesIO:
    """Generate in-memory JPEG image bytes with unique hash based on text_overlay."""
    h = int(hashlib.md5(text_overlay.encode()).hexdigest()[:6], 16)
    r, g, b = (h & 0xFF), ((h >> 8) & 0xFF), ((h >> 16) & 0xFF)
    img = Image.new("RGB", (400, 300), color=(r, g, b))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def test_police_fir_case_registration(client: TestClient, state_token: str):
    """
    Ordinary Police FIR (Theft / Bodily Injury / IPC / BNS):
    - Requires Police Station, District, FIR Number, Offence Nature.
    - Does NOT require contraband_type or seized_quantity.
    - Verifies successful registration and case status.
    """
    headers = {"Authorization": f"Bearer {state_token}"}

    # 1. Upload evidence document
    img_buf = _create_test_image("Theft FIR under IPC 379 unique 1")
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("police_theft_fir.jpg", img_buf, "image/jpeg")},
        headers=headers
    )
    assert upload_res.status_code == 200
    doc_data = upload_res.json()
    doc_id = doc_data.get("document_id") or doc_data.get("id")
    run_id = doc_data.get("run_id")

    # Get extraction run if run_id not in upload response
    if not run_id:
        ext_res = client.get(f"/api/v1/extraction/document/{doc_id}", headers=headers)
        assert ext_res.status_code == 200
        run_id = ext_res.json()["run_id"]

    # 2. Confirm Police FIR without contraband
    fir_num = "AP-POL-2024-0099"
    police_review = {
        "structured_fields": [
            {"key": "fir_number", "value": fir_num},
            {"key": "year", "value": 2024},
            {"key": "district", "value": "Visakhapatnam"},
            {"key": "station", "value": "MVP Colony Police Station"},
            {"key": "offence_nature", "value": "Theft of Motor Vehicle"},
            {"key": "reported_offences_acts", "value": "Section 379 IPC / Section 303(2) BNS"},
            {"key": "vehicle_details", "value": "Hero Splendor AP31AB9988"},
            {"key": "property_loss_amount", "value": "75000"}
        ],
        "entities": [
            {"name": "Suresh Kumar", "type": "COMPLAINANT", "source_page": 1, "confidence": 0.95},
            {"name": "Unknown Suspect", "type": "ACCUSED", "source_page": 1, "confidence": 0.90}
        ],
        "document_content": "Theft reported at MVP Colony. Complainant Suresh Kumar reported motorcycle stolen."
    }

    conf_res = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": police_review},
        headers=headers
    )
    assert conf_res.status_code == 200
    conf_data = conf_res.json()
    assert conf_data["success"] is True
    assert conf_data["fir_number"] == fir_num
    assert "case_id" in conf_data
    case_id = conf_data["case_id"]

    # Verify case details via Case detail API
    case_res = client.get(f"/api/v1/cases/{case_id}", headers=headers)
    assert case_res.status_code == 200
    case_detail = case_res.json()["case"]
    assert case_detail["fir_number"] == fir_num
    assert case_detail["district"] == "Visakhapatnam"
    assert case_detail["station"] == "MVP Colony Police Station"
    assert case_detail["contraband_type"] is None


def test_excise_fir_case_registration(client: TestClient, state_token: str):
    """
    Excise FIR (AP Excise Act 34(a)):
    - Requires Excise Station, District, Contraband details.
    """
    headers = {"Authorization": f"Bearer {state_token}"}

    img_buf = _create_test_image("Excise Seizure FIR unique 2")
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("excise_seizure_fir.jpg", img_buf, "image/jpeg")},
        headers=headers
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json().get("document_id") or upload_res.json().get("id")

    ext_res = client.get(f"/api/v1/extraction/document/{doc_id}", headers=headers)
    assert ext_res.status_code == 200
    run_id = ext_res.json()["run_id"]

    fir_num = "AP-EXC-2024-0551"
    excise_review = {
        "structured_fields": [
            {"key": "fir_number", "value": fir_num},
            {"key": "year", "value": 2024},
            {"key": "district", "value": "Kurnool"},
            {"key": "station", "value": "Kurnool Prohibition & Excise Station"},
            {"key": "offence_nature", "value": "Illicit Distillation and Transport"},
            {"key": "contraband_type", "value": "ID Liquor"},
            {"key": "seized_quantity", "value": 60.0},
            {"key": "seized_unit", "value": "Litres"},
            {"key": "law_sections", "value": ["Section 34(a) AP Excise Act 1968"]}
        ],
        "entities": [
            {"name": "Govind Rao", "type": "ACCUSED", "source_page": 1, "confidence": 0.98}
        ],
        "document_content": "Seized 60 Litres of ID Liquor transported illegally."
    }

    conf_res = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": excise_review},
        headers=headers
    )
    assert conf_res.status_code == 200
    assert conf_res.json()["success"] is True
    case_id = conf_res.json()["case_id"]

    case_res = client.get(f"/api/v1/cases/{case_id}", headers=headers)
    assert case_res.status_code == 200
    case_detail = case_res.json()["case"]
    assert case_detail["contraband_type"] == "ID Liquor"
    assert case_detail["seized_quantity"] == 60.0


def test_missing_station_validation_rejection(client: TestClient, state_token: str):
    """
    If Station is missing, registration MUST fail with 400 Bad Request and clear error.
    It must not invent a station.
    Once provided by officer review, confirmation succeeds.
    """
    headers = {"Authorization": f"Bearer {state_token}"}

    img_buf = _create_test_image("Missing Station FIR unique 3")
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("missing_station_fir.jpg", img_buf, "image/jpeg")},
        headers=headers
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json().get("document_id") or upload_res.json().get("id")

    ext_res = client.get(f"/api/v1/extraction/document/{doc_id}", headers=headers)
    assert ext_res.status_code == 200
    run_id = ext_res.json()["run_id"]

    # 1. Attempt confirm without station
    invalid_review = {
        "structured_fields": [
            {"key": "fir_number", "value": "FIR-NO-STATION-01"},
            {"key": "district", "value": "Guntur"},
            {"key": "offence_nature", "value": "Assault"}
            # Notice: NO station field
        ]
    }

    failed_conf = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": invalid_review},
        headers=headers
    )
    assert failed_conf.status_code == 400
    detail = failed_conf.json()["detail"]
    assert "station" in detail.lower()
    assert "Missing required fields" in detail

    # 2. Officer provides verified station -> succeeds
    valid_review = {
        "structured_fields": [
            {"key": "fir_number", "value": "FIR-NO-STATION-01"},
            {"key": "district", "value": "Guntur"},
            {"key": "station", "value": "Guntur Urban Police Station"},
            {"key": "offence_nature", "value": "Assault"}
        ]
    }
    success_conf = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": valid_review},
        headers=headers
    )
    assert success_conf.status_code == 200
    assert success_conf.json()["success"] is True


def test_extraction_export_all_formats(client: TestClient, state_token: str):
    """
    Test export in all 4 formats: Excel (.xlsx), Word (.docx), CSV (.csv), JSON (.json).
    Verifies Content-Disposition attachment filenames and Unicode handling (Telugu, Hindi, English).
    """
    headers = {"Authorization": f"Bearer {state_token}"}

    img_buf = _create_test_image("Unicode Export Test unique 4")
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("sample_kallur_fir.jpg", img_buf, "image/jpeg")},
        headers=headers
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json().get("document_id") or upload_res.json().get("id")

    ext_res = client.get(f"/api/v1/extraction/document/{doc_id}", headers=headers)
    assert ext_res.status_code == 200
    run_id = ext_res.json()["run_id"]

    # Review with multilingual content
    reviewed_data = {
        "structured_fields": [
            {"key": "fir_number", "value": "AP-KUR-2024-9988"},
            {"key": "district", "value": "Kurnool (కర్నూలు)"},
            {"key": "station", "value": "Kallur PS (కల్లూరు స్టేషన్)"},
            {"key": "offence_nature", "value": "Theft / దొంగతనం / चोरी"},
        ],
        "entities": [
            {"name": "రమేష్ బాబు", "type": "ACCUSED", "source_page": 1, "confidence": 0.98},
            {"name": "सुरेश कुमार", "type": "COMPLAINANT", "source_page": 1, "confidence": 0.95}
        ],
        "key_points": [
            {"id": "kp_1", "point": "ఘటన స్థలంలో నిందితుడు పట్టుబడ్డాడు.", "source_page": 1}
        ]
    }
    client.put(
        f"/api/v1/extraction/run/{run_id}/review",
        json={"reviewed_data": reviewed_data},
        headers=headers
    )

    # 1. Export Excel (.xlsx)
    res_xlsx = client.get(f"/api/v1/extraction/run/{run_id}/export/xlsx", headers=headers)
    assert res_xlsx.status_code == 200
    assert "openxmlformats" in res_xlsx.headers["content-type"]
    assert "sample_kallur_fir_extraction.xlsx" in res_xlsx.headers["content-disposition"]
    assert len(res_xlsx.content) > 100

    # 2. Export Word (.docx)
    res_docx = client.get(f"/api/v1/extraction/run/{run_id}/export/docx", headers=headers)
    assert res_docx.status_code == 200
    assert "wordprocessingml" in res_docx.headers["content-type"]
    assert "sample_kallur_fir_extraction.docx" in res_docx.headers["content-disposition"]
    assert len(res_docx.content) > 100

    # 3. Export CSV (.csv)
    res_csv = client.get(f"/api/v1/extraction/run/{run_id}/export/csv", headers=headers)
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "sample_kallur_fir_extraction.csv" in res_csv.headers["content-disposition"]
    csv_text = res_csv.content.decode("utf-8-sig")
    assert "AP-KUR-2024-9988" in csv_text
    assert "కర్నూలు" in csv_text

    # 4. Export JSON (.json)
    res_json = client.get(f"/api/v1/extraction/run/{run_id}/export/json", headers=headers)
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]
    assert "sample_kallur_fir_extraction.json" in res_json.headers["content-disposition"]
    json_data = json.loads(res_json.content.decode("utf-8"))
    assert json_data["metadata"]["run_id"] == run_id
    assert any(f["key"] == "fir_number" and f["value"] == "AP-KUR-2024-9988" for f in json_data["structured_fields"])


def test_case_confirmation_idempotency(client: TestClient, state_token: str):
    """
    Confirming the same case multiple times updates the existing case rather than
    creating duplicates.
    """
    headers = {"Authorization": f"Bearer {state_token}"}

    img_buf = _create_test_image("Idempotent Test FIR unique 5")
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("idempotent_fir.jpg", img_buf, "image/jpeg")},
        headers=headers
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json().get("document_id") or upload_res.json().get("id")

    ext_res = client.get(f"/api/v1/extraction/document/{doc_id}", headers=headers)
    run_id = ext_res.json()["run_id"]

    fir_num = "AP-IDEMP-2024-001"
    review = {
        "structured_fields": [
            {"key": "fir_number", "value": fir_num},
            {"key": "district", "value": "Chittoor"},
            {"key": "station", "value": "Chittoor West PS"},
            {"key": "offence_nature", "value": "Cheating / Fraud"}
        ]
    }

    # First confirmation
    res1 = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": review},
        headers=headers
    )
    assert res1.status_code == 200
    case_id_1 = res1.json()["case_id"]

    # Second confirmation (retry or double-click)
    res2 = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": review},
        headers=headers
    )
    assert res2.status_code == 200
    case_id_2 = res2.json()["case_id"]

    # Must return the exact same case_id, not a duplicate
    assert case_id_1 == case_id_2


def test_multi_field_validation_report_completeness(client: TestClient, state_token: str):
    """
    Test Requirement 5: Multi-Field Validation Report.
    When multiple required fields are missing or unconfirmed (e.g. station AND district),
    registration must return HTTP 400 with a structured `validation_report` containing
    ALL missing fields together with labels, reasons, and correction sections,
    rather than failing one field at a time.
    """
    headers = {"Authorization": f"Bearer {state_token}"}

    img_buf = _create_test_image("Validation Report FIR unique 6")
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("val_report_fir.jpg", img_buf, "image/jpeg")},
        headers=headers
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json().get("document_id") or upload_res.json().get("id")

    ext_res = client.get(f"/api/v1/extraction/document/{doc_id}", headers=headers)
    assert ext_res.status_code == 200
    run_id = ext_res.json()["run_id"]

    # Submit review missing BOTH station and district
    invalid_review = {
        "structured_fields": [
            {"key": "fir_number", "value": "CR-MULTI-VAL-01"},
            {"key": "offence_nature", "value": "Theft / Property Crime"}
            # Neither district nor station provided
        ],
        "document_content": "Incident registered at Kurnool Town Police Station, Kurnool District."
    }

    res = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": invalid_review},
        headers=headers
    )
    assert res.status_code == 400
    data = res.json()
    assert "validation_report" in data
    report = data["validation_report"]
    assert isinstance(report, list)
    assert len(report) >= 2

    flagged_fields = [item["field"] for item in report]
    assert "station" in flagged_fields
    assert "district" in flagged_fields

    for item in report:
        assert "field" in item
        assert "label" in item
        assert "reason" in item
        assert "correction_section" in item
        assert item["issue"] == "MISSING"


def test_canonical_alias_field_resolution(client: TestClient, state_token: str):
    """
    Test Requirement 3: Field Mapping & Alias Resolution.
    If an external model or OCR outputs alias field names (e.g. `police_station`,
    `district_name`, `crime_no`), the backend canonical mapping layer normalizes them
    to standard schema keys and completes registration without error.
    """
    headers = {"Authorization": f"Bearer {state_token}"}

    img_buf = _create_test_image("Alias Resolution FIR unique 7")
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("alias_resolution_fir.jpg", img_buf, "image/jpeg")},
        headers=headers
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json().get("document_id") or upload_res.json().get("id")

    ext_res = client.get(f"/api/v1/extraction/document/{doc_id}", headers=headers)
    assert ext_res.status_code == 200
    run_id = ext_res.json()["run_id"]

    # Submit review using alias keys
    alias_review = {
        "structured_fields": [
            {"key": "crime_no", "value": "CR-ALIAS-2024-99"},
            {"key": "district_name", "value": "Visakhapatnam"},
            {"key": "police_station", "value": "MVP Colony Police Station"},
            {"key": "crime_type", "value": "Cyber Crime Fraud"}
        ]
    }

    conf_res = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": alias_review},
        headers=headers
    )
    assert conf_res.status_code == 200
    case_id = conf_res.json()["case_id"]

    # Verify that case was registered with canonical fields populated
    case_res = client.get(f"/api/v1/cases/{case_id}", headers=headers)
    assert case_res.status_code == 200
    case = case_res.json()["case"]
    assert case["fir_number"] == "CR-ALIAS-2024-99"
    assert case["district"] == "Visakhapatnam"
    assert case["station"] == "MVP Colony Police Station"
    assert case["offence_nature"] == "Cyber Crime Fraud"


def test_district_candidate_detection_and_registration(client: TestClient, state_token: str):
    """
    Test Persistent District Registration Error Fix:
    Verifies that when an FIR document (such as FIR 6.jpg) mentions a location/district
    in an address line (e.g. 'Chennai - 600034') without the explicit 'District:' keyword:
    1. detect_district_from_text identifies 'Chennai'
    2. Missing district in confirmation returns candidate 'Chennai' in validation report
    3. Applying the candidate allows successful registration and database persistence
    """
    from app.api.v1.extraction import detect_district_from_text, detect_station_from_text

    doc_text = (
        "FIRST INFORMATION REPORT\n"
        "FIR No: 212/2025  Date: 20/06/2025\n"
        "Police Station: Egmore Police Station\n"
        "Complainant: Arun Kumar\n"
        "Address: 45, 3rd Street, Nungambakkam, Chennai - 600034\n"
        "Offence: Bike/Vehicle Theft, Section 379 IPC\n"
    )

    # 1. Verify helper detection functions
    detected_dist = detect_district_from_text(doc_text)
    assert detected_dist == "Chennai"

    detected_stn = detect_station_from_text(doc_text)
    assert "Egmore" in detected_stn and "Police Station" in detected_stn

    headers = {"Authorization": f"Bearer {state_token}"}
    img_buf = _create_test_image("District Candidate Verification FIR")
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("district_test_fir.jpg", img_buf, "image/jpeg")},
        headers=headers
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json().get("document_id") or upload_res.json().get("id")

    ext_res = client.get(f"/api/v1/extraction/document/{doc_id}", headers=headers)
    assert ext_res.status_code == 200
    run_id = ext_res.json()["run_id"]

    # 2. Submit confirmation missing district, but with document_content provided
    missing_dist_review = {
        "structured_fields": [
            {"key": "fir_number", "value": "212/2025"},
            {"key": "station", "value": "Egmore Police Station"},
            {"key": "offence_nature", "value": "Bike/Vehicle Theft"}
            # district missing
        ],
        "document_content": doc_text
    }

    res_missing = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": missing_dist_review},
        headers=headers
    )
    assert res_missing.status_code == 400
    err_body = res_missing.json()
    assert "validation_report" in err_body
    dist_report = next((item for item in err_body["validation_report"] if item["field"] == "district"), None)
    assert dist_report is not None
    assert dist_report["issue"] == "MISSING"
    assert dist_report["candidate_value"] == "Chennai"

    # 3. Supply the candidate district and confirm registration
    resolved_review = {
        "structured_fields": [
            {"key": "fir_number", "value": "212/2025"},
            {"key": "district", "value": dist_report["candidate_value"]},
            {"key": "station", "value": "Egmore Police Station"},
            {"key": "offence_nature", "value": "Bike/Vehicle Theft"}
        ],
        "document_content": doc_text
    }

    res_success = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": resolved_review},
        headers=headers
    )
    assert res_success.status_code == 200
    success_body = res_success.json()
    assert success_body.get("success") is True
    case_id = success_body["case_id"]

    # 4. Verify case is persisted in database with district == Chennai
    case_res = client.get(f"/api/v1/cases/{case_id}", headers=headers)
    assert case_res.status_code == 200
    case_data = case_res.json()["case"]
    assert case_data["district"] == "Chennai"
    assert case_data["station"] == "Egmore Police Station"
    assert case_data["fir_number"] == "212/2025"
    assert case_data["offence_nature"] == "Bike/Vehicle Theft"

