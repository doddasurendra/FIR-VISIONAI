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
