"""
One run that brings the database to the state the requirement check expects (v2.1.0 data fixes).

  python scripts/fix_all_fulfilled.py                # dry run: what would change, counts per table
  python scripts/fix_all_fulfilled.py --backup       # JSON backup of every affected table (BACKUPS_DIR)
  python scripts/fix_all_fulfilled.py --apply        # apply (run --backup first; migrations must be applied)

Steps (each change is audit-logged through the locked audit append, with before and after values):
 1. Page text: strip picture descriptions ("The image depicts the emblem ...") and mark placeholder
    text ("... EVIDENCE PHOTOGRAPH ... authenticated via SHA-256", "No visible text was found") unreadable.
 2. Documents: archive synthetic test fixtures listed as FIRs, move circulars filed as FIRs to the
    Knowledge Base (CIRCULAR), fix wrong document-case links.
 3. Re-process documents that still have no readable text (OCR with retries, enhanced image, second
    engine) and re-index (chunks, embeddings, full-text) every document whose text changed.
 4. Cases: re-extract 178/2024 and FIR-2024-EXC-IMAGE-01 (all six workflow stages), correct districts
    against the station master list, set contraband (from the FIR text, or "Not applicable"), archive
    the end-to-end test cases that have no FIR content, drop vehicle links without a registration and
    re-link vehicles by registration number.
 5. Legal corpus: IPC->BNS mapping and special-Act provisions (scripts/import_legal_corpus_v2.py).
 6. Extraction quality check over every case (flags stored in extraction_quality_flags).
 7. Summaries: every pending, failed or stale record, plus FIR-2024-KNL-0042 (EN/TE/HI).
"""
import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import func, select, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.case import Case  # noqa: E402
from app.models.document import Document, DocumentPage  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.audit import log_audit_event  # noqa: E402
from app.services.text_processing import is_placeholder_text, strip_image_descriptions  # noqa: E402

BACKUP_TABLES = ("cases", "case_fields", "documents", "document_pages", "document_chunks", "entities", "entity_mentions",
                 "graph_edges", "legal_corpus", "case_legal_sections", "case_summaries", "fir_summaries", "audit_log",
                 "verified_stations", "workflow_executions", "extraction_runs", "ingestion_jobs", "fir_folders",
                 "case_folder_assignments")
FIXTURE_REASON = "Synthetic test fixture (generated image or PDF with no FIR text); not a historical FIR record"
# Generated test images and PDFs (a few KB, placeholder text) that tests uploaded as FIRs
FIXTURE_MAX_BYTES_HINT = 5000
CIRCULARS = {  # FIR-category documents that are circulars: moved to the Knowledge Base
    "AP_Excise_Circular_14_2024_v2.pdf": "AP Excise Circular 14/2024 (revised)",
    "WhatsApp Image 2026-10-15 at 2.35.22 PM.jpeg": "High Court of A.P. ROC No.171/SO/2024 - Supreme Court judgment in Dablu Kujur v. State of Jharkhand",
}
REEXTRACT = ("178/2024", "FIR-2024-EXC-IMAGE-01")
PLACE_COLUMNS = {"incident_place_raw", "location_description", "incident_landmark", "incident_village",
                 "incident_district", "incident_location_evidence_passage", "incident_location_verified"}
E2E_TEST_CASES = ("TEST-FIR-E2E-2024-99", "TEST-FIR-E2E-f28a799c", "TEST-FIR-E2E-c90cd8cd")


class Plan:
    def __init__(self):
        self.counts = Counter()      # (table, action) -> rows
        self.items = []              # human-readable lines
        self.removed = set()         # documents archived or moved out of the FIR list
        self.links = {}              # document id -> case id it is (re)linked to

    def add(self, table, action, line, n=1):
        self.counts[(table, action)] += n
        self.items.append(f"[{table}:{action}] {line}")


async def actor(db) -> User:
    user = (await db.execute(select(User).where(func.upper(User.role) == "STATE", User.is_active == True)  # noqa: E712
                             .order_by(User.username))).scalars().first()
    if not user:
        raise SystemExit("A STATE user is needed (every jurisdiction).")
    return user


async def audit(db, user, action, obj_type, obj_id, before, after):
    await log_audit_event(db=db, actor_id=user.id, actor_username=user.username, action_type=action,
                          object_type=obj_type, object_id=obj_id, before_state=before, after_state=after)


