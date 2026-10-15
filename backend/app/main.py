import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import setup_database_sync, SyncSessionLocal
from .models.user import User
from .models.legal import LegalCorpus
from .services.auth import hash_password

# Import API Routers
from .api.v1.auth import router as auth_router
from .api.v1.employees import router as employees_router
from .api.v1.cases import router as cases_router
from .api.v1.documents import router as documents_router
from .api.v1.extraction import router as extraction_router
from .api.v1.legal import router as legal_router
from .api.v1.entities import router as entities_router
from .api.v1.generation import router as generation_router
from .api.v1.rag import router as rag_router
from .api.v1.bulk import router as bulk_router
from .api.v1.audit import router as audit_router
from .api.v1.analytics import router as analytics_router

def seed_initial_data_if_empty():
    """Seed demo accounts and verified legal corpus into the database."""
    session = SyncSessionLocal()
    try:
        # Check users
        if session.query(User).count() == 0:
            demo_users = [
                User(
                    username="station_officer",
                    email="officer.kurnool@apexcise.gov.in",
                    password_hash=hash_password("StationPass@2024"),
                    full_name="K. Venkateshwarlu",
                    role="STATION",
                    district="Kurnool",
                    station="Kurnool Town Station",
                    badge_number="EXC-KNL-104",
                    designation="Excise Sub-Inspector"
                ),
                User(
                    username="district_admin",
                    email="sp.kurnool@apexcise.gov.in",
                    password_hash=hash_password("DistrictPass@2024"),
                    full_name="M. Rajasekhar IPS",
                    role="DISTRICT",
                    district="Kurnool",
                    station=None,
                    badge_number="IPS-KNL-01",
                    designation="Superintendent of Excise"
                ),
                User(
                    username="state_director",
                    email="director.hq@apexcise.gov.in",
                    password_hash=hash_password("StateAdmin@2024"),
                    full_name="Dr. C. Anjaneyulu IAS",
                    role="STATE",
                    district="Amaravati Headquarters",
                    station=None,
                    badge_number="IAS-AP-002",
                    designation="Commissioner of Prohibition & Excise"
                )
            ]
            session.add_all(demo_users)
            session.commit()
            print("Demo accounts seeded successfully.")

        # Seed legal corpus from JSON files
        if session.query(LegalCorpus).count() == 0:
            corpus_files = [
                os.path.join(settings.CORPUS_DIR, "ap_excise_act_1968.json"),
                os.path.join(settings.CORPUS_DIR, "bns_2023.json"),
                os.path.join(settings.CORPUS_DIR, "ipc_historical.json"),
            ]
            for c_file in corpus_files:
                if os.path.exists(c_file):
                    with open(c_file, "r", encoding="utf-8") as f:
                        records = json.load(f)
                        for r in records:
                            sec = LegalCorpus(
                                act_name=r["act_name"],
                                section_number=r["section_number"],
                                section_title=r["section_title"],
                                full_text=r["full_text"],
                                explanation=r.get("explanation"),
                                essential_ingredients_json=json.dumps(r.get("essential_ingredients", [])),
                                penalty_text=r.get("penalty_text"),
                                effective_date=r.get("effective_date"),
                                repeal_date=r.get("repeal_date"),
                                source_url=r.get("source_url"),
                                source_gazette=r.get("source_gazette"),
                                verification_status=r.get("verification_status", "VERIFIED")
                            )
                            session.add(sec)
            session.commit()
            print("Verified legal corpus seeded successfully.")

    finally:
        session.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize SQLite schema & FTS5 tables
    setup_database_sync()
    seed_initial_data_if_empty()
    yield

app = FastAPI(
    title="FIR Sahayak - Andhra Pradesh Excise AI Platform",
    description="AI-Enabled Unified First Information Report (u-FIR) and Case Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register v1 Routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(employees_router, prefix="/api/v1")
app.include_router(cases_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(extraction_router, prefix="/api/v1")
app.include_router(legal_router, prefix="/api/v1")
app.include_router(entities_router, prefix="/api/v1")
app.include_router(generation_router, prefix="/api/v1")
app.include_router(rag_router, prefix="/api/v1")
app.include_router(bulk_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")

@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "database": "sqlite3_fts5_connected",
        "demo_mode": settings.DEMO_MODE
    }
