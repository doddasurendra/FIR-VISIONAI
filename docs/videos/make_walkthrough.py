"""
Build the FIR VisionAI walkthrough videos (English and Telugu) from the running application.

Stages:
  capture  - log in with Playwright and screenshot each page of the live app (1920x1080)
  build    - per language: neural narration (edge-tts), frames rendered in Chromium (so Telugu
             script is shaped correctly), one segment per sentence, then one MP4 with chapter
             markers, burned-in subtitles and a separate .srt
  verify   - duration, streams, audio level, chapters, subtitle timing and sample frames

Usage (from the repository root, with the app running on http://localhost:5173):
    python docs/videos/make_walkthrough.py --stage all
    python docs/videos/make_walkthrough.py --stage build --lang te
Credentials come from FIR_VIDEO_USER / FIR_VIDEO_PASSWORD (default: the seeded demo state officer).
Outputs: docs/videos/output/ (MP4s, not committed) and docs/videos/subtitles/*.srt.
"""
import argparse
import asyncio
import base64
import html
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from narration import CHAPTERS  # noqa: E402

OUT = os.path.join(HERE, "output")
SCREENS = os.path.join(OUT, "screens")
SUBS = os.path.join(HERE, "subtitles")
BASE_URL = os.environ.get("FIR_VIDEO_URL", "http://localhost:5173")
VOICES = {"en": "en-IN-NeerjaNeural", "te": "te-IN-ShrutiNeural"}
NAMES = {"en": "English", "te": "Telugu"}
PAUSE = 0.45      # silence after each sentence (s)
FPS = 25
W, H = 1920, 1080


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode != 0:
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(cmd[:6])} ...\n{r.stderr[-1500:]}")
    return r


def media_info(path: str) -> str:
    return subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stderr


def duration_of(path: str) -> float:
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", media_info(path))
    if not m:
        raise RuntimeError(f"no duration for {path}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


# ── Capture ─────────────────────────────────────────────────────────────────

SHOTS = [
    ("dashboard_top", "/", None),
    ("dashboard_kpi", "/", "scroll:430"),  # count cards + Action Items below the sticky header
    ("cases", "/cases", None),
    ("case_detail", "/cases", "open_first_case"),
    ("intake", "/intake", None),
    ("extraction", "/document-extraction", None),
    ("ai_assist", "/ai-fir-assistance", None),
    ("kb", "/knowledge-base", None),
    ("summaries", "/summaries", "wait:5"),
    ("legal", "/legal", None),
    ("network", "/network", "wait:7"),
    ("entity_review", "/entity-review", None),
    ("case_diary", "/case-diary", None),
    ("employees", "/employees", None),
    ("audit", "/audit-trail", None),
    ("folders_menu", "/", "open_folders_menu"),
    ("folder_view", "/folders/illicit-distillation", None),
    ("voice", "/", "voice_assistant"),
]


async def capture():
    from playwright.async_api import async_playwright
    os.makedirs(SCREENS, exist_ok=True)
    user = os.environ.get("FIR_VIDEO_USER", "state_director")
    password = os.environ.get("FIR_VIDEO_PASSWORD", "StateAdmin@2024")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=os.path.join(SCREENS, "login.png"))
        await page.fill('input[placeholder^="e.g. station_officer"]', user)
        await page.fill('input[type="password"]', password)
        await page.click('button[type="submit"]:has-text("Sign In")')
        await page.wait_for_selector("text=QUICK ACCESS", timeout=60000)
        for shot_id, path, action in SHOTS:
            await page.goto(BASE_URL + path, wait_until="networkidle")
            await page.wait_for_timeout(2500)
            if action and action.startswith("scroll:"):
                await page.evaluate(f"window.scrollTo(0, {int(action.split(':')[1])})")
                await page.wait_for_timeout(800)
            elif action and action.startswith("wait:"):
                await page.wait_for_timeout(int(action.split(":")[1]) * 1000)
            elif action == "open_first_case":
                link = page.locator("text=Review Case").first
                if not await link.count():
                    link = page.locator("text=Details").first
                await link.click()
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(3000)
            elif action == "open_folders_menu":
                await page.locator("button:has-text('All FIR Folders')").first.click()
                await page.wait_for_timeout(1200)
            elif action == "voice_assistant":
                await page.click('button[aria-label="Open the FIR VisionAI voice assistant"]')
                await page.fill('input[aria-label="Type your question"]', "What can you do?")
                await page.keyboard.press("Enter")
                await page.wait_for_selector("text=I can help in three ways", timeout=60000)
                await page.wait_for_timeout(800)
            await page.screenshot(path=os.path.join(SCREENS, f"{shot_id}.png"))
            print(f"captured {shot_id}", flush=True)
        await browser.close()


# ── Build ───────────────────────────────────────────────────────────────────

