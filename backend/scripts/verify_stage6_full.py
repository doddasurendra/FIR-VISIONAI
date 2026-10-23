import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=20)

print("=== 1. HEALTH CHECK ===")
health = client.get("/api/v1/health")
print("Health:", health.status_code, health.json().get("status"), health.json().get("database"))
assert health.status_code == 200

print("\n=== 2. AUTHENTICATION ===")
login = client.post("/api/v1/auth/login", json={"username": "state_director", "password": "StateAdmin@2024"})
assert login.status_code == 200
token = login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("Login successful (token acquired)")

print("\n=== 3. STAGE 6 CRIMINAL NETWORK INTELLIGENCE ENDPOINT ===")
case_id = "20836946-e448-4af8-9be3-561cfaf47190"
s6_res = client.get(f"/api/v1/entities/case/{case_id}/stage6-intelligence", headers=headers)
print("Stage 6 status code:", s6_res.status_code)
assert s6_res.status_code == 200
s6_data = s6_res.json()

print(f"FIR Number: {s6_data['fir_number']}")
print(f"Status: {s6_data['status']}")
print(f"Identified Entity Categories: {list(s6_data['identified_entities'].keys())}")
print(f"Total Case Entities: {s6_data['stats']['total_entities']}")
print(f"Repeat Appearances Found: {s6_data['stats']['repeat_appearances_count']}")
print(f"Graph Nodes: {len(s6_data['graph_data']['nodes'])}, Graph Edges: {len(s6_data['graph_data']['edges'])}")

if s6_data["repeat_appearances"]:
    rep = s6_data["repeat_appearances"][0]
    print(f"Sample Repeat Match: {rep['canonical_name']} ({rep['match_label']}, Conf: {rep['confidence_score']})")
    print(f"  Source Citation: {rep['source_evidence']['doc_name']} (Pg {rep['source_evidence']['page_number']})")
    print(f"  Related Case(s): {[rc['fir_number'] for rc in rep['related_cases']]}")
    print(f"  Advisory: {rep['advisory_notice'][:80]}...")

print("\n=== 4. OFFICER MATCH DECISION (CONFIRM, REJECT, CORRECT) ===")
test_ent_id = s6_data["repeat_appearances"][0]["entity_id"] if s6_data["repeat_appearances"] else "3990317b-5791-4dbd-982d-d53aca47db45"

# Confirm
conf_res = client.post("/api/v1/entities/matches/decision", headers=headers, json={
    "case_id": case_id,
    "entity_id": test_ent_id,
    "decision": "CONFIRM",
    "notes": "Verified by State Director"
})
print("Confirm Match:", conf_res.status_code, conf_res.json()["message"])
assert conf_res.status_code == 200

# Correct
corr_res = client.post("/api/v1/entities/matches/decision", headers=headers, json={
    "case_id": case_id,
    "entity_id": test_ent_id,
    "decision": "CORRECT",
    "corrected_name": "Ramu Naidu (Verified)",
    "notes": "Spelling normalized"
})
print("Correct Match:", corr_res.status_code, corr_res.json()["message"])
assert corr_res.status_code == 200

# Reset back
client.post("/api/v1/entities/matches/decision", headers=headers, json={
    "case_id": case_id,
    "entity_id": test_ent_id,
    "decision": "CONFIRM",
    "corrected_name": "Ramu Naidu",
    "notes": "Reset to standard"
})

print("\n=== 5. WORKFLOW STAGES VERIFICATION ===")
wf_res = client.get(f"/api/v1/folders/workflow/{case_id}", headers=headers)
print("Workflow status code:", wf_res.status_code)
assert wf_res.status_code == 200
stages = wf_res.json()
print(f"Stages in DB for case: {[s['stage'] for s in stages]}")

print("\n=== 6. WORKFLOW RETRY PIPELINE TRIGGER ===")
retry_res = client.post(f"/api/v1/folders/workflow/{case_id}/retry", headers=headers)
print("Workflow retry status:", retry_res.status_code, retry_res.json())
assert retry_res.status_code == 200

# Recheck stages after workflow trigger
wf_res2 = client.get(f"/api/v1/folders/workflow/{case_id}", headers=headers)
stages2 = wf_res2.json()
stage_names = [s["stage"] for s in stages2]
print(f"Updated stages in DB: {stage_names}")
assert "REPEAT_OFFENDER_INTELLIGENCE" in stage_names, "REPEAT_OFFENDER_INTELLIGENCE must be in workflow stages!"

print("\nALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
