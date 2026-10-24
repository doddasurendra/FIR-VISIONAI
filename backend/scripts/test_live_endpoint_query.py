import requests

BASE = "http://localhost:8000/api/v1"
login_res = requests.post(f"{BASE}/auth/login", json={"username": "state_director", "password": "StateAdmin@2024"})
token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

payload = {
    "query": "What persons or names are visible in this document?",
    "mode": "PDF_ONLY",
    "document_id": "87391677-cae2-4c7f-a64d-652671cfb1af",
    "language": "en"
}

resp = requests.post(f"{BASE}/rag/query", json=payload, headers=headers)
print("HTTP Status:", resp.status_code)
data = resp.json()
clean_ans = str(data.get("answer", "")).encode("ascii", errors="replace").decode("ascii")
print("\nAnswer:\n", clean_ans)
print("\nCitations count:", len(data.get("citations", [])))
for cit in data.get("citations", []):
    print(" - Citation:", cit.get("source_label"), "| doc_id:", cit.get("document_id"))
