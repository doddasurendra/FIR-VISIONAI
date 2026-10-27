"""
Crime hotspots: clusters come from each case's own incident coordinates, inside the user's
jurisdiction; levels are HIGH (5+ cases or 50L+), MEDIUM (2+ cases), LOW; units are never added
together; cases without coordinates are listed as "location not yet verified".
"""
import sqlite3

import pytest

from app.config import settings
from app.services.hotspots import build_clusters, cluster_by_distance, intensity, normalise_unit
from tests.test_knowledge_base_rag import auth  # noqa: F401

KURNOOL_A = (15.8281, 78.0373)
KURNOOL_B = (15.8301, 78.0390)    # ~0.3 km from A
GUNTUR = (16.3067, 80.4365)


def _inc(case_id, lat, lon, district="Kurnool", station="Kurnool Town Station", qty=None, unit=None):
    return {"case_id": case_id, "fir_number": case_id, "district": district, "station": station, "mandal": None,
            "latitude": lat, "longitude": lon, "seized_quantity": qty, "unit": normalise_unit(unit),
            "contraband_type": "ID Liquor", "incident_date": None, "geocoder_status": "APPROXIMATE"}


# ── Rules ────────────────────────────────────────────────────────────────────

def test_levels_follow_the_department_thresholds():
    assert intensity(5, 0) == "HIGH"
    assert intensity(1, 50) == "HIGH"       # 50 litres or more
    assert intensity(2, 10) == "MEDIUM"
    assert intensity(1, 49.9) == "LOW"


def test_nearby_cases_cluster_and_distant_ones_do_not():
    pts = [_inc("a", *KURNOOL_A), _inc("b", *KURNOOL_B), _inc("c", *GUNTUR)]
    sizes = sorted(len(c) for c in cluster_by_distance(pts))
    assert sizes == [1, 2]


def test_different_stations_are_separate_hotspots_even_when_close():
    pts = [_inc("a", *KURNOOL_A), _inc("b", *KURNOOL_B, station="Kurnool Prohibition & Excise Station")]
    assert len(build_clusters(pts)) == 2


def test_quantities_are_kept_per_unit_and_only_litres_count_towards_50L():
    pts = [_inc("a", *KURNOOL_A, qty=40, unit="Litres"), _inc("b", *KURNOOL_B, qty=500, unit="Bottles"),
           _inc("c", *KURNOOL_B, qty=20, unit="ltrs")]
    (cluster,) = build_clusters(pts)
    assert cluster["seized_by_unit"] == {"Bottles": 500.0, "Litres": 60.0}
    assert cluster["risk_intensity"] == "HIGH"          # 60 L, not 560 "units"
    assert cluster["incident_count"] == 3 and len(cluster["cases"]) == 3


# ── Endpoint ─────────────────────────────────────────────────────────────────

@pytest.fixture
def located_demo_cases():
    """Give three seeded cases coordinates (one left unlocated); restore afterwards."""
    con = sqlite3.connect(settings.DATABASE_URL.split("///", 1)[1])
    rows = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT fir_number, incident_latitude, incident_longitude FROM cases WHERE fir_number IN "
        "('FIR-2024-KNL-0042','FIR-2024-KNL-0019','FIR-2024-GNT-0088','FIR-2023-VSP-0112')")}
    coords = {"FIR-2024-KNL-0042": KURNOOL_A, "FIR-2024-KNL-0019": KURNOOL_B, "FIR-2024-GNT-0088": GUNTUR,
              "FIR-2023-VSP-0112": (None, None)}
    for fir, (lat, lon) in coords.items():
        con.execute("UPDATE cases SET incident_latitude=?, incident_longitude=? WHERE fir_number=?", (lat, lon, fir))
    con.commit()
    yield
    for fir, (lat, lon) in rows.items():
        con.execute("UPDATE cases SET incident_latitude=?, incident_longitude=? WHERE fir_number=?", (lat, lon, fir))
    con.commit()
    con.close()


def _cases_in(body):
    return {i["fir_number"] for h in body["hotspots"] for i in h["cases"]}


def test_station_user_sees_only_their_stations_hotspots(client, located_demo_cases):
    body = client.get("/api/v1/analytics/hotspots", headers=auth(client, "station_officer", "StationPass@2024")).json()
    assert body["total_hotspots"] > 0
    stations = {i["station"] for h in body["hotspots"] for i in h["cases"]}
    stations |= {i["station"] for i in body["incidents"]} | {c["station"] for c in body["unlocated_cases"]}
    assert stations == {"Kurnool Town Station"}
    assert {"FIR-2024-KNL-0042", "FIR-2024-KNL-0019"} <= _cases_in(body)
    assert "FIR-2024-GNT-0088" not in _cases_in(body)


def test_state_user_sees_all_hotspots_and_unlocated_cases(client, located_demo_cases):
    body = client.get("/api/v1/analytics/hotspots", headers=auth(client, "state_director", "StateAdmin@2024")).json()
    assert {"FIR-2024-KNL-0042", "FIR-2024-GNT-0088"} <= _cases_in(body)
    assert "FIR-2023-VSP-0112" in {c["fir_number"] for c in body["unlocated_cases"]}
    assert all(c["location_status"] == "LOCATION_NOT_YET_VERIFIED" for c in body["unlocated_cases"])
    assert body["totals"]["cases"] == body["totals"]["located"] + body["totals"]["unlocated"]
    for h in body["hotspots"]:
        assert h["risk_intensity"] in ("HIGH", "MEDIUM", "LOW") and h["latitude"] and h["longitude"]


def test_filters_narrow_the_hotspots(client, located_demo_cases):
    h = auth(client, "state_director", "StateAdmin@2024")
    body = client.get("/api/v1/analytics/hotspots", headers=h, params={"contraband_type": "Ganja (Cannabis)"}).json()
    assert "FIR-2024-GNT-0088" in _cases_in(body)
    assert all(i["contraband_type"] == "Ganja (Cannabis)" for i in body["incidents"])
    assert "Ganja (Cannabis)" in body["filters"]["contraband_types"]
    future = client.get("/api/v1/analytics/hotspots", headers=h, params={"date_from": "2099-01-01"}).json()
    assert future["total_hotspots"] == 0
    bad = client.get("/api/v1/analytics/hotspots", headers=h, params={"date_from": "2024-02-01", "date_to": "2024-01-01"})
    assert bad.status_code == 400