FRAME_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { width: 1920px; height: 1080px; overflow: hidden; font-family: 'Nirmala UI', 'Segoe UI', sans-serif; }
.bg { position: absolute; inset: 0; width: 1920px; height: 1080px; object-fit: cover; }
.badge { position: absolute; top: 28px; left: 28px; background: rgba(15, 32, 74, 0.92); color: #fff;
         padding: 12px 22px; border-radius: 14px; font-size: 30px; font-weight: 700; box-shadow: 0 6px 18px rgba(0,0,0,.35); }
.badge small { font-weight: 400; opacity: .8; margin-right: 10px; }
.sub { position: absolute; left: 50%; bottom: 46px; transform: translateX(-50%); width: 1640px;
       background: rgba(0, 0, 0, 0.80); color: #fff; font-size: 40px; line-height: 1.38; text-align: center;
       padding: 22px 36px; border-radius: 16px; }
.card { position: absolute; inset: 0; background: linear-gradient(135deg, #0b1d4d 0%, #123a7a 55%, #0f5132 100%);
        color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
.card .brand { font-size: 46px; letter-spacing: 2px; opacity: .85; }
.card .title { font-size: 96px; font-weight: 700; margin: 18px 0 10px; }
.card .meta { font-size: 30px; opacity: .75; }
"""


def frame_html(lang, chapter_no, chapter_count, title, text, screen_png):
    sub = f'<div class="sub">{html.escape(text)}</div>'
    if screen_png:
        with open(screen_png, "rb") as f:
            img = base64.b64encode(f.read()).decode()
        badge = f'<div class="badge"><small>{chapter_no}/{chapter_count}</small>{html.escape(title)}</div>'
        body = f'<img class="bg" src="data:image/png;base64,{img}">{badge}{sub}'
    else:
        meta = "u-FIR v2.0 · Andhra Pradesh Prohibition & Excise Department"
        body = (f'<div class="card"><div class="brand">FIR VisionAI</div><div class="title">{html.escape(title)}</div>'
                f'<div class="meta">{meta}</div></div>{sub}')
    return f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><style>{FRAME_CSS}</style></head><body>{body}</body></html>'


async def tts(text, voice, path, attempts=4):
    import edge_tts
    for i in range(attempts):
        try:
            await edge_tts.Communicate(text, voice).save(path)
            if os.path.getsize(path) > 1000:
                return
        except Exception as e:
            print(f"  tts retry {i + 1}: {e}", flush=True)
        await asyncio.sleep(2 * (i + 1))
    raise RuntimeError(f"TTS failed for: {text[:60]}")


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


async def build(lang):
    from playwright.async_api import async_playwright
    work = os.path.join(OUT, lang)
    os.makedirs(work, exist_ok=True)
    os.makedirs(SUBS, exist_ok=True)
    ff = ffmpeg_exe()
    scenes = []
    for ci, ch in enumerate(CHAPTERS, start=1):
        for si, (shot, texts) in enumerate(ch["scenes"], start=1):
            scenes.append({"chapter": ci, "title": ch["title"][lang], "shot": shot, "text": texts[lang], "id": f"{ci:02}_{si:02}"})
    missing = [s["shot"] for s in scenes if s["shot"] and not os.path.exists(os.path.join(SCREENS, f"{s['shot']}.png"))]
    if missing:
        raise RuntimeError(f"missing screenshots (run --stage capture): {sorted(set(missing))}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": W, "height": H})
        for s in scenes:
            audio = os.path.join(work, f"{s['id']}.mp3")
            frame = os.path.join(work, f"{s['id']}.png")
            if not os.path.exists(audio):
                await tts(s["text"], VOICES[lang], audio)
            screen = os.path.join(SCREENS, f"{s['shot']}.png") if s["shot"] else None
            await page.set_content(frame_html(lang, s["chapter"], len(CHAPTERS), s["title"], s["text"], screen), wait_until="load")
            await page.wait_for_timeout(150)
            await page.screenshot(path=frame)
            s["audio"], s["frame"] = audio, frame
            s["seconds"] = round(duration_of(audio) + PAUSE, 3)
        await browser.close()
    print(f"[{lang}] narration and frames ready for {len(scenes)} scenes", flush=True)

    segs = []
    for s in scenes:
        seg = os.path.join(work, f"{s['id']}.mp4")
        run([ff, "-y", "-loop", "1", "-framerate", str(FPS), "-i", s["frame"], "-i", s["audio"],
             "-filter_complex", f"[1:a]aresample=48000,apad=pad_dur={PAUSE}[a]", "-map", "0:v", "-map", "[a]",
             "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage", "-crf", "20", "-pix_fmt", "yuv420p",
             "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-t", f"{s['seconds']:.3f}",
             "-shortest", seg])
        s["seconds"] = round(duration_of(seg), 3)  # actual segment length drives subtitles and chapters
        segs.append(seg)
    concat = os.path.join(work, "concat.txt")
    with open(concat, "w", encoding="utf-8") as f:
        f.writelines(f"file '{seg.replace(os.sep, '/')}'\n" for seg in segs)
    joined = os.path.join(work, "joined.mp4")
    run([ff, "-y", "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", joined])

    # Chapters and subtitles from the actual segment lengths
    t, srt, chapters = 0.0, [], []
    for i, s in enumerate(scenes, start=1):
        start, end = t, t + s["seconds"]
        srt.append(f"{i}\n{srt_time(start)} --> {srt_time(end - 0.05)}\n{s['text']}\n")
        if not chapters or chapters[-1]["chapter"] != s["chapter"]:
            chapters.append({"chapter": s["chapter"], "title": s["title"], "start": start, "end": end})
        else:
            chapters[-1]["end"] = end
        t = end
    meta = os.path.join(work, "chapters.txt")
    with open(meta, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        f.write(f"title=FIR VisionAI walkthrough ({NAMES[lang]})\nlanguage={'tel' if lang == 'te' else 'eng'}\n")
        for c in chapters:
            f.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(c['start'] * 1000)}\nEND={int(c['end'] * 1000)}\n"
                    f"title={c['chapter']}. {c['title']}\n")
    final = os.path.join(OUT, f"FIR_VisionAI_Walkthrough_{NAMES[lang]}.mp4")
    run([ff, "-y", "-i", joined, "-i", meta, "-map", "0", "-map_metadata", "1", "-map_chapters", "1",
         "-metadata:s:a:0", f"language={'tel' if lang == 'te' else 'eng'}", "-c", "copy", "-movflags", "+faststart", final])
    srt_path = os.path.join(SUBS, f"FIR_VisionAI_Walkthrough_{NAMES[lang]}.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt))
    with open(os.path.join(work, "scenes.json"), "w", encoding="utf-8") as f:
        json.dump({"scenes": [{k: v for k, v in s.items() if k in ("id", "chapter", "title", "shot", "seconds", "text")} for s in scenes],
                   "chapters": chapters, "total": t}, f, ensure_ascii=False, indent=1)
    print(f"[{lang}] wrote {final} and {srt_path}", flush=True)
    return final, srt_path


# ── Verify ──────────────────────────────────────────────────────────────────

def verify(lang):
    ff = ffmpeg_exe()
    final = os.path.join(OUT, f"FIR_VisionAI_Walkthrough_{NAMES[lang]}.mp4")
    srt_path = os.path.join(SUBS, f"FIR_VisionAI_Walkthrough_{NAMES[lang]}.srt")
    info = media_info(final)
    dur = duration_of(final)
    video = re.search(r"Video: (\w+).*?, (\d+)x(\d+)", info)
    # ffmpeg prints e.g. "Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp"
    audio = re.search(r"Audio: (\w+)[^,]*, (\d+) Hz, (\w+)", info)
    chapters = len(re.findall(r"Chapter #", info))
    vol = subprocess.run([ff, "-hide_banner", "-i", final, "-vn", "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", vol)
    peak = re.search(r"max_volume: (-?[\d.]+) dB", vol)
    with open(srt_path, encoding="utf-8") as f:
        cues = re.findall(r"(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)", f.read())

    def secs(s):
        h, m, rest = s.split(":")
        sec, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000
    scene_count = sum(len(c["scenes"]) for c in CHAPTERS)
    samples = []
    for frac in (0.08, 0.35, 0.62, 0.9):
        out = os.path.join(OUT, f"sample_{lang}_{int(frac * 100):02}.png")
        run([ff, "-y", "-ss", f"{dur * frac:.2f}", "-i", final, "-frames:v", "1", out])
        samples.append(out)
    report = {
        "file": final, "bytes": os.path.getsize(final), "duration_s": round(dur, 2),
        "video": video.groups() if video else None, "audio": audio.groups() if audio else None,
        "chapters": chapters, "expected_chapters": len(CHAPTERS),
        "mean_volume_db": float(mean.group(1)) if mean else None, "max_volume_db": float(peak.group(1)) if peak else None,
        "srt": srt_path, "srt_cues": len(cues), "expected_cues": scene_count,
        "srt_last_end_s": round(secs(cues[-1][1]), 2) if cues else None,
        "srt_monotonic": all(secs(a) < secs(b) for a, b in cues) and all(secs(cues[i][1]) <= secs(cues[i + 1][0]) for i in range(len(cues) - 1)),
        "samples": samples,
    }
    report["ok"] = bool(video and video.group(1) == "h264" and video.group(2) == str(W) and video.group(3) == str(H)
                        and audio and audio.group(1) == "aac" and chapters == len(CHAPTERS)
                        and report["mean_volume_db"] is not None and report["mean_volume_db"] > -40
                        and len(cues) == scene_count and report["srt_monotonic"]
                        and abs(report["srt_last_end_s"] - dur) < 1.0)
    with open(os.path.join(OUT, f"verify_{lang}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=("capture", "build", "verify", "all"), default="all")
    ap.add_argument("--lang", default="en,te")
    args = ap.parse_args()
    langs = [l for l in args.lang.split(",") if l in VOICES]
    if args.stage in ("capture", "all"):
        asyncio.run(capture())
    if args.stage in ("build", "all"):
        for l in langs:
            asyncio.run(build(l))
    if args.stage in ("verify", "all", "build"):
        results = [verify(l) for l in langs]
        sys.exit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()
