import io
import requests
import json
from PIL import Image, ImageDraw, ImageFont

BASE_URL = "http://localhost:8000"

def create_sample_jpeg():
    img = Image.new('RGB', (800, 600), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    text_content = (
        "GOVERNMENT OF ANDHRA PRADESH\n"
        "PROHIBITION & EXCISE DEPARTMENT\n"
        "FIRST INFORMATION REPORT (u-FIR)\n\n"
        "FIR Number: FIR-2024-KNL-JPEG-0099\n"
        "District: Kurnool\n"
        "Station: Kurnool Station\n"
        "Date of Offence: 2024-10-15\n"
        "Offence: Illegal possession and transportation of Non-Duty-Paid Liquor (NDPL)\n"
        "Accused: Venkat Ramana, S/o Subba Rao\n"
        "Contraband Seized: 25 Bottles of IML Liquor (180ml each)\n"
        "Vehicle Used: Hero Splendor AP 21 BX 4455\n"
        "Seizing Officer: K. Venkateshwarlu, Inspector\n"
    )
    d.text((40, 40), text_content, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95)
    return buf.getvalue()

def run_tests():
    print("=" * 70)
    print("Testing Intake Upload & Automatic Workflow E2E against Live Server")
    print("=" * 70)

    # 1. Login
    print("\n[Step 1] Logging in as Station Officer (Kurnool)...")
    login_resp = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "station_officer",
        "password": "StationPass@2024"
    })
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("  -> Authenticated successfully!")

    # 2. Upload JPEG Image (mimicking FIR 11.jpg)
    print("\n[Step 2] Uploading JPEG Image 'FIR 11.jpg' to /api/v1/documents/upload...")
    jpeg_bytes = create_sample_jpeg()
    files = {"file": ("FIR 11.jpg", jpeg_bytes, "image/jpeg")}
    upload_resp = requests.post(f"{BASE_URL}/api/v1/documents/upload", files=files, headers=headers)
    print(f"  -> Upload status code: {upload_resp.status_code}")
    if upload_resp.status_code != 200:
        print(f"  -> Error response: {upload_resp.text}")
    assert upload_resp.status_code == 200, f"Expected 200, got: {upload_resp.text}"
    upload_data = upload_resp.json()
    doc_id = upload_data.get("document_id") or upload_data.get("id")
    assert doc_id, "Missing document_id in upload response"
    print(f"  -> Successfully ingested JPEG document ID: {doc_id}")
    print(f"  -> MIME Type: {upload_data.get('mime_type')}")
    print(f"  -> File Hash: {upload_data.get('file_hash')}")
    print(f"  -> Run ID: {upload_data.get('run_id')}")

    # 3. Idempotent re-upload test
    print("\n[Step 3] Testing Idempotent Re-upload of identical JPEG 'FIR 11.jpg'...")
    reupload_resp = requests.post(f"{BASE_URL}/api/v1/documents/upload", files={"file": ("FIR 11.jpg", jpeg_bytes, "image/jpeg")}, headers=headers)
    assert reupload_resp.status_code == 200, f"Re-upload failed: {reupload_resp.text}"
    re_doc_id = reupload_resp.json().get("document_id") or reupload_resp.json().get("id")
    assert re_doc_id == doc_id, f"Document ID changed on re-upload: {re_doc_id} vs {doc_id}"
    print("  -> Idempotent re-upload succeeded with identical document ID (Zero duplicates).")

    # 4. Invalid file rejection test
    print("\n[Step 4] Testing Rejection of Corrupt/Unsupported File...")
    bad_files = {"file": ("fake_document.txt", b"plain text with no magic bytes", "text/plain")}
    bad_resp = requests.post(f"{BASE_URL}/api/v1/documents/upload", files=bad_files, headers=headers)
    assert bad_resp.status_code == 400, f"Expected 400, got {bad_resp.status_code}"
    print(f"  -> Properly rejected with HTTP 400: {bad_resp.json().get('detail')}")

    # 5. Officer Review & Confirmation (Stage 2 Sign-Off)
    print("\n[Step 5] Performing Officer Review & Sign-Off to register case...")
    run_id = upload_data.get("run_id")
    case_payload = {
        "fir_number": "FIR-2024-KNL-JPEG-0099",
        "year": 2024,
        "district": "Kurnool",
        "station": "Kurnool Town Station",
        "mandal": "Kurnool Urban",
        "village": "Kurnool",
        "offence_nature": "Illegal possession and transportation of Non-Duty-Paid Liquor (NDPL)",
        "contraband_type": "IML Liquor",
        "seized_quantity": 4.5,
        "seized_unit": "Litres",
        "vehicle_details": "Hero Splendor AP 21 BX 4455",
        "seizing_officer_name": "K. Venkateshwarlu",
        "seizing_officer_rank": "Inspector",
        "narrative": "During regular vehicular patrol at Kurnool checkpost, accused Venkat Ramana was intercepted carrying 25 bottles of illicit NDPL without permits.",
        "document_ids": [doc_id]
    }

    if run_id:
        confirm_resp = requests.post(f"{BASE_URL}/api/v1/extraction/run/{run_id}/confirm", json={
            "case_id": None,
            "reviewed_data": {
                "structured_fields": [
                    {"key": k, "value": v, "label": k, "data_type": "string", "required": True}
                    for k, v in case_payload.items() if k != "document_ids"
                ],
                "entities": [
                    {"name": "Venkat Ramana", "type": "ACCUSED", "source_page": 1}
                ],
                "document_content": case_payload["narrative"]
            }
        }, headers=headers)
    else:
        confirm_resp = requests.post(f"{BASE_URL}/api/v1/cases/", json=case_payload, headers=headers)

    print(f"  -> Confirm status code: {confirm_resp.status_code}")
    if confirm_resp.status_code != 200:
        print(f"  -> Error: {confirm_resp.text}")
    assert confirm_resp.status_code == 200, f"Case registration failed: {confirm_resp.text}"
    case_data = confirm_resp.json()
    case_id = case_data.get("case_id") or case_data.get("id")
    print(f"  -> Registered case ID: {case_id}")

    # 6. Check Automatic Workflow Progression (Stages 3, 4, 5)
    print("\n[Step 6] Verifying Automated Workflow Execution in Supabase...")
    wf_resp = requests.get(f"{BASE_URL}/api/v1/folders/workflow/{case_id}", headers=headers)
    assert wf_resp.status_code == 200, f"Workflow fetch failed: {wf_resp.text}"
    stages = wf_resp.json()
    print(f"  -> Executed stages: {[s.get('stage') + ': ' + s.get('status') for s in stages]}")
    completed_stages = [s.get("stage") for s in stages if s.get("status") == "COMPLETED"]
    assert len(completed_stages) >= 4, f"Expected at least 4 completed stages, got: {completed_stages}"

    # 7. Test All 5 Case Exports for this case
    print("\n[Step 7] Testing Consolidated Case Exports for case {}:".format(case_id))
    for fmt in ["xlsx", "docx", "pdf", "csv", "json"]:
        exp_resp = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}/export/{fmt}", headers=headers)
        assert exp_resp.status_code == 200, f"Export {fmt} failed with {exp_resp.status_code}"
        cd = exp_resp.headers.get("content-disposition", "")
        print(f"  -> [{fmt.upper()}] Status 200 OK, size: {len(exp_resp.content)} bytes, header: {cd}")

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED WITH ZERO TRANSACTION ERRORS!")
    print("=" * 70)

if __name__ == '__main__':
    run_tests()
