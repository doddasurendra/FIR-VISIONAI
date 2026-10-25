"""
Import official legal documents listed in corpus/official_sources.json into the Knowledge Base.

For each source: obtain the official file (local --file override, download cache, or download),
verify it is a PDF containing the expected title text, store it (Supabase Storage or local), ingest
it through the shared pipeline (pages, section-aware chunks, embeddings, verified index), and create
one legal_corpus row per parsed Section/Article with its page number. Re-running is safe: a file
whose SHA-256 is already imported is skipped unless --refresh is given.

Usage (from backend/):
    python scripts/import_official_documents.py                       # all VERIFIED_SOURCE entries
    python scripts/import_official_documents.py --only bns_2023 bsa_2023
    python scripts/import_official_documents.py --file bns_2023=C:/path/250883.pdf
    python scripts/import_official_documents.py --include-pending      # also try PENDING_DOWNLOAD entries
    python scripts/import_official_documents.py --env-file ../../.env  # target the database in that env file
    python scripts/import_official_documents.py --dry-run              # download and verify only
"""
import argparse
import asyncio
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_DIR = os.path.abspath(os.path.join(BACKEND_DIR, ".."))
DEFAULT_MANIFEST = os.path.join(REPO_DIR, "corpus", "official_sources.json")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", default=DEFAULT_MANIFEST)
    p.add_argument("--only", nargs="*", help="Source ids to import")
    p.add_argument("--file", action="append", default=[], help="id=path to use a local copy of the official file")
    p.add_argument("--download-dir", default=os.path.join(REPO_DIR, "data", "official_sources"))
    p.add_argument("--include-pending", action="store_true", help="Also attempt PENDING_DOWNLOAD entries")
    p.add_argument("--refresh", action="store_true", help="Re-ingest even if the file was imported before")
    p.add_argument("--env-file", help="Load environment variables (e.g. Supabase settings) from this file first")
    p.add_argument("--dry-run", action="store_true", help="Download and verify files without touching the database")
    return p.parse_args()