# ── 1-2. Pages and documents ────────────────────────────────────────────────

async def step_pages(db, user, plan: Plan, apply: bool) -> set:
    changed_docs = set()
    pages = (await db.execute(select(DocumentPage, Document.original_filename).join(
        Document, Document.id == DocumentPage.document_id))).all()
    for page, fname in pages:
        raw = page.raw_text or ""
        if raw and not page.is_unreadable and is_placeholder_text(raw):
            plan.add("document_pages", "mark_unreadable", f"{fname} p{page.physical_page_number}: placeholder text")
            changed_docs.add(page.document_id)
            if apply:
                page.is_unreadable = True
                page.ocr_confidence = None
                await audit(db, user, "OCR_TEXT_CORRECTED", "DOCUMENT", page.document_id,
                            {"page": page.physical_page_number, "is_unreadable": False, "text_start": raw[:200]},
                            {"page": page.physical_page_number, "is_unreadable": True,
                             "reason": "placeholder text is not OCR of the page"})
            continue
        stripped = strip_image_descriptions(raw)
        if stripped != raw:
            plan.add("document_pages", "strip_image_description",
                     f"{fname} p{page.physical_page_number}: {len(raw) - len(stripped)} chars of picture description removed")
            changed_docs.add(page.document_id)
            if apply:
                page.raw_text = stripped
                await audit(db, user, "OCR_TEXT_CORRECTED", "DOCUMENT", page.document_id,
                            {"page": page.physical_page_number, "chars": len(raw),
                             "removed_text": raw[:4000] if len(raw) - len(stripped) <= 4000 else None},
                            {"page": page.physical_page_number, "chars": len(stripped),
                             "reason": "description of a picture/logo removed; only text printed on the page kept"})
    if apply:
        await db.commit()
    return changed_docs


async def _doc_by_name(db, name, linked_case_fir=None):
    stmt = select(Document).where(Document.original_filename == name, Document.is_archived == False)  # noqa: E712
    docs = (await db.execute(stmt)).scalars().all()
    if linked_case_fir:
        case = (await db.execute(select(Case).where(Case.fir_number == linked_case_fir))).scalar_one_or_none()
        docs = [d for d in docs if case and d.case_id == case.id]
    return docs


async def step_documents(db, user, plan: Plan, apply: bool) -> set:
    changed = set()
    fir_docs = (await db.execute(select(Document).where(Document.doc_category == "FIR",
                                                        Document.is_archived == False))).scalars().all()  # noqa: E712
    for doc in fir_docs:
        pages = (await db.execute(select(DocumentPage).where(DocumentPage.document_id == doc.id))).scalars().all()
        texts = [p.raw_text or "" for p in pages]
        all_placeholder = pages and all(is_placeholder_text(t) for t in texts)
        boilerplate = any("Under AP Excise Act 1968 Section 34a all contraband seized must undergo" in t for t in texts) \
            and doc.original_filename not in CIRCULARS
        if doc.original_filename in CIRCULARS:
            plan.add("documents", "reclassify_to_kb", f"{doc.original_filename}: FIR -> CIRCULAR (Knowledge Base)"
                     + (", unlinked from its case" if doc.case_id else ""))
            if apply:
                before = {"doc_category": doc.doc_category, "case_id": doc.case_id, "document_title": doc.document_title}
                doc.doc_category, doc.document_title = "CIRCULAR", CIRCULARS[doc.original_filename]
                doc.case_id = None
                await audit(db, user, "DOCUMENT_RECLASSIFIED", "DOCUMENT", doc.id, before,
                            {"doc_category": "CIRCULAR", "case_id": None, "document_title": doc.document_title,
                             "reason": "a circular, not an FIR"})
            changed.add(doc.id)
            plan.removed.add(doc.id)
        elif (all_placeholder and doc.original_filename not in ("FIR 14.jpg",)) or boilerplate:
            plan.add("documents", "archive_fixture", f"{doc.original_filename} ({doc.id[:8]})")
            plan.removed.add(doc.id)
            if apply:
                doc.is_archived, doc.archived_at, doc.archived_by = True, datetime.utcnow(), user.id
                doc.archive_reason = FIXTURE_REASON
                await audit(db, user, "DOCUMENT_ARCHIVED", "DOCUMENT", doc.id, {"is_archived": False, "doc_category": "FIR"},
                            {"is_archived": True, "reason": FIXTURE_REASON})
    # Links: EXC-IMAGE-01's FIR text is ap_logo_test.jpg; fir_c41834.png is a different excise FIR, not CR-99/2024's theft FIR
    exc = (await db.execute(select(Case).where(Case.fir_number == "FIR-2024-EXC-IMAGE-01"))).scalar_one_or_none()
    for doc in await _doc_by_name(db, "ap_logo_test.jpg"):
        if exc and doc.case_id != exc.id:
            plan.add("documents", "link_to_case", "ap_logo_test.jpg -> FIR-2024-EXC-IMAGE-01 (its FIR text)")
            plan.links[doc.id] = exc.id
            if apply:
                await audit(db, user, "DOCUMENT_LINKED", "DOCUMENT", doc.id, {"case_id": doc.case_id},
                            {"case_id": exc.id, "fir_number": exc.fir_number, "reason": "the document's text is this FIR"})
                doc.case_id = exc.id
    for doc in await _doc_by_name(db, "fir_c41834.png", linked_case_fir="CR-99/2024"):
        plan.add("documents", "unlink_from_case", "fir_c41834.png unlinked from CR-99/2024 (an excise FIR, not the theft case)")
        if apply:
            await audit(db, user, "DOCUMENT_UNLINKED", "DOCUMENT", doc.id, {"case_id": doc.case_id},
                        {"case_id": None, "reason": "excise FIR text unrelated to the motorcycle-theft case CR-99/2024"})
            doc.case_id = None
    if apply:
        await db.commit()
    return changed


