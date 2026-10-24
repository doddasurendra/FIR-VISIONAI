# FIR VisionAI — Complete System Architecture & Step-by-Step User Guide

**Document Version:** 2.0  
**Date:** October 2026  
**Department:** Andhra Pradesh Prohibition & Excise Department  
**Classification:** OFFICIAL — For Authorised Officers Only  
**Application:** FIR Sahayak u-FIR v2.0 / FIR VisionAI  
**Repository:** https://github.com/doddasurendra/fir-sahayak

---

## TABLE OF CONTENTS

1. Executive Summary
2. System Architecture Overview
3. Technology Stack
4. Frontend Architecture — All Pages & Features
5. Backend Architecture — All API Endpoints
6. Database Schema & Relationships
7. OCR & Extraction Pipeline
8. AI FIR Chatbot & RAG Pipeline
9. Knowledge Base & Legal Corpus
10. Investigation Tools
11. End-to-End Six-Stage Workflow
12. Security, Roles & Audit
13. Troubleshooting Guide
14. Testing & Deployment
15. Glossary

---

## 1. EXECUTIVE SUMMARY

FIR VisionAI (FIR Sahayak u-FIR v2.0) is a secure, AI-powered case intelligence platform developed for the **Andhra Pradesh Prohibition & Excise Department**. It digitises handwritten and printed First Information Reports (FIRs), performs multilingual OCR and structured field extraction, provides legal section intelligence, and enables officers to query case knowledge through an AI chatbot grounded exclusively in authorised documents.

### Key Capabilities (Implemented & Verified)

| Capability | Status |
|---|---|
| Multilingual FIR upload (PDF + image) | Implemented |
| AI text extraction via Gemini + Sarvam AI | Implemented |
| Officer verification & field override | Implemented |
| Legal section suggestion (BNS/IPC/AP Excise Act) | Implemented |
| AI FIR Chatbot — 4 grounded modes | Implemented |
| Knowledge Base management | Implemented |
| Historical FIR retrieval | Implemented |
| Entity network analysis | Implemented |
| Case diary & chargesheet generation | Implemented |
| Bulk document ingestion | Implemented |
| Cryptographic audit trail | Implemented |
| FIR folder classification (auto + manual) | Implemented |
| Dashboard KPI cards with navigation | Implemented |
| Role-based access (STATION / DISTRICT / STATE) | Implemented |
| Supabase PostgreSQL + local SQLite fallback | Implemented |
| PDF/XLSX/DOCX case export | Implemented |

---

## 2. SYSTEM ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 1 — USER INTERFACE                     │
│  React 18 + TypeScript + Vite + TailwindCSS                     │
│  Government Portal Design (AP Excise Dept branding)             │
│  Routes: 22 pages | Code-split lazy loading                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS REST API
┌──────────────────────────▼──────────────────────────────────────┐
│                   LAYER 2 — FRONTEND SERVICES                   │
│  Axios API Client (client.ts) | JWT Auth Interceptor            │
│  AuthContext | LanguageContext (EN/TE/HI) | FIRModalContext     │
│  React Router v6 | ErrorBoundary | Suspense/Lazy loading        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                  LAYER 3 — BACKEND API                          │
│  FastAPI 0.115 | Python 3.12 | Uvicorn ASGI                     │
│  16 Router modules | JWT HS256 | CORS middleware                │
│  Pydantic v2 schemas | SQLAlchemy 2.0 async ORM                 │
└────────┬──────────────┬─────────────────┬───────────────────────┘
         │              │                 │
┌────────▼──┐  ┌────────▼────────┐  ┌────▼──────────────────────┐
│  LAYER 4  │  │    LAYER 5      │  │       LAYER 6             │
│ PROCESSING│  │  DATA/STORAGE   │  │     AI/RETRIEVAL          │
│ Services  │  │                 │  │                           │
│ pdf_pipe  │  │ Supabase/SQLite │  │ Google Gemini Flash       │
│ sarvam_ai │  │ PostgreSQL      │  │ Sarvam AI (Vision 1.5)    │
│ rag_engine│  │ Local FileStore │  │ FTS5 keyword search       │
│ gemini    │  │ 15+ tables      │  │ Embedding-based retrieval │
│ workflow  │  │ evidence bucket │  │ BNS/IPC/AP Act corpus     │
└───────────┘  └─────────────────┘  └───────────────────────────┘
```

### Data Flow — FIR Upload to Answer

```
Officer uploads FIR PDF
       ↓
Frontend validates file (MIME, size)
       ↓
POST /api/v1/documents/upload → StorageService
       ↓
File stored: Supabase bucket OR local data/evidence/
       ↓
SHA-256 hash computed → Document record created in DB
       ↓
PDFPipeline.process_document() → pypdf extracts text per page
       ↓
DocumentPage records created with raw_text
       ↓
Text chunked (500 chars, 100 overlap) → DocumentChunk records
       ↓
FTS5 index updated (SQLite) OR pg_tsvector (PostgreSQL)
       ↓
GeminiService.extract_structured_case() → CaseField records
       ↓
SarvamDocAI.digitise_document() → OCR for scanned/handwritten
       ↓
Officer reviews in DocumentExtractionWorkspace
       ↓
Field overrides saved with verification_status = VERIFIED
       ↓
Case status: DRAFT → IN_REVIEW → APPROVED
       ↓
