"""
Comprehensive Structured Data for FIR VisionAI Manager Documentation.
Includes:
- Button Reference Table (Every single button in UI)
- API Endpoints Table
- Database Schema Table
- 19-Step User Guide Data
- Glossary & Presentation Points
"""

BUTTON_DATA = [
    # Dashboard
    ("Dashboard: Total Scoped Cases", "KPI metric card showing total accessible cases within officer's jurisdiction.", "Navigates to /cases displaying all authorized non-archived cases.", "cases table filtered by user scope", "Filtered case list with active count banner", "None; opens empty list if no cases exist in jurisdiction"),
    ("Dashboard: Under Review", "KPI card showing cases currently in review queue requiring officer sign-off.", "Navigates to /cases?status=IN_REVIEW with status filter locked.", "cases table where status='IN_REVIEW'", "Displays only cases awaiting field or section verification", "None; shows 'No cases match filter' if queue is clear"),
    ("Dashboard: Approved FIRs", "KPI card showing cases that completed full review and approved.", "Navigates to /cases?status=APPROVED with court-ready records.", "cases table where status='APPROVED'", "Displays official approved FIR records ready for court", "None; read-only view for finalized cases"),
    ("Dashboard: Pending Drafts", "KPI card showing unsubmitted or incomplete case drafts.", "Navigates to /cases?status=DRAFT allowing officer to resume editing.", "cases table where status='DRAFT'", "Displays drafts with 'Continue Draft' action button", "None; prevents duplicate case generation"),
    ("Dashboard: Quick Intake Button", "Action shortcut on dashboard header.", "Opens FIRFormSelectionModal to choose intake template.", "Intake router", "Modal with Excise, NDPS, General FIR templates", "Requires STATION or DISTRICT role"),
    ("Dashboard: Verify Action Item", "Action button on pending verification table rows.", "Directly opens the case verification workspace.", "case_fields table", "Navigates to /cases/{id} focused on unverified fields", "Disabled if case locked by supervisor"),

    # Case Management
    ("Case Mgmt: Quick Filter Pills", "Toggle pills: All | Under Review | Approved | Drafts | Archived.", "Updates URL query params without page reload and re-filters list.", "cases API /cases/?status=...", "Instant filtered view matching pill count", "URL remains shareable and bookmarkable"),
    ("Case Mgmt: Search Bar", "Full-text case search input.", "Debounced live search across FIR number, vehicle, location, contraband.", "Full-text search (ILIKE / tsvector)", "Updated table with matching records highlighted", "Returns 0 matches if search query not found"),
    ("Case Mgmt: Date Range Search", "Start Date and End Date pickers with 'Filter by Date' button.", "Queries cases registered or occurred within selected date interval.", "registration_date column", "Cases filtered by date boundaries", "Validates start_date <= end_date"),
    ("Case Mgmt: Continue Draft", "Action button on DRAFT status rows.", "Opens FIR Application Form pre-populated with saved draft values.", "fir_applications table", "Resumes drafting session without data loss", "Session restored from localStorage/DB"),
    ("Case Mgmt: Review Case", "Action button on IN_REVIEW status rows.", "Opens Case Detail workspace with side-by-side evidence viewer.", "Document extraction API", "Case details, extracted fields, and PDF preview", "Shows unverified badges in amber"),
    ("Case Mgmt: View Details", "Action button on APPROVED status rows.", "Opens read-only Case Detail workspace with audit stamps.", "Case model & audit table", "Case details, linked entities, and export actions", "Audit trail permanently records access"),

    # Document Extraction & Case Detail
    ("Case Detail: Field Override Edit", "Edit pencil button next to each extracted case field.", "Opens modal to type corrected value and reason for change.", "case_fields override API", "Updates field, marks VERIFIED, logs audit trail", "Rejects empty values on mandatory fields"),
    ("Case Detail: Approve Document", "Green approval button on case header.", "Checks required fields, marks status APPROVED, logs officer ID.", "cases approval endpoint", "Case status changes to APPROVED, unlocks official exports", "Fails if mandatory fields unverified"),
    ("Case Detail: Export XLSX", "Export dropdown option for Excel spreadsheet.", "Downloads formatted .xlsx workbook with case fields and entities.", "openpyxl export service", "File download dialog: FIR_Record_TIMESTAMP.xlsx", "Requires active session token"),
    ("Case Detail: Export DOCX", "Export dropdown option for Word document.", "Downloads court-ready .docx document with Unicode text.", "python-docx export service", "File download dialog: FIR_Record_TIMESTAMP.docx", "Preserves Telugu and Hindi characters"),
    ("Case Detail: Export PDF", "Export dropdown option for official PDF.", "Generates ReportLab PDF with watermarks and signatures.", "ReportLab PDF engine", "File download dialog: FIR_Record_TIMESTAMP.pdf", "Renders IndicFont Nirmala.ttf cleanly"),

    # Incident Location & Map
    ("Incident Map: View on Map", "Map marker button inside Incident Location card.", "Centers Leaflet map at resolved latitude and longitude coordinates.", "Nominatim OSM / AP Centroid DB", "Interactive marker with popup showing FIR details", "Shows AP state overview if unresolved"),
    ("Incident Map: Get Directions", "Blue navigation button with external link icon.", "Opens Google Maps in new tab with route to incident spot.", "Google Maps Navigation URL", "Navigates to https://www.google.com/maps/dir/?api=1...", "Disabled if coordinates null"),
    ("Incident Map: Verify Location", "Green verification button on location card.", "Confirms incident spot coordinates, marks verified in DB.", "cases location PUT endpoint", "Location status changes to MANUAL_CONFIRMED", "Updates audit ledger with officer ID"),
    ("Incident Map: Edit Location", "Pencil button to manually correct address or pin.", "Enables dragging pin on map and reveals custom address input.", "Leaflet drag event handler", "Allows officer to drag marker or re-geocode address", "Audit logs before/after coordinates"),
    ("Incident Map: Re-Geocode", "Action button next to custom address input.", "Submits corrected address to Nominatim geocoding service.", "Nominatim geocoder service", "Pins newly resolved coordinates on map", "Falls back to AP district centroid if not found"),
    ("Incident Map: View Source in FIR", "Toggle button below location card.", "Expands panel showing original passage and page citation.", "incident_location_evidence_passage", "Displays exact sentence extracted from FIR scan", "Hidden if no text passage extracted"),

    # AI FIR RAG Assistant
    ("AI Chatbot: Source Selector", "4-mode pill selector: Selected FIR | Knowledge Base | Combined | Intel.", "Switches retrieval scope for question answering.", "RAG retrieval router", "Restricts context to selected corpus", "Cross-Case requires State Director role"),
    ("AI Chatbot: Category Filter", "Dropdown shown in Knowledge Base Only mode.", "Filters retrieval to 1 of 8 official departmental categories.", "knowledge_base category filter", "Retrieval scoped strictly to selected category", "All Documents searches across all 8"),
    ("AI Chatbot: Ask Question", "Send button next to query text input.", "Sends query to backend RAG engine with selected scope.", "Gemini 1.5 + pgvector cosine search", "Streams grounded answer with verifiable citations", "Returns 'Information not found' if out of scope"),
    ("AI Chatbot: Citation Pill", "Clickable document/page citation badge below answer.", "Opens PDF viewer modal scrolled directly to cited page.", "PDFViewerModal component", "Displays original evidence document with highlight", "Shows warning if document unindexed"),

    # Case Diary & Chargesheet Generators
    ("Case Diary: Language Selector", "3-button toggle: English | Telugu (తెలుగు) | Hindi (हिन्दी).", "Switches generation template and document language.", "Jinja2 multilingual templates", "Loads draft for chosen language or creates new one", "Preserves separate drafts per language"),
    ("Case Diary: Regenerate", "Refresh button on editor toolbar.", "Re-renders draft template from case fields in selected language.", "Document generator draft API", "Overwrites editor with fresh structured text", "Prompts confirmation before replacing edits"),
    ("Case Diary: Save Draft", "Save button on editor toolbar.", "Persists edited text as a new version in database.", "generated_documents PUT API", "Version counter increments (e.g., v1 -> v2)", "Saves officer ID in audit history"),
    ("Case Diary: Approve Document", "Green check button on editor toolbar.", "Marks document status APPROVED and certifies review.", "generation approve API", "Status badge changes to APPROVED, unlocks exports", "Requires verifying officer role"),
    ("Case Diary: Export PDF", "PDF download button on generator toolbar.", "Streams official Case Diary PDF with ReportLab IndicFont.", "generation export-pdf endpoint", "Downloads Case_Diary_ID_vX.pdf", "Draft watermark removed upon approval"),
    ("Case Diary: Export DOCX", "DOCX download button on generator toolbar.", "Streams editable Microsoft Word Case Diary document.", "generation export-docx endpoint", "Downloads Case_Diary_ID_vX.docx", "Full Unicode font support for Telugu"),
    ("Chargesheet: Approve & Export", "Official approval button on Chargesheet generator.", "Validates accused, sections, and evidence before export.", "generation chargesheet router", "Finalizes Section 173 CrPC judicial report", "Fails if accused details missing"),

    # Settings & Downloads
    ("Settings: Download Diagram (PNG)", "Prominent blue button on Settings & Documentation.", "Initiates direct HTTP download of 3840x2400 architecture image.", "/api/v1/download/architecture-image", "Downloads FIR_VisionAI_System_Architecture_Diagram.png", "Direct binary stream with attachment header"),
    ("Settings: Download Guide (PDF)", "Green button on Settings & Documentation.", "Initiates direct HTTP download of comprehensive PDF guide.", "/api/v1/download/architecture-guide", "Downloads FIR_VisionAI_Complete_Architecture_and_Step_by_Step_Guide.pdf", "Direct binary stream with attachment header"),
    ("Settings: Create Backup", "Database maintenance button.", "Triggers database snapshot and configuration dump.", "System maintenance API", "Success notification with backup timestamp", "Admin / State Director only")
]