async def step_reprocess(db, user, plan: Plan, apply: bool, changed_docs: set) -> dict:
    """Re-run OCR on FIR documents with no readable text; re-index documents whose text changed."""
    from app.services.ingestion import ingest_file, materialize_document_file, reindex_from_pages
    out = {"reprocessed": [], "reindexed": 0, "still_unreadable": []}
    docs = (await db.execute(select(Document).where(Document.is_archived == False))).scalars().all()  # noqa: E712
    for doc in docs:
        if doc.doc_category != "FIR" or doc.id in plan.removed:
            continue
        pages = (await db.execute(select(DocumentPage).where(DocumentPage.document_id == doc.id))).scalars().all()
        # As it will be after step 1 (in a dry run the pages are not yet changed)
        readable = sum(len(strip_image_descriptions(p.raw_text or "")) for p in pages
                       if not p.is_unreadable and not is_placeholder_text(p.raw_text or ""))
        if readable >= 200:
            continue
        if not apply:
            plan.add("documents", "reprocess_ocr", f"{doc.original_filename} ({doc.id[:8]}): {readable} readable chars")
            continue
        path, temporary = await materialize_document_file(doc)
        if not path:
            out["still_unreadable"].append((doc.original_filename, "FILE_MISSING: original file not in storage; re-upload it"))
            continue
        try:
            await ingest_file(db, doc, path, trigger="REPROCESS_V210", user_id=user.id)
        finally:
            if temporary:
                os.remove(path)
        await db.refresh(doc)
        out["reprocessed"].append((doc.original_filename, doc.index_status, doc.error_message))
        await audit(db, user, "AI_OCR_REPROCESSED", "DOCUMENT", doc.id, {"readable_chars": readable},
                    {"index_status": doc.index_status, "error": doc.error_message, "ai_assisted": True})
        changed_docs.discard(doc.id)
    for doc_id in sorted(changed_docs):
        doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
        if not doc or (doc.id in plan.removed and doc.original_filename not in CIRCULARS):
            continue   # archived fixtures are not re-indexed; circulars moved to the Knowledge Base are
        plan.add("document_chunks", "reindex", f"{doc.original_filename}: rebuild chunks, embeddings, full-text rows")
        if apply:
            await reindex_from_pages(db, doc, trigger="TEXT_CORRECTED_V210", user_id=user.id)
            out["reindexed"] += 1
    return out


# ── 4. Cases ────────────────────────────────────────────────────────────────

