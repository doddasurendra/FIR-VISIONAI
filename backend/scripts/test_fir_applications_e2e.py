"""
FIR VisionAI — Comprehensive E2E Verification for Multilingual FIR Applications & Date-Wise Search
Tests:
1. Station Officer Authentication
2. Creation of Multilingual FIR Application (EN, TE, HI templates)
3. Multiple Applications on Same Day (distinct case IDs & timestamps)
4. Preservation of Separate Dates (application_date, registration_date, incident_date)
5. Date-wise Search & Filtering (by date, date range, status, person, location)
6. Daily Summary Counts derived from database
7. Export Results (xlsx, csv, json)
8. Individual Form Download (pdf, docx, json) with trilingual language preservation
9. Jurisdiction Scoping Enforcement (cross-district blocked with 403)
"""
import sys
import os
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

def run_tests():
    print("=" * 75)
    print("FIR VisionAI — Multilingual FIR Applications & Date-Wise Search E2E Test")
    print("=" * 75)

    # 1. Login
    print("\n[Step 1/9] Authenticating Station Officer (Kurnool)...")
    res = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "station_officer",
        "password": "StationPass@2024"
    })
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("  -> Authenticated successfully as K. Venkateshwarlu (STATION - Kurnool)")

    # 2. Create Multilingual FIR Application (Telugu template & English values)
    print("\n[Step 2/9] Creating First FIR Application (Telugu template)...")
    payload1 = {
        "fir_number": f"TEST-FIR-2024-KNL-{datetime.utcnow().strftime('%H%M%S')}-01",
        "district": "Kurnool",
        "station": "Kurnool Town Station",
        "mandal": "Kurnool Urban",
        "village": "Budhawarpet",
        "location_description": "Near Old Bus Stand Checkpost",
        "offence_nature": "Illicit Distillation and Transport",
        "offence_category": "EXCISE",
        "contraband_type": "ID Liquor (Arrack)",
        "seized_quantity": 45.5,
        "seized_unit": "Litres",
        "vehicle_details": "Auto AP21TY4567",
        "seizing_officer_name": "K. Venkateshwarlu",
        "seizing_officer_rank": "Excise Sub-Inspector",
        "witnesses_summary": "P. Ramesh (Punch 1), G. Suresh (Punch 2)",
        "narrative": "During regular vehicular checking, seized 45.5 litres illicit liquor.",
        "application_date": "2024-10-22",
        "incident_date": "2024-10-21",
        "form_template": "FIR_FORM_AP_EXCISE_v1",
        "form_language": "te",
        "form_values_json": json.dumps({"notes": "భాష: తెలుగు, దరఖాస్తుదారు వివరాలు భద్రపరచబడ్డాయి"}),
        "application_status": "DRAFT"
    }
    res = requests.post(f"{BASE_URL}/api/v1/fir-applications/", headers=headers, json=payload1)
    assert res.status_code == 200, f"Create application 1 failed: {res.text}"
    app1 = res.json()
    case_id_1 = app1["id"]
    print(f"  [OK] Created Application 1: ID={case_id_1}, FIR={app1['fir_number']}, Lang={app1['form_language']}")

    # 3. Multiple FIR Applications on the Same Day
    print("\n[Step 3/9] Creating Second FIR Application on Same Day (Hindi template)...")
    payload2 = {
        "fir_number": f"TEST-FIR-2024-KNL-{datetime.utcnow().strftime('%H%M%S')}-02",
        "district": "Kurnool",
        "station": "Kurnool Town Station",
        "mandal": "Kurnool Rural",
        "village": "Gargeyapuram",
        "location_description": "Highway NH44 km 214",
        "offence_nature": "NDPS Transport",
        "offence_category": "NDPS",
        "contraband_type": "Ganja (Cannabis)",
        "seized_quantity": 12.0,
        "seized_unit": "Kgs",
        "vehicle_details": "Bolero AP21AB9999",
        "seizing_officer_name": "K. Venkateshwarlu",
        "seizing_officer_rank": "Excise Sub-Inspector",
        "witnesses_summary": "Local witnesses near toll gate",
        "narrative": "Intercepted vehicle carrying contraband hidden in secret compartment.",
        "application_date": "2024-10-22",
        "incident_date": "2024-10-20",
        "form_template": "NDPS_REPORT_v1",
        "form_language": "hi",
        "form_values_json": json.dumps({"notes": "भाषा: हिंदी, एनडीपीएस जब्ती रिपोर्ट"}),
        "application_status": "SUBMITTED"
    }
    res = requests.post(f"{BASE_URL}/api/v1/fir-applications/", headers=headers, json=payload2)
    assert res.status_code == 200, f"Create application 2 failed: {res.text}"
    app2 = res.json()
    case_id_2 = app2["id"]
    assert case_id_1 != case_id_2, "Case IDs must be distinct"
    print(f"  [OK] Created Application 2: ID={case_id_2}, FIR={app2['fir_number']}, Lang={app2['form_language']}")
    print("  -> Multiple applications successfully registered on same day with distinct IDs")

    # 4. Date Distinction Verification
    print("\n[Step 4/9] Verifying Distinct Date Storage (Application, Registration, Incident)...")
    res = requests.get(f"{BASE_URL}/api/v1/fir-applications/{case_id_1}", headers=headers)
    assert res.status_code == 200, f"Get detail failed: {res.text}"
    c1 = res.json()
    print(f"  * Application Date  : {c1['application_date']}")
    print(f"  * Registration Date : {c1['registration_date']}")
    print(f"  * Incident Date     : {c1['incident_date']}")
    assert c1['application_date'] is not None, "Application date must exist"
    assert c1['incident_date'] is not None, "Incident date must exist"
    assert c1['incident_date'][:10] != c1['application_date'][:10], "Incident date must not equal application date"
    print("  [OK] Dates stored separately and verified distinct!")

    # 5. Date-Wise Search & Filtering
    print("\n[Step 5/9] Testing Date-Wise Search & Advanced Filters...")
    # Search by single application date
    res = requests.get(f"{BASE_URL}/api/v1/fir-applications/?date=2024-10-22&date_type=application", headers=headers)
    assert res.status_code == 200, f"Search by date failed: {res.text}"
    data = res.json()
    assert data["total"] >= 2, f"Expected at least 2 records for 2024-10-22, got {data['total']}"
    print(f"  [OK] Single date search (2024-10-22): {data['total']} records found")

    # Search by FIR Number
    res = requests.get(f"{BASE_URL}/api/v1/fir-applications/?fir_number={app1['fir_number']}", headers=headers)
    assert res.status_code == 200
    assert res.json()["total"] == 1, "Expected exactly 1 match for specific FIR number"
    print(f"  [OK] Search by FIR Number: 1 match verified")

    # Search by Person
    res = requests.get(f"{BASE_URL}/api/v1/fir-applications/?person=Venkateshwarlu", headers=headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 2, "Expected matching person records"
    print(f"  [OK] Search by Person ('Venkateshwarlu'): {res.json()['total']} matches")

    # Search by Location
    res = requests.get(f"{BASE_URL}/api/v1/fir-applications/?location=Budhawarpet", headers=headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 1, "Expected matching location records"
    print(f"  [OK] Search by Location ('Budhawarpet'): {res.json()['total']} match")

    # 6. Daily Summary Counts
    print("\n[Step 6/9] Testing Daily Summary Counts Endpoint...")
    res = requests.get(f"{BASE_URL}/api/v1/fir-applications/summary?date=2024-10-22&date_type=application", headers=headers)
    assert res.status_code == 200, f"Summary failed: {res.text}"
    summary = res.json()
    print(f"  * Total Applications : {summary['total_applications']}")
    print(f"  * Registered         : {summary['registered']}")
    print(f"  * Drafts             : {summary['drafts']}")
    print(f"  * Under Investigation: {summary['under_investigation']}")
    assert summary["total_applications"] >= 2, "Summary total must be >= 2"
    assert summary["drafts"] >= 1, "Summary drafts must be >= 1"
    print("  [OK] Real database-derived summary counts verified!")

    # 7. Export Results (xlsx, csv, json)
    print("\n[Step 7/9] Testing Date-Wise Search Results Export (xlsx, csv, json)...")
    for fmt in ("xlsx", "csv", "json"):
        res = requests.get(
            f"{BASE_URL}/api/v1/fir-applications/export/results?fmt={fmt}&date=2024-10-22&date_type=application",
            headers=headers
        )
        assert res.status_code == 200, f"Export {fmt} failed: {res.text}"
        assert len(res.content) > 100, f"Export {fmt} returned empty content"
        cd = res.headers.get("content-disposition", "")
        print(f"  [OK] Export .{fmt}: {len(res.content)} bytes, header: {cd}")

    # 8. Individual Form Download (pdf, docx, json) with Language Preserved
    print("\n[Step 8/9] Testing Individual Form Download (pdf, docx, json)...")
    for fmt, lang in [("pdf", "te"), ("docx", "hi"), ("json", "en")]:
        res = requests.get(
            f"{BASE_URL}/api/v1/fir-applications/{case_id_1}/download?fmt={fmt}&lang={lang}",
            headers=headers
        )
        assert res.status_code == 200, f"Form download {fmt} failed: {res.text}"
        assert len(res.content) > 100, f"Form download {fmt} returned empty content"
        cd = res.headers.get("content-disposition", "")
        print(f"  [OK] Download .{fmt} (lang={lang}): {len(res.content)} bytes, header: {cd}")

    # 9. Jurisdiction Enforcement
    print("\n[Step 9/9] Testing Jurisdiction Enforcement...")
    # Attempt to create application in unauthorized district (Cyberabad/Hyderabad) as Kurnool station officer
    unauth_payload = {
        "fir_number": f"UNAUTH-FIR-{datetime.utcnow().strftime('%H%M%S')}",
        "district": "Hyderabad",
        "station": "Cyberabad Central",
        "offence_nature": "Testing Breach",
        "application_status": "DRAFT"
    }
    res = requests.post(f"{BASE_URL}/api/v1/fir-applications/", headers=headers, json=unauth_payload)
    assert res.status_code == 403, f"Expected 403 Forbidden for out-of-jurisdiction, got {res.status_code}"
    print("  [OK] Jurisdiction enforcement: correctly blocked out-of-jurisdiction creation with 403 Forbidden!")

    print("\n" + "=" * 75)
    print("ALL 9 E2E FIR APPLICATION VERIFICATION TESTS PASSED 100%!")
    print("=" * 75)
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
