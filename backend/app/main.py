import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import setup_database_sync, SyncSessionLocal
from .models.user import User
from .models.legal import LegalCorpus
from .models.folder import FIRFolder, CaseFolderAssignment, WorkflowExecution  # noqa: F401 — ensures table creation
from .models.extraction import ExtractionConfig, ExtractionRun  # noqa: F401 — ensures table creation
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
from .api.v1.jurisdictions import router as jurisdictions_router
from .api.v1.folders import router as folders_router
from .api.v1.system import router as system_router
from .api.v1.summaries import router as summaries_router
from .api.v1.assistant import router as assistant_router
from .api.v1.fir_applications import router as fir_applications_router

def seed_initial_data_if_empty():
    """Seed demo accounts and verified legal corpus into the database."""
    session = SyncSessionLocal()
    try:
        # Check users
        if session.query(User).count() == 0:
            demo_users = [
                User(
                    username="developer_test",
                    email="dev.lead@apexcise.gov.in",
                    password_hash=hash_password("DevPass@2024"),
                    full_name="Lead System Architect",
                    role="STATE",
                    district="Amaravati Headquarters",
                    station=None,
                    badge_number="SYS-DEV-001",
                    designation="Principal Systems Engineer",
                    department="AP Prohibition & Excise Department",
                    approval_status="APPROVED",
                    is_active=True
                ),
                User(
                    username="station_officer",
                    email="officer.kurnool@apexcise.gov.in",
                    password_hash=hash_password("StationPass@2024"),
                    full_name="K. Venkateshwarlu",
                    role="STATION",
                    district="Kurnool",
                    station="Kurnool Town Station",
                    badge_number="EXC-KNL-104",
                    designation="Excise Sub-Inspector",
                    department="AP Prohibition & Excise Department",
                    approval_status="APPROVED",
                    is_active=True
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
                    designation="Superintendent of Excise",
                    department="AP Prohibition & Excise Department",
                    approval_status="APPROVED",
                    is_active=True
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
                    designation="Commissioner of Prohibition & Excise",
                    department="AP Prohibition & Excise Department",
                    approval_status="APPROVED",
                    is_active=True
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
                                verification_status=r.get("verification_status", "VERIFIED"),
                                # Seed files hold short summaries, not official text (see corpus/official_sources.json)
                                source_type=r.get("source_type", "UNVERIFIED"),
                            )
                            session.add(sec)
            session.commit()
            print("Verified legal corpus seeded successfully.")

        # Seed FIR Folder categories
        from .models.folder import FIRFolder
        if session.query(FIRFolder).count() == 0:
            from .models.base import generate_uuid
            folder_definitions = [
                # FIR Types group
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
                # Person-Based group
                ("single-fir-persons", "Single-FIR Persons", "Person-Based", "#0369a1", "User", False, None, 200),
                ("multiple-fir-persons", "Multiple-FIR Person Records", "Person-Based", "#7c2d12", "Users", False, None, 210),
                # Status group
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
            print(f"Seeded {len(folder_definitions)} FIR folder categories.")

        # Seed default ExtractionConfig
        from .models.extraction import ExtractionConfig
        if session.query(ExtractionConfig).count() == 0:
            # json is the module-level import; a local "import json" here made json unbound at the corpus seed above
            default_schema = [
                {"id": "f_fir_number", "key": "fir_number", "label": "FIR / Crime Number", "data_type": "string", "required": True, "description": "Official Crime or FIR registration number", "validation_rules": "Format: [Number]/[Year]"},
                {"id": "f_year", "key": "year", "label": "Year", "data_type": "number", "required": True, "description": "Year of registration", "validation_rules": "Four digit year (e.g. 2024)"},
                {"id": "f_district", "key": "district", "label": "District", "data_type": "string", "required": True, "description": "District jurisdiction name in Andhra Pradesh", "validation_rules": "Valid AP district"},
                {"id": "f_station", "key": "station", "label": "Police / Excise Station", "data_type": "string", "required": True, "description": "Jurisdiction station name", "validation_rules": ""},
                {"id": "f_offence_date", "key": "offence_date", "label": "Date & Time of Offence", "data_type": "string", "required": False, "description": "Date and approximate time when offence occurred", "validation_rules": ""},
                {"id": "f_registration_date", "key": "registration_date", "label": "Registration Date", "data_type": "string", "required": False, "description": "Date FIR was booked at station", "validation_rules": ""},
                {"id": "f_place_of_occurrence", "key": "place_of_occurrence", "label": "Place of Occurrence", "data_type": "string", "required": False, "description": "Specific street, landmark, village or coordinates", "validation_rules": ""},
                {"id": "f_complainant_details", "key": "complainant_details", "label": "Complainant / Informant", "data_type": "string", "required": False, "description": "Name and designation of complainant/seizing official", "validation_rules": ""},
                {"id": "f_accused_names", "key": "accused_names", "label": "Accused Persons", "data_type": "array", "required": False, "description": "List of accused names and parentage if mentioned", "validation_rules": ""},
                {"id": "f_offence_nature", "key": "offence_nature", "label": "Offence Nature", "data_type": "string", "required": True, "description": "Gist or classification of the alleged crime", "validation_rules": ""},
                {"id": "f_contraband_type", "key": "contraband_type", "label": "Contraband / Seized Property", "data_type": "string", "required": False, "description": "Property, narcotic, liquor, or stolen items seized", "validation_rules": ""},
                {"id": "f_seized_quantity", "key": "seized_quantity", "label": "Seized Quantity", "data_type": "number", "required": False, "description": "Numerical quantity of seized goods", "validation_rules": "Positive numeric value"},
                {"id": "f_seized_unit", "key": "seized_unit", "label": "Quantity Unit", "data_type": "string", "required": False, "description": "Unit of measurement (e.g. Litres, Kgs, Bottles)", "validation_rules": ""},
                {"id": "f_vehicle_details", "key": "vehicle_details", "label": "Vehicle Details", "data_type": "string", "required": False, "description": "Registration number, make, model of transport vehicle used", "validation_rules": ""},
                {"id": "f_law_sections", "key": "law_sections", "label": "Invoked Law Sections", "data_type": "array", "required": False, "description": "List of statutory sections invoked (e.g. AP Excise Act Sec 34(a), BNS 303(2))", "validation_rules": ""},
                {"id": "f_investigating_officer", "key": "investigating_officer", "label": "Investigating Officer (IO)", "data_type": "string", "required": False, "description": "Name and rank of assigned IO", "validation_rules": ""}
            ]
            default_instructions = (
                "CRITICAL DEFENSIVE EXTRACTION RULES:\n"
                "1. STRICT DOCUMENT GROUNDING: Extract ONLY information explicitly present in this document. Never invent missing details.\n"
                "2. ZERO ASSUMPTIONS: Do not assume this is an excise or liquor offence unless explicitly stated in the document text.\n"
                "3. UNKNOWN / MISSING FIELDS: If any field cannot be found or verified in the document text, return null or empty array.\n"
                "4. CITATION INTEGRITY: Tag extracted entities and structured fields with the exact source physical page number where the information appears."
            )
            session.add(ExtractionConfig(
                id="cfg-default-fir",
                name="FIR Standard Extraction",
                version=1,
                schema_json=json.dumps(default_schema),
                instructions=default_instructions,
                is_active=True,
                created_by="system"
            ))
            session.commit()
            print("Default ExtractionConfig seeded successfully.")

    finally:
        session.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize SQLite schema & FTS5 tables
    setup_database_sync()
    seed_initial_data_if_empty()
    yield

app = FastAPI(
    title="FIR VisionAI - Andhra Pradesh Excise AI Platform",
    description="Unified FIR & AI-Powered Case Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def json_errors(request, call_next):
    """
    Unhandled errors return JSON with a reference instead of a bare "Internal Server Error", so the
    page can show something actionable and the log line can be found. Declared before the CORS
    middleware, which therefore wraps it and still adds CORS headers to these responses.
    """
    import logging
    import uuid
    from fastapi.responses import JSONResponse
    from .services.audit import is_connection_error
    try:
        return await call_next(request)
    except Exception as exc:
        ref = uuid.uuid4().hex[:8]
        if is_connection_error(exc):
            # Network/database outage, not a bug: say so, and keep the log line short
            logging.getLogger("app.errors").error(
                f"Database unreachable ref={ref} {request.method} {request.url.path}: {type(exc).__name__}: {str(exc)[:200]}")
            return JSONResponse(status_code=503, content={
                "code": "DATABASE_UNAVAILABLE",
                "detail": f"The case database could not be reached (reference {ref}). Check the internet connection "
                          f"and try again in a moment. If you were saving something, check whether it was saved "
                          f"before repeating it.",
                "reference": ref,
            })
        logging.getLogger("app.errors").exception(f"Unhandled error ref={ref} {request.method} {request.url.path}: {exc}")
        return JSONResponse(status_code=500, content={
            "code": "INTERNAL_ERROR",
            "detail": f"Unexpected server error (reference {ref}). Nothing further was processed; try again, "
                      f"and report the reference to the administrator if it repeats.",
            "reference": ref,
        })


# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
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
app.include_router(jurisdictions_router, prefix="/api/v1")
app.include_router(folders_router, prefix="/api/v1")
app.include_router(fir_applications_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")
app.include_router(summaries_router, prefix="/api/v1")
app.include_router(assistant_router, prefix="/api/v1")

@app.get("/api/v1/health")
async def health_check():
    from .database import get_database_status
    from .services.storage import storage_service
    db_status = get_database_status()
    st_status = storage_service.get_status()
    return {
        "status": "healthy",
        # Fixed marker so start/diagnose scripts can tell this server apart from another app on the same port
        "app": "fir-visionai",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "database": "supabase_postgresql_connected" if db_status["is_postgres"] else "sqlite3_fts5_connected",
        "database_details": db_status,
        "storage_details": st_status,
        "demo_mode": settings.DEMO_MODE
    }

@app.get("/api/v1/health/ready")
async def readiness_check():
    """Deep check: runs SELECT 1 on the database and probes the storage bucket. 503 if either fails."""
    import logging
    from fastapi.responses import JSONResponse
    from .services.health import readiness
    report = await readiness()
    if report["status"] != "ready":
        logging.getLogger("app.health").warning(f"Readiness check degraded: {report['checks']}")
    return JSONResponse(status_code=200 if report["status"] == "ready" else 503, content=report)

@app.get("/download/report")
@app.get("/api/v1/download/report")
async def download_technical_report():
    """Provides direct, one-click HTTP download of the generated Word technical report."""
    report_path = os.path.join(settings.BASE_DIR, "docs", "FIR_Sahayak_Complete_Technical_Report.docx")
    if not os.path.exists(report_path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Technical report file not found on server.")
    return FileResponse(
        path=report_path,
        filename="FIR_Sahayak_Complete_Technical_Report.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=FIR_Sahayak_Complete_Technical_Report.docx"}
    )

@app.get("/download/presentation")
@app.get("/api/v1/download/presentation")
async def download_presentation():
    """Provides direct, one-click HTTP download of the generated PowerPoint presentation (.pptx)."""
    pptx_path = os.path.join(settings.BASE_DIR, "docs", "FIR_Sahayak_Complete_Project_Explanation.pptx")
    if not os.path.exists(pptx_path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Presentation file not found on server.")
    return FileResponse(
        path=pptx_path,
        filename="FIR_Sahayak_Complete_Project_Explanation.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": "attachment; filename=FIR_Sahayak_Complete_Project_Explanation.pptx"}
    )

@app.get("/download/presentation-report")
@app.get("/api/v1/download/presentation-report")
async def download_presentation_report():
    """Provides direct, one-click HTTP download of the supporting presentation report (.md)."""
    md_path = os.path.join(settings.BASE_DIR, "docs", "FIR_Sahayak_Complete_Project_Explanation.md")
    if not os.path.exists(md_path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Presentation report file not found on server.")
    return FileResponse(
        path=md_path,
        filename="FIR_Sahayak_Complete_Project_Explanation.md",
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=FIR_Sahayak_Complete_Project_Explanation.md"}
    )

@app.get("/download/technical-qa")
@app.get("/api/v1/download/technical-qa")
async def download_technical_qa_docx():
    """Provides direct, one-click HTTP download of the Technical Interview Questions & Answers Word document (.docx)."""
    qa_path = os.path.join(settings.BASE_DIR, "docs", "FIR_Sahayak_Technical_Interview_Questions_and_Answers.docx")
    if not os.path.exists(qa_path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Technical Q&A document file not found on server.")
    return FileResponse(
        path=qa_path,
        filename="FIR_Sahayak_Technical_Interview_Questions_and_Answers.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=FIR_Sahayak_Technical_Interview_Questions_and_Answers.docx"}
    )

@app.get("/download/architecture-guide")
@app.get("/api/v1/download/architecture-guide")
@app.get("/download/guide")
@app.get("/api/v1/download/guide")
async def download_architecture_guide_pdf():
    """Provides direct, one-click HTTP download of the Complete System Architecture & User Guide PDF."""
    pdf_path = os.path.join(settings.BASE_DIR, "docs", "FIR_VisionAI_Complete_Architecture_and_Step_by_Step_Guide.pdf")
    if not os.path.exists(pdf_path):
        pdf_path_alt = os.path.join(settings.BASE_DIR, "backend", "docs", "FIR_VisionAI_Complete_Architecture_and_Step_by_Step_Guide.pdf")
        if os.path.exists(pdf_path_alt):
            pdf_path = pdf_path_alt
        else:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Architecture Guide PDF not found on server.")
    return FileResponse(
        path=pdf_path,
        filename="FIR_VisionAI_Complete_Architecture_and_Step_by_Step_Guide.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=FIR_VisionAI_Complete_Architecture_and_Step_by_Step_Guide.pdf"}
    )

@app.get("/download/architecture-image")
@app.get("/api/v1/download/architecture-image")
async def download_architecture_diagram_image():
    """Provides direct, one-click HTTP download of the High-Resolution System Architecture Diagram Image (PNG)."""
    img_path = os.path.join(settings.BASE_DIR, "docs", "FIR_VisionAI_Architecture_Diagram.png")
    if not os.path.exists(img_path):
        img_path_alt = os.path.join(settings.BASE_DIR, "backend", "docs", "FIR_VisionAI_Architecture_Diagram.png")
        if os.path.exists(img_path_alt):
            img_path = img_path_alt
        else:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Architecture Diagram image not found on server.")
    return FileResponse(
        path=img_path,
        filename="FIR_VisionAI_System_Architecture_Diagram.png",
        media_type="image/png",
        headers={"Content-Disposition": "attachment; filename=FIR_VisionAI_System_Architecture_Diagram.png"}
    )

@app.get("/download/manager-guide")
@app.get("/api/v1/download/manager-guide")
async def download_manager_guide_pdf():
    """Provides direct, one-click HTTP download of the complete, professional Manager Reference Guide PDF."""
    pdf_path = os.path.join(settings.BASE_DIR, "docs", "FIR_VisionAI_Complete_Manager_Guide.pdf")
    if not os.path.exists(pdf_path):
        pdf_path_alt = os.path.join(settings.BASE_DIR, "backend", "docs", "FIR_VisionAI_Complete_Manager_Guide.pdf")
        if os.path.exists(pdf_path_alt):
            pdf_path = pdf_path_alt
        else:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Manager Guide PDF not found on server.")
    return FileResponse(
        path=pdf_path,
        filename="FIR_VisionAI_Complete_Manager_Guide.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=FIR_VisionAI_Complete_Manager_Guide.pdf"}
    )



