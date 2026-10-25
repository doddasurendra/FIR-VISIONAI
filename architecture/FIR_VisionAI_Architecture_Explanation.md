# FIR VisionAI – System Architecture Explanation

**Project:** FIR VisionAI, Andhra Pradesh Prohibition & Excise Department
**Purpose:** AI-powered multilingual FIR extraction, case intelligence, investigation support and an evidence-grounded chatbot
**Diagram:** [`FIR_VisionAI_System_Architecture.png`](FIR_VisionAI_System_Architecture.png) (4800 × 5080 px) · [`FIR_VisionAI_System_Architecture.svg`](FIR_VisionAI_System_Architecture.svg) (vector)
**Basis:** Direct inspection of the source code in repository `doddasurendra/FIR-VISIONAI` at commit `d224abf` (25 October 2026)

> Everything marked **Implemented** below is called by application code. Everything marked **Planned** exists only as configuration, a schema line or an unused column, and is not wired into the running application.

---

## 1. Architecture at a glance

| Layer | Main technology (from the code) | Status |
|---|---|---|
| 1. Users & Access | Browser SPA, STATION / DISTRICT / STATE roles, EN / TE / HI | Implemented |
| 2. Frontend | React 18, TypeScript, Vite 5, Tailwind CSS, React Router 6, Axios, Leaflet, vis-network | Implemented |
| 3. Backend & APIs | FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.0 (async), 16 routers / ~110 endpoints under `/api/v1` | Implemented |
| 4. AI & Document Intelligence | pypdf, pdfplumber, pypdfium2, Pillow, Google Gemini (`google-genai`), Sarvam Document AI, RapidFuzz, NetworkX | Implemented |
| 5. RAG Pipeline & Chatbot | Page-level chunking, SQLite FTS5 / keyword retrieval, Gemini grounded generation | Implemented (lexical); embeddings & vector search **Planned** |
| 6. Data & Storage | Supabase PostgreSQL (asyncpg / psycopg2) or local SQLite + FTS5; Supabase Storage or local disk | Implemented; vector storage **Planned** |
| 7. External Integrations | Gemini API, Sarvam AI, OpenStreetMap (tiles + Nominatim), `.env` secrets, GitHub | Implemented; deployment platform **Planned** |

---

## 2. Layer-by-layer description

### Layer 1 – Users & Access
- **Users:** Excise Department officers: station Sub-Inspectors, District Superintendents and State headquarters officials (see seeded demo accounts in `backend/app/main.py`).
- **Roles:** `STATION`, `DISTRICT`, `STATE`. New registrations stay inactive until a DISTRICT/STATE administrator approves them (`approval_status`, enforced in `services/auth.py → get_current_user`).
- **Access channel:** a browser-based single-page application (Vite dev server on port 5173).
- **Languages:** English, Telugu and Hindi through `frontend/src/context/LanguageContext.tsx` and `frontend/src/i18n/translations.ts`. The selected language is also sent to the backend so chatbot answers and generated documents come back in that language.

### Layer 2 – Frontend
**Stack:** React 18 + TypeScript, built with Vite 5, styled with Tailwind CSS, routed with React Router 6, API calls via Axios (`src/api/client.ts` attaches the JWT and refreshes it automatically), Leaflet for the incident map, vis-network for the entity graph.

Modules follow the real navigation groups in `components/layout/HorizontalNav.tsx`:

| Diagram box | Pages (`frontend/src/pages`) |
|---|---|
| Dashboard & Case Management | `Dashboard`, `ReportsAnalytics`, `CaseManagement`, `CaseDetail`, `FolderView`, `PersonsView` (22 FIR folders) |
| FIR Document Upload | `NewCaseIntake`, `FIRApplicationForm`, `BulkIngestion` |
| Evidence Upload & OCR | `DocumentExtractionWorkspace`, `PDFViewerModal` |
| AI & Legal Intelligence | `KnowledgeBase`, `AICaseSummaries`, `LegalSectionAssistance` |
| AI FIR RAG Assistant | `AIFIRAssistance` |
| Investigation Tools | `EntityNetwork`, `EntityReviewQueue`, `CaseDiaryGenerator`, `ChargesheetGenerator`, `IncidentLocationMap` |
| Administration | `EmployeeManagement` (DISTRICT/STATE only), `AuditTrail`, `SettingsHealth` |

### Layer 3 – Backend & APIs
**Stack:** FastAPI on Uvicorn, Pydantic v2 schemas, SQLAlchemy 2.0 async ORM. All routes are mounted under `/api/v1` in `backend/app/main.py`.

