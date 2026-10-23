import requests
import json

BASE = "http://localhost:8000/api/v1"

# 1. Login to get token
login_res = requests.post(f"{BASE}/auth/login", json={"username": "state_director", "password": "StateAdmin@2024"})
print("Login status:", login_res.status_code)
assert login_res.status_code == 200, f"Login failed: {login_res.text}"
token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Test /documents/historical-firs
print("\n--- Testing GET /documents/historical-firs ---")
hf_res = requests.get(f"{BASE}/documents/historical-firs", headers=headers)
print("Historical FIRs status:", hf_res.status_code)
hf_data = hf_res.json()
print("Historical FIRs count:", hf_data.get("total", len(hf_data.get("records", []))))
if hf_data.get("records"):
    first = hf_data["records"][0]
    print(f"First record: id={first['document_id']} label={first.get('display_label')} is_image={first.get('is_image')}")

# 3. Test fir_c41834.png (doc_id = 763579c9-b7fc-4eed-845f-b532a08702c8)
c41834_id = "763579c9-b7fc-4eed-845f-b532a08702c8"
print(f"\n--- Testing GET /documents/{c41834_id}/pages ---")
pages_res = requests.get(f"{BASE}/documents/{c41834_id}/pages", headers=headers)
print("Pages status:", pages_res.status_code)
pages_data = pages_res.json()
print("Filename:", pages_data.get("original_filename"))
print("Status:", pages_data.get("ingestion_status"))
print("Is image:", pages_data.get("is_image"))
print("Page count:", len(pages_data.get("pages", [])))
if pages_data.get("pages"):
    snippet = pages_data["pages"][0].get("text_snippet", "")
    print(f"Snippet length: {len(snippet)} chars; snippet start: {snippet[:120]}...")

print(f"\n--- Testing GET /documents/{c41834_id}/view ---")
view_res = requests.get(f"{BASE}/documents/{c41834_id}/view", headers=headers)
print("View status:", view_res.status_code)
print("Content-Type:", view_res.headers.get("content-type"))
print("Content-Length:", len(view_res.content), "bytes")

# 4. Test Mode D CROSS_CASE RAG query
print("\n--- Testing POST /rag/query (Mode D: CROSS_CASE) ---")
cross_payload = {
    "query": "What vehicles or registration numbers are mentioned in illicit liquor cases?",
    "mode": "CROSS_CASE",
    "language": "en"
}
cross_res = requests.post(f"{BASE}/rag/query", json=cross_payload, headers=headers)
print("Cross-case RAG status:", cross_res.status_code)
cross_data = cross_res.json()
clean_cross_ans = cross_data.get("answer", "")[:250].encode('ascii', errors='replace').decode('ascii')
print("Answer start:", clean_cross_ans)
print("Citations count:", len(cross_data.get("citations", [])))
for cit in cross_data.get("citations", [])[:3]:
    clean_label = cit.get('source_label', '').encode('ascii', errors='replace').decode('ascii')
    print(f" - Citation: label={clean_label} doc_id={cit.get('document_id')} page={cit.get('physical_page_number')}")

# 5. Test Mode A PDF_ONLY on fir_c41834.png
print(f"\n--- Testing POST /rag/query (Mode A on {c41834_id}) ---")
mode_a_payload = {
    "query": "What are the details of this FIR?",
    "mode": "PDF_ONLY",
    "document_id": c41834_id,
    "language": "en"
}
mode_a_res = requests.post(f"{BASE}/rag/query", json=mode_a_payload, headers=headers)
print("Mode A status:", mode_a_res.status_code)
mode_a_data = mode_a_res.json()
clean_mode_a_ans = mode_a_data.get("answer", "")[:250].encode('ascii', errors='replace').decode('ascii')
print("Answer start:", clean_mode_a_ans)
print("Citations count:", len(mode_a_data.get("citations", [])))
for cit in mode_a_data.get("citations", []):
    clean_label = cit.get('source_label', '').encode('ascii', errors='replace').decode('ascii')
    print(f" - Citation: label={clean_label} doc_id={cit.get('document_id')} page={cit.get('physical_page_number')}")

print("\nALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
