import io
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.services.sarvam_doc_ai import (
    sarvam_doc_ai,
    SarvamDocAIService,
    convert_field_list_to_json_schema,
    MAX_PAGES_PER_JOB,
)
from app.api.v1.extraction import DEFAULT_FIR_SCHEMA


def test_sarvam_service_availability():
    """Verify is_available() logic based on API key configuration."""
    svc = SarvamDocAIService()
    # If key is set in environment, is_available should reflect it
    assert isinstance(svc.is_available(), bool)

    # Test with dummy/invalid keys
    svc.api_key = None
    assert svc.is_available() is False

    svc.api_key = "your_sarvam_api_key_here"
    assert svc.is_available() is False

    svc.api_key = "short"
    assert svc.is_available() is False

    svc.api_key = "sk_live_valid_sarvam_key_example_12345"
    assert svc.is_available() is True


def test_schema_conversion_to_sarvam_json_schema():
    """Verify conversion from UI field list to official Sarvam Extract JSON schema."""
    ui_fields = [
        {"id": "f_fir", "key": "fir_number", "label": "FIR Number", "data_type": "string", "description": "Official FIR number"},
        {"id": "f_year", "key": "year", "label": "Year", "data_type": "number", "description": "Year of registration"},
        {"id": "f_accused", "key": "accused_names", "label": "Accused Persons", "data_type": "array", "description": "Names of accused"},
        {"id": "f_verified", "key": "is_verified", "label": "Verified", "data_type": "boolean", "description": "Whether verified"},
    ]

    schema = convert_field_list_to_json_schema(ui_fields)
    assert schema["type"] == "object"
    props = schema["properties"]

    assert "fir_number" in props
    assert props["fir_number"]["type"] == "string"
    assert props["fir_number"]["description"] == "Official FIR number"

    assert "year" in props
    assert props["year"]["type"] == "number"

    assert "accused_names" in props
    assert props["accused_names"]["type"] == "array"
    assert props["accused_names"]["items"]["type"] == "string"

    assert "is_verified" in props
    assert props["is_verified"]["type"] == "boolean"


def test_default_fir_schema_completeness():
    """Verify DEFAULT_FIR_SCHEMA contains all comprehensive FIR target fields across 3 categories."""
    keys = {f["key"] for f in DEFAULT_FIR_SCHEMA}

    # Group 1: Document & FIR identification
    for k in ["document_title", "document_type", "fir_number", "year", "general_diary_reference",
              "information_received_date", "offence_date", "registration_date", "district",
              "station", "place_of_occurrence", "type_of_information"]:
        assert k in keys, f"Missing identification field: {k}"

    # Group 2: People & contact details
    for k in ["complainant_name", "complainant_parentage", "complainant_age", "complainant_address",
              "complainant_occupation", "complainant_nationality", "complainant_contact",
              "accused_names", "accused_details", "witness_names", "victim_names", "other_named_persons"]:
        assert k in keys, f"Missing person field: {k}"

    # Group 3: Incident & evidence details
    for k in ["offence_nature", "brief_facts", "incident_narrative", "reported_offences_acts",
              "property_loss_amount", "vehicle_details", "contraband_type", "seized_quantity",
              "seized_unit", "seized_property_details", "digital_identifiers", "law_sections",
              "investigating_officer", "officer_signature_details"]:
        assert k in keys, f"Missing incident/evidence field: {k}"


def test_config_api_supports_sarvam_config_id(client: TestClient, station_token: str):
    """Test getting and updating extraction config with sarvam_config_id."""
    headers = {"Authorization": f"Bearer {station_token}"}

    # 1. Get config
    get_res = client.get("/api/v1/extraction/config", headers=headers)
    assert get_res.status_code == 200
    cfg = get_res.json()
    assert "sarvam_config_id" in cfg

    # 2. Update with custom sarvam_config_id
    test_sarvam_id = "cfg_sarvam_workbench_001"
    update_res = client.put(
        "/api/v1/extraction/config",
        json={
            "name": "FIR Custom Config",
            "schema_json": cfg["schema_json"],
            "instructions": "Test defensive extraction rules",
            "sarvam_config_id": test_sarvam_id
        },
        headers=headers
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["sarvam_config_id"] == test_sarvam_id

    # 3. Verify retrieval reflects the saved sarvam_config_id
    verify_res = client.get("/api/v1/extraction/config", headers=headers)
    assert verify_res.status_code == 200
    assert verify_res.json()["sarvam_config_id"] == test_sarvam_id

    # 4. Clean up / reset sarvam_config_id to None
    reset_res = client.put(
        "/api/v1/extraction/config",
        json={
            "name": "FIR Standard Extraction",
            "schema_json": cfg["schema_json"],
            "instructions": "Test defensive extraction rules",
            "sarvam_config_id": ""
        },
        headers=headers
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["sarvam_config_id"] is None


@pytest.mark.asyncio
async def test_sarvam_document_processing_mocked():
    """Verify process_document pipeline with annotations and page citations."""
    mock_extract_res = {
        "type": "extract",
        "status": "completed",
        "result": {
            "fir_number": "142/2024",
            "year": 2024,
            "district": "Kurnool",
            "station": "Kurnool Town Police Station",
            "offence_nature": "Illicit Liquor Smuggling",
            "accused_names": ["Ramu Naidu", "Suresh Kumar"],
            "complainant_name": "K. Venkata Rao, Sub-Inspector",
            "vehicle_details": "Auto AP21TY4567",
            "brief_facts": "Vehicle intercepted near highway checkpost with illicit brew.",
        },
        "annotations": {
            "fir_number": {"confidence": 0.998, "sources": [{"page_num": 1}]},
            "district": {"confidence": 0.985, "sources": [{"page_num": 1}]},
            "accused_names": [
                {"confidence": 0.975, "sources": [{"page_num": 2}]},
                {"confidence": 0.960, "sources": [{"page_num": 2}]},
            ],
            "vehicle_details": {"confidence": 0.991, "sources": [{"page_num": 1}]},
        },
        "sarvam_job_id": "01a14d41-test-job-id",
    }

    mock_digitise_res = {
        "documents": [
            {
                "pages": [
                    {
                        "page_num": 1,
                        "blocks": [
                            {"text": "FIRST INFORMATION REPORT", "reading_order": 0},
                            {"text": "FIR No: 142/2024, Kurnool Town PS", "reading_order": 1},
                        ]
                    }
                ]
            }
        ]
    }

    svc = SarvamDocAIService()
    with patch.object(svc, "is_available", return_value=True), \
         patch.object(svc, "extract", new_callable=AsyncMock, return_value=mock_extract_res), \
         patch.object(svc, "digitise", new_callable=AsyncMock, return_value=mock_digitise_res), \
         patch("os.path.exists", return_value=True):

        res = await svc.process_document(
            file_path="mock_fir.pdf",
            mime_type="application/pdf",
            schema_fields=DEFAULT_FIR_SCHEMA[:5],
        )

        assert res["provider"] == "Sarvam Document AI (Sarvam Vision 1.5)"
        assert res["sarvam_job_id"] == "01a14d41-test-job-id"
        assert res["extract"]["result"]["fir_number"] == "142/2024"
        assert 1 in res["pages_text_map"]
        assert "FIRST INFORMATION REPORT" in res["pages_text_map"][1]


def test_batching_constant():
    """Verify Sarvam Document AI 10-page batching limit constant."""
    assert MAX_PAGES_PER_JOB == 10