| Capability | Routers / services |
|---|---|
| Authentication | `/auth` — Argon2 password hashing, JWT HS256 access token (120 min) and refresh token (7 days) |
| Role-based access control | `services/auth.py` — `apply_case_scope_filter` and `enforce_data_scope` restrict every query to the user's state / district / station |
| FIR processing & case management | `/cases`, `/fir-applications`, `/folders`, `/jurisdictions`; incident geocoding via `services/geocoder.py` |
| Document extraction & validation | `/documents`, `/extraction`, `/bulk` — 50 MB limit, MIME detection, SHA-256 de-duplication, configurable extraction schemas (`ExtractionConfig`) |
| Legal section recommendation | `/legal` → `services/legal_service.py` |
| Entity resolution & relationships | `/entities` → `services/entity_resolution.py` |
| Investigation workflow | `services/workflow.py` (7 post-intake stages: intake, classification, entity extraction, AI legal, investigation, repeat-offender intelligence, admin) and `/generation` (case diary, chargesheet, approval, PDF / DOCX export) |
| RAG chatbot | `/rag/query` → `services/rag_engine.py` |
| Audit, analytics, admin | `/audit`, `/analytics`, `/employees`, `/system`, `/api/v1/health` |

### Layer 4 – AI & Document Intelligence
1. **Input:** handwritten or printed FIRs as PDF, JPG, PNG or WebP. Each file is stored and fingerprinted with SHA-256 (`services/pdf_pipeline.py`).
2. **OCR & multilingual text extraction:**
   - Digital PDFs: `pypdf`, with `pdfplumber` as a fallback for complex layouts.
   - Scanned PDF pages: rendered with `pypdfium2`, then read by **Gemini multimodal OCR**.
   - Images: **Gemini multimodal OCR** first, then **Sarvam Document AI – Digitise** if Gemini returns nothing useful.
   - The Gemini OCR prompt explicitly preserves Telugu, English and Hindi text.
3. **Structured data extraction** (`/extraction`): **Sarvam Extract** with a JSON schema built from the active field configuration, then **Gemini JSON extraction**, then a deterministic regex extractor (`_rule_based_fallback_extraction`). The prompts forbid inventing facts and require `null` for missing fields.
4. **Case classification:** keyword classifier (`services/classification.py`) assigns one of 22 FIR folders. *Rule-based.*
5. **Case summarisation:** Gemini produces the narrative summary (`/generation/case/{id}/summary`). Case diaries and chargesheets are produced in EN / TE / HI from Jinja2 templates and rendered with ReportLab.
6. **Entity detection & matching:** accused persons, vehicles and phone numbers become entities. RapidFuzz token-sort similarity plus exact matches on vehicle registration and phone, and a NetworkX relationship graph. Pairs scoring 0.70–0.98 go to the human review queue.
7. **Legal section suggestions:** statutory-ingredient matching of case facts against the **verified** legal corpus (AP Excise Act 1968, BNS 2023, historical IPC from `corpus/*.json`). It is date-aware: BNS for offences on or after 1 July 2024, IPC before. *This is rule-based, not an LLM.* The officer must accept a section before it is used in a draft.
8. **Human review & correction:** per-field officer overrides (`CaseField.human_override_value`), the entity review queue, and an approval workflow for generated documents (`DocumentApprovalHistory`).

### Layer 5 – RAG Pipeline & Chatbot
See section 4 for the full retrieval process. Implemented components: page-level chunking, FTS5 / keyword index, scoped question, hybrid lexical retrieval, grounded answer generation and citations with guardrails. **Planned:** embedding generation and vector index.

### Layer 6 – Data & Storage
- **Database selection** (`backend/app/database.py`): if `SUPABASE_DATABASE_URL` is set, the app uses **Supabase PostgreSQL** (async `asyncpg`, sync `psycopg2`, pooled). Otherwise it uses **local SQLite** (`data/fir_sahayak.db`, WAL mode) with FTS5 virtual tables for chunks, cases and the legal corpus.
- **22 ORM tables**, grouped in the diagram:
  - *FIR & case metadata:* `cases`, `case_fields`, `fir_folders`, `case_folder_assignments`, `workflow_executions`
  - *Extracted text & page references:* `documents`, `document_pages`, `document_chunks`, `extraction_runs`, `extraction_configs`, `bulk_jobs`
  - *Intelligence & legal data:* `entities`, `entity_mentions`, `graph_edges`, `legal_corpus`, `case_legal_sections`, `case_summaries`
  - *Audit & permissions:* `users`, `refresh_tokens`, `audit_logs`, `generated_documents`, `document_approval_history`
- **Evidence & document storage** (`services/storage.py`): private Supabase Storage bucket `evidence` with signed URLs when Supabase credentials are configured, otherwise the local `data/evidence` folder.
- **Search:** SQLite FTS5 in local mode; SQL `ILIKE` keyword matching on PostgreSQL.
- **Vector storage:** *Planned* (see section 6).