def load_env_file(path: str) -> None:
    """Minimal KEY=VALUE loader; values are never printed."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: str, attempts: int = 3, timeout: int = 180) -> None:
    ctx = ssl.create_default_context()
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FIR-VisionAI-official-importer/1.0"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp, open(dest + ".part", "wb") as out:
                while True:
                    block = resp.read(65536)
                    if not block:
                        break
                    out.write(block)
            os.replace(dest + ".part", dest)
            return
        except Exception as e:
            last_err = e
            print(f"    download attempt {attempt} failed: {e}")
            time.sleep(5 * attempt)
    raise RuntimeError(f"download failed after {attempts} attempts: {last_err}")


def verify_file(path: str, expect_text):
    """Return (ok, message, page_count). The file must be a PDF whose opening pages contain expect_text."""
    with open(path, "rb") as f:
        if f.read(5) != b"%PDF-":
            return False, "not a PDF file", 0
    from pypdf import PdfReader
    try:
        reader = PdfReader(path)
        pages = len(reader.pages)
        head = " ".join((reader.pages[i].extract_text() or "") for i in range(min(pages, 8)))
    except Exception as e:
        return False, f"unreadable PDF: {e}", 0
    flat = " ".join(head.split()).upper()
    squeezed = flat.replace(" ", "")
    missing = [t for t in expect_text if t.upper() not in flat and t.upper().replace(" ", "") not in squeezed]
    if missing:
        return False, f"expected text not found: {missing}", pages
    return True, "ok", pages


async def import_source(src: dict, path: str, checksum: str, args) -> dict:
    from sqlalchemy import delete, select
    from app.database import AsyncSessionLocal, setup_database_sync
    from app.models.document import Document, DocumentPage
    from app.models.legal import LegalCorpus
    from app.models.user import User
    from app.services.ingestion import ingest_file
    from app.services.storage import storage_service
    from app.services.text_processing import PageText, section_label_for, segment_pages

    setup_database_sync()
    async with AsyncSessionLocal() as db:
        # Only reuse a record that is already this legal document; never convert case evidence
        # (or anything else that happens to share the file) into a legal source
        existing = (await db.execute(
            select(Document).where(Document.file_hash == checksum, Document.doc_category == "LEGAL_ACT",
                                   Document.case_id.is_(None)).order_by(Document.created_at.desc())
        )).scalars().first()
        if existing and existing.index_status in ("INDEXED", "PARTIALLY_INDEXED") and not args.refresh:
            return {"id": src["id"], "result": "SKIPPED_ALREADY_IMPORTED", "document_id": existing.id}

        importer = (await db.execute(select(User).where(User.role == "STATE").order_by(User.created_at))).scalars().first()
        importer_id = importer.id if importer else "system-importer"

        with open(path, "rb") as f:
            data = f.read()
        filename = os.path.basename(path)
        storage = await storage_service.upload_file(data, filename, "application/pdf")

        doc = existing or Document(file_hash=checksum, created_by=importer_id, original_filename=filename,
                                   stored_path=storage["stored_path"], mime_type="application/pdf")
        doc.stored_path = storage["stored_path"]
        doc.document_title = src["title"]
        doc.doc_category = src.get("category", "LEGAL_ACT")
        doc.source_type = "OFFICIAL"
        doc.is_verified_official = True
        doc.source_url = src["source_url"]
        doc.issuing_authority = src.get("issuing_authority")
        doc.source_department = (src.get("issuing_authority") or "")[:100] or None  # varchar(100)
        doc.reference_number = src.get("reference_number")
        doc.jurisdiction = src.get("jurisdiction")
        doc.publication_date = src.get("publication_date")
        doc.commencement_date = src.get("commencement_date")
        doc.version_date = src.get("publication_date")
        doc.legal_status = src.get("legal_status")
        doc.language = src.get("language")
        doc.verification_note = src.get("verification_note")
        doc.last_verified_at = datetime.utcnow()
        doc.district = "Statewide"
        doc.is_archived = False
        if existing is None:
            db.add(doc)
        await db.commit()
        await db.refresh(doc)

        job = await ingest_file(db, doc, path, trigger="IMPORT", user_id=importer_id)

        # One legal_corpus row per parsed provision, linked to the document and its start page
        provisions_written = 0
        if job.status in ("INDEXED", "PARTIALLY_INDEXED"):
            rows = (await db.execute(
                select(DocumentPage).where(DocumentPage.document_id == doc.id).order_by(DocumentPage.physical_page_number)
            )).scalars().all()
            pages = [PageText(p.physical_page_number, p.raw_text or "") for p in rows if p.raw_text]
            _, provisions = segment_pages(pages, section_label_for(doc.document_title, doc.doc_category))
            await db.execute(delete(LegalCorpus).where(LegalCorpus.document_id == doc.id,
                                                       LegalCorpus.source_type == "OFFICIAL"))
            seen_refs = set()
            for prov in provisions:
                body = prov.text
                # Keep the first (main-text) occurrence of each provision number
                if len(body) < 20 or prov.section_ref in seen_refs:
                    continue
                seen_refs.add(prov.section_ref)
                db.add(LegalCorpus(
                    act_name=src["act_name"],
                    section_number=prov.section_ref[:50],
                    section_title=(prov.section_title or prov.section_ref)[:200],
                    full_text=body[:20000],
                    effective_date=src.get("commencement_date"),
                    repeal_date=None,
                    version=src.get("publication_date") or "official",
                    jurisdiction=src.get("jurisdiction") or "Central",
                    source_url=src["source_url"],
                    source_gazette=src.get("reference_number"),
                    verification_status="VERIFIED",
                    source_type="OFFICIAL",
                    document_id=doc.id,
                    category=src.get("legal_corpus_category"),
                    physical_page_number=prov.page_start,
                    source_checksum=checksum,
                    last_verified_at=datetime.utcnow(),
                    essential_ingredients_json="[]",
                ))
                provisions_written += 1
            await db.commit()

        return {
            "id": src["id"], "result": job.status, "document_id": doc.id,
            "pages": job.pages_total, "pages_with_text": job.pages_with_text,
            "chunks": job.chunks_written, "embedded": job.chunks_embedded,
            "provisions": provisions_written, "error": job.error_message,
        }


def main():
    args = parse_args()
    if args.env_file:
        load_env_file(args.env_file)
    sys.path.insert(0, BACKEND_DIR)

    with open(args.manifest, encoding="utf-8") as f:
        sources = json.load(f)["sources"]
    overrides = dict(item.split("=", 1) for item in args.file)
    os.makedirs(args.download_dir, exist_ok=True)

    selected = [s for s in sources if (not args.only or s["id"] in args.only)
                and (s["status"] == "VERIFIED_SOURCE" or args.include_pending or s["id"] in overrides)]
    results = []
    ready = []  # (src, path, checksum) verified files to import in one event loop
    for src in selected:
        print(f"\n== {src['id']}: {src['title']}")
        path = overrides.get(src["id"]) or os.path.join(args.download_dir, f"{src['id']}.pdf")
        if not os.path.exists(path):
            print(f"   downloading {src['download_url']}")
            try:
                download(src["download_url"], path)
            except Exception as e:
                results.append({"id": src["id"], "result": "DOWNLOAD_FAILED", "error": str(e)})
                print(f"   DOWNLOAD FAILED: {e}")
                continue
        ok, msg, pages = verify_file(path, src.get("expect_text", []))
        checksum = sha256_file(path)
        print(f"   file: {pages} pages, sha256 {checksum[:16]}..., verification: {msg}")
        if not ok:
            results.append({"id": src["id"], "result": "VERIFICATION_FAILED", "error": msg})
            continue
        if args.dry_run:
            results.append({"id": src["id"], "result": "VERIFIED_DRY_RUN", "pages": pages})
            continue
        ready.append((src, path, checksum))

    async def run_all():
        for src, path, checksum in ready:
            print(f"\n-- importing {src['id']} ...")
            res = await import_source(src, path, checksum, args)
            results.append(res)
            print(f"   result: {json.dumps(res)}")

    if ready:
        asyncio.run(run_all())

    print("\n=== Summary ===")
    for r in results:
        print(f"  {r['id']:<20} {r['result']:<26} " + json.dumps({k: v for k, v in r.items() if k not in ('id', 'result')}))
    failed = [r for r in results if r["result"] not in ("INDEXED", "PARTIALLY_INDEXED", "SKIPPED_ALREADY_IMPORTED", "VERIFIED_DRY_RUN")]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
