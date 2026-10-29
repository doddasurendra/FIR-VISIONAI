# FIR VisionAI — AI-Enabled Unified First Information Report Platform

> **Hackathon Demo System** — Built for the Andhra Pradesh Excise & Prohibition Department.
> All case records included are **synthetic demonstration data only**. Not officially government-integrated or production-certified.

---

## 📋 Overview

**FIR Sahayak** (FIR Helper) is a full-stack AI-powered case intelligence platform for managing First Information Reports (FIRs), supporting multilingual operations (English, Telugu, Hindi), PDF-grounded RAG answers with physical page citations, entity resolution, legal section matching, and tamper-evident audit trails.

### Core Capabilities

| Module | Description |
|---|---|
| 📁 Case Management | CRUD, field provenance, human verification |
| 🤖 AI FIR Assistance | PDF-Only Grounded RAG (Section 26) with exact page citations |
| ⚖️ Legal Section Assistant | Case facts → legal section candidate matching (Section 27) |
| 🕸️ Entity Network | Interactive vis-network graph + deduplication review queue |
| 📝 Document Generator | Case diary, chargesheet, case summary drafts |
| 📦 Bulk Ingestion | CSV/JSON/PDF import with AI extraction |
| 🔍 Audit Trail | SHA-256 tamper-evident hash chain (Section 15) |
| 📊 Reports & Analytics | District/state-level dashboards |

---

## 🏗️ Architecture

```
FIR-Sahayak/
├── backend/                  # Python FastAPI backend
│   ├── app/
│   │   ├── api/v1/           # REST routers (12 modules)
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic v2 schemas
│   │   ├── services/         # Business logic & AI services
│   │   │   ├── gemini.py         # Gemini API adapter + fallback
│   │   │   ├── rag_engine.py     # Section 26: PDF-Only RAG
│   │   │   ├── legal_service.py  # Section 27: Legal matching
│   │   │   ├── audit.py          # Section 15: Hash chain
│   │   │   └── entity_resolution.py  # Component 4: Dedup
│   │   ├── config.py         # Pydantic-settings configuration
│   │   ├── database.py       # SQLite + FTS5 async engine
│   │   └── main.py           # FastAPI app + lifespan seeding
│   ├── tests/
│   │   └── test_backend.py   # 10/10 pytest suite
│   └── requirements.txt
├── frontend/                 # React 18 + TypeScript + Vite
│   ├── src/
│   │   ├── pages/            # 16 page components
│   │   ├── components/       # Layout, PDF viewer, network graph
│   │   ├── context/          # Auth + Language contexts
│   │   ├── i18n/             # English, Telugu, Hindi translations
│   │   └── api/client.ts     # Axios + JWT interceptor
│   └── dist/                 # Production build output
├── corpus/                   # Legal corpus (JSON)
│   ├── ap_excise_act_1968.json
│   ├── bns_2023.json
│   └── ipc_historical.json
├── data/
│   ├── fir_sahayak.db        # SQLite database (demo data)
│   ├── evidence/             # Uploaded FIR PDFs
│   ├── exports/              # Generated documents
│   └── backups/
├── scripts/                  # Seed & utility scripts
├── .env                      # Local environment (not committed)
├── .env.example              # Safe template
├── start_all.bat / .ps1      # Start backend + frontend, wait until both are verified
├── start_backend.ps1         # Backend only (window "FIR VisionAI Backend")
├── start_frontend.ps1        # Frontend only (window "FIR VisionAI Frontend")
├── stop_all.ps1              # Stop this folder's dev servers (nothing else)
├── diagnose.bat / .ps1       # Read-only health check when localhost fails
├── logs/                     # backend.log, frontend.log (not committed)
└── run_tests.ps1             # Run full test suite
```

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12+ | `C:\...\Python312\python.exe` |
| Node.js | 18+ | Portable at `C:\...\PortableTools\node\` |
| Git | Any | `C:\...\PortableTools\git\` |

### 1. Start FIR VisionAI (Windows)

Double-click **`start_all.bat`** in the project folder, or in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_all.ps1
```