RAGEngine answers chatbot queries from DocumentChunk records
```

---

## 3. TECHNOLOGY STACK

### Frontend
| Technology | Version | Purpose |
|---|---|---|
| React | 18.x | UI framework |
| TypeScript | 5.x | Type safety |
| Vite | 5.4 | Build tool & dev server |
| TailwindCSS | 3.x | Utility CSS styling |
| React Router | 6.x | Client-side routing |
| Axios | 1.x | HTTP client |
| Lucide React | Latest | Icon library |
| Recharts | 2.x | Analytics charts |

### Backend
| Technology | Version | Purpose |
|---|---|---|
| FastAPI | 0.115 | ASGI REST API framework |
| Python | 3.12 | Runtime |
| SQLAlchemy | 2.0 | Async ORM |
| Pydantic | v2 | Schema validation |
| Uvicorn | Latest | ASGI server |
| pypdf | Latest | PDF text extraction |
| google-genai | Latest | Gemini AI SDK |
| httpx | Latest | Async HTTP (Sarvam AI) |
| argon2-cffi | Latest | Password hashing |
| PyJWT | Latest | JWT tokens |
| ReportLab | 5.0.1 | PDF generation |
| python-docx | Latest | DOCX generation |
| openpyxl | Latest | XLSX export |

### Database & Storage
| Component | Details |
|---|---|
| Primary DB | Supabase PostgreSQL (cloud) |
| Fallback DB | SQLite 3 + FTS5 (local) |
| File Storage (Cloud) | Supabase Private Storage bucket "evidence" |
| File Storage (Local) | data/evidence/ directory |
| AI Provider | Google Gemini Flash (configurable) |
| OCR Provider | Sarvam AI Document Intelligence (Vision 1.5) |

---

## 4. FRONTEND ARCHITECTURE — ALL PAGES & FEATURES

### Application Layout

Every page shares a consistent government portal layout:

1. **GovernmentHeader** — Official AP Government banner with Emblem, department name (AP Prohibition & Excise), Jai Hind badge, location pill (station/district), and language switcher (EN/TE/HI).
2. **HorizontalNav** — Dropdown navigation bar with all module access.
3. **Main Content Area** — Page-specific content (max-width 1700px, responsive).
4. **GovernmentFooter** — Statutory disclaimers, version info, copyright.

### 4.1 Login Page (`/login` — implicit, shown when unauthenticated)

**Route:** Rendered by `AppContent` when `isAuthenticated === false`  
**Component:** `Login.tsx`

**Features:**
- Username and password form fields
- POST `/api/v1/auth/login` with credentials
- JWT access token stored in `localStorage`
- Refresh token support
- Error display for invalid credentials
- Auto-redirect to Dashboard on success

### 4.2 Dashboard (`/`)

**Component:** `Dashboard.tsx`  
**API:** `GET /api/v1/analytics/dashboard`

**KPI Cards (all clickable, URL-bound):**

| Card | Count | Target Route | Filter |
|---|---|---|---|
| Total Scoped Cases | 41 | `/cases` | All active cases |
| Under Review | 28 | `/cases?status=IN_REVIEW` | Awaiting verification |
| Approved FIRs | 6 | `/cases?status=APPROVED` | Court-ready records |
| Pending Drafts | 7 | `/cases?status=DRAFT` | Unsubmitted drafts |

**Charts:**
- Contraband Seizures by Volume (Bar chart — Recharts)
- District-wise Case Distribution (Bar chart)

**Quick Action Cards:**
- New Case Intake → `/intake`
- AI FIR Assistance → `/ai-fir-assistance`
- Legal Intelligence → `/legal`
- Case Network → `/network`

**Action Queue:**
- Pending Field Verifications (from `case_fields` table, `verification_status = UNVERIFIED`)
- Recent Cases list with FIR numbers and statuses

### 4.3 Case Management (`/cases`)

**Component:** `CaseManagement.tsx`  
**API:** `GET /api/v1/cases/?status={STATUS}&search={TERM}&limit=100`

**Features:**
- URL-bound status filter (persists across browser Back/Forward/Refresh)
- Quick-filter pills: All Cases | Under Review | Approved FIRs | Pending Drafts | Archived
- Text search by FIR Number, Contraband Type, Offence Nature, Vehicle, Location
- Table columns: FIR Number, Jurisdiction, Offence Nature, Contraband Seized, Vehicle Details, Status, Actions
- Context-aware action buttons:
  - DRAFT → "Continue Draft" (Edit icon)
  - IN_REVIEW → "Review Case" (Eye icon)
  - APPROVED → "View Details" (Eye icon)
- Date-Wise FIR Search component (by date range)
- New Case Intake button (opens FIRFormSelectionModal)
- Filter count banner showing active filter description
- X-Total-Count header used for real record counts

### 4.4 FIR Folders (`/folders/:slug`)

**Component:** `FolderView.tsx`  
**API:** `GET /api/v1/folders/{slug}/cases`

**21 pre-seeded folders across 3 groups:**

*FIR Types:* Illicit Distillation, NDPS/Drug Transport, Non-Duty-Paid Liquor, Vehicle Seizure, Unlawful Possession, Theft/Property Crime, Assault/Bodily Harm, Road/Traffic Accidents, Cheating/Fraud, Public Nuisance, Missing Persons, Sexual Offence (District+), Domestic Violence, Land/Property Dispute, Cyber Crime, Death Investigation, Arms & Explosives (District+)

*Person-Based:* Single-FIR Persons, Multiple-FIR Person Records

*Status:* Pending Classification, Under Investigation, Closed/Charge-sheeted

**Features:**
- Auto-classification by keyword rules (classification.py service)
- Manual folder assignment by officers
- Folder-level search and status filter
- AI confidence score display per case

### 4.5 Case Detail (`/cases/:id`)

**Component:** `CaseDetail.tsx`  
**API:** `GET /api/v1/cases/{case_id}`

**Sections:**
- Case header (FIR Number, District, Station, Registration Date, Status badge)
- Extracted field table with confidence scores and verification status
- Document list with Open Evidence Viewer button per document
- Legal sections (AI-recommended + officer-accepted)
- Entity list (Persons, Vehicles, Locations)
- Workflow stage progress (CLASSIFICATION, ENTITY_EXTRACTION, AI_SUMMARY)
- AI-generated case summary
- Case Diary and Chargesheet generation buttons
- Approve Case button (STATE/DISTRICT roles)
- Archive Case button with reason field
- Export buttons: XLSX, DOCX, CSV, JSON, PDF

**Field Override Flow:**
1. Officer clicks "Override" on a field
2. Modal opens with original vs. current value
3. Officer enters correction
4. PUT `/api/v1/cases/{case_id}/fields/{field_id}/override`
5. `verification_status` → OVERRIDDEN, `verified_by` set, audit log created

### 4.6 New Case Intake (`/intake`)

**Component:** `NewCaseIntake.tsx`  
**API:** `POST /api/v1/documents/upload`

**Upload Flow:**
1. Officer opens page
2. Selects file (PDF or image: PNG, JPG, TIFF, WebP — max 50 MB)
3. Optional: link to existing Case ID
4. Click "Upload & Process"
5. Frontend POSTs multipart form to `/api/v1/documents/upload`
6. Backend validates MIME type, computes SHA-256, stores file
7. `Document` record created (status: PENDING → PROCESSING)
8. `PDFPipeline.process_document()` runs:
   - PDF: text extracted per page via pypdf
   - Image: sent to Sarvam AI for OCR + digitisation
9. `DocumentPage` records created with raw_text and OCR confidence
10. Text chunked and indexed in `document_chunks` + FTS5
11. Gemini extraction runs → `CaseField` records created
12. Status → COMPLETED
13. Officer redirected to Document Extraction Workspace

### 4.7 FIR Application Form (`/fir-application`, `/fir-application/:case_id`)

**Component:** `FIRApplicationForm.tsx`  
**API:** `POST /api/v1/fir-applications/`, `GET /api/v1/fir-applications/{case_id}`

A structured digital FIR application form with:
- Template selection (AP Excise, Standard FIR)
- Language selection (English, Telugu, Hindi)
- Fields: FIR Number, District, Station, Date, Accused Details, Offence Nature, Sections, Narrative
- Draft save → Resume later
- Submit for registration

### 4.8 Document Extraction Workspace (`/document-extraction`)

**Component:** `DocumentExtractionWorkspace.tsx`  
**APIs:** `GET /api/v1/extraction/config`, `POST /api/v1/extraction/run`, `GET /api/v1/documents/{id}/pages`

**Three-panel layout:**
- Left: Document list and extraction config
- Center: Extracted field review table with confidence scores
- Right: Document viewer (PDF or image)

**Features:**
- Run extraction with current config
- Field-by-field verification (VERIFY / OVERRIDE buttons)
- Confidence score colour coding (Green ≥0.85 / Amber 0.6-0.84 / Red <0.6)
- XLSX/DOCX export of extracted fields
- Schema editor for custom extraction fields
- Sarvam AI Extract job status polling

### 4.9 AI & Legal Intelligence (`/legal`)

**Component:** `LegalSectionAssistance.tsx`  
**API:** `GET /api/v1/legal/suggest/{case_id}`, `POST /api/v1/legal/sections/{case_id}/accept`

**Features:**
- AI-recommended legal sections for a case
- Section details: Act name, Section number, Title, Full text, Penalty
- Essential ingredients checklist
- Matched facts from FIR text
- Missing elements warning
- Officer decision buttons: ACCEPT / REJECT (with reason)
- Accepted sections carry to Chargesheet
- Source: Verified corpus of AP Excise Act 1968, BNS 2023, IPC (historical), NDPS Act

> **Important:** AI recommendations are suggestions only. An authorised officer must explicitly ACCEPT each section before it becomes part of the official case record.

### 4.10 AI Case Summaries (`/summaries`)

**Component:** `AICaseSummaries.tsx`  
**API:** `POST /api/v1/generation/summary/{case_id}`

- Generates a factual AI summary of a case in EN/TE/HI
- Grounded strictly in extracted and officer-verified case fields
- Saved to `case_summaries` table with version tracking
- Used as input for case diary generation

### 4.11 AI FIR Chatbot (`/ai-fir-assistance`)

**Component:** `AIFIRAssistance.tsx`  
**API:** `POST /api/v1/rag/query`

**Language Selection:**
- English | తెలుగు | हिन्दी
- Confirmation message sent in selected language

**Source Modes:**

| Mode | Code | Data Source | FIR Required? |
|---|---|---|---|
| Selected FIR Only | PDF_ONLY | Single selected document's chunks | Yes |
| Knowledge Base Only | KNOWLEDGE_BASE_ONLY | KB documents (acts, circulars, guides) | No |
| FIR + Legal Corpus | FIR_PLUS_LEGAL | Selected FIR + legal_corpus table | Yes |
| Cross-Case Intelligence | CROSS_CASE | All authorized cases in jurisdiction | No |

**Document Selector:**
- Dropdown: Current case documents
- Historical FIR documents (from `documents` table, `doc_category = HISTORICAL_FIR`)

**Chat Features:**
- Message history with sender (AI/Officer) and timestamp
- Citation cards showing physical page numbers and source document
- "Open Evidence" button links citation to PDF Viewer Modal
- Suggested questions per mode
- Clear Chat button
- Direct PDF upload for Mode A (bypasses case requirement)
- Loading spinner during response generation

**Response Format:**
- Answer text (grounded, never fabricated)
- Citations: [{document_name, physical_page, excerpt}]
- If not found: "Information not found in selected source" — never guesses

### 4.12 Knowledge Base (`/knowledge-base`)

**Component:** `KnowledgeBase.tsx`  
**APIs:** `GET /api/v1/legal/kb`, `POST /api/v1/documents/upload` (with doc_category)

**Document Categories:**
- LEGAL_ACT — Legislation texts
- CIRCULAR — Department circulars
- INVESTIGATION_GUIDE — Procedural manuals
- REFERENCE — Reference materials
- SEIZURE_REPORT — Historical seizure reports

**Features:**
- Upload new KB document (PDF/image)
- Auto-indexing into `document_chunks` after upload
- Search by title, category, department
- Document status: PENDING → PROCESSING → COMPLETED / FAILED
- Re-index button for failed documents
- Access control: DISTRICT+ role for restricted categories

### 4.13 Entity Network (`/network`)

**Component:** `EntityNetwork.tsx`  
**API:** `GET /api/v1/entities/network/{case_id}`

- Visual graph of entity relationships (NetworkGraph component using D3/force-directed)
- Nodes: PERSON, VEHICLE, LOCATION, ORGANIZATION
- Edges: CO_ACCUSED, VEHICLE_USED, ASSOCIATE
- Community detection (Louvain algorithm — Planned for full implementation)
- Risk score badges
- Click node to view entity details and linked cases

### 4.14 Entity Review Queue (`/entity-review`)

**Component:** `EntityReviewQueue.tsx`  
**API:** `GET /api/v1/entities/review-queue`, `PUT /api/v1/entities/{id}/merge`

- Lists entities with `verification_status = REVIEW_PENDING`
- Officers can CONFIRM, MERGE (deduplication), or REJECT entities
- Merger links duplicate entity records into canonical entity

### 4.15 Case Diary Generator (`/case-diary`)

**Component:** `CaseDiaryGenerator.tsx`  
**API:** `POST /api/v1/generation/case-diary/{case_id}`, `GET /api/v1/generation/documents`

- Select case → Generate AI-drafted case diary
- Content pulled from verified case fields, entities, and extracted narrative
- Edit in rich-text editor before submitting for review
- Status: DRAFT → IN_REVIEW → APPROVED
- Export as DOCX or PDF once approved

### 4.16 Chargesheet Generator (`/chargesheet`)

**Component:** `ChargesheetGenerator.tsx`  
**API:** `POST /api/v1/generation/chargesheet/{case_id}`

- Select case with APPROVED legal sections
- Generates structured chargesheet with:
  - FIR details
  - Accused particulars
  - Offence description
  - Invoked legal sections (officer-accepted only)
  - Evidence summary
- Same review/approve workflow as case diary

### 4.17 Bulk Ingestion (`/bulk-ingestion`)

**Component:** `BulkIngestion.tsx`  
**API:** `POST /api/v1/bulk/upload`, `GET /api/v1/bulk/status/{job_id}`

- Upload CSV/JSON file with multiple FIR records
- Background job processing with progress polling
- Success/failure counts per record
- Error report download

### 4.18 Employee Management (`/employees`)

**Component:** `EmployeeManagement.tsx`  
**APIs:** `GET /api/v1/employees/`, `POST /api/v1/employees/`, `PUT /api/v1/employees/{id}`

- User list with role, designation, station
- Create new user account (STATE role required)
- Edit user details and jurisdiction
- Approval workflow: PENDING_APPROVAL → APPROVED
- Activate/deactivate accounts

### 4.19 Audit Trail (`/audit-trail`)

**Component:** `AuditTrail.tsx`  
**API:** `GET /api/v1/audit/logs`

- Cryptographically hash-chained audit log (SHA-256)
- Filters: Actor, Action Type, Object Type, Date Range
- Each entry shows: Timestamp, Actor, Action, Object, Before/After state
- Tamper-evident: each entry's hash includes previous entry hash (blockchain-style)

### 4.20 Reports & Analytics (`/reports`)

**Component:** `ReportsAnalytics.tsx`  
**API:** `GET /api/v1/analytics/dashboard`

- Contraband seizure statistics
- District-wise case distribution
- Status pipeline chart
- Export report as XLSX

### 4.21 Settings & Health (`/settings`)

**Component:** `SettingsHealth.tsx`  
**APIs:** `GET /api/v1/health`, `GET /api/v1/system/backups`, `POST /api/v1/system/backup`

- System health dashboard (FastAPI status, Database, AI Model)
- Create database backup snapshot (SQLite integrity verification + SHA-256)
- Download existing backup files
- Documentation download buttons (Architecture Guide PDF, Technical Report, Presentation)

### 4.22 Persons View (`/folders/persons/:type`)

**Component:** `PersonsView.tsx`  
**APIs:** `GET /api/v1/folders/persons/single-fir`, `GET /api/v1/folders/persons/multiple-fir`

- Single-FIR Persons: Entities linked to exactly 1 case
- Multiple-FIR Persons: Potential repeat offenders (2+ cases)
- Search by name, risk score filter
- Links to entity detail and associated cases

> **IMPORTANT:** Multiple-case matches are advisory indicators only. Similar names or details across cases must not be treated as proof that two records involve the same individual without officer verification.

---

## 5. BACKEND ARCHITECTURE — ALL API ENDPOINTS

FastAPI application entry point: `backend/app/main.py`  
Base URL: `http://localhost:8000/api/v1`

