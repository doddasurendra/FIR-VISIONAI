"""
Read-only verification of the v2.1.0 requirement points against the configured database.

  python scripts/verify_v210.py            # prints a JSON report
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import func, select, text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.case import Case, CaseField  # noqa: E402
from app.models.user import User  # noqa: E402

SQL = {
    "fir_records_needing_ocr": None,  # from the summaries listing below
    "cases_unknown_or_bad_contraband": "select count(*) from cases where not is_archived and deleted_at is null and "
                                       "(contraband_type is null or trim(contraband_type)='' or contraband_type ilike 'unknown' "
                                       "or contraband_type ilike '%permit%')",
    "cases_district_not_matching_station": "select count(*) from cases c join verified_stations v on lower(v.station_name)="
                                           "lower(c.station) where not c.is_archived and lower(v.district)<>lower(c.district)",
    "active_document_chunks_without_embedding": "select count(*) from document_chunks c join documents d on d.id=c.document_id "
                                                "where not d.is_archived and c.embedding is null",
    "active_fir_kb_chunks_without_embedding": "select count(*) from document_chunks c join documents d on d.id=c.document_id "
                                              "where not d.is_archived and d.doc_category<>'LEGAL_ACT' and c.embedding is null",
    "tables_without_rls": "select count(*) from pg_tables where schemaname='public' and not rowsecurity",
    "open_quality_flags": "select count(*) from extraction_quality_flags where status='OPEN'",
}
COUNT_TABLES = ("cases", "case_fields", "documents", "document_pages", "document_chunks", "entities", "entity_mentions",
                "graph_edges", "legal_corpus", "ipc_bns_mapping", "case_legal_sections", "case_summaries", "fir_summaries",
                "extraction_quality_flags", "audit_log")


async def main():
    out = {}
    async with AsyncSessionLocal() as db:
        out["row_counts"] = {t: (await db.execute(text(f"select count(*) from {t}"))).scalar() for t in COUNT_TABLES}
        for k, q in SQL.items():
            if q:
                out[k] = (await db.execute(text(q))).scalar()
        state = (await db.execute(select(User).where(func.upper(User.role) == "STATE", User.is_active == True)  # noqa: E712
                                  .order_by(User.username))).scalars().first()

        # AI Case Summaries counters (same computation as GET /summaries/records)
        from app.services import fir_summaries as fs
        records = await fs.list_records(db, state)
        rows = await fs.summary_rows(db, [r["record_key"] for r in records], status_only=True)
        cov = {"records": len(records), "with_usable_text": 0, "need_ocr_or_review": 0, "summarised_en": 0,
               "stale": 0, "by_language": {l: {} for l in fs.LANGUAGES}, "needs_review_items": []}
        for r in records:
            st = fs.summary_state(r, rows.get(r["record_key"], {}))
            usable = r["source_chars"] >= fs.MIN_SOURCE_CHARS
            cov["with_usable_text" if usable else "need_ocr_or_review"] += 1
            if not usable:
                cov["needs_review_items"].append(r.get("fir_number") or r.get("title"))
            cov["summarised_en"] += st["en"] == "COMPLETED"
            cov["stale"] += any(s == "STALE" for s in st.values())
            for l in fs.LANGUAGES:
                cov["by_language"][l][st[l]] = cov["by_language"][l].get(st[l], 0) + 1
        out["summaries"] = cov
        out["fir_records_needing_ocr"] = cov["need_ocr_or_review"]

        async def case(fir):
            return (await db.execute(select(Case).where(Case.fir_number == fir))).scalar_one_or_none()

        def fields(c, rows_):
            return {f.field_name: f.human_override_value or f.normalized_value for f in rows_}

        for fir in ("178/2024", "FIR-2024-EXC-IMAGE-01"):
            c = await case(fir)
            fr = (await db.execute(select(CaseField).where(CaseField.case_id == c.id))).scalars().all()
            ents = (await db.execute(text("select e.entity_type, e.canonical_name, m.role_in_case from entity_mentions m "
                                          "join entities e on e.id=m.entity_id where m.case_id=:c"), {"c": c.id})).all()
            stages = (await db.execute(text("select stage, status from workflow_executions where case_id=:c"), {"c": c.id})).all()
            out[fir] = {"offence_nature": c.offence_nature, "offence_date": str(c.offence_date),
                        "place": c.incident_place_raw, "district": c.district, "contraband": c.contraband_type,
                        "quantity": f"{c.seized_quantity} {c.seized_unit}", "vehicle": c.vehicle_details,
                        "fields": {k: v for k, v in fields(c, fr).items() if k in ("complainant", "accused", "law_sections", "offence_time")},
                        "entities": [tuple(e) for e in ents], "workflow": sorted(tuple(s) for s in stages)}

        # Legal suggestions for 178/2024
        from app.services.legal_service import legal_service
        rec = await legal_service.recommend_sections_for_case((await case("178/2024")).id, state, db)
        out["178/2024"]["legal"] = rec

        # Vehicle AP21TY4567: FIRs linked through the entity network
        out["AP21TY4567_linked_firs"] = [r[0] for r in (await db.execute(text(
            "select distinct c.fir_number from entity_mentions m join entities e on e.id=m.entity_id join cases c on c.id=m.case_id "
            "where e.entity_type='VEHICLE' and replace(replace(upper(e.canonical_name),' ',''),'-','') like '%AP21TY4567%' "
            "and not c.is_archived order by 1"))).all()]

        # Dashboard contraband rows
        from app.services.analytics import AnalyticsService
        kpis = await AnalyticsService.get_dashboard_kpis(state, db)
        out["dashboard_contraband"] = [(s["contraband"], s["cases"]) for s in kpis.get("contraband_stats", [])]

        # KNL-0042 Telugu summary
        knl = await case("FIR-2024-KNL-0042")
        te = (await db.execute(text("select summary_text, status from fir_summaries where language='te' and "
                                    "(case_id=:c or document_id in (select id from documents where case_id=:c))"), {"c": knl.id})).all()
        out["KNL-0042_te"] = [{"status": s, "mentions_20_august": ("20" in (t or "") and "ఆగస్టు" in (t or "") and
                                                                   any(x in (t or "") for x in ("20 ఆగస్టు", "ఆగస్టు 20", "20th"))),
                               "date_lines": [ln for ln in (t or "").splitlines() if "2024" in ln][:3]} for t, s in te]

        # Case diary IO
        from app.services.document_generator import investigating_officer_for_case
        out["KNL-0042_diary_io"] = await investigating_officer_for_case(knl, db)
        out["178/2024_diary_io"] = await investigating_officer_for_case(await case("178/2024"), db)

        # Hotspots vs case page for 178/2024
        from app.services.case_location import case_location
        from app.services.hotspots import get_crime_hotspots
        c178 = await case("178/2024")
        hs = await get_crime_hotspots(state, db)
        unloc = [u.get("fir_number") for u in hs.get("unlocated", hs.get("location_not_verified", []))] if isinstance(hs, dict) else []
        out["178/2024_location"] = {"case_page": case_location(c178), "in_hotspots_unlocated": "178/2024" in unloc}

        # Audit chain
        from app.services.audit import verify_audit_chain_report
        out["audit_chain"] = await verify_audit_chain_report(db)
    print(json.dumps(out, default=str, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