### Layer 7 – External Integrations
| Integration | How it is used | Status |
|---|---|---|
| Google Gemini API | `google-genai` SDK, model from `GEMINI_TEXT_MODEL`: OCR, structured extraction, summaries, grounded answers | Implemented |
| Sarvam AI Document Intelligence | `api.sarvam.ai`: Digitise and Extract as async jobs (max 10 pages per job, polled) | Implemented (used when `SARVAM_API_KEY` is set) |
| OpenStreetMap | Nominatim geocoding (backend); map tiles for the Leaflet map (frontend) | Implemented |
| Environment variables & secrets | `.env` loaded by pydantic-settings; `.env` is git-ignored; `.env.example` is the template | Implemented |
| GitHub | Source control at `doddasurendra/FIR-VISIONAI`, branch `main`; no CI workflows | Implemented |
| Local runtime | `start_all.ps1` / `start_all.bat`: Uvicorn on port 8000, Vite on port 5173 | Implemented |
| Deployment platform | No hosting, container or CI/CD configuration found | **Planned** |
| Firebase | Not present anywhere in the code | Not used |

---

## 3. Data flow

**A. FIR intake and extraction**
1. The officer uploads an FIR (PDF or image) from *New Case Intake*, *FIR Application* or *Bulk Ingestion*.
2. The frontend sends it over REST with the JWT. The backend validates size and MIME type, computes the SHA-256 hash and stores the file (Supabase Storage or local disk).
3. The ingestion pipeline extracts page text (pypdf / pdfplumber / Gemini OCR / Sarvam Digitise), stores one `document_pages` row per physical page and splits each page into `document_chunks`.
4. Structured extraction (Sarvam Extract → Gemini → regex) fills the case fields. The officer reviews and corrects them in the extraction workspace.
5. The post-intake workflow classifies the case, extracts entities, suggests legal sections and runs repeat-offender checks. The results are stored and shown in the case, network and legal pages.

**B. Investigation and drafting**
- Entity resolution links people, vehicles and phone numbers across cases. Uncertain matches go to the review queue.
- Case diaries and chargesheets are drafted in EN / TE / HI, approved by an officer and exported to PDF or DOCX.

**C. Chatbot question** (see section 4)

**D. Every write** passes through the SQLAlchemy ORM and, for audited actions, appends an entry to the hash-chained audit log.

---

## 4. RAG retrieval process (as implemented)

The chatbot (`/rag/query` → `services/rag_engine.py`) supports four modes:

| Mode | Scope |
|---|---|
| FIR-only (PDF or image) | Only the selected uploaded FIR |
| Knowledge Base | Authorised Knowledge Base documents in 8 categories (legal acts, circulars, seizure reports, SOPs, references, historical FIRs, evidence) |
| Cross-case | Authorised cases in the user's jurisdiction (includes SQL counts for "how many" questions) |
| FIR + Legal | The selected FIR plus the verified legal corpus, cited separately |

**Steps for the FIR-only mode:**
1. **Cache check.** An in-memory cache keyed by document, query hash and language (5-minute TTL, 200 entries) returns repeat answers instantly.
2. **Authorisation.** The document must exist, and its case must lie inside the user's district / station unless the user is STATE. Documents still processing or failed return a clear message.
3. **Indexing check.** If chunks are missing or contain only placeholder text, the document is re-chunked automatically (`reindex_document`).
4. **Chunking (at ingestion).** Each physical page is split into 400-character chunks with 80 characters of overlap. Every chunk keeps its **physical page number**.
5. **Hybrid lexical retrieval:**
   - SQLite FTS5 `MATCH` with BM25 ranking, restricted to the selected document (local mode).
   - Keyword matching over the document's chunks (works on PostgreSQL too), with stop-word removal and investigative term expansion (persons, vehicles, places, sections).
   - Page fallback: for summaries, entity questions, images and short documents, the full page text is added.
6. **Grounded generation.** Gemini receives only the retrieved segments, labelled with their physical page numbers, and a strict prompt: answer only from these segments, never use outside knowledge, never invent facts.
7. **Citations & guardrails.** Each answer carries citations with physical page numbers and an evidence excerpt. If the answer isn't in the document, the reply is the fixed sentence *"The requested information was not found in the uploaded FIR PDF/image."* in English, Telugu or Hindi, with no citations. Questions about criminal history are refused unless the document actually mentions prior cases.
8. **Offline fallback.** If Gemini is unavailable (no key, quota or network error), a deterministic extractor answers from the same retrieved text with the same citation format.

**Important:** retrieval today is *lexical* (full-text and keyword). No embeddings are computed and no vector similarity search is performed (see section 6).

---

## 5. Security controls (implemented)