### 5.1 Authentication (`/auth`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/login` | Username/password login → access + refresh tokens |
| POST | `/auth/refresh` | Refresh access token using refresh token |
| POST | `/auth/logout` | Revoke refresh token |
| GET | `/auth/me` | Current user profile |
| POST | `/auth/register` | Register new user (pending approval) |

**Auth mechanism:** JWT HS256 tokens. Access token expires in 120 minutes. Refresh token expires in 7 days. Both stored on frontend. `get_current_user()` dependency validates every protected route.

### 5.2 Cases (`/cases`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/cases/` | List cases (filters: status, district, station, search) |
| GET | `/cases/{case_id}` | Full case detail with fields, entities, documents |
| POST | `/cases/` | Create new case record |
| PUT | `/cases/{case_id}` | Update case fields |
| POST | `/cases/{case_id}/approve` | Approve case (DISTRICT+ role) |
| POST | `/cases/{case_id}/archive` | Archive/soft-delete case |
| GET | `/cases/{case_id}/export/{format}` | Export: xlsx/docx/csv/json/pdf |
| PUT | `/cases/{case_id}/fields/{field_id}/override` | Officer field override |

### 5.3 Documents (`/documents`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/documents/upload` | Upload PDF or image evidence |
| GET | `/documents/{doc_id}` | Document metadata |
| GET | `/documents/{doc_id}/pages` | All pages with OCR text |
| GET | `/documents/{doc_id}/view` | Serve file (signed URL or local stream) |
| GET | `/documents/{doc_id}/view-page/{page}` | Serve single page image |
| POST | `/documents/{doc_id}/replace` | Replace document with new version |
| POST | `/documents/{doc_id}/archive` | Archive document |
| GET | `/documents/{doc_id}/signed-url` | Get time-limited download URL |

