"""
Authentication E2E test script for FIR VisionAI.
Tests valid logins, invalid credentials, JWT usage on protected endpoints,
and stress-tests for intermittent 500 errors.

Usage:
    py scripts/test_auth_e2e.py
"""
from __future__ import annotations
import sys
import time
import json
import urllib.request
import urllib.error
from typing import Optional

BASE_URL = "http://localhost:8000"

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
INFO = "\033[94mℹ\033[0m"

results: list[tuple[str, bool, str]] = []


def post_json(path: str, data: dict, token: Optional[str] = None) -> tuple[int, dict]:
    body = json.dumps(data).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except Exception as exc:
        return 0, {"error": str(exc)}


def get_json(path: str, token: Optional[str] = None) -> tuple[int, dict]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE_URL}{path}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except Exception as exc:
        return 0, {"error": str(exc)}


def check(name: str, condition: bool, detail: str = "") -> bool:
    label = PASS if condition else FAIL
    print(f"  {label}  {name}" + (f" — {detail}" if detail else ""))
    results.append((name, condition, detail))
    return condition


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== FIR VisionAI — Authentication E2E Tests ===\n")

# ── TEST 1: Health check ──────────────────────────────────────────────────────
print("● Health Check")
status, body = get_json("/api/v1/health")
check("Backend reachable", status == 200, f"status={status}")

# ── TEST 2: Valid logins ──────────────────────────────────────────────────────
print("\n● Valid Login Tests")
demo_accounts = [
    ("station_officer", "StationPass@2024"),
    ("developer_test",  "DevPass@2024"),
    ("district_admin",  "DistrictPass@2024"),
    ("state_director",  "StateAdmin@2024"),
]
tokens: dict[str, str] = {}
for username, password in demo_accounts:
    status, body = post_json("/api/v1/auth/login", {"username": username, "password": password})
    ok = status == 200 and "access_token" in body
    if ok:
        tokens[username] = body["access_token"]
    check(f"Login: {username}", ok, f"status={status}" + (f", error={body.get('detail','')}" if not ok else ""))

# ── TEST 3: Invalid credentials → 401 ────────────────────────────────────────
print("\n● Invalid Credential Tests")
status, body = post_json("/api/v1/auth/login", {"username": "station_officer", "password": "wrongpassword"})
check("Wrong password → 401", status == 401, f"status={status}")

status, body = post_json("/api/v1/auth/login", {"username": "nonexistent_user_xyz", "password": "any"})
check("Unknown username → 401", status in (401, 404), f"status={status}")

status, body = post_json("/api/v1/auth/login", {"username": "", "password": ""})
check("Empty credentials → non-200", status != 200, f"status={status}")

# ── TEST 4: JWT works on protected endpoint ───────────────────────────────────
print("\n● JWT Token Verification")
if "station_officer" in tokens:
    tok = tokens["station_officer"]
    status, body = get_json("/api/v1/cases/", token=tok)
    check("Protected /cases/ with valid JWT → 200", status == 200, f"status={status}")

    # Tampered token should fail
    bad_tok = tok[:-5] + "XXXXX"
    status, _ = get_json("/api/v1/cases/", token=bad_tok)
    check("Tampered JWT → 401/403/422", status in (401, 403, 422), f"status={status}")
else:
    check("station_officer token available", False, "login failed — skipping JWT tests")

# ── TEST 5: No token → 401/403 ────────────────────────────────────────────────
print("\n● Unauthenticated Access")
status, _ = get_json("/api/v1/cases/")
check("No token → 401 or 403", status in (401, 403), f"status={status}")

# ── TEST 6: No HTTP 500 on 10 sequential rapid logins ────────────────────────
print("\n● Stress Test — 10 sequential logins (checking for intermittent 500)")
five_hundreds = 0
for i in range(10):
    status, body = post_json("/api/v1/auth/login", {"username": "station_officer", "password": "StationPass@2024"})
    if status == 500:
        five_hundreds += 1
        print(f"    {INFO} Attempt {i+1}: HTTP 500 received")
    elif status not in (200, 503):
        print(f"    {INFO} Attempt {i+1}: Unexpected status {status}")
    time.sleep(0.2)
check("0 HTTP 500s in 10 rapid logins", five_hundreds == 0, f"{five_hundreds} 500s encountered")

# ── TEST 7: Check 503 is returned (not 500) if db fails ──────────────────────
# This can't be reliably triggered without killing the DB, so just verify
# the response shape is correct if we got any 503 above
print("\n● Error Response Shape")
# Send a request that forces a graceful error (wrong creds)
status, body = post_json("/api/v1/auth/login", {"username": "station_officer", "password": "wrong"})
check("Error response has 'detail' field", "detail" in body, f"keys={list(body.keys())}")
check("No raw Python traceback in error response", "Traceback" not in str(body), "")

# ── SUMMARY ──────────────────────────────────────────────────────────────────
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed

print(f"\n{'='*50}")
print(f"Results: {passed}/{total} passed, {failed} failed")

if failed > 0:
    print("\nFailed tests:")
    for name, ok, detail in results:
        if not ok:
            print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))

print("="*50 + "\n")
sys.exit(0 if failed == 0 else 1)
