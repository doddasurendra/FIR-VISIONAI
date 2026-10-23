import os
import sys
import mimetypes
import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sqlalchemy import text
from app.config import settings
from app.database import sync_engine, SyncSessionLocal, Base
# Import all models to ensure metadata is complete
from app.models.case import Case, CaseField
from app.models.document import Document, DocumentPage, DocumentChunk
from app.models.folder import FIRFolder, CaseFolderAssignment, WorkflowExecution
from app.models.legal import LegalCorpus
from app.models.user import User, RefreshToken
from app.models.entity import Entity, EntityMention
from app.models.audit import AuditLog
from app.models.extraction import ExtractionRun, ExtractionConfig
from app.models.station import VerifiedStation

def update_supabase_schema():
    print("=== 1. Checking and Updating Supabase PostgreSQL Schema ===")
    # 1. Create any missing tables
    Base.metadata.create_all(bind=sync_engine)
    print("  + Base.metadata.create_all completed.")

    # 2. Add columns to cases table if not exists
    alter_cases_sqls = [
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS classification_status VARCHAR(20) DEFAULT 'PENDING';",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS classification_confidence FLOAT;",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS classification_source VARCHAR(20);",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS application_date TIMESTAMP WITH TIME ZONE;",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS incident_date TIMESTAMP WITH TIME ZONE;",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS form_template VARCHAR(50);",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS form_language VARCHAR(5);",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS form_values_json TEXT;",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS application_status VARCHAR(20) DEFAULT 'DRAFT';"
    ]
    with sync_engine.connect() as conn:
        for sql in alter_cases_sqls:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as e:
                print(f"  ! Error running SQL: {sql} -> {e}")
        print("  + cases columns verified/updated.")

    # 3. Add columns to documents table if not exists
    alter_doc_sqls = [
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_category VARCHAR(50) DEFAULT 'FIR';",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_title VARCHAR(255);",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_department VARCHAR(100);",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS district VARCHAR(100);",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS station VARCHAR(100);",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_verified_official BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS archive_reason VARCHAR(255);",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE;",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS replaced_by_id VARCHAR(36);",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS replaces_id VARCHAR(36);",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS replacement_reason VARCHAR(255);"
    ]
    with sync_engine.connect() as conn:
        for sql in alter_doc_sqls:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as e:
                print(f"  ! Error running SQL: {sql} -> {e}")
        print("  + documents columns verified/updated.")

def seed_supabase_folders():
    print("\n=== 2. Checking FIR Folders in Supabase ===")
    with SyncSessionLocal() as session:
        count = session.query(FIRFolder).count()
        print(f"  Current FIRFolder count: {count}")
        if count == 0:
            from app.models.base import generate_uuid
            folder_definitions = [
                ("illicit-distillation", "Illicit Distillation", "FIR Types", "#7c3aed", "FlaskConical", False, None, 10),
                ("ndps-transport", "NDPS / Drug Transport", "FIR Types", "#dc2626", "Truck", False, None, 20),
                ("non-duty-paid-liquor", "Non-Duty-Paid Liquor", "FIR Types", "#b45309", "Wine", False, None, 30),
                ("vehicle-seizure", "Vehicle Seizure Cases", "FIR Types", "#0891b2", "Car", False, None, 40),
                ("unlawful-possession", "Unlawful Possession", "FIR Types", "#4f46e5", "PackageX", False, None, 50),
                ("theft", "Theft / Property Crime", "FIR Types", "#ca8a04", "ShieldAlert", False, None, 60),
                ("assault", "Assault / Bodily Harm", "FIR Types", "#e11d48", "Zap", False, None, 70),
                ("road-accident", "Road / Traffic Accidents", "FIR Types", "#ea580c", "AlertTriangle", False, None, 80),
                ("cheating-fraud", "Cheating / Fraud", "FIR Types", "#059669", "HandCoins", False, None, 90),
                ("public-nuisance", "Public Nuisance / Disorder", "FIR Types", "#6b7280", "Volume2", False, None, 100),
                ("missing-person", "Missing Person Reports", "FIR Types", "#0f5132", "UserSearch", False, None, 110),
                ("sexual-offence", "Sexual Offence Cases", "FIR Types", "#9f1239", "ShieldX", True, "DISTRICT", 120),
                ("domestic-violence", "Domestic Violence", "FIR Types", "#be185d", "Home", False, None, 130),
                ("land-property", "Land / Property Dispute", "FIR Types", "#15803d", "Landmark", False, None, 140),
                ("cyber-crime", "Cyber Crime", "FIR Types", "#1d4ed8", "Monitor", False, None, 150),
                ("death-investigation", "Death / Unnatural Death", "FIR Types", "#374151", "Skull", False, None, 160),
                ("arms-explosives", "Arms & Explosives", "FIR Types", "#b91c1c", "Crosshair", True, "DISTRICT", 170),
                ("single-fir-persons", "Single-FIR Persons", "Person-Based", "#0369a1", "User", False, None, 200),
                ("multiple-fir-persons", "Multiple-FIR Person Records", "Person-Based", "#7c2d12", "Users", False, None, 210),
                ("pending-classification", "Pending Classification", "Status", "#d97706", "Clock", False, None, 300),
                ("under-investigation", "Under Investigation", "Status", "#2563eb", "Search", False, None, 310),
                ("closed-cases", "Closed / Charge-sheeted", "Status", "#16a34a", "CheckCircle2", False, None, 320),
            ]
            for slug, name, group, color, icon, restricted, req_role, sort in folder_definitions:
                session.add(FIRFolder(
                    id=generate_uuid(),
                    name=name, slug=slug, group_label=group,
                    color_code=color, icon_name=icon,
                    is_restricted=restricted, required_role=req_role,
                    is_system=True, sort_order=sort, is_active=True,
                ))
            session.commit()
            print(f"  + Seeded {len(folder_definitions)} FIR folders into Supabase.")
        else:
            print(f"  + FIR folders already exist in Supabase ({count} records).")