### 5.4 Extraction (`/extraction`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/extraction/run` | Run AI extraction on a document |
| GET | `/extraction/runs/{doc_id}` | List extraction runs for a document |
| GET | `/extraction/config` | Get active extraction configuration |
| PUT | `/extraction/config` | Update extraction schema/instructions |
| POST | `/extraction/narrative` | Extract from free-text narrative |
| GET | `/extraction/export/{run_id}/xlsx` | Export extraction as XLSX |
| GET | `/extraction/export/{run_id}/docx` | Export extraction as DOCX |

### 5.5 Legal Intelligence (`/legal`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/legal/corpus` | List all legal corpus sections |
| GET | `/legal/corpus/{section_id}` | Single section detail |
| GET | `/legal/suggest/{case_id}` | AI-suggested sections for a case |
| POST | `/legal/sections/{case_id}/accept` | Officer accepts a section |
| POST | `/legal/sections/{case_id}/reject` | Officer rejects a section |
| GET | `/legal/kb` | Knowledge Base document list |
| POST | `/legal/kb/upload` | Upload KB document |
| POST | `/legal/kb/{doc_id}/reindex` | Re-index failed KB document |

### 5.6 RAG / AI Chatbot (`/rag`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/rag/query` | Submit question to RAG engine |

**Request body:**
```json
{
  "query": "What contraband was seized?",
  "mode": "PDF_ONLY | KNOWLEDGE_BASE_ONLY | FIR_PLUS_LEGAL | CROSS_CASE",
  "document_id": "uuid-of-selected-document",
  "language": "en | te | hi"
}
```

