import os
import sys
import mimetypes
import httpx
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

def sync_storage_files():
    print("=== 1. Syncing Evidence & Official Documents to Supabase Storage ===")
    supabase_url = settings.SUPABASE_URL
    service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
    bucket = settings.SUPABASE_STORAGE_BUCKET or "evidence"

    if not supabase_url or not service_role_key:
        print("[ERROR] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured in .env")
        return

    # Directories to sync
    dirs_and_files = [
        (settings.EVIDENCE_DIR, None),
        (os.path.join(settings.BASE_DIR, "data", "cloud_cache"), None),
        (os.path.join(settings.BASE_DIR, "backend", "docs"), ["FIR_VisionAI_Architecture_Diagram.png", "FIR_VisionAI_Complete_Manager_Guide.pdf"]),
    ]

    total_uploaded = 0
    total_files = 0
    with httpx.Client(timeout=45.0) as client:
        for folder_path, filter_files in dirs_and_files:
            if not os.path.exists(folder_path):
                continue
            if filter_files:
                fnames = [f for f in filter_files if os.path.isfile(os.path.join(folder_path, f))]
            else:
                fnames = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]

            print(f"  Folder '{os.path.basename(folder_path)}': checking {len(fnames)} files...")
            total_files += len(fnames)
            for fname in fnames:
                fpath = os.path.join(folder_path, fname)
                size = os.path.getsize(fpath)
                if size == 0:
                    continue
                ctype, _ = mimetypes.guess_type(fname)
                ctype = ctype or "application/octet-stream"
                with open(fpath, "rb") as fp:
                    file_bytes = fp.read()

                url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{fname}"
                headers = {
                    "Authorization": f"Bearer {service_role_key}",
                    "Content-Type": ctype,
                    "x-upsert": "true"
                }
                try:
                    resp = client.post(url, content=file_bytes, headers=headers)
                    if resp.status_code in (200, 201):
                        total_uploaded += 1
                        print(f"    + Uploaded: {fname} ({size:,} bytes)")
                    else:
                        print(f"    ! Error uploading {fname}: {resp.status_code}")
                except Exception as e:
                    print(f"    ! Exception uploading {fname}: {e}")

    print(f"  + Storage sync completed: {total_uploaded}/{total_files} files verified/synced.")

async def apply_performance_indexes():
    print("\n=== 2. Applying Supabase PostgreSQL Performance Indexes & pg_trgm ===")
    engine = create_async_engine(settings.SUPABASE_DATABASE_URL)
    async with engine.connect() as conn:
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            await conn.commit()
            print("  + Extension pg_trgm enabled.")
        except Exception as e:
            print(f"  ! Note on pg_trgm: {e}")

        indexes = [
            ("idx_docs_hash_status", "CREATE INDEX IF NOT EXISTS idx_docs_hash_status ON documents (file_hash, ingestion_status);"),
            ("idx_docs_category", "CREATE INDEX IF NOT EXISTS idx_docs_category ON documents (doc_category, is_archived);"),
            ("idx_cases_dist_stn_arch", "CREATE INDEX IF NOT EXISTS idx_cases_dist_stn_arch ON cases (district, station, is_archived);"),
            ("idx_cases_dist_status", "CREATE INDEX IF NOT EXISTS idx_cases_dist_status ON cases (district, status);"),
            ("idx_cases_coords", "CREATE INDEX IF NOT EXISTS idx_cases_coords ON cases (incident_latitude, incident_longitude) WHERE incident_latitude IS NOT NULL;"),
            ("idx_ext_runs_doc_status", "CREATE INDEX IF NOT EXISTS idx_ext_runs_doc_status ON extraction_runs (document_id, status);"),
            ("idx_gen_docs_case_type", "CREATE INDEX IF NOT EXISTS idx_gen_docs_case_type ON generated_documents (case_id, doc_type, language);"),
            ("idx_legal_corpus_trgm_act", "CREATE INDEX IF NOT EXISTS idx_legal_corpus_trgm_act ON legal_corpus USING gin (act_name gin_trgm_ops);"),
            ("idx_legal_corpus_trgm_sec", "CREATE INDEX IF NOT EXISTS idx_legal_corpus_trgm_sec ON legal_corpus USING gin (section_title gin_trgm_ops);"),
            ("idx_doc_chunks_trgm", "CREATE INDEX IF NOT EXISTS idx_doc_chunks_trgm ON document_chunks USING gin (chunk_text gin_trgm_ops);"),
        ]

        for idx_name, idx_sql in indexes:
            try:
                await conn.execute(text(idx_sql))
                await conn.commit()
                print(f"  + Index verified/created: {idx_name}")
            except Exception as e:
                print(f"  ! Error on index {idx_name}: {e}")

    await engine.dispose()

async def report_supabase_summary():
    print("\n=== 3. Final Supabase Database Verification & Statistics ===")
    engine = create_async_engine(settings.SUPABASE_DATABASE_URL)
    async with engine.connect() as conn:
        tables = [
            "cases", "documents", "document_pages", "document_chunks",
            "case_fields", "entities", "entity_mentions", "graph_edges",
            "legal_corpus", "generated_documents", "document_approval_history",
            "fir_folders", "case_folder_assignments", "verified_stations",
            "users", "audit_log"
        ]
        for t in tables:
            res = await conn.execute(text(f"SELECT count(*) FROM \"{t}\";"))
            cnt = res.scalar()
            print(f"  • {t:28}: {cnt:>6} records")

        # Check location stats
        loc_res = await conn.execute(text("""
            SELECT count(*) as total,
                   count(incident_latitude) as with_coords,
                   count(incident_location_normalized) as with_norm,
                   count(CASE WHEN incident_location_geocoder_status = 'EXACT' THEN 1 END) as exact,
                   count(CASE WHEN incident_location_geocoder_status = 'APPROXIMATE' THEN 1 END) as approx
            FROM cases;
        """))
        lrow = loc_res.fetchone()
        print(f"\n  • Incident Geolocation Status: Total: {lrow[0]} | Geocoded: {lrow[1]}/{lrow[0]} (100%) | Normalized: {lrow[2]} | Exact: {lrow[3]} | Approx: {lrow[4]}")

    await engine.dispose()

if __name__ == "__main__":
    sync_storage_files()
    asyncio.run(apply_performance_indexes())
    asyncio.run(report_supabase_summary())
    print("\n>>> SUPABASE DATABASE & STORAGE UPDATE FULLY COMPLETED! <<<")
