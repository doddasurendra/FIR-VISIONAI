# Knowledge Base & AI Assistant: Operations Guide

How documents get into FIR VisionAI, how they become searchable, and how to add or update official legal sources.

## 1. How a document becomes searchable

Every upload, retry and import goes through the same pipeline (`backend/app/services/ingestion.py`):

1. **Validate**: file type and size (50 MB), empty or corrupt files, duplicates (same SHA-256).
2. **Extract text**: PDFs page by page (pypdf, then pdfplumber, then OCR of the rendered page); DOCX; TXT; images by OCR (Gemini, then Sarvam if configured). Garbled legacy-font Hindi lines found in official Gazette PDFs are dropped.
3. **Chunk**: passages of up to about 1,100 characters that never cross a page, so every citation names an exact page. In laws, each passage also carries its Section/Article/Rule (for example *BNS Section 303*).
4. **Embed**: semantic vectors with the configured Gemini embedding model (768 dimensions).
5. **Index**: full-text (SQLite FTS5 locally; PostgreSQL `tsvector` + GIN on Supabase) and vectors (pgvector HNSW on Supabase).
6. **Verify**: a real test search must find the document before it is marked searchable.

### Status meanings

| Status | Meaning | Searchable? |
|---|---|---|
| Processing | Pipeline running | No |
| Stalled | Processing stopped more than 15 minutes ago without finishing (e.g. server restart) | No (retry) |
| Indexed | Text extracted, indexed and verified | Yes |
| Partially indexed | Some pages unreadable, or embeddings could not be generated (keyword search still works) | Yes |
| Needs review | No readable text at all (OCR unavailable or failed). No placeholder text is stored | No (retry once OCR works) |
| Failed | Corrupt/unsupported file, or index verification failed; the error is shown | No (fix and retry) |