**Response:**
```json
{
  "answer": "Grounded answer text...",
  "citations": [
    {
      "document_name": "FIR_2024_KNL_001.pdf",
      "physical_page": 2,
      "excerpt": "...relevant text snippet..."
    }
  ],
  "mode": "PDF_ONLY",
  "confidence": 0.87
}
```

### 5.7 Entities (`/entities`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/entities/` | List entities (filter by type, case) |
| GET | `/entities/{entity_id}` | Entity detail with all mentions |
| GET | `/entities/network/{case_id}` | Graph edges for case |
| GET | `/entities/review-queue` | Entities pending verification |
| PUT | `/entities/{entity_id}/merge` | Merge duplicate entities |
| PUT | `/entities/{entity_id}/verify` | Confirm entity |
| GET | `/entities/repeat-offenders` | Entities with 2+ case mentions |

### 5.8 Generation (`/generation`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/generation/summary/{case_id}` | Generate AI case summary |
| POST | `/generation/case-diary/{case_id}` | Generate case diary draft |
| POST | `/generation/chargesheet/{case_id}` | Generate chargesheet draft |
| GET | `/generation/documents` | List all generated documents |
| PUT | `/generation/documents/{doc_id}` | Edit generated document |
| POST | `/generation/documents/{doc_id}/approve` | Approve generated document |
| GET | `/generation/documents/{doc_id}/export/pdf` | Export as PDF |

### 5.9 Bulk Ingestion (`/bulk`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/bulk/upload` | Upload CSV/JSON for batch processing |
| GET | `/bulk/status/{job_id}` | Poll job status |
| GET | `/bulk/jobs` | List all bulk jobs |

### 5.10 Employees (`/employees`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/employees/` | List employees |
| POST | `/employees/` | Create employee account |
| PUT | `/employees/{id}` | Update employee |
| PUT | `/employees/{id}/approve` | Approve pending account |
| PUT | `/employees/{id}/deactivate` | Deactivate account |

### 5.11 Audit (`/audit`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/audit/logs` | Paginated audit log with filters |
| GET | `/audit/logs/{entry_uuid}` | Single audit entry |

### 5.12 Analytics (`/analytics`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/analytics/dashboard` | KPI counts, contraband stats, district stats |
| GET | `/analytics/repeat-offenders` | Repeat offender analysis |

### 5.13 Folders (`/folders`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/folders/` | List all FIR folder categories |
| GET | `/folders/counts` | Case count per folder (scoped) |
| GET | `/folders/{slug}/cases` | Cases in a specific folder |
| POST | `/folders/{slug}/cases/{case_id}` | Manually assign case to folder |
| GET | `/folders/workflow/{case_id}` | Workflow execution stages |
| GET | `/folders/persons/single-fir` | Persons with exactly 1 case |
| GET | `/folders/persons/multiple-fir` | Persons with 2+ cases |

### 5.14 FIR Applications (`/fir-applications`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/fir-applications/` | Submit new FIR application form |
| GET | `/fir-applications/{case_id}` | Get application for case |
| PUT | `/fir-applications/{case_id}` | Update draft application |

### 5.15 System (`/system`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/system/backup` | Create database backup snapshot |
| GET | `/system/backups` | List backup files |
| GET | `/system/backups/download/{filename}` | Download backup file |

### 5.16 Download Endpoints (root level)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/health` | System health check |
| GET | `/download/report` | Download Technical Report (.docx) |
| GET | `/download/presentation` | Download Presentation (.pptx) |
| GET | `/download/guide` | Download Architecture & User Guide (.pdf) |

### 5.17 Jurisdictions (`/jurisdictions`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/jurisdictions/districts` | List all AP districts |
| GET | `/jurisdictions/stations/{district}` | List stations in district |

---

## 6. DATABASE SCHEMA & RELATIONSHIPS

### 6.1 All Tables

| Table | Purpose |
|---|---|
| `users` | Officer accounts with role and jurisdiction |
| `refresh_tokens` | JWT refresh token revocation |
| `cases` | FIR case records — core table |
| `case_fields` | Extracted field values per case with confidence |
| `case_legal_sections` | AI-recommended + officer-accepted legal sections |
| `documents` | Uploaded evidence documents (PDF/images) |
| `document_pages` | Per-page OCR text and confidence |
| `document_chunks` | Text chunks for RAG retrieval (500 char, 100 overlap) |
| `entities` | Persons, Vehicles, Locations, Organizations |
| `entity_mentions` | Entity appearances in specific cases |
| `graph_edges` | Entity-entity relationships (CO_ACCUSED, VEHICLE_USED) |
| `legal_corpus` | Verified BNS/IPC/AP Excise Act sections |
| `case_summaries` | AI-generated case summaries (EN/TE/HI) |
| `generated_documents` | Case diary and chargesheet drafts |
| `document_approval_history` | Version history of generated docs |
| `audit_log` | Cryptographic hash-chained action log |
| `bulk_jobs` | Batch import job tracking |
| `fir_folders` | 21 pre-seeded FIR category folders |
| `case_folder_assignments` | Many-to-many: cases ↔ folders |
| `workflow_executions` | Automated post-intake workflow stage tracking |
| `extraction_configs` | AI extraction schema configuration |
| `extraction_runs` | Per-document extraction job records |
| `stations` (optional) | District/station master data |

