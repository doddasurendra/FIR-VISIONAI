import io
import json
import uuid
import pytest
from PIL import Image
from fastapi.testclient import TestClient


def test_end_to_end_intake_workflow(client: TestClient, station_token: str):
    headers = {"Authorization": f"Bearer {station_token}"}

    # 1. Create a genuine test image representing an FIR document
    img = Image.new("RGB", (300, 300), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    # 2. Upload document via /api/v1/documents/upload (Stage 1: Evidence Upload / OCR)
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("FIR_Evidence_Test_2024.jpg", jpeg_bytes, "image/jpeg")},
        headers=headers
    )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    upload_data = upload_res.json()

    # Verify upload returns the full shared extraction workspace payload
    assert "document_id" in upload_data or "id" in upload_data
    doc_id = upload_data.get("document_id") or upload_data.get("id")
    assert upload_data.get("file_hash") is not None
    assert "structured_fields" in upload_data
    assert "entities" in upload_data
    assert "key_points" in upload_data
    assert "document_metadata" in upload_data
    assert "run_id" in upload_data
    run_id = upload_data.get("run_id")

    # 3. Stage 2: Mandatory Officer Review
    # Unverified state: The case must not be automatically confirmed or auto-approved
    # Inspect review data before confirming
    review_res = client.get(f"/api/v1/extraction/run/{run_id}", headers=headers)
    assert review_res.status_code == 200
    review_run = review_res.json()
    assert review_run["document_id"] == doc_id
    assert len(review_run["structured_fields"]) > 0

    # Modify structured fields during review (e.g. Officer corrects FIR number & details)
    sample_fir_num = f"TEST-FIR-E2E-{uuid.uuid4().hex[:8]}"
    reviewed_fields = []
    for f in review_run["structured_fields"]:
        if f["key"] == "fir_number":
            reviewed_fields.append({**f, "value": sample_fir_num, "reviewed": True})
        elif f["key"] == "offence_nature":
            reviewed_fields.append({**f, "value": "Illegal transport and possession of contraband", "reviewed": True})
        elif f["key"] == "district":
            reviewed_fields.append({**f, "value": "Kurnool", "reviewed": True})
        elif f["key"] == "station":
            reviewed_fields.append({**f, "value": "Kurnool Town Station", "reviewed": True})
        else:
            reviewed_fields.append(f)

    keys = {f["key"] for f in reviewed_fields}
    if "district" not in keys:
        reviewed_fields.append({"key": "district", "value": "Kurnool", "reviewed": True})
    if "station" not in keys:
        reviewed_fields.append({"key": "station", "value": "Kurnool Town Station", "reviewed": True})

    # 4. Officer confirms and signs off (POST /api/v1/extraction/run/{run_id}/confirm)
    confirm_payload = {
        "reviewed_data": {
            **review_run,
            "structured_fields": reviewed_fields
        }
    }
    confirm_res = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json=confirm_payload,
        headers=headers
    )
    assert confirm_res.status_code == 200, f"Confirmation failed: {confirm_res.text}"
    confirm_data = confirm_res.json()
    assert confirm_data.get("success") is True
    case_id = confirm_data.get("case_id")
    assert case_id is not None
    assert confirm_data.get("fir_number") == sample_fir_num

    # 5. Verify Stages 3, 4, 5: Post-Intake Workflow Executions
    # The confirmation triggers trigger_post_intake_workflow:
    # INTAKE -> CLASSIFICATION -> ENTITY_EXTRACTION -> AI_LEGAL -> INVESTIGATION -> ADMIN
    wf_res = client.get(f"/api/v1/folders/workflow/{case_id}", headers=headers)
    assert wf_res.status_code == 200, f"Workflow query failed: {wf_res.text}"
    stages = wf_res.json()
    assert len(stages) >= 5, f"Expected at least 5 workflow stages, got {len(stages)}"

    stage_names = [s["stage"] for s in stages]
    assert "INTAKE" in stage_names
    assert "CLASSIFICATION" in stage_names
    assert "ENTITY_EXTRACTION" in stage_names
    assert "AI_LEGAL" in stage_names
    assert "INVESTIGATION" in stage_names
    assert "ADMIN" in stage_names

    # Check that stages completed
    for st in stages:
        assert st["status"] in ["COMPLETED", "RUNNING"], f"Stage {st['stage']} unexpected status {st['status']}"

    # 6. Verify Stage 4 Investigation Artifacts (Case Diary & Chargesheet drafts)
    gen_res = client.get(f"/api/v1/generation/case/{case_id}/documents", headers=headers)
    assert gen_res.status_code == 200
    gen_docs = gen_res.json()
    doc_types = [d["doc_type"] for d in gen_docs]
    assert "CASE_DIARY" in doc_types
    assert "CHARGESHEET" in doc_types
    # Workflow-generated drafts must remain in draft state until an officer signs.
    # Other document types on a reused case may have been approved explicitly elsewhere.
    for d in gen_docs:
        if d["doc_type"] in ("CASE_DIARY", "CHARGESHEET"):
            assert d["status"] == "DRAFT"

    # 7. Verify Idempotent Workflow Retry
    retry_res = client.post(f"/api/v1/folders/workflow/{case_id}/retry", headers=headers)
    assert retry_res.status_code == 200
    assert retry_res.json().get("case_id") == case_id

    # 8. Verify Stage 6: Existing/Old FIRs display
    case_res = client.get(f"/api/v1/cases/{case_id}", headers=headers)
    assert case_res.status_code == 200
    case_data = case_res.json()
    assert case_data["case"]["fir_number"] == sample_fir_num
    assert case_data["case"]["district"] == "Kurnool"
    assert len(case_data["documents"]) >= 1
    assert case_data["documents"][0]["id"] == doc_id