Use **Retry** in the Knowledge Base (or the document's detail panel): *Re-extract from original file* runs the whole pipeline again; *Rebuild index from stored text* re-chunks and re-embeds without OCR.

## 2. Source labels

| Label | Use for |
|---|---|
| **Official source** | Text obtained from an official government portal (Gazette of India, Legislative Department, India Code, AP Government). Requires the official URL. Only STATE users can apply it. |
| Secondary | Training material, commentaries, explanatory notes |
| Synthetic / demo | Sample or test data. Never a government record |
| Unverified | Anything whose provenance has not been checked (default) |

FIRs and evidence can also be marked **Actual**, **Redacted** or **Synthetic** records.

## 3. Adding or updating an official legal document

1. **Find the official file** on an official portal. Do not use third-party copies. Note the Act/notification number, issuing authority, publication and commencement dates, and whether it is in force, amended or repealed.
2. **Add an entry** to `corpus/official_sources.json`:
   ```json
   {
     "id": "ap_excise_1968",
     "status": "VERIFIED_SOURCE",
     "title": "The Andhra Pradesh Excise Act, 1968 (Act No. 17 of 1968)",
     "act_name": "Andhra Pradesh Excise Act, 1968",
     "category": "LEGAL_ACT",
     "legal_corpus_category": "STATE_EXCISE_PROHIBITION",
     "reference_number": "Andhra Pradesh Act No. 17 of 1968",
     "jurisdiction": "Andhra Pradesh",
     "issuing_authority": "...",
     "publication_date": "1968-08-29",
     "commencement_date": null,
     "legal_status": "AMENDED",
     "language": "en",
     "source_url": "https://<official page>",
     "download_url": "https://<official PDF>",
     "verification_note": "What the file covers and what it does not (e.g. later amendments).",
     "expect_text": ["EXCISE"]
   }
   ```
   `expect_text` lists phrases that must appear in the first pages; a wrong file is rejected.
3. **Import** (from `backend/`):
   ```powershell
   # Local database (SQLite)
   python scripts/import_official_documents.py --only ap_excise_1968
   # Live Supabase: use the backend's env file (credentials are never printed)
   python scripts/import_official_documents.py --env-file ..\..\.env --only ap_excise_1968
   # If the portal is slow, download the file in a browser and pass it directly
   python scripts/import_official_documents.py --env-file ..\..\.env --file ap_excise_1968=C:\path\file.pdf
   ```
   The importer verifies the file, stores it in the private `evidence` bucket, ingests it, and creates one `legal_corpus` row per parsed Section/Article with its page number. Re-running skips files already imported (same SHA-256); `--refresh` re-ingests them.
4. **Check** the document in the Knowledge Base: status *Indexed*, the expected page count, and its sections in the detail panel. Then ask the assistant a question about a known section and confirm the cited page.

**New version of a law:** import it as a new entry (new `id`), then mark the old document's legal status as *Superseded* or archive it with the reason. The assistant always shows each citation's source label and legal status.

### Sources still pending

`ndps_1985`, `ap_excise_1968` and `ap_act_17_1995` are listed with status `PENDING_DOWNLOAD` because India Code returned HTTP 504 during the October 2026 import. Retry with:
```powershell
python scripts/import_official_documents.py --env-file ..\..\.env --include-pending
```
Confirm their titles, status and consolidation date from the downloaded files before relying on them.

## 4. Assistant search scopes

| Scope | Searches |
|---|---|
| Current FIR | The selected document only |
| Case + evidence | All searchable documents of the selected FIR's case |
| FIR + Law | The selected FIR and the legal corpus; legal answers separate *what the FIR states*, *what the law states*, and *suggestions for review* |
| Knowledge Base | Authorised Knowledge Base documents (optionally one category) |
| All authorised | Everything searchable in the officer's jurisdiction |

If the answer is not in the selected scope the assistant replies *"I could not find sufficient supporting information in the selected FIR VisionAI documents to answer this question."* and offers a wider scope. Without a working Gemini key it quotes the matching passages instead of summarising them, and says so.

## 5. Configuration

| Setting | Notes |
|---|---|
| `GEMINI_API_KEY` | Required for OCR, AI answers, Telugu/Hindi query translation and embeddings |
| `GEMINI_EMBEDDING_MODEL` | Use `gemini-embedding-001`. `text-embedding-004` has been retired (HTTP 404); the app falls back automatically and logs a warning |
| `SARVAM_API_KEY` | Optional second OCR/extraction provider |

Vectors from different embedding models are never compared; after changing the model, use *Rebuild index from stored text* on documents that should use semantic search.

### Filling in missing embeddings

Documents indexed without embeddings (no key, retired model, or quota exhausted) are *Partially indexed* and still searchable by keywords. Add the vectors later with:
```powershell
python scripts/backfill_embeddings.py --env-file ..\..\.env --max-chunks 900 --official-first
```
The Gemini free tier allows about 100 embeddings per minute and about 1,000 per day; the script waits out per-minute limits, commits after every batch, stops cleanly at the daily limit, and continues where it left off when run again. A document becomes *Indexed* once every passage has a vector.

## 6. Database migrations (Supabase)

The application tables are owned by the backend's database user, not by Supabase's `postgres` role, so migrations come in two kinds:

| File | Run as | How |
|---|---|---|
| `supabase/migrations/20261025120000_kb_rag_extensions.sql` | `postgres` | Supabase SQL editor |
| `supabase/migrations/20261025120100_knowledge_base_rag_upgrade.sql` | table owner | `python scripts/apply_sql_migration.py --env-file ..\..\.env --file ..\supabase\migrations\<file> [--dry-run]` |
| `supabase/migrations/20261025120200_relabel_unverified_legal_summaries.sql` | table owner | same as above |

All three are additive and safe to re-run. `apply_sql_migration.py` refuses to run unless the connected role owns the tables, runs the file in one transaction, and supports `--dry-run`.

## 7. Access control

Every document route, search, preview, download, extraction and assistant query uses `backend/app/services/document_access.py`:
- STATE users see everything.
- Laws, circulars, investigation guides and reference material are statewide.
- A document linked to a case follows the case's district/station.
- Other documents follow their own district/station, or their uploader's jurisdiction.

Changing statewide reference material, or marking a source official, needs DISTRICT/STATE (official: STATE only). Row Level Security is enabled on every Supabase table; the backend (table owner) is unaffected, and Supabase's public API roles have no access.