API_ENDPOINTS_DATA = [
    ("POST", "/api/v1/auth/login", "Authenticate officer & issue JWT access + refresh tokens", "LoginRequest (username, password)", "TokenResponse (access_token, token_type, role)", "Public (Rate limited)"),
    ("POST", "/api/v1/auth/refresh", "Refresh expired JWT access token using refresh token", "RefreshTokenRequest (refresh_token)", "TokenResponse with new access_token", "Bearer Refresh Token"),
    ("GET", "/api/v1/cases/", "List cases scoped to officer's station/district jurisdiction", "Query: status, district, station, search, page, limit", "List[CaseResponse] with X-Total-Count header", "Authenticated (RBAC Scoped)"),
    ("POST", "/api/v1/cases/", "Create new case record with auto-geocoded incident location", "CaseCreate (fir_number, year, district, station...)", "CaseResponse (created case with UUID)", "Authenticated (Station/Dist)"),
    ("GET", "/api/v1/cases/{id}", "Get complete case details, fields, entities, and evidence", "Path: id (UUID)", "CaseDetailResponse (nested objects)", "Authenticated (Scoped)"),
    ("GET", "/api/v1/cases/{id}/location", "Fetch incident location, geocoding coordinates, navigation", "Path: id (UUID)", "IncidentLocationResponse (coords, status, URLs)", "Authenticated (Scoped)"),
    ("PUT", "/api/v1/cases/{id}/location", "Update, drag-pin or verify incident coordinates", "IncidentLocationUpdate (lat, lng, normalized...)", "IncidentLocationResponse (updated state)", "Authenticated (Officer Sign-off)"),
    ("POST", "/api/v1/cases/{id}/location/geocode", "Re-geocode custom address against Nominatim and centroids", "RegeocodeRequest (custom_address)", "IncidentLocationResponse with resolved coords", "Authenticated (Scoped)"),
    ("POST", "/api/v1/documents/upload", "Upload scanned FIR or evidence PDF/image to storage bucket", "Multipart form: file, case_id, doc_type", "DocumentResponse (storage path, SHA-256 hash)", "Authenticated (Scoped)"),
    ("POST", "/api/v1/extraction/process/{doc_id}", "Trigger multilingual OCR and Gemini field extraction", "Path: doc_id (UUID)", "ExtractionResult (parsed fields, confidence)", "Authenticated (Scoped)"),
    ("POST", "/api/v1/cases/{id}/fields/override", "Save manual officer correction for extracted field", "CaseFieldOverride (field_name, override_value, reason)", "CaseFieldResponse (status: VERIFIED)", "Authenticated (Officer Review)"),
    ("GET", "/api/v1/knowledge-base/", "List authorized departmental Knowledge Base documents", "Query: category (1-8), search, status", "List[KnowledgeBaseDocument]", "Authenticated"),
    ("POST", "/api/v1/rag/chat", "Ask question to AI Chatbot with grounded citation search", "ChatQuery (question, mode, category, case_id)", "ChatResponse (answer, citations, sources)", "Authenticated"),
    ("POST", "/api/v1/generation/draft", "Generate multilingual Case Diary or Chargesheet draft", "DocumentGenerateRequest (case_id, doc_type, language)", "GeneratedDocument (title, content, version)", "Authenticated"),
    ("PUT", "/api/v1/generation/{doc_id}", "Save officer edits to generated document draft", "Path: doc_id, Query: content", "GeneratedDocument (incremented version)", "Authenticated"),
    ("POST", "/api/v1/generation/{doc_id}/approve", "Officially approve case diary or chargesheet for court", "DocumentApprovalRequest (action, comments)", "GeneratedDocument (status: APPROVED)", "Authenticated (Officer/Supervisor)"),
    ("GET", "/api/v1/generation/{doc_id}/export-pdf", "Export official ReportLab PDF with Indic Unicode font", "Path: doc_id (UUID)", "Binary FileResponse (application/pdf)", "Authenticated"),
    ("GET", "/api/v1/generation/{doc_id}/export-docx", "Export editable Microsoft Word document (.docx)", "Path: doc_id (UUID)", "Binary FileResponse (application/docx)", "Authenticated"),
    ("GET", "/api/v1/download/architecture-image", "Direct download of 3840x2400 architecture diagram PNG", "None", "Binary FileResponse (image/png)", "Public / Authenticated"),
    ("GET", "/api/v1/download/architecture-guide", "Direct download of complete 33-page user guide PDF", "None", "Binary FileResponse (application/pdf)", "Public / Authenticated"),
    ("GET", "/api/v1/audit/trail", "Retrieve cryptographic immutable audit ledger", "Query: object_type, actor_id, page, limit", "List[AuditEvent] with before/after state", "Supervisor / Director only")
]