### 6.2 Key Relationships

```
users ────────────────────────────────────────── creates → cases
                                                         ↓
cases ─── 1:N ──→ case_fields (extracted values, confidence)
       ─── 1:N ──→ case_legal_sections (AI + officer sections)
       ─── 1:N ──→ case_summaries
       ─── 1:N ──→ generated_documents (diary, chargesheet)
       ─── 1:N ──→ entity_mentions
       ─── 1:N ──→ case_folder_assignments
       ─── 1:N ──→ workflow_executions
       ─── 1:N ──→ extraction_runs
       ─── N:1 ──→ documents (via case_id FK on documents)

documents ─── 1:N ──→ document_pages (per-page OCR)
           ─── 1:N ──→ document_chunks (RAG chunks)
           ─── 1:1 ──→ extraction_runs

entities ─── 1:N ──→ entity_mentions (cross-case)
          ─── N:M (via graph_edges) ──→ entities (relationships)

legal_corpus ─── 1:N ──→ case_legal_sections (linked sections)

fir_folders ─── N:M (via case_folder_assignments) ──→ cases
```

### 6.3 Case Lifecycle Status Transitions

```
DRAFT ──→ IN_REVIEW ──→ APPROVED
  ↓                        ↓
ARCHIVED ←────────────────←
```

### 6.4 Document Lifecycle

```
PENDING ──→ PROCESSING ──→ COMPLETED
                  ↓
               FAILED ──→ (retry)
```

### 6.5 Role-Based Data Scoping (apply_case_scope_filter)

| Role | Visible Cases |
|---|---|
| STATION | Cases where district = user.district AND station = user.station |
| DISTRICT | Cases where district = user.district |
| STATE | All cases in the system |

---

## 7. OCR & EXTRACTION PIPELINE

### Stage 1 — File Intake & Validation

- Frontend validates MIME type (PDF, PNG, JPG, TIFF, WebP) and file size (max 50 MB)
- POST to `/api/v1/documents/upload` with multipart form
- Backend: `_detect_mime_type()` verifies actual file header bytes
- SHA-256 hash computed for deduplication
- File stored: Supabase private storage bucket OR local `data/evidence/` directory

### Stage 2 — PDF Text Extraction (Digital PDFs)

- `PDFPipeline.process_pdf()` uses `pypdf.PdfReader`
- Text extracted per page: `page.extract_text()`
- `DocumentPage` records created with `raw_text`, `physical_page_number`
- Page count stored in `Document.physical_page_count`

### Stage 3 — OCR for Scanned/Handwritten Documents

**Provider: Sarvam AI Document Intelligence (Vision 1.5)**

- `SarvamDocAI.digitise_document()`: submits document for full OCR
  - Returns: reading-order blocks, markdown content per page
  - Max 10 pages per job (splits larger documents automatically)
- `SarvamDocAI.extract_document()`: schema-based structured extraction
  - Returns: key-value pairs with confidence scores and source citations
- Jobs polled until COMPLETED/FAILED (terminal states)
- Results stored in `DocumentPage.raw_text` and `ExtractionRun.raw_extracted_json`

**Fallback provider: Google Gemini Vision**
- Used when Sarvam AI is unconfigured or fails
- Gemini vision model reads image/PDF as multimodal input

### Stage 4 — Structured Field Extraction

**Service: `GeminiService.extract_structured_case()`**

- Input: Raw text from OCR/PDF extraction
- Prompt: Strict defensive extraction rules (no assumption of offence type)
- Output: JSON with 16 standard FIR fields:
  - fir_number, year, district, station, mandal, village
  - offence_date, detection_date, registration_date
  - offence_nature, contraband_type, seized_quantity, seized_unit
  - accused_names[], witness_names[], seizing_officer_name
  - vehicle_details, law_sections[], narrative_summary
- `CaseField` records created with `confidence_score` and `extraction_method`
- Null returned for any field not explicitly present in source text

### Stage 5 — Text Chunking & Indexing

- `chunk_text()`: 500-character chunks with 100-character overlap
- `DocumentChunk` records created with `chunk_text`, `char_start`, `char_end`, `physical_page_number`
- SQLite: FTS5 full-text search index populated
- PostgreSQL: Indexed via `pg_trgm` and LIKE patterns
- Embeddings: `DocumentChunk.embedding_json` column exists for future vector search

### Stage 6 — Human-in-the-Loop Review

- Fields with confidence < 0.85 flagged for officer review (reference threshold from HLD)
- Officer views extracted fields in DocumentExtractionWorkspace
- Each field shows: original_value, normalized_value, confidence_score, source page
- VERIFY: marks `verification_status = VERIFIED`
- OVERRIDE: officer enters correct value → `verification_status = OVERRIDDEN`, audit log entry

### Stage 7 — Post-Intake Automation

- `trigger_post_intake_workflow()` runs after case save
- Stage 1: CLASSIFICATION — `classify_case_text()` assigns FIR folder via keyword rules
- Stage 2: ENTITY_EXTRACTION — extracts Person/Vehicle entities (future expansion)
- Stage 3: AI_SUMMARY — generates case summary (triggered on demand)
- Each stage tracked in `workflow_executions` table with PENDING/RUNNING/COMPLETED/FAILED status

---

## 8. AI FIR CHATBOT & RAG PIPELINE

### End-to-End Question Flow

```
1. Officer types question → selects mode + document (if needed)
2. POST /api/v1/rag/query {query, mode, document_id, language}
3. Backend: get_current_user() → validates JWT
4. Mode dispatched to RAGEngine method
5. Document authorization checked (case_id ownership via apply_case_scope_filter)
6. DocumentChunk records retrieved for selected document
7. Hybrid retrieval:
   - SQLite: FTS5 MATCH query
   - PostgreSQL: ILIKE pattern matching across chunks
   - Full document fallback if sparse results
8. Retrieved chunks passed to GeminiService with grounding prompt
9. Gemini generates answer grounded ONLY in provided chunks
10. Response: {answer, citations[{document_name, physical_page, excerpt}]}
11. RAG query logged in audit_log (action_type = RAG_QUERY_EXECUTED)
12. Response returned to frontend
13. Citations rendered as clickable cards linking to PDF viewer
```