It opens two windows — **FIR VisionAI Backend** and **FIR VisionAI Frontend** — waits until both really
answer, checks the database (Supabase or SQLite) and storage, checks that the frontend can reach the backend,
and only then prints `FIR VisionAI is running and verified` and opens **http://localhost:5173**.

- Already-running healthy servers are reused, never started twice.
- If port 8000 is used by **another program**, that program is left alone and the backend starts on the
  next free port (8001, 8002, …); the frontend is pointed at it automatically. The summary shows the port.
- If something fails, the script says what, shows the end of the log and exits with an error.
- Keep both windows open. Closing a window stops that server; the window prints a red **STOPPED** banner if
  its server exits on its own.
- First run on a fresh clone: copy `.env.example` to `.env` and fill it in. Missing frontend packages are
  installed automatically (`npm ci`).

Health endpoints (on the backend port shown in the summary, or through the frontend):
- `http://localhost:5173/api/v1/health` — the backend process is up
- `http://localhost:5173/api/v1/health/ready` — database and storage actually answer (HTTP 503 if not)
- API docs: `http://localhost:<backend port>/docs`

### 2. If localhost "refused to connect" (ERR_CONNECTION_REFUSED)

That message means no server is listening — usually because the PC restarted or a server window was closed.

1. Find out what is wrong (read-only, changes nothing): double-click **`diagnose.bat`**, or
   `powershell -ExecutionPolicy Bypass -File .\diagnose.ps1`
