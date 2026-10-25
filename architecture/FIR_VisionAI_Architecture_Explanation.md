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
| 5. RAG Pipeline & Chatbot | Section-aware page chunking, full-text + vector hybrid retrieval, Gemini answers with mandatory citations, five search scopes | Implemented |
| 6. Data & Storage | Supabase PostgreSQL (asyncpg / psycopg2) with pgvector and `tsvector`, or local SQLite + FTS5; Supabase Storage or local disk | Implemented |
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
See section 4 for the full retrieval process. Implemented components: shared ingestion pipeline with index verification, section-aware page chunking, Gemini embeddings (`gemini-embedding-001`, 768 dimensions), full-text and vector indexes, scope resolution with access control, hybrid retrieval, cited answer generation and guardrails. Operating instructions: `docs/KNOWLEDGE_BASE_OPERATIONS.md`.

### Layer 6 – Data & Storage
- **Database selection** (`backend/app/database.py`): if `SUPABASE_DATABASE_URL` is set, the app uses **Supabase PostgreSQL** (async `asyncpg`, sync `psycopg2`, pooled). Otherwise it uses **local SQLite** (`data/fir_sahayak.db`, WAL mode) with FTS5 virtual tables for chunks, cases and the legal corpus.
- **22 ORM tables**, grouped in the diagram:
  - *FIR & case metadata:* `cases`, `case_fields`, `fir_folders`, `case_folder_assignments`, `workflow_executions`
  - *Extracted text & page references:* `documents`, `document_pages`, `document_chunks`, `extraction_runs`, `extraction_configs`, `bulk_jobs`
  - *Intelligence & legal data:* `entities`, `entity_mentions`, `graph_edges`, `legal_corpus`, `case_legal_sections`, `case_summaries`
  - *Audit & permissions:* `users`, `refresh_tokens`, `audit_logs`, `generated_documents`, `document_approval_history`
- **Evidence & document storage** (`services/storage.py`): private Supabase Storage bucket `evidence` with signed URLs when Supabase credentials are configured, otherwise the local `data/evidence` folder.
- **Search:** SQLite FTS5 in local mode; on Supabase a generated `tsvector` column (section reference, title and text) with a GIN index, and a pgvector `embedding vector(768)` column with an HNSW cosine index.
- **Ingestion jobs:** `ingestion_jobs` records every ingestion or retry with page/chunk/embedding counts, warnings and errors.
- **Provenance:** documents record source type (official, secondary, synthetic, unverified), official URL, reference number, authority, dates and legal status; official provisions in `legal_corpus` record their page and source checksum.

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

The assistant (`/rag/query` → `services/rag_engine.py`) searches one of five scopes:

| Scope | Documents searched |
|---|---|
| Current FIR | Only the selected document |
| Case + evidence | All searchable documents of the selected FIR's case |
| FIR + Law | The selected FIR plus the legal corpus, cited separately |
| Knowledge Base | Authorised Knowledge Base documents (optionally one category) |
| All authorised | Every searchable document in the officer's jurisdiction (plus SQL counts for "how many" questions) |

**Ingestion** (`services/ingestion.py`, shared by uploads, retries and the official-source importer):
1. Validate type, size, corruption and duplicates (SHA-256).
2. Extract text page by page (pypdf, pdfplumber, OCR of rendered pages; DOCX; TXT; images by Gemini OCR, then Sarvam). Legacy-font garbage lines are dropped. **No placeholder text is ever stored**: a document with no readable text is marked *Needs review* and is not searchable.
3. Chunk into passages of up to about 1,100 characters that never cross a page. In laws, numbered headings are tracked so each passage carries its Section/Article; tables of contents, amendment footnotes and appended Acts are handled.
4. Embed passages with Gemini (`gemini-embedding-001`, 768 dimensions; automatic fallback if the configured model is retired).
5. Index: SQLite FTS5 locally; PostgreSQL `tsvector` + GIN and pgvector HNSW on Supabase.
6. Verify with a real test search before marking the document *Indexed* (or *Partially indexed* when some pages or embeddings are missing).

**Answering a question:**
1. **Scope and access.** The scope is resolved to an explicit list of document ids the officer may access (`services/document_access.py`). Archived, failed and needs-review documents are excluded.
2. **Query preparation.** Telugu and Hindi questions are translated to English for searching (Gemini), while the answer stays in the officer's language.
3. **Hybrid retrieval.** Full-text ranking and vector similarity (only against documents embedded with the same model) are fused with reciprocal rank fusion.
4. **Answer.** Gemini receives the top passages as numbered sources and must cite `[S#]` after every claim; an answer without citations is treated as *not found*. For legal questions it separates what the FIR states, what the official law states, and suggestions for review (decision support only). Without Gemini, the matching passages are quoted directly and labelled as such.
5. **Citations.** Each citation names the document, section, page, a supporting excerpt, the source type (official, secondary, synthetic, unverified), legal status, and links to the page and the official source.
6. **Not found.** If the scope doesn't support an answer: *"I could not find sufficient supporting information in the selected FIR VisionAI documents to answer this question."* (also in Telugu and Hindi), with no citations and an option to search a wider scope.
7. **Audit.** Each query is audited with scope and retrieval counts, never the document text.