DB_TABLES_DATA = [
    ("users", "Officer credentials, roles (STATE, DISTRICT, STATION), station assignment, status", "id (UUID PK)", "username, email, role, district, station, hashed_password, is_active, created_at"),
    ("cases", "Core FIR record, jurisdiction, incident coordinates, contraband, narrative, status", "id (UUID PK)", "fir_number, year, district, station, incident_latitude, incident_longitude, incident_place_raw, incident_location_geocoder_status, incident_location_verified, status, narrative, created_by (FK users.id)"),
    ("fir_documents", "Attached scanned FIR PDFs, seized evidence images, storage paths, SHA-256 hashes", "id (UUID PK)", "case_id (FK cases.id), file_name, file_type, storage_path, file_hash, ocr_text, page_count, created_at"),
    ("case_fields", "Extracted structured fields with confidence scores and officer override audit", "id (UUID PK)", "case_id (FK cases.id), field_name, field_value, confidence, verification_status, override_value, override_reason, verified_by (FK users.id)"),
    ("entities", "Extracted persons (accused, complainant) and vehicles with canonical names and risk", "id (UUID PK)", "entity_type (PERSON, VEHICLE), canonical_name, aliases, risk_score, created_at"),
    ("entity_mentions", "Links entities to specific case records with role (e.g. PRIMARY_ACCUSED, DRIVER)", "id (UUID PK)", "case_id (FK cases.id), entity_id (FK entities.id), role_in_case, context_passage"),
    ("knowledge_base", "Departmental legal corpus: Acts, circulars, SOPs, seizure guides across 8 categories", "id (UUID PK)", "title, category (1-8), act_name, section_number, file_path, content_text, status, created_at"),
    ("kb_chunks", "Document text chunks with 1536-dimensional vector embeddings for pgvector RAG", "id (UUID PK)", "document_id (FK knowledge_base.id), chunk_index, chunk_text, embedding (vector(1536)), metadata"),
    ("generated_documents", "Jinja2 drafted Case Diaries and Chargesheets in English, Telugu and Hindi", "id (UUID PK)", "case_id (FK cases.id), doc_type, title, language (en, te, hi), content, version, status, approved_by"),
    ("audit_logs", "Immutable cryptographic audit ledger recording every user action and data modification", "id (UUID PK)", "actor_id (FK users.id), actor_username, action_type, object_type, object_id, before_state, after_state, timestamp")
]