def sync_supabase_storage():
    print("\n=== 3. Syncing Files to Supabase Storage ===")
    supabase_url = settings.SUPABASE_URL
    service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
    bucket = settings.SUPABASE_STORAGE_BUCKET or "evidence"

    if not supabase_url or not service_role_key:
        print("  ! SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured.")
        return

    # Check directories
    dirs_to_sync = [
        settings.EVIDENCE_DIR,
        os.path.join(settings.BASE_DIR, "data", "cloud_cache")
    ]

    total_uploaded = 0
    with httpx.Client(timeout=30.0) as client:
        for sync_dir in dirs_to_sync:
            if not os.path.exists(sync_dir):
                continue
            files = [f for f in os.listdir(sync_dir) if os.path.isfile(os.path.join(sync_dir, f))]
            print(f"  Checking {len(files)} files in {sync_dir}...")
            for fname in files:
                fpath = os.path.join(sync_dir, fname)
                size = os.path.getsize(fpath)
                if size == 0:
                    continue
                ctype, _ = mimetypes.guess_type(fname)
                ctype = ctype or "application/octet-stream"
                with open(fpath, "rb") as fp:
                    content = fp.read()

                # Upload with both raw filename and any prefix
                url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{fname}"
                headers = {
                    "Authorization": f"Bearer {service_role_key}",
                    "Content-Type": ctype,
                    "x-upsert": "true"
                }
                resp = client.post(url, content=content, headers=headers)
                if resp.status_code in (200, 201):
                    total_uploaded += 1
                    print(f"    + Uploaded to Supabase Storage: {fname} ({size} bytes)")
                else:
                    print(f"    ! Failed to upload {fname}: {resp.status_code}")

    print(f"  + Supabase Storage sync completed. Total synced/upserted: {total_uploaded}")

def report_supabase_row_counts():
    print("\n=== 4. Supabase Database Status & Row Counts ===")
    with SyncSessionLocal() as session:
        models = [
            ("Users", User),
            ("Cases", Case),
            ("Documents", Document),
            ("Document Pages", DocumentPage),
            ("Document Chunks", DocumentChunk),
            ("Legal Corpus Sections", LegalCorpus),
            ("FIR Folders", FIRFolder),
            ("Case Folder Assignments", CaseFolderAssignment),
            ("Workflow Executions", WorkflowExecution),
            ("Entities", Entity),
            ("Entity Mentions", EntityMention),
            ("Audit Events", AuditLog),
            ("Verified Stations", VerifiedStation),
        ]
        for label, model in models:
            try:
                cnt = session.query(model).count()
                print(f"  • {label:26}: {cnt:>6} records")
            except Exception as e:
                print(f"  • {label:26}: Error reading count ({e})")

if __name__ == "__main__":
    update_supabase_schema()
    seed_supabase_folders()
    sync_supabase_storage()
    report_supabase_row_counts()
    print("\n>>> SUPABASE UPDATE & SYNCHRONIZATION FULLY COMPLETED! <<<")