---

## 5. Security controls (implemented)

| Control | Implementation |
|---|---|
| Password storage | Argon2 hashing (`argon2-cffi`) |
| Authentication | JWT HS256 access token (120 min) + refresh token (7 days, unique `jti`), stored refresh tokens |
| Account approval | Inactive accounts are rejected with 403 until approved by a DISTRICT/STATE administrator |
| Role-based access & jurisdiction isolation | One shared document-access module applied to listing, search, pages, view, download, extraction, case linking and assistant retrieval; statewide reference material changes need DISTRICT/STATE, official labels need STATE |
| Row Level Security | Enabled on all Supabase tables; the backend (table owner) is unaffected, Supabase's public API roles have no row access |
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
- `asyncpg`, `psycopg2-binary`, `pypdfium2` and `Pillow` were missing from `backend/requirements.txt`. They were added in commit `7cf833d`.

---

## 6. Implemented vs planned

| Component | Status | Evidence in code |
|---|---|---|
| React frontend, FastAPI backend, JWT + RBAC | Implemented | `frontend/src`, `backend/app/api/v1`, `services/auth.py` |
| Gemini OCR, extraction, summaries, grounded answers | Implemented | `services/gemini.py`, called from pipeline, extraction, generation and RAG |
| Sarvam Digitise / Extract | Implemented (when key is set) | `services/sarvam_doc_ai.py`, called from `pdf_pipeline.py` and `/extraction` |
| Shared ingestion pipeline with index verification and retries | Implemented | `services/ingestion.py`, `ingestion_jobs` |
| Section-aware, page-bounded chunking | Implemented | `services/text_processing.py` |
| Full-text index | Implemented | SQLite FTS5 locally; `document_chunks.content_tsv` + GIN on Supabase |
| Embedding generation | Implemented (needs a Gemini key) | `services/embeddings.py` (`gemini-embedding-001`, 768 dims) |
| Vector index / semantic search | Implemented | `document_chunks.embedding` (pgvector HNSW) on Supabase; cosine over `embedding_json` locally |
| Hybrid retrieval, five scopes, cited answers | Implemented | `services/retrieval.py`, `services/rag_engine.py` |
| Official legal sources | Imported: Constitution (as on 1 May 2024), BNS, BNSS, BSA | `corpus/official_sources.json`, `scripts/import_official_documents.py` |
| Rule-based legal section suggestions | Implemented | `services/legal_service.py` |
| Fuzzy entity resolution + graph | Implemented | `services/entity_resolution.py` |
| Hash-chained audit log | Implemented | `services/audit.py` |
| Supabase PostgreSQL + Storage with local fallback | Implemented | `database.py`, `storage.py` |
| **Official AP Excise Act 1968, AP Act 17 of 1995, NDPS Act** | **Pending download** | Listed in the manifest; India Code returned HTTP 504 during import |
| **Deployment platform / CI/CD** | **Planned** | No Dockerfile, hosting config or `.github/workflows` |
| Firebase | Not used | No references in code |

> **Note on older documents:** `backend/docs/make_full_doc.py`, `backend/docs/guide_data.py` and `backend/scripts/generate_architecture_image.py` (and the PDFs and diagram generated from them) describe "pgvector with 1536-dimensional embeddings". The implemented design uses 768-dimensional Gemini embeddings; this document and diagram reflect the code.
>
> **Earlier legal summaries:** 28 "legal" documents and 108 legal sections created during development are short paraphrases, not official text. They are labelled *Unverified* and shown with a warning; official text is preferred wherever it exists.

---

## 7. Suggested next steps
1. Retry the pending official sources (`--include-pending`) when India Code responds, and add AP prohibition/excise rules and notifications from official portals.
2. Set `GEMINI_EMBEDDING_MODEL=gemini-embedding-001` in the backend `.env` (the retired `text-embedding-004` currently triggers an automatic fallback).
3. Re-run OCR for the 17 FIR uploads marked *Needs review* once OCR is available.
4. Choose a deployment target, add a Dockerfile or hosting config and a CI workflow, set production CORS origins and a strong `SECRET_KEY`, and turn off demo mode.