GLOSSARY_DATA = [
    ("FIR", "First Information Report — Initial formal document prepared by police/excise upon receiving information of a cognizable offence under Section 154 CrPC."),
    ("CrPC", "Code of Criminal Procedure, 1973 — Procedural statute governing investigation, arrest, inquiry, trial, and bail in Indian criminal jurisprudence."),
    ("BNSS", "Bharatiya Nagarik Suraksha Sanhita, 2023 — The modernized criminal procedure code replacing the CrPC 1973 in India."),
    ("BNS", "Bharatiya Nyaya Sanhita, 2023 — The modernized penal code replacing the Indian Penal Code (IPC 1860)."),
    ("AP Excise Act", "Andhra Pradesh Excise Act, 1968 — Statutory law regulating production, manufacture, possession, transport, purchase, and sale of intoxicating liquor and drugs in Andhra Pradesh."),
    ("NDPS Act", "Narcotic Drugs and Psychotropic Substances Act, 1985 — Strict federal statute regulating illicit trafficking of narcotic drugs and psychotropic substances."),
    ("Case Diary", "Mandatory daily chronological investigation diary maintained by investigating officers under Section 172 CrPC / Section 192 BNSS."),
    ("Chargesheet", "Final formal police/excise investigation report submitted to the magistrate under Section 173 CrPC / Section 193 BNSS."),
    ("RAG", "Retrieval-Augmented Generation — AI architectural pattern combining vector semantic search over authorized documents with LLM generation to prevent hallucinations."),
    ("pgvector", "PostgreSQL database extension enabling high-performance storage, indexing (HNSW), and cosine distance search of high-dimensional vector embeddings."),
    ("RLS", "Row Level Security — Kernel-level PostgreSQL security feature enforcing that database queries only return rows authorized for the executing user's role and jurisdiction."),
    ("Nominatim", "OpenStreetMap open-source search engine providing reverse and forward geocoding based on geographic coordinates and road networks.")
]

print("Guide data dictionaries loaded successfully.")
