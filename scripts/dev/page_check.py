"""
Open FIR VisionAI pages in a real (headless Chromium) browser and report problems.

For each page: console errors, uncaught page errors, failed /api calls (HTTP >= 400 or network
failure), spinners still visible after the wait, and a screenshot. Signs in through the API with the
given demo account and stores the session the way the app does.

  python scripts/dev/page_check.py --user station_officer --password ... /reports "click:Geographic Hotspots"
  python scripts/dev/page_check.py --user state_director --password ... --lang te / /cases /legal

Each page argument is a path, optionally followed by steps separated by "|":
  click:<visible text>   click the first element showing that text
  type:<text>            type into the last visible text box and press Enter
  "/reports|click:Geographic Hotspots"   "/ai-fir-assistance?docId=...|type:What was seized?"
Exit code 1 if any page had a problem.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright


def login(base: str, user: str, password: str) -> dict:
    req = urllib.request.Request(f"{base}/api/v1/auth/login", data=json.dumps({"username": user, "password": password}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="+")
    ap.add_argument("--base", default="http://localhost:5173")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--lang", default="en", choices=["en", "te", "hi"])
    ap.add_argument("--wait", type=float, default=6.0, help="seconds to let each page settle")
    ap.add_argument("--out", default=os.path.join("logs", "page_checks"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    session = login(args.base, args.user, args.password)
    problems_total = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script(f"""
            localStorage.setItem('fir_sahayak_token', {json.dumps(session['access_token'])});
            localStorage.setItem('fir_sahayak_refresh_token', {json.dumps(session.get('refresh_token') or '')});
            localStorage.setItem('fir_sahayak_user', {json.dumps(json.dumps(session.get('user') or {}))});
            localStorage.setItem('fir_sahayak_lang', {json.dumps(args.lang)});
        """)
        for spec in args.pages:
            path, *steps = spec.split("|")
            page = ctx.new_page()
            page.set_default_timeout(60000)  # no browser operation may hang the check
            problems = []
            page.on("console", lambda m: problems.append(f"console {m.type}: {m.text[:200]}") if m.type == "error" else None)
            page.on("pageerror", lambda e: problems.append(f"page error: {str(e)[:200]}"))
            page.on("requestfailed", lambda r: problems.append(f"request failed: {r.url[-80:]} {r.failure}")
                    if "/api/" in r.url else None)
            page.on("response", lambda r: problems.append(f"HTTP {r.status}: {r.request.method} {r.url.split('/api/v1')[-1][:90]}")
                    if "/api/" in r.url and r.status >= 400 else None)
            page.goto(args.base + path, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(args.wait * 1000)
            for step in steps:
                if step.startswith("click:"):
                    page.get_by_text(step[6:], exact=False).first.click(timeout=15000)
                    page.wait_for_timeout(args.wait * 1000)
                elif step.startswith("type:"):
                    # Types into the last visible text box (e.g. the chat input) and submits with Enter
                    box = page.locator("textarea:visible, input[type=text]:visible").last
                    box.fill(step[5:])
                    box.press("Enter")
                    page.wait_for_timeout(args.wait * 1000)
            spinners = page.locator(".animate-spin:visible").count()
            if spinners:
                problems.append(f"{spinners} spinner(s) still visible after {args.wait:g}s")
            name = re.sub(r"[^a-z0-9]+", "_", f"{args.user}_{args.lang}_{spec}".lower()).strip("_")[:90]
            shot = os.path.join(args.out, name + ".png")
            try:
                page.screenshot(path=shot, full_page=True, timeout=60000)
            except Exception as e:
                problems.append(f"screenshot failed: {str(e)[:120]}")
            status = "OK" if not problems else f"{len(problems)} problem(s)"
            print(f"[{status}] {spec} ({args.user}, {args.lang}) -> {shot}", flush=True)
            for prob in problems:
                print("     -", prob, flush=True)
            problems_total += len(problems)
            page.close()
        browser.close()
    return 1 if problems_total else 0


if __name__ == "__main__":
    sys.exit(main())
