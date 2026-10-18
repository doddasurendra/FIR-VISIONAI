import io
import json
import pytest
from PIL import Image
from fastapi.testclient import TestClient


def test_extraction_config_lifecycle(client: TestClient, station_token: str):
    headers = {"Authorization": f"Bearer {station_token}"}

    # 1. Get default config
    res = client.get("/api/v1/extraction/config", headers=headers)
    assert res.status_code == 200
    cfg = res.json()
    assert cfg["id"] == "cfg-default-fir"
    assert cfg["version"] >= 1
    assert "fir_number" in cfg["schema_json"]

    # 2. Validate valid schema
    sample_schema = [
        {"id": "f_fir", "key": "fir_number", "label": "FIR Number", "data_type": "string", "required": True},
        {"id": "f_crime", "key": "offence_nature", "label": "Crime Type", "data_type": "string", "required": True}
    ]
    val_res = client.post("/api/v1/extraction/config/validate", json={"schema_json": json.dumps(sample_schema)}, headers=headers)
    assert val_res.status_code == 200
    assert val_res.json()["valid"] is True
    assert val_res.json()["field_count"] == 2

    # 3. Validate invalid schema (duplicate keys)
    dup_schema = [
        {"id": "1", "key": "test_key", "label": "Label 1"},
        {"id": "2", "key": "test_key", "label": "Label 2"}
    ]
    val_dup = client.post("/api/v1/extraction/config/validate", json={"schema_json": json.dumps(dup_schema)}, headers=headers)
    assert val_dup.status_code == 200
    assert val_dup.json()["valid"] is False

    # 4. Update config
    update_res = client.put(
        "/api/v1/extraction/config",
        json={
            "name": "Updated FIR Schema",
            "schema_json": json.dumps(sample_schema),
            "instructions": "Strict extraction only."
        },
        headers=headers
    )
    assert update_res.status_code == 200
    updated_cfg = update_res.json()
    assert updated_cfg["version"] > cfg["version"]


def test_extraction_run_and_review_workflow(client: TestClient, station_token: str):
    headers = {"Authorization": f"Bearer {station_token}"}

    # 1. Check existing documents or upload a valid test image
    docs_res = client.get("/api/v1/documents/", headers=headers)
    docs = docs_res.json() if docs_res.status_code == 200 else []

    if docs:
        doc_id = docs[0]["id"]
    else:
        # Generate genuine PIL JPEG image
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        jpeg_bytes = buf.getvalue()

        upload_res = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test_fir_evidence.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
            headers=headers
        )
        assert upload_res.status_code == 200
        doc_id = upload_res.json()["document_id"]

    # 2. Run extraction
    run_res = client.post(
        "/api/v1/extraction/run",
        json={"document_id": doc_id},
        headers=headers
    )
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["document_id"] == doc_id
    assert "run_id" in run_data
    run_id = run_data["run_id"]
    assert "structured_fields" in run_data
    assert "entities" in run_data
    assert "key_points" in run_data

    # 3. Save review draft
    for f in run_data.get("structured_fields", []):
        if f["key"] == "fir_number":
            f["value"] = "Cr. No. 999/2026"
        elif f["key"] == "offence_nature":
            f["value"] = "Illicit Distillation"
        elif f["key"] == "district":
            f["value"] = "Kurnool"
        elif f["key"] == "station":
            f["value"] = "Kurnool Town Station"
    review_res = client.put(
        f"/api/v1/extraction/run/{run_id}/review",
        json={"reviewed_data": run_data},
        headers=headers
    )
    assert review_res.status_code == 200

    # 4. Retrieve run
    get_res = client.get(f"/api/v1/extraction/run/{run_id}", headers=headers)
    assert get_res.status_code == 200
    if get_res.json()["structured_fields"]:
        assert get_res.json()["structured_fields"][0]["value"] == "Cr. No. 999/2026"

    # 5. Export to XLSX, DOCX, CSV, JSON
    for fmt in ["xlsx", "docx", "csv", "json"]:
        exp_res = client.get(f"/api/v1/extraction/run/{run_id}/export/{fmt}", headers=headers)
        assert exp_res.status_code == 200
        assert len(exp_res.content) > 10

    # 6. Confirm and Register Case
    confirm_res = client.post(
        f"/api/v1/extraction/run/{run_id}/confirm",
        json={"reviewed_data": run_data},
        headers=headers
    )
    assert confirm_res.status_code == 200
    confirm_body = confirm_res.json()
    assert confirm_body["success"] is True
    assert "case_id" in confirm_body
