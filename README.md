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
├── start_backend.ps1         # One-click backend start
├── start_frontend.ps1        # One-click frontend start
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

### 1. Start the Backend

Open a PowerShell terminal and run:

```powershell
cd C:\Users\LENOVO\Desktop\FIR-Sahayak
.\start_backend.ps1
```

Backend starts at **http://localhost:8000**
- Interactive API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### 2. Start the Frontend

Open a **second** PowerShell terminal and run:

```powershell
cd C:\Users\LENOVO\Desktop\FIR-Sahayak
.\start_frontend.ps1
```

Frontend starts at **http://localhost:5173**

### 3. Run Tests

```powershell
.\run_tests.ps1
# Expected: 10 passed, 0 failed
```

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

**Current model:** `gemini-2.0-flash` (configurable via `.env`)

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
| `GEMINI_TEXT_MODEL` | Gemini model identifier | `gemini-2.0-flash` |
| `DATABASE_URL` | SQLite async URL | Local path |
| `DEMO_MODE` | Enable synthetic data labelling | `true` |

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