async def step_cases(db, user, plan: Plan, apply: bool) -> dict:
    from app.services.case_reextraction import drop_invalid_vehicle_links, reextract_case
    from app.services.workflow import _run_entity_extraction_stage
    from app.services.fir_form_parser import normalise_registration
    from app.services.extraction_quality import _PLACEHOLDER_PLACE
    out = {"reextracted": {}, "district": [], "contraband": [], "archived": [], "vehicle_links_removed": []}
    cases = (await db.execute(select(Case).where(Case.is_archived == False, Case.deleted_at.is_(None))  # noqa: E712
                              .order_by(Case.fir_number))).scalars().all()
    for case in cases:
        if case.fir_number in E2E_TEST_CASES:
            plan.add("cases", "archive_test_case", f"{case.fir_number}: end-to-end test case with no FIR content")
            if apply:
                case.is_archived, case.archived_at, case.archived_by = True, datetime.utcnow(), user.id
                case.archived_reason = "Automated end-to-end test case (no FIR content); archived, not deleted"
                await db.commit()
                await audit(db, user, "CASE_ARCHIVED", "CASE", case.id, {"is_archived": False},
                            {"is_archived": True, "reason": case.archived_reason})
            out["archived"].append(case.fir_number)
            continue
        if case.fir_number in REEXTRACT:
            source = None
            if not apply:
                # In a dry run step 2's links are not written yet: read the text the case will be linked to
                linked = [d for d, c in plan.links.items() if c == case.id]
                if linked:
                    pages = (await db.execute(select(DocumentPage).where(DocumentPage.document_id == linked[0]))).scalars().all()
                    source = (linked[0], "\n\n".join(p.raw_text or "" for p in pages))
            rep = await reextract_case(db, case, user.id, user.username, dry_run=not apply, source=source)
            out["reextracted"][case.fir_number] = rep
            for k, ch in rep["changes"].items():
                plan.add("cases", "reextract", f"{case.fir_number}.{k}: {str(ch['before'])[:60]!r} -> {str(ch['after'])[:80]!r}")
            for k, ch in rep["fields"].items():
                plan.add("case_fields", "upsert", f"{case.fir_number}.{k}: {ch['before']!r} -> {ch['after']!r}")
            continue
        # Other cases: district, contraband and app-user officers are corrected; a date or place is only
        # filled in where the case has none and the FIR text states it (stored values are not overwritten)
        only = {"district", "contraband_type", "seized_quantity", "seized_unit", "seizing_officer_name",
                "seizing_officer_rank", "narrative"}
        if not case.offence_date:
            only.add("offence_date")
        place = case.incident_place_raw or case.location_description
        if not case.incident_location_verified and (not place or _PLACEHOLDER_PLACE.match(place) or "null" in place.lower()):
            only |= PLACE_COLUMNS
        rep = await reextract_case(db, case, user.id, user.username, dry_run=not apply, only=only)
        for k, ch in rep["changes"].items():
            kind = ("district" if k == "district" else "officer" if k.startswith("seizing_officer") else
                    "date" if k == "offence_date" else "place" if k in PLACE_COLUMNS else "contraband")
            plan.add("cases", "correct_" + kind, f"{case.fir_number}.{k}: {ch['before']!r} -> {ch['after']!r}")
            out.setdefault(kind, []).append((case.fir_number, k, ch["after"]))
    # Vehicles: links to "vehicles" without a registration go; vehicles are linked by registration
    from app.models.entity import Entity, EntityMention
    bad = (await db.execute(select(EntityMention, Entity, Case).join(Entity, Entity.id == EntityMention.entity_id)
                            .join(Case, Case.id == EntityMention.case_id).where(Entity.entity_type == "VEHICLE"))).all()
    for mention, ent, case in bad:
        if not normalise_registration(ent.canonical_name):
            plan.add("entity_mentions", "remove_invalid_vehicle", f"{case.fir_number}: '{ent.canonical_name}'")
    if apply:
        for case in {c.id: c for _, _, c in bad}.values():
            removed = await drop_invalid_vehicle_links(db, case)
            if removed:
                await db.commit()
                await audit(db, user, "ENTITY_LINK_REMOVED", "CASE", case.id, {"vehicle_links": removed},
                            {"vehicle_links": [], "reason": "not a vehicle (no registration number)"})
                out["vehicle_links_removed"] += removed
    for case in cases:
        if case.fir_number in E2E_TEST_CASES or case.fir_number in REEXTRACT:
            continue
        reg = normalise_registration(case.vehicle_details)
        if reg:
            plan.add("entity_mentions", "link_vehicle", f"{case.fir_number}: vehicle {reg}")
            if apply:
                await _run_entity_extraction_stage(db, case.id)
    return out