| Control | Implementation |
|---|---|
| Password storage | Argon2 hashing (`argon2-cffi`) |
| Authentication | JWT HS256 access token (120 min) + refresh token (7 days, unique `jti`), stored refresh tokens |
| Account approval | Inactive accounts are rejected with 403 until approved by a DISTRICT/STATE administrator |
| Role-based access & jurisdiction isolation | Server-side SQL filters by role on cases, documents, knowledge base and chatbot retrieval |
| Restricted folders | Sensitive FIR folders (e.g. sexual offences, arms & explosives) require DISTRICT role or higher |
| Evidence integrity | SHA-256 hash for every uploaded file; duplicates detected by hash |
| Tamper-evident audit trail | Each `audit_logs` entry stores the SHA-256 of the previous entry; `/audit` can verify the whole chain |
| Private file access | Supabase Storage private bucket with signed URLs; authenticated document-view endpoint |
| AI grounding | Strict prompts, fixed "not found" replies, no citations when nothing is found |
| Secrets | API keys and database URLs in `.env` (git-ignored); `.env.example` holds placeholders |
| Upload limits | 50 MB maximum, MIME type detection, empty-file rejection |
| CORS | Restricted to localhost origins |

**Observations for hardening** (not changed, listed for awareness):
- `config.py` contains a default `SECRET_KEY`. Production must override it through `.env`.
- `DEMO_MODE` and `ALLOW_SYNTHETIC_DATA` default to `True`, and demo accounts with known passwords are seeded on an empty database.
- CORS allows only localhost, so a real deployment will need its own allowed origins.
- `asyncpg`, `psycopg2` and `pypdfium2` are used by the code (and installed locally) but are missing from `backend/requirements.txt`. Pillow is also used but only arrives as a dependency of ReportLab.

---

## 6. Implemented vs planned

| Component | Status | Evidence in code |
|---|---|---|
| React frontend, FastAPI backend, JWT + RBAC | Implemented | `frontend/src`, `backend/app/api/v1`, `services/auth.py` |
| Gemini OCR, extraction, summaries, grounded answers | Implemented | `services/gemini.py`, called from pipeline, extraction, generation and RAG |
| Sarvam Digitise / Extract | Implemented (when key is set) | `services/sarvam_doc_ai.py`, called from `pdf_pipeline.py` and `/extraction` |
| Page-level chunking with physical page numbers | Implemented | `pdf_pipeline.chunk_text`, `document_chunks` |
| SQLite FTS5 full-text index | Implemented (local mode) | `database.init_fts5` |
| Hybrid **lexical** retrieval + page citations | Implemented | `rag_engine.answer_from_active_fir` |
| Rule-based legal section suggestions | Implemented | `services/legal_service.py` |
| Fuzzy entity resolution + graph | Implemented | `services/entity_resolution.py` |
| Hash-chained audit log | Implemented | `services/audit.py` |
| Supabase PostgreSQL + Storage with local fallback | Implemented | `database.py`, `storage.py` |
| **Embedding generation** | **Planned** | `GEMINI_EMBEDDING_MODEL = "text-embedding-004"` in `config.py` and `DocumentChunk.embedding_json` column exist, but nothing calls an embedding API or writes the column |
| **Vector index / semantic search** | **Planned** | `scripts/supabase_schema.sql` tries to enable `pgvector`, but no vector column or similarity query is used by the app |
| **PostgreSQL full-text index (tsvector)** | **Planned** | On PostgreSQL, retrieval uses `ILIKE`; FTS5 is SQLite-only |
| **Deployment platform / CI/CD** | **Planned** | No Dockerfile, hosting config or `.github/workflows` |
| Firebase | Not used | No references in code |

> **Note on older documents:** `backend/docs/make_full_doc.py`, `backend/docs/guide_data.py` and `backend/scripts/generate_architecture_image.py` (and the PDFs and diagram generated from them) describe "pgvector with 1536-dimensional embeddings and cosine search". That does not match the current code: retrieval is lexical. This new diagram and document reflect the code as it is.

---

## 7. Suggested next steps to complete the planned items
1. Generate embeddings for each chunk at ingestion (the configured `text-embedding-004` model) and store them in a `vector` column on Supabase (pgvector, HNSW index).
2. Combine vector similarity with the existing FTS5 / keyword scores (for example with reciprocal rank fusion) to make retrieval truly hybrid.
3. Add a PostgreSQL `tsvector` + GIN index so cloud mode has ranked full-text search like local mode.
4. Choose a deployment target, add a Dockerfile or hosting config and a CI workflow, set production CORS origins and a strong `SECRET_KEY`, and turn off demo mode.
5. Add `asyncpg`, `psycopg2-binary`, `pypdfium2` and `Pillow` to `backend/requirements.txt`.