### Mode A — Selected FIR Only (PDF_ONLY)

- `RAGEngine.answer_from_active_fir(document_id, query, user, db, language)`
- Strictly isolated to ONE document's chunks
- Citation: physical page number within that document
- In-memory cache: 5-minute TTL keyed by (document_id, query_hash, language)
- Auto-reindexes chunks if missing

### Mode B — Knowledge Base Only (KNOWLEDGE_BASE_ONLY)

- `RAGEngine.answer_from_knowledge_base(query, user, db, language)`
- Searches `document_chunks` where parent document has `doc_category IN (LEGAL_ACT, CIRCULAR, INVESTIGATION_GUIDE, REFERENCE)`
- Jurisdiction-scoped: only documents accessible to user's role
- No case documents included

### Mode C — FIR + Legal Corpus (FIR_PLUS_LEGAL)

- `RAGEngine.answer_fir_plus_legal(document_id, query, user, db, language)`
- Combines Mode A document chunks with `legal_corpus` table sections
- Both sources cited separately in response
- Officers can ask: "Which BNS sections apply to the facts in this FIR?"

### Mode D — Cross-Case Intelligence (CROSS_CASE)

- `RAGEngine.answer_cross_case(query, user, db, language)`
- Searches across ALL case documents within user's authorized jurisdiction
- Useful for: "Have we seen this vehicle registration before?"
- Role-scoped: STATION sees only their station's cases

> **Grounding guarantee:** The Gemini prompt instructs the model: "Answer ONLY from the provided context. If the information is not present, say it was not found. Never invent facts, page numbers, FIR numbers, names, or legal sections."

---

## 9. KNOWLEDGE BASE & LEGAL CORPUS

### Legal Corpus (legal_corpus table)

**Pre-seeded from JSON files at startup:**
- `ap_excise_act_1968.json` — AP Prohibition & Excise Act sections
- `bns_2023.json` — Bharatiya Nyaya Sanhita 2023 sections
- `ipc_historical.json` — IPC sections (historical reference)

**Each entry contains:**
- act_name, section_number, section_title, full_text
- essential_ingredients_json (checklist for prosecution)
- penalty_text, effective_date, repeal_date
- source_url, source_gazette (authoritative provenance)
- verification_status = VERIFIED

### Knowledge Base Documents

- Uploaded via `/knowledge-base` page or `/api/v1/legal/kb/upload`
- Document categories: LEGAL_ACT, CIRCULAR, INVESTIGATION_GUIDE, REFERENCE
- After upload: same pipeline as evidence documents (OCR → chunks → indexed)
- Status must be COMPLETED before chatbot can retrieve content
- Re-index option for FAILED documents

---

## 10. INVESTIGATION TOOLS

### Entity Resolution

**Implemented:**
- Entities extracted during case processing (PERSON, VEHICLE, LOCATION, ORGANIZATION)
- `entity_resolution.py` service: deduplication by name similarity
- Aliases stored in `aliases_json` for variant spellings (e.g., "Ramaiah" / "Ramaiya")
- Merge workflow: duplicate → REVIEW_PENDING → officer merges → merged_into_id set
- Risk score computed based on number of case mentions

**Planned/Partial:**
- Transliteration-based matching across Telugu/Hindi/English names
- Automated phonetic deduplication (Soundex/Metaphone)

### Network Graph

**Implemented:**
- Force-directed graph visualization (NetworkGraph component)
- Node types: PERSON (circle), VEHICLE (square), LOCATION (diamond)
- Edge types: CO_ACCUSED, VEHICLE_USED, ASSOCIATE
- Community IDs (Louvain algorithm output stored in `community_id` column)

**Planned:**
- Live community detection calculation
- Centrality scoring visualization

### Repeat Offender Detection

**Implemented:**
- Persons View (`/folders/persons/multiple-fir`) lists entities appearing in 2+ cases
- `GET /api/v1/analytics/repeat-offenders` returns analysis
- Risk factors listed (number of cases, roles — ACCUSED, ASSOCIATE)

**CRITICAL WARNING:** Similar names or vehicle numbers appearing in multiple cases are advisory indicators only. They must never be treated as proof of identity or guilt without full officer investigation and verification.

---

## 11. END-TO-END SIX-STAGE WORKFLOW

### Example Case: Illicit Distillation FIR — Kurnool District

**Stage 1 — Evidence Upload & Extraction**

1. Officer opens New Case Intake (`/intake`)
2. Uploads scanned FIR PDF: `FIR_2024_KNL_001.pdf`
3. System stores file → creates Document record (PENDING)
4. PDFPipeline runs → text extracted per page
5. Sarvam AI OCR digitises handwritten sections
6. Gemini extracts: FIR Number, Accused Names, Contraband, Quantity, Sections
7. Document status → COMPLETED
8. Officer opens DocumentExtractionWorkspace
9. Reviews extracted fields, verifies accurate ones, overrides errors
10. Case created: `status = DRAFT`

**Stage 2 — Officer Review & Sign-Off**

1. Officer navigates to Case Management → case appears in DRAFT queue
2. Opens Case Detail
3. Reviews all extracted fields and confidence scores
4. Verifies entity records (accused names, vehicle numbers)
5. Reviews AI-suggested legal sections (AP Excise Act §34(a), BNS §304)
6. ACCEPTS applicable sections, REJECTS inapplicable ones
7. Submits for supervisor review: `status → IN_REVIEW`

**Stage 3 — AI & Legal Intelligence**

1. Supervisor opens case in Legal Intelligence (`/legal`)
2. Reviews AI-recommended sections with matched facts
3. Checks essential ingredients checklist
4. Accepts final legal sections
5. Generates AI Case Summary (EN/TE/HI as needed)
6. Reviews chatbot response to "What quantity of illicit liquor was seized and where?" (Mode A)

**Stage 4 — Investigation Tools**

1. Opens Entity Network (`/network`)
2. Sees accused person linked to 1 prior case (VEHICLE_USED edge)
3. Officer notes advisory match — initiates manual verification
4. Confirms entity identity through official records
5. Updates entity verification_status to CONFIRMED