async def run(apply: bool) -> dict:
    plan = Plan()
    result = {"mode": "APPLY" if apply else "DRY RUN", "started": datetime.utcnow().isoformat()}
    async with AsyncSessionLocal() as db:
        user = await actor(db)
        result["actor"] = user.username
        if apply:
            for table in ("extraction_quality_flags", "ipc_bns_mapping"):
                try:
                    await db.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
                except Exception:
                    raise SystemExit(f"Table {table} is missing: apply the migrations first.")
                await db.rollback()
        changed = await step_pages(db, user, plan, apply)
        changed |= await step_documents(db, user, plan, apply)
        result["reprocess"] = await step_reprocess(db, user, plan, apply, changed)
        result["cases"] = {k: v for k, v in (await step_cases(db, user, plan, apply)).items() if k != "reextracted"}

    # 5. Legal corpus
    import importlib.util
    spec = importlib.util.spec_from_file_location("legal_import", os.path.join(os.path.dirname(__file__), "import_legal_corpus_v2.py"))
    legal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legal)
    try:
        result["legal_corpus"] = await legal.run(apply)
    except Exception as e:
        result["legal_corpus"] = f"skipped: {type(e).__name__}: {e}"

    async with AsyncSessionLocal() as db:
        user = await actor(db)
        # 6. Quality check
        from app.services.extraction_quality import run_quality_check
        cases = (await db.execute(select(Case).where(Case.is_archived == False, Case.deleted_at.is_(None)))).scalars().all()  # noqa: E712
        qc = await run_quality_check(db, cases, persist=apply)
        result["quality_check"] = {k: qc[k] for k in ("cases_checked", "flags", "cases_with_flags")}
        result["quality_flags"] = [(r["fir_number"], f["check_code"], f["field_name"]) for r in qc["results"] for f in r["flags"]]
        plan.add("extraction_quality_flags", "insert", "quality-check flags", n=qc["flags"])
        if apply:
            await audit(db, user, "EXTRACTION_QUALITY_CHECK", "SYSTEM", qc["run_id"], None, result["quality_check"])

    # 7. Summaries (pending + failed + stale + KNL-0042)
    spec = importlib.util.spec_from_file_location("regen", os.path.join(os.path.dirname(__file__), "regenerate_stale_summaries.py"))
    regen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regen)
    await regen.main(apply, None, [], include_pending=True)

    result["counts"] = {f"{t}:{a}": n for (t, a), n in sorted(plan.counts.items())}
    result["items"] = plan.items
    return result


async def backup(tables=BACKUP_TABLES, folder=None) -> str:
    folder = folder or os.path.join(settings.BACKUPS_DIR, "supabase_" + datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"))
    os.makedirs(folder, exist_ok=True)
    async with engine.connect() as conn:
        for table in tables:
            rows, last_id = [], ""
            try:
                # Read in pages by id: one SELECT of a table with embeddings exceeds the statement timeout
                while True:
                    page = (await conn.execute(text(f"SELECT * FROM {table} WHERE id::text > :last ORDER BY id::text LIMIT 400"),
                                               {"last": last_id})).mappings().all()
                    rows += [dict(r) for r in page]
                    if len(page) < 400:
                        break
                    last_id = str(page[-1]["id"])
            except Exception as e:
                print(f"  {table}: FAILED ({type(e).__name__}: {str(e)[:120]})")
                await conn.rollback()
                continue
            with open(os.path.join(folder, f"{table}.json"), "w", encoding="utf-8") as f:
                json.dump(rows, f, default=str, ensure_ascii=False)
            print(f"  {table}: {len(rows)} rows")
    return folder


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--out", help="write the result JSON here")
    ap.add_argument("--tables", nargs="*", help="with --backup: only these tables")
    ap.add_argument("--into", help="with --backup: existing backup folder to add to")
    args = ap.parse_args()
    if args.backup:
        print("Backup folder:", asyncio.run(backup(tuple(args.tables or BACKUP_TABLES), args.into)))
        sys.exit(0)
    res = asyncio.run(run(args.apply))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, default=str, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "items"}, default=str, ensure_ascii=False, indent=1))
    print("\n".join(res["items"]))
