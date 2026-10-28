"""
Call every GET endpoint under /api/v1 as a STATION, DISTRICT and STATE user and report unexpected
responses. Read-only: POST/PUT/DELETE are never called, and GETs with side effects (running an
extraction, generating an AI summary) are skipped.

Path parameters are filled with real records: an in-jurisdiction case (FIR-2024-KNL-0042, Kurnool
Town Station) that every demo role may see, and an out-of-jurisdiction case (89/2024, Prakasam)
that only STATE may see. Expected outcomes:
  - 5xx is always a failure;
  - an in-scope resource must answer 2xx for every role, except admin-only endpoints for lower roles;
  - an out-of-scope resource must answer 403/404 for STATION and DISTRICT and 2xx for STATE.

Usage (app running, e.g. via start_all.ps1):
    python scripts/dev/endpoint_sweep.py [--base http://localhost:5173]
"""
import argparse
import re
import sys
import time

import requests

USERS = {
    "STATION": ("station_officer", "StationPass@2024"),
    "DISTRICT": ("district_admin", "DistrictPass@2024"),
    "STATE": ("state_director", "StateAdmin@2024"),
}
IN_SCOPE_FIR, OUT_SCOPE_FIR = "FIR-2024-KNL-0042", "89/2024"
SKIP = {
    "/api/v1/documents/{document_id}/extract",          # runs an AI extraction
    "/api/v1/generation/case/{case_id}/summary",        # may generate an AI summary
    "/api/v1/system/backups/download/{filename}",       # downloads a whole database backup
}
# Required query parameters
QUERY = {
    "/api/v1/jurisdictions/detect-station": {"latitude": 15.8281, "longitude": 78.0373},
    "/api/v1/jurisdictions/reverse-geocode": {"latitude": 15.8281, "longitude": 78.0373},
    "/api/v1/jurisdictions/stations": {"district": "Kurnool"},
    "/api/v1/legal/acts/sections": {"act_name": "Andhra Pradesh Excise Act, 1968"},
}
# Endpoints only higher roles may use: 403 is the correct answer for the roles listed
ADMIN_ONLY = {
    r"^/api/v1/employees": {"STATION"},
    r"^/api/v1/system/backups": {"STATION", "DISTRICT"},
    r"^/api/v1/audit": {"STATION"},
}


def login(base, user, password):
    r = requests.post(f"{base}/api/v1/auth/login", json={"username": user, "password": password}, timeout=60)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def discover(base, h):
    """Real ids for path parameters, read as the STATE user."""
    cases = requests.get(f"{base}/api/v1/cases/", headers=h, timeout=120).json()
    ins = next(c for c in cases if c["fir_number"] == IN_SCOPE_FIR)
    out = next(c for c in cases if c["fir_number"] == OUT_SCOPE_FIR)
    ids = {"in": {"case_id": ins["id"]}, "out": {"case_id": out["id"]}}
    for key, case in (("in", ins), ("out", out)):
        docs = requests.get(f"{base}/api/v1/cases/{case['id']}", headers=h, timeout=60).json().get("documents") or []
        if docs:
            ids[key]["document_id"] = docs[0]["id"]
            run = requests.get(f"{base}/api/v1/extraction/document/{docs[0]['id']}", headers=h, timeout=60)
            if run.ok and run.json().get("run_id"):
                ids[key]["run_id"] = run.json()["run_id"]
        gen = requests.get(f"{base}/api/v1/generation/case/{case['id']}/documents", headers=h, timeout=60).json()
        if gen:
            ids[key]["doc_id"] = gen[0]["id"]
        ids[key]["record_key"] = f"doc:{ids[key]['document_id']}" if ids[key].get("document_id") else f"case:{case['id']}"
        ids[key]["format"] = "json"
    prof = requests.get(f"{base}/api/v1/entities/network-graph", headers=h, params={"case_id": ins["id"]}, timeout=120).json()
    ent = next((n["id"] for n in prof.get("nodes", []) if not str(n["id"]).startswith("vehicle:")), None)
    if ent:
        ids["in"]["entity_id"] = ent
    ids["in"]["folder_slug"] = "illicit-distillation"  # folders are not tied to one case: in-scope run only
    return ids


def fill(path, values):
    names = re.findall(r"\{(\w+)\}", path)
    if any(n not in values for n in names):
        return None
    return re.sub(r"\{(\w+)\}", lambda m: str(values[m.group(1)]), path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5173")
    ap.add_argument("--api", help="backend address for /openapi.json (default: try :8000, then :8001)")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    # The API description is served by the backend itself (8000, or 8001 when 8000 is taken)
    spec = None
    for api in ([args.api] if args.api else ["http://localhost:8000", "http://localhost:8001"]):
        try:
            spec = requests.get(f"{api}/openapi.json", timeout=60)
            if spec.ok:
                break
        except requests.RequestException:
            continue
    if spec is None or not spec.ok:
        sys.exit("The backend's /openapi.json could not be reached; start the app or pass --api.")
    paths = sorted(p for p, ops in spec.json()["paths"].items() if "get" in ops and p.startswith("/api/v1"))
    headers = {role: login(base, *cred) for role, cred in USERS.items()}
    ids = discover(base, headers["STATE"])

    failures, checked, skipped, outages = [], 0, [], []
    for path in paths:
        if path in SKIP:
            skipped.append(f"{path} (side effects)")
            continue
        variants = [("list", path)] if "{" not in path else [
            (scope, fill(path, ids[scope])) for scope in ("in", "out")]
        for scope, url in variants:
            if url is None:
                skipped.append(f"{path} [{scope}] (no record to fill it)")
                continue
            for role, h in headers.items():
                t = time.perf_counter()
                try:
                    r = requests.get(f"{base}{url}", headers=h, params=QUERY.get(path), timeout=120)
                    code = r.status_code
                except requests.RequestException as e:
                    code, r = 0, None
                took = time.perf_counter() - t
                checked += 1
                if code == 503:
                    # The database was unreachable: try once more, and report the outage either way
                    retry = requests.get(f"{base}{url}", headers=h, params=QUERY.get(path), timeout=120)
                    outages.append(f"{role:8} 503 then {retry.status_code} {url}")
                    r, code = retry, retry.status_code
                admin_denied = any(re.search(rx, path) and role in roles for rx, roles in ADMIN_ONLY.items())
                if code >= 500 or code == 0:
                    ok = False
                elif admin_denied:
                    ok = code in (200, 403)  # 403 expected; some admin lists answer scoped data instead
                elif scope == "out" and role != "STATE":
                    ok = code in (403, 404)
                else:
                    ok = 200 <= code < 300
                if not ok:
                    detail = ""
                    if r is not None:
                        try:
                            detail = str(r.json().get("detail", ""))[:120]
                        except ValueError:
                            detail = r.text[:120]
                    failures.append(f"{role:8} {code} {url}  [{scope}] {detail}")
                elif took > 15:
                    failures.append(f"{role:8} SLOW {took:.0f}s {url}")
    print(f"GET endpoints: {len(paths)}; requests: {checked}; skipped: {len(skipped)}")
    for s in skipped:
        print("  skipped:", s)
    print(f"database outages during the sweep (503, retried once): {len(outages)}")
    for o in outages:
        print("  ", o)
    print(f"unexpected: {len(failures)}")
    for f in failures:
        print("  ", f)
    return 1 if failures or outages else 0


if __name__ == "__main__":
    sys.exit(main())