**Stage 5 — Administration & Existing FIRs**

1. Supervisor approves case: `status → APPROVED`
2. Case diary generated and approved
3. Chargesheet generated with all accepted legal sections
4. Chargesheet exported as DOCX for court filing
5. All actions recorded in cryptographic audit_log

**Stage 6 — Repeat Offender Intelligence** *(advisory only)*

1. Monthly review: open Persons View → Multiple-FIR
2. Accused "Raju S/o Lakshmaiah" appears in 3 cases across 2 years
3. Risk score: 0.74 (based on frequency and recency)
4. Officers review all 3 cases for investigative patterns
5. Repeat-offender status: ADVISORY — requires officer verification before any official action

---

## 12. SECURITY, ROLES & AUDIT

### Authentication

- JWT HS256 tokens (access: 120 min, refresh: 7 days)
- Argon2id password hashing (OWASP recommended)
- Refresh token revocation on logout stored in `refresh_tokens` table
- `is_revoked` flag prevents reuse of revoked tokens
- All routes protected by `Depends(get_current_user)`

### Role-Based Access Control

| Role | Scope | Capabilities |
|---|---|---|
| STATION | Own station cases only | Create, upload, extract, verify, review |
| DISTRICT | All cases in district | All STATION actions + Approve, District reports |
| STATE | All cases system-wide | All actions + Employee management, system config |

### Jurisdiction Enforcement

- `apply_case_scope_filter()` applied on every case list query
- STATION: `WHERE district = ? AND station = ?`
- DISTRICT: `WHERE district = ?`
- STATE: No filter (sees all)
- Cannot be bypassed by URL manipulation — enforced at DB query level

### Audit Logging

- Every significant action logged in `audit_log`
- SHA-256 hash chain: `entry_hash = SHA256(previous_hash + canonical_content)`
- Genesis hash: 64 zeros
- Tampering with any entry breaks the subsequent hash chain
- Logged actions include: CASE_CREATED, FIELD_OVERRIDE, SECTION_ACCEPTED, SECTION_REJECTED, RAG_QUERY_EXECUTED, CASE_APPROVED, DOCUMENT_ARCHIVED, ENTITY_MERGED

### Secure File Access

- Supabase: Private bucket (not publicly accessible)
- Signed URLs generated server-side with 1-hour expiry
- Local fallback: Files served through authenticated FastAPI endpoint only
- SHA-256 hash stored per document for integrity verification

---

## 13. TROUBLESHOOTING GUIDE

| Error | Possible Cause | Resolution |
|---|---|---|
| Login fails (401) | Wrong credentials, account inactive | Verify username/password; check approval_status in users table |
| Upload fails (413) | File too large (>50 MB) | Compress or split document |
| Upload fails (415) | Unsupported file type | Use PDF, PNG, JPG, TIFF, or WebP |
| OCR fails | Sarvam AI key missing or expired | Check SARVAM_API_KEY in .env; system falls back to Gemini |
| Extraction returns nulls | Gemini API key missing or quota exceeded | Check GEMINI_API_KEY; system uses rule-based fallback |
| Document stuck in PROCESSING | OCR job timeout | Re-upload document; check Sarvam API status |
| Historical FIR not found | document_id not selected in chatbot | Select document from dropdown in Mode A |
| Chatbot no answer | Chunks not indexed | Check document status = COMPLETED; use re-index option |
| Evidence image broken | Signed URL expired | Refresh page; backend generates new signed URL |
| Permission denied (403) | Role insufficient for action | Check user role; contact district/state admin |
| Database error | Supabase connection issue | Check SUPABASE_DATABASE_URL; system falls back to SQLite |
| PDF download fails (404) | PDF file not generated yet | Generate document first; check status = APPROVED |
| Case count mismatch | KPI cache stale (60s TTL) | Wait 60 seconds or restart backend |
| Incorrect citation | Chunks from different document in results | Verify document_id in chatbot selector |

---

## 14. TESTING & DEPLOYMENT

### Running Locally

**Backend:**
```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

**Demo Accounts:**
| Username | Password | Role |
|---|---|---|
| developer_test | DevPass@2024 | STATE |
| state_director | StateAdmin@2024 | STATE |
| district_admin | DistrictPass@2024 | DISTRICT — Kurnool |
| station_officer | StationPass@2024 | STATION — Kurnool Town |

### Environment Variables (.env)

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_DATABASE_URL=postgresql://postgres:password@db.project.supabase.co:5432/postgres
SUPABASE_STORAGE_BUCKET=evidence
GEMINI_API_KEY=your-gemini-api-key
SARVAM_API_KEY=your-sarvam-api-key
```

### Build for Production

```bash
cd frontend
npm run build  # Generates dist/ directory
```

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 15. GLOSSARY

| Term | Definition |
|---|---|
| BNS | Bharatiya Nyaya Sanhita 2023 — new criminal code replacing IPC |
| IPC | Indian Penal Code (historical — superseded by BNS) |
| FIR | First Information Report — initial police/excise complaint |
| NDPS | Narcotic Drugs and Psychotropic Substances Act |
| OCR | Optical Character Recognition |
| RAG | Retrieval-Augmented Generation — AI answers grounded in source documents |
| FTS5 | SQLite Full-Text Search version 5 |
| RLS | Row Level Security (Supabase/PostgreSQL) |
| IO | Investigating Officer |
| HITL | Human-in-the-Loop — officer verification step |
| Chunk | 500-character segment of extracted text used for RAG retrieval |
| Canonical Entity | The primary record after deduplication of entity aliases |
| Signed URL | Time-limited authenticated URL for accessing private stored files |
| JWT | JSON Web Token — authentication credential |
| SHA-256 | Cryptographic hash algorithm used for file integrity and audit chaining |
| AP Excise | Andhra Pradesh Prohibition & Excise Department |
| Sarvam AI | Indian AI company providing document OCR/extraction API |
| Gemini | Google's multimodal AI model used for extraction and generation |

---

*Document generated from verified source code inspection of FIR Sahayak u-FIR v2.0.*  
*Reference HLD: Multilingual Handwritten FIR Extraction Engine (Google Docs).*  
*Features labelled "Planned" are not yet fully implemented in the codebase.*