2. Start whatever is missing: **`start_all.bat`**
3. If a server is stuck or the ports no longer match:
   `powershell -ExecutionPolicy Bypass -File .\start_all.ps1 -Restart`
   (stops only this folder's FIR VisionAI servers, verified by command line, then starts fresh)

Logs: `logs\backend.log` and `logs\frontend.log` (the previous run is kept as `*.log.previous`).
To stop everything: `powershell -ExecutionPolicy Bypass -File .\stop_all.ps1`.

### 3. Run Tests

```powershell
.\run_tests.ps1
```

The suite runs against a temporary SQLite database with all cloud and AI keys blanked, so it never
writes to the live Supabase database or storage.

Frontend checks (also run by CI, `.github/workflows/ci.yml`, on every push and pull request):

```powershell
cd frontend
npm run lint        # ESLint (errors fail; warnings are reported)
npm run typecheck   # tsc --noEmit
npm run build
```

Checks against the running app (read-only; install `backend/requirements-dev.txt` and
`python -m playwright install chromium` first):

```powershell
python scripts\dev\endpoint_sweep.py     # every GET /api/v1 endpoint as STATION, DISTRICT and STATE
python scripts\dev\page_check.py --user state_director --password StateAdmin@2024 "/" "/reports"
```

### 4. Database migrations (Supabase / PostgreSQL)

Locally the SQLite schema is created from the SQLAlchemy models. Schema changes for Supabase are
versioned SQL files in `supabase/migrations/` (named `YYYYMMDDHHMMSS_description.sql`), applied in
order with the role that owns the tables:

```powershell
cd backend
# 1. Back up the tables the migration touches (Supabase dashboard backup or pg_dump of those tables)
# 2. Rehearse: runs in a transaction and rolls back
python scripts\apply_sql_migration.py --env-file ..\.env --file ..\supabase\migrations\<file>.sql --dry-run
# 3. Apply
python scripts\apply_sql_migration.py --env-file ..\.env --file ..\supabase\migrations\<file>.sql
# 4. Confirm models, SQLite schema and Supabase agree and RLS is on for every table (exit 1 on a mismatch)
python scripts\check_schema_sync.py
```

Every new table must enable row-level security (`alter table ... enable row level security;`).
When a migration changes a column, change the matching model too so the SQLite schema stays in sync.

**v2.1.0 migrations and data corrections** (apply in this order):

| Migration | Adds |
|---|---|
| `20261028100000_legal_ipc_bns_mapping.sql` | `ipc_bns_mapping` table (IPC→BNS correspondence, RLS on), legal-corpus lookup index |
| `20261028110000_extraction_quality_and_station_district.sql` | `extraction_quality_flags` table (RLS on); trigger: a station in `verified_stations` must carry its district |

```powershell
cd backend
python scripts\fix_all_fulfilled.py --backup            # JSON backup of every affected table into BACKUPS_DIR
python scripts\fix_all_fulfilled.py                     # dry run: every change and the row counts per table
python scripts\fix_all_fulfilled.py --apply             # strip picture descriptions, archive test fixtures, move
                                                        # circulars to the Knowledge Base, re-OCR, re-index,
                                                        # re-extract 178/2024 + FIR-2024-EXC-IMAGE-01, correct
                                                        # districts/contraband/officers, legal corpus, quality
                                                        # check, summaries (EN/TE/HI). Every change is audit-logged.
python scripts\import_legal_corpus_v2.py [--apply]      # legal corpus only
python scripts\regenerate_stale_summaries.py [--apply] [--include-pending]   # summaries only
```

### 5. Extraction quality check

Flags any case whose stored fields contradict its FIR text: offence date, place, offence nature, legal
sections, contraband, vehicle, an application user stored as officer, and a district that does not match the
station master list. Flags are stored in `extraction_quality_flags` (open / resolved on the next run).

- On demand (jurisdiction-scoped, audit-logged): `POST /api/v1/extraction/quality-check` (all cases the officer
  may see, or `?case_id=`), results at `GET /api/v1/extraction/quality-flags`.
- Nightly: set `EXTRACTION_QC_NIGHTLY=true` (runs at `EXTRACTION_QC_HOUR`, local time, default 02:00).

### What changed in v2.1.0

- **Records → structured data:** OCR transcribes only page text (never describes logos or photos), retries with
  backoff, re-reads an enhanced (deskewed, contrast-stretched, upscaled) image, renders PDFs at 300/400 DPI and
  falls back to the second engine (Sarvam Digitise) in 10-page batches. Placeholder text never counts as
  readable; unreadable documents carry a specific reason (`OCR_QUOTA`, `OCR_NO_TEXT`, ...).
- **Extraction:** a deterministic FIR-form reader (date/time, place, complainant, accused, IPC/BNS/IT/NDPS/Arms/MV/
  Excise sections, contraband, vehicle) backs the model; vehicles are linked by registration number; contraband is
  "Not applicable" for non-seizure cases; a station's district must match the station master list.
- **Legal:** a section is suggested only when its key ingredients are supported; IPC→BNS mapping table; IT Act,
  NDPS, Arms and MV Act provisions; sections of other Acts recorded in the FIR are shown; Gazette headers and
  page furniture are removed from official text; one consistent ingredient verdict per section.
- **Summaries:** dates, numbers, names and section numbers are protected tokens in Telugu and Hindi.
- **Consistency:** the case diary's investigating officer comes from the FIR (station SHO fallback); hotspots and
  the case page share one location rule (approximate points are marked); chatbot answers read accused from
  the case records.

---

## 🔐 Development & Demonstration Test Accounts

> All accounts use **synthetic demonstration identities only**. Passwords are encrypted with Argon2id.

| Role | Username | Password | Access Scope | Description |
|---|---|---|---|---|
| 🛠️ Dev / Admin | `developer_test` | `DevPass@2024` | Statewide (All AP Districts) | Principal Systems Engineer / Technical Lead |
| 🏛️ State Director | `state_director` | `StateAdmin@2024` | Statewide (All AP Districts) | Commissioner of Prohibition & Excise |
| 🏢 District Admin | `district_admin` | `DistrictPass@2024` | Kurnool District (All Stations) | Superintendent of Excise |
| 🚔 Station Officer | `station_officer` | `StationPass@2024` | Kurnool Town Station Only | Excise Sub-Inspector |

### 📝 Self-Registration & Approval Workflow

- **Station Officers:** Self-registration is automatically approved and activated for development & testing.
- **District Admins & State Directors:** Self-registration creates a `PENDING_APPROVAL` account. An administrator must approve the account from the **Employee Management** console before login is permitted.
- **Master Data Integration:** Self-registration uses dependent dropdowns mapped to all **26 official Andhra Pradesh districts** and verified departmental Excise Stations. Arbitrary jurisdictions cannot be entered.

---

## 📂 Demo Cases (Synthetic)

| FIR Number | District | Station | Accused | Status |
|---|---|---|---|---|
| FIR-2024-KNL-0042 | Kurnool | Kurnool-1 | Raju Yadav | Under Investigation |
| FIR-2024-KNL-0019 | Kurnool | Kurnool-1 | Suresh Kumar | Chargesheeted |
| FIR-2024-GNT-0088 | Guntur | Guntur-2 | Mohammed Farooq | Under Investigation |
| FIR-2023-VSP-0112 | Visakhapatnam | VSP-Central | Lakshmi Devi | Closed |

---

## 🤖 AI Integration

### Model Configuration

The Gemini API is used for:
- Structured extraction from scanned documents
- PDF-Only Grounded RAG answers (Section 26)
- Legal section candidate matching (Section 27)
- Draft generation (case diary, chargesheet)

**Current model:** `GEMINI_TEXT_MODEL` in `.env` (currently `gemini-3-flash-preview`), with `gemini-flash-lite-latest` as the fallback.

### AI FIR Assistant (chatbot): speed, grounding and failures

- **Selected FIR:** a short record (up to 16 passages) is read in full, in page order; it is not searched again.
  Answers must cite `[S#]` passages; uncited model replies are discarded. The citation names the document and
  page (image FIRs are cited as "Image evidence").
- **Time budget:** answering gets 7 s (sign-in and the audit entry add 1–3 s over a slow link). The AI call runs
  off the server's event loop, so a slow model never stalls other users.
- **When the AI is unavailable** (timeout, quota, overload): the officer gets the exact matching passages, or a
  plain statement that the AI is unavailable and no passage matches. The officer never gets a guess or a
  "not found" that blames the documents. These answers show **Try again** and are not cached.
- **Quota:** a daily-quota error puts the model aside until its quota resets (as reported by the API). A model that
  times out is skipped for 2 minutes. A free-tier key allows about **20 answers per day** for
  `gemini-3-flash-preview`; enable billing on the key for regular use.
- **Tracing:** every answer carries `trace_id` and per-stage `timings`. The matching line in `logs\backend.log` is
  `RAG trace=<id> ... total_ms=... stages={...}`, with no question or document text. Answers over 10 s are logged as `SLOW`.
- **Monitoring:** `GET /api/v1/health/ready` → `chat` shows recent average/p95 latency, slow and AI-unavailable
  counts, and models in cooldown.
- **Database drops:** a lost connection during the audit write is retried once. Otherwise the reply is
  HTTP 503 with a reference, never an unexplained 500 (this was error `0127eb95`).

### Deterministic Fallback

All AI features have a **complete deterministic fallback** — the system works fully without any API connection. The fallback produces structured, clearly-labelled synthetic responses so demo functionality is never blocked by API availability.

---

## 🔒 Security Architecture

### Authentication
- Argon2id password hashing
- Short-lived JWT access tokens (15 min)
- Secure refresh tokens with random `jti` claim (7 days)
- Role-based data scoping enforced server-side

### Data Scoping (Role Hierarchy)
```
STATE  → sees all districts and stations
  └── DISTRICT → sees only their district
        └── STATION → sees only their station
```

### Audit Trail (Section 15)
- Every write operation logged with SHA-256 hash
- Each audit entry links to the previous entry's hash
- Chain verified at runtime: `SECURE_AND_VERIFIED` / `TAMPERED`

---

## ✅ Test Coverage

```
tests/test_backend.py — 10/10 PASSING

test_health_check                              ✅
test_station_role_data_scoping                 ✅  (sees only 2 Kurnool cases)
test_state_role_sees_all_cases                 ✅  (sees all 4 cases)
test_field_override_persists                   ✅  (DB write verified)
test_pdf_only_grounded_rag_with_citations      ✅  (Section 26: Page 2 citation)
test_pdf_only_missing_information_...phrase    ✅  (Section 26: mandatory English phrase)
test_pdf_only_telugu_missing_phrase            ✅  (Section 26: mandatory Telugu phrase)
test_legal_section_recommendation_...regime   ✅  (Section 27: BNS vs IPC date routing)
test_audit_hash_chain_integrity                ✅  (Section 15: SECURE_AND_VERIFIED)
test_network_graph_generation                  ✅  (nodes & edges returned)
```

---

## 🌐 API Reference

Base URL: `http://localhost:8000/api/v1/`

| Endpoint | Method | Description |
|---|---|---|
| `/auth/login` | POST | JWT login |
| `/auth/refresh` | POST | Refresh access token |
| `/cases/` | GET/POST | List / create cases |
| `/cases/{id}` | GET/PATCH/DELETE | Case detail |
| `/cases/{id}/fields/{fid}/verify` | PATCH | Verify extracted field |
| `/documents/upload` | POST | Upload FIR PDF |
| `/rag/pdf-only` | POST | Section 26: PDF-Only RAG |
| `/legal/match-sections` | POST | Section 27: Legal matching |
| `/entities/network/{case_id}` | GET | Entity graph |
| `/entities/review-queue` | GET | Duplicate review queue |
| `/generation/case-diary` | POST | Generate case diary draft |
| `/generation/chargesheet` | POST | Generate chargesheet draft |
| `/audit/` | GET | Audit log |
| `/audit/verify-chain` | GET | Hash chain integrity |
| `/bulk/ingest` | POST | Bulk CSV/JSON/PDF import |
| `/analytics/overview` | GET | Dashboard stats |
| `/employees/` | GET/POST | Employee management |

Full interactive docs at: **http://localhost:8000/docs**

---

## 🌍 Multilingual Support

Supported languages: **English (en)**, **Telugu (te)**, **Hindi (hi)**

- Language selector in the header
- All UI labels translated via `i18n/translations.ts`
- RAG answers and mandatory phrases return in the requested language
- Telugu font: Noto Sans Telugu (loaded via Google Fonts)

---

## 🔄 Source Code Sync (Git Workflow)

```powershell
# Check status
git -C "C:\Users\LENOVO\Desktop\FIR-Sahayak" status

# Commit changes
git -C "C:\Users\LENOVO\Desktop\FIR-Sahayak" add -A
git -C "C:\Users\LENOVO\Desktop\FIR-Sahayak" commit -m "feat: describe your change"

# Push to GitHub
git -C "C:\Users\LENOVO\Desktop\FIR-Sahayak" push origin main
```

> **Never commit** `.env`, `fir_sahayak.db`, evidence files, or any real case data.
> The `.gitignore` already excludes all of the above.

---

## 📦 Environment Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | JWT signing key | Change in production! |
| `GEMINI_API_KEY` | Google Gemini API key | Required for live AI |
| `GEMINI_TEXT_MODEL` | Gemini model identifier | `gemini-3-flash-preview` |
| `GEMINI_EMBEDDING_MODEL` | Embedding model | `gemini-embedding-001` |
| `GEMINI_BACKUP_MODEL` | Optional second model tried when the main one fails or its quota is used up | empty |
| `GEMINI_BACKUP_API_KEY` | Optional key for the backup model (another project's quota); empty = same key | empty |
| `SUPABASE_DATABASE_URL` | PostgreSQL URL of the live database (keep it only in `.env`) | empty = SQLite |
| `DATABASE_URL` | SQLite async URL | Local path |
| `DEMO_MODE` | Enable synthetic data labelling | `true` |
| `SARVAM_API_KEY` | Second OCR engine (Sarvam Digitise), used when the primary OCR reads nothing | empty = off |
| `EXTRACTION_QC_NIGHTLY` | Run the extraction quality check every night | `false` |
| `EXTRACTION_QC_HOUR` | Local hour of the nightly quality check | `2` |

---

## ⚠️ Disclaimer

This system is a **hackathon demonstration prototype**. It:
- Contains **synthetic demonstration data only** — no real case records
- Is **not officially government-integrated** or legally approved
- Is **not production-certified** or audited for government deployment
- Makes **no accuracy guarantees** on AI predictions

For actual departmental deployment, all AI outputs must be verified by authorized officers, and the system must undergo government security and compliance review.

---

## 📄 License

MIT — See [LICENSE](LICENSE) for details.

Built for the AP Excise & Prohibition Department Hackathon 2024.
