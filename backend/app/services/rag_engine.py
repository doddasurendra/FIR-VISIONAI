import os
import sqlite3
import re
import hashlib
import time
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from ..config import settings
from ..database import is_postgres
from ..models.user import User
from ..models.case import Case
from ..models.document import Document, DocumentChunk, DocumentPage
from .gemini import gemini_service
from .auth import apply_case_scope_filter
import logging
logger = logging.getLogger(__name__)

# ─── In-memory query result cache for Mode A (document-grounded) RAG ─────────
# Key: (document_id, query_hash, language)
# Value: (result_dict, cached_at_timestamp)
_RAG_CACHE: Dict[Tuple[str, str, str], Tuple[Dict[str, Any], float]] = {}
_RAG_CACHE_TTL_SECONDS = 300  # 5-minute TTL per document-query pair
_RAG_CACHE_MAX_ENTRIES = 200  # prevent unbounded growth

def _query_cache_key(document_id: str, query: str, language: str) -> Tuple[str, str, str]:
    q_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16]
    return (document_id, q_hash, language)

def _cache_get(document_id: str, query: str, language: str) -> Optional[Dict[str, Any]]:
    key = _query_cache_key(document_id, query, language)
    entry = _RAG_CACHE.get(key)
    if not entry:
        return None
    result, cached_at = entry
    if time.monotonic() - cached_at > _RAG_CACHE_TTL_SECONDS:
        del _RAG_CACHE[key]
        return None
    return result

def _cache_put(document_id: str, query: str, language: str, result: Dict[str, Any]) -> None:
    key = _query_cache_key(document_id, query, language)
    if len(_RAG_CACHE) >= _RAG_CACHE_MAX_ENTRIES:
        # Evict oldest 25 entries
        oldest = sorted(_RAG_CACHE.items(), key=lambda kv: kv[1][1])[:25]
        for k, _ in oldest:
            del _RAG_CACHE[k]
    _RAG_CACHE[key] = (result, time.monotonic())


def _cache_invalidate(document_id: Optional[str] = None) -> None:
    """Invalidates RAG query cache when documents are replaced or archived."""
    global _RAG_CACHE
    if document_id:
        keys_to_del = [k for k in _RAG_CACHE if k[0] == document_id]
        for k in keys_to_del:
            _RAG_CACHE.pop(k, None)
    else:
        _RAG_CACHE.clear()


class RAGEngine:
    @staticmethod
    async def answer_from_active_fir(
        document_id: str,
        query: str,
        user: User,
        db: AsyncSession,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Unified Grounded RAG engine for Mode A (both PDF and Image evidence).
        - Enforces strict document-scoping and authorization.
        - Resolves document and pages.
        - Auto-reindexes chunks if missing or stale.
        - Performs hybrid retrieval (FTS5 + keyword matching + full document fallback).
        - Generates strict grounded response citing physical page 1-based references.
        - In-memory query result cache (5-min TTL) for identical document+query pairs.
        - Never invents answers or page numbers.
        """
        # Check in-memory query cache (document-isolated, keyed by document_id + query hash)
        cached = _cache_get(document_id, query, language)
        if cached is not None:
            logger.debug(f"RAG cache hit for doc={document_id[:8]} lang={language}")
            cached_result = dict(cached)
            cached_result["from_cache"] = True
            return cached_result

        # 1. Verify Document existence and access permissions
        doc_stmt = select(Document).where(Document.id == document_id)
        res = await db.execute(doc_stmt)
        document = res.scalar_one_or_none()
        if not document:
            return {
                "answer": "The selected document was not found or access is denied.",
                "citations": [],
                "mode": "PDF_ONLY"
            }

        # Jurisdiction authorization check if document is attached to a registered case
        if document.case_id:
            case_stmt = select(Case).where(Case.id == document.case_id)
            c_res = await db.execute(case_stmt)
            case_obj = c_res.scalar_one_or_none()
            if case_obj and user.role != "STATE":
                if user.role == "DISTRICT" and case_obj.district != user.district:
                    return {
                        "answer": "Access denied: This document belongs to a case outside your authorized district jurisdiction.",
                        "citations": [],
                        "mode": "PDF_ONLY"
                    }
                elif user.role == "STATION" and (case_obj.district != user.district or case_obj.station != user.station):
                    return {
                        "answer": "Access denied: This document belongs to a case outside your authorized station jurisdiction.",
                        "citations": [],
                        "mode": "PDF_ONLY"
                    }

        # Check ingestion status
        if document.ingestion_status == "PROCESSING":
            return {
                "answer": "The document is currently being processed and indexed. Please wait a moment and try again.",
                "citations": [],
                "mode": "PDF_ONLY"
            }
        if document.ingestion_status == "FAILED":
            return {
                "answer": f"Document ingestion failed: {document.error_message or 'Corrupted file'}. Please re-upload.",
                "citations": [],
                "mode": "PDF_ONLY"
            }

        is_image = document.mime_type.startswith("image/") or not (document.original_filename or "").lower().endswith(".pdf")
        active_mode = "IMAGE_ONLY" if is_image else "PDF_ONLY"

        # 2. Load pages and chunks
        p_stmt = select(DocumentPage).where(DocumentPage.document_id == document_id).order_by(DocumentPage.physical_page_number.asc())
        p_res = await db.execute(p_stmt)
        pages = p_res.scalars().all()

        chunk_stmt = select(DocumentChunk).where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index.asc())
        c_res = await db.execute(chunk_stmt)
        chunks = c_res.scalars().all()

        # Check if chunks are missing or contain only boilerplate placeholder while pages have real text
        has_dummy_chunks = chunks and any("GOVERNMENT OF ANDHRA PRADESH - LAW ENFORCEMENT EVIDENCE RECORD" in (c.chunk_text or "") for c in chunks)
        has_real_page_text = pages and any(len((p.raw_text or "").strip()) > 50 and not (p.raw_text or "").startswith("GOVERNMENT OF ANDHRA PRADESH") for p in pages)

        if not chunks or (has_dummy_chunks and has_real_page_text):
            try:
                from .pdf_pipeline import reindex_document
                await reindex_document(document_id, db)
                c_res = await db.execute(chunk_stmt)
                chunks = c_res.scalars().all()
            except Exception as e:
                logger.warning(f"Auto-reindexing failed for {document_id}: {e}")

        # 3. Hybrid Retrieval: FTS5 + Keyword search + Document Page Fallback
        retrieved_snippets = []
        db_path = settings.SYNC_DATABASE_URL.replace("sqlite:///", "")

        # A. FTS5 full-text search (SQLite only — skip for PostgreSQL).
        # Decide from the active engine: in Supabase mode SYNC_DATABASE_URL still holds the
        # SQLite default, and a stale local file must never be searched.
        is_sqlite_db = not is_postgres
        stop_words = {
            "what", "which", "where", "when", "who", "whom", "how", "many", "the",
            "and", "this", "that", "with", "from", "for", "are", "was", "were",
            "tell", "show", "give", "please", "about", "mentioned", "visible",
            "uploaded", "image", "document", "record", "fir", "any", "persons",
            "names", "details"
        }
        clean_terms = [w for w in re.findall(r'\b[A-Za-z0-9_]{3,}\b', query) if w.lower() not in stop_words]

        # Expand semantic terms for common investigative queries
        q_lower_raw = query.lower()
        if any(w in q_lower_raw for w in ["person", "name", "accused", "suspect", "complainant", "witness", "who"]):
            clean_terms.extend(["name", "accused", "complainant", "witness", "suspect", "person"])
        if any(w in q_lower_raw for w in ["vehicle", "car", "bike", "registration", "number plate"]):
            clean_terms.extend(["vehicle", "registration", "auto", "bike"])
        if any(w in q_lower_raw for w in ["address", "location", "place", "where", "occurrence"]):
            clean_terms.extend(["address", "locality", "occurrence", "place"])
        if any(w in q_lower_raw for w in ["section", "law", "ipc", "bns", "act", "charge", "offence", "crime"]):
            clean_terms.extend(["section", "offence", "crime", "act"])
        # Deduplicate
        clean_terms = list(dict.fromkeys(clean_terms))

        if clean_terms and is_sqlite_db and os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path, timeout=30.0)
                cursor = conn.cursor()
                fts_query = " OR ".join(clean_terms)
                cursor.execute("""
                    SELECT chunk_id, document_id, physical_page_number, chunk_text, rank
                    FROM document_chunks_fts
                    WHERE document_chunks_fts MATCH ? AND document_id = ?
                    ORDER BY rank
                    LIMIT 6
                """, (fts_query, document_id))
                rows = cursor.fetchall()
                for row in rows:
                    retrieved_snippets.append({
                        "chunk_id": row[0],
                        "document_id": row[1],
                        "physical_page_number": int(row[2]) if row[2] else 1,
                        "text": row[3],
                        "score": float(row[4])
                    })
                conn.close()
            except Exception as e:
                logger.warning(f"FTS5 retrieval query failed ({e}), using direct text matching.")

        # B. Direct keyword match on chunks (works with both SQLite and PostgreSQL)
        if len(retrieved_snippets) < 2 and chunks:
            for c in chunks:
                c_text = (c.chunk_text or "").lower()
                # Match if any clean term hits — or include all chunks for image/short docs
                term_hit = any(w.lower() in c_text for w in clean_terms) if clean_terms else False
                if term_hit:
                    if not any(s.get("chunk_id") == c.id for s in retrieved_snippets):
                        retrieved_snippets.append({
                            "chunk_id": c.id,
                            "document_id": c.document_id,
                            "physical_page_number": c.physical_page_number or 1,
                            "text": c.chunk_text,
                            "score": 0.8
                        })

        # C. Fallback: Provide full page text if insufficient snippets were retrieved,
        # or when user asks for a full document summary or questions about entities/names
        is_summary_query = any(k in q_lower_raw for k in [
            "summar", "overview", "brief", "సారాంశం", "सारांश"
        ])
        is_entity_query = any(k in q_lower_raw for k in [
            "person", "name", "who", "accused", "suspect", "witness", "complainant",
            "detail", "vehicle", "address", "section", "charge", "offence", "date",
            "విరివరాలు", "వ్యక్తి", "నిందితుడు", "साक्षी", "आरोपी"
        ])

        if len(retrieved_snippets) < 2 or is_summary_query or is_entity_query:
            if is_image or len(pages) <= 2:
                # Include page text so Gemini has complete FIR context
                for p in pages:
                    p_text = (p.raw_text or "").strip()
                    if p_text and not any(s.get("text") == p_text for s in retrieved_snippets):
                        retrieved_snippets.append({
                            "chunk_id": f"page-{p.physical_page_number or 1}",
                            "document_id": document_id,
                            "physical_page_number": p.physical_page_number or 1,
                            "text": p_text,
                            "score": 0.9
                        })
                # Also include all chunks if pages gave nothing (chunks may have more text)
                if len(retrieved_snippets) < 2 and chunks:
                    for c in chunks:
                        if not any(s.get("chunk_id") == c.id for s in retrieved_snippets):
                            retrieved_snippets.append({
                                "chunk_id": c.id,
                                "document_id": c.document_id,
                                "physical_page_number": c.physical_page_number or 1,
                                "text": c.chunk_text,
                                "score": 0.7
                            })
            else:
                for c in chunks[:5]:
                    if not any(s.get("chunk_id") == c.id for s in retrieved_snippets):
                        retrieved_snippets.append({
                            "chunk_id": c.id,
                            "document_id": c.document_id,
                            "physical_page_number": c.physical_page_number or 1,
                            "text": c.chunk_text,
                            "score": 0.5
                        })

        # 4. Synthesize grounded answer
        result = gemini_service.generate_grounded_answer(
            query=query,
            context_snippets=retrieved_snippets,
            mode=active_mode,
            language=language
        )
        result["mode"] = active_mode
        result["document_id"] = document_id
        result["original_filename"] = document.original_filename

        # Store in cache (document-isolated)
        _cache_put(document_id, query, language, result)
        return result

    @staticmethod
    async def answer_pdf_only(
        document_id: str,
        query: str,
        user: User,
        db: AsyncSession,
        language: str = "en"
    ) -> Dict[str, Any]:
        """PDF-Only Mode A handler: delegates to unified answer_from_active_fir."""
        return await RAGEngine.answer_from_active_fir(
            document_id=document_id,
            query=query,
            user=user,
            db=db,
            language=language
        )

    @staticmethod
    async def answer_image_only(
        document_id: str,
        query: str,
        user: User,
        db: AsyncSession,
        language: str = "en"
    ) -> Dict[str, Any]:
        """Image-Only Mode A handler: delegates to unified answer_from_active_fir."""
        return await RAGEngine.answer_from_active_fir(
            document_id=document_id,
            query=query,
            user=user,
            db=db,
            language=language
        )

    @staticmethod
    def invalidate_cache(document_id: Optional[str] = None):
        """Invalidate RAG query cache when documents are replaced or archived."""
        _cache_invalidate(document_id)

    @staticmethod
    async def answer_from_knowledge_base(
        query: str,
        user: User,
        db: AsyncSession,
        language: str = "en",
        category: Optional[str] = "ALL"
    ) -> Dict[str, Any]:
        """
        Mode B: Knowledge Base Only Grounded RAG.
        - Supports 8 searchable categories:
          1. ALL: All Documents (balanced across categories without duplicate records or FIR over-representation)
          2. LEGAL_ACT: Official Laws & Sections (Acts, provisions, sections, rules + LegalCorpus)
          3. CIRCULAR: Circulars & Orders (official circulars, GOs, departmental instructions)
          4. SEIZURE_REPORT: Seizure Reports (authorized seizure records and related reports)
          5. INVESTIGATION_GUIDE: Investigation Guides & SOPs (SOPs, manuals, timelines)
          6. REFERENCE: Reference Materials (authorized departmental reference documents)
          7. HISTORICAL_FIR: Historical FIR Records (FIR documents, subject to jurisdiction permissions)
          8. EVIDENCE: Approved Evidence (approved evidence records; image evidence with no fake page numbers)
        - Enforces jurisdictional scoping:
          - Statewide departmental documents (LEGAL_ACT, CIRCULAR, INVESTIGATION_GUIDE, REFERENCE) are accessible statewide.
          - Case-specific / FIR documents are scoped to user station/district.
        - Strict factual grounding:
          - If the selected category or scope does not contain the answer, returns exact standardized response:
            EN: "The requested information was not found in the selected authorized Knowledge Base documents."
            TE: "ఎంచుకున్న అధీకృత నాలెడ్జ్ బేస్ పత్రాల్లో కోరిన సమాచారం కనుగొనబడలేదు."
            HI: "चयनित अधिकृत नॉलेज बेस दस्तावेज़ों में मांगी गई जानकारी नहीं मिली।"
        """
        cat_upper = (category or "ALL").strip().upper()
        if cat_upper in ("HISTORICAL_FIRS", "FIRS"):
            cat_upper = "HISTORICAL_FIR"

        # 1. Cache lookup per category
        cache_key = f"KB_{cat_upper}"
        cached = _cache_get(cache_key, query, language)
        if cached is not None:
            cached_res = dict(cached)
            cached_res["from_cache"] = True
            return cached_res

        # Helper for standard not found message
        def _get_kb_not_found(lang: str) -> str:
            if lang == "te":
                return "ఎంచుకున్న అధీకృత నాలెడ్జ్ బేస్ పత్రాల్లో కోరిన సమాచారం కనుగొనబడలేదు."
            elif lang == "hi":
                return "चयनित अधिकृत नॉलेज बेस दस्तावेज़ों में मांगी गई जानकारी नहीं मिली।"
            return "The requested information was not found in the selected authorized Knowledge Base documents."

        # 2. Extract search terms
        words = re.findall(r'\b[a-zA-Z0-9_\u0C00-\u0C7F\u0900-\u097F]{2,}\b', query.lower())
        stop_words = {"what", "when", "where", "which", "does", "have", "with", "from", "that", "this", "tell", "explain", "about", "case", "under", "who", "whom", "how", "the", "and", "for", "are", "was", "excise", "department", "andhra", "pradesh", "govt", "government"}
        search_terms = [w for w in words if w not in stop_words][:8]

        retrieved_snippets = []
        citations = []

        # 3. Query LegalCorpus if category in ("LEGAL_ACT", "ALL")
        if cat_upper in ("LEGAL_ACT", "ALL") and search_terms:
            from ..models.legal import LegalCorpus
            legal_stmt = select(LegalCorpus).where(LegalCorpus.verification_status == "VERIFIED")
            lc_conds = []
            for term in search_terms[:5]:
                p = f"%{term}%"
                lc_conds.append(LegalCorpus.act_name.ilike(p))
                lc_conds.append(LegalCorpus.section_number.ilike(p))
                lc_conds.append(LegalCorpus.section_title.ilike(p))
                lc_conds.append(LegalCorpus.full_text.ilike(p))
            legal_stmt = legal_stmt.where(or_(*lc_conds)).limit(25)
            lc_res = await db.execute(legal_stmt)
            matched_legal = lc_res.scalars().all()

            scored_legal = []
            for lc in matched_legal:
                combined_text = f"{lc.act_name} {lc.section_number} {lc.section_title} {lc.full_text} {lc.explanation or ''}".lower()
                hits = sum(1 for t in search_terms if t in combined_text)
                if hits > 0:
                    scored_legal.append((hits, lc))
            scored_legal.sort(key=lambda x: x[0], reverse=True)

            for hits, lc in scored_legal[:4]:
                sec_text = f"Official Legal Provision:\nAct: {lc.act_name}\nSection {lc.section_number}: {lc.section_title}\n{lc.full_text}"
                if lc.explanation:
                    sec_text += f"\nLegal Application: {lc.explanation}"
                if lc.penalty_text:
                    sec_text += f"\nPenalty: {lc.penalty_text}"
                retrieved_snippets.append({
                    "chunk_id": f"legal-corpus-{lc.id}",
                    "document_id": lc.document_id,
                    "physical_page_number": 1,
                    "document_name": f"{lc.act_name} (Section {lc.section_number})",
                    "category": "LEGAL_ACT",
                    "source_label": f"Statute: {lc.act_name} Sec {lc.section_number}",
                    "text": sec_text,
                    "score": hits + 2
                })
                citations.append({
                    "document_name": f"{lc.act_name} - Sec {lc.section_number}",
                    "document_id": lc.document_id,
                    "physical_page_number": 1,
                    "category": "LEGAL_ACT",
                    "is_image": False,
                    "source_label": f"Statute: {lc.act_name} Sec {lc.section_number}"
                })

        # 4. Fetch authorized active Knowledge Base documents (exclude archived/deleted)
        doc_stmt = select(Document).where(
            Document.is_archived == False,
            Document.ingestion_status == "COMPLETED"
        )

        if cat_upper in ("HISTORICAL_FIR", "FIR"):
            doc_stmt = doc_stmt.where(Document.doc_category.in_(["HISTORICAL_FIR", "FIR"]))
        elif cat_upper != "ALL":
            doc_stmt = doc_stmt.where(Document.doc_category == cat_upper)

        # Jurisdiction access control
        statewide_cats = ["LEGAL_ACT", "CIRCULAR", "INVESTIGATION_GUIDE", "REFERENCE"]
        if user.role == "DISTRICT":
            doc_stmt = doc_stmt.where(
                or_(
                    Document.doc_category.in_(statewide_cats),
                    Document.district == user.district,
                    Document.district == None,
                    Document.district == "STATE",
                    Document.district == "ALL"
                )
            )
        elif user.role == "STATION":
            doc_stmt = doc_stmt.where(
                or_(
                    Document.doc_category.in_(statewide_cats),
                    and_(
                        Document.district == user.district,
                        or_(Document.station == user.station, Document.station == None)
                    ),
                    Document.district == None,
                    Document.district == "STATE",
                    Document.district == "ALL"
                )
            )

        doc_res = await db.execute(doc_stmt)
        docs = doc_res.scalars().all()

        doc_ids = [d.id for d in docs]
        doc_map = {d.id: d for d in docs}

        # 5. Retrieve matching DocumentChunks
        if doc_ids and search_terms:
            kw_conditions = []
            for term in search_terms[:5]:
                kw_conditions.append(DocumentChunk.chunk_text.ilike(f"%{term}%"))

            chunk_stmt = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id.in_(doc_ids),
                    or_(*kw_conditions)
                )
                .limit(120)
            )
            c_res = await db.execute(chunk_stmt)
            all_chunks = c_res.scalars().all()

            scored_chunks = []
            for ch in all_chunks:
                text_lower = (ch.chunk_text or "").lower()
                hits = sum(1 for term in search_terms if term in text_lower)
                if hits > 0:
                    d = doc_map.get(ch.document_id)
                    d_cat = getattr(d, "doc_category", "REFERENCE") if d else "REFERENCE"
                    scored_chunks.append((hits, ch, d, d_cat))

            scored_chunks.sort(key=lambda x: x[0], reverse=True)

            # Balanced category retrieval when cat_upper == "ALL"
            if cat_upper == "ALL":
                by_category = {}
                for item in scored_chunks:
                    c_name = item[3]
                    by_category.setdefault(c_name, []).append(item)

                selected_chunks = []
                # First take up to 2 top chunks from each category that matched
                for c_name, items in by_category.items():
                    selected_chunks.extend(items[:2])

                # Fill remaining slots up to 8 total
                selected_ids = {item[1].id for item in selected_chunks}
                for item in scored_chunks:
                    if len(selected_chunks) >= 8:
                        break
                    if item[1].id not in selected_ids:
                        selected_chunks.append(item)
                        selected_ids.add(item[1].id)

                selected_chunks.sort(key=lambda x: x[0], reverse=True)
            else:
                selected_chunks = scored_chunks[:8]

            for hits, ch, d, d_cat in selected_chunks:
                d_name = (d.document_title or d.original_filename) if d else "Knowledge Base Record"
                is_img = False
                if d:
                    mime = (d.mime_type or "").lower()
                    fname = (d.original_filename or "").lower()
                    if mime.startswith("image/") or fname.endswith((".jpg", ".jpeg", ".png", ".webp")) or d_cat == "EVIDENCE":
                        is_img = True

                p_num = ch.physical_page_number or 1
                source_lbl = f"{d_name} (Evidence Image)" if is_img else f"{d_name} (Page {p_num})"

                retrieved_snippets.append({
                    "chunk_id": ch.id,
                    "document_id": ch.document_id,
                    "physical_page_number": p_num if not is_img else None,
                    "document_name": d_name,
                    "category": d_cat,
                    "is_image": is_img,
                    "source_label": source_lbl,
                    "text": ch.chunk_text,
                    "score": hits
                })
                citations.append({
                    "document_name": d_name,
                    "document_id": ch.document_id,
                    "physical_page_number": p_num if not is_img else None,
                    "category": d_cat,
                    "is_image": is_img,
                    "version_date": getattr(d, "version_date", None) if d else None,
                    "source_label": source_lbl
                })

        # 6. Check if anything was retrieved
        if not retrieved_snippets:
            not_found_msg = _get_kb_not_found(language)
            return {
                "answer": not_found_msg,
                "citations": [],
                "mode": "KNOWLEDGE_BASE_ONLY",
                "category": cat_upper,
                "total_sources_consulted": len(doc_ids)
            }

        # 7. Synthesize grounded answer
        result = gemini_service.generate_grounded_answer(
            query=query,
            context_snippets=retrieved_snippets,
            mode="KNOWLEDGE_BASE_ONLY",
            language=language
        )
        result["mode"] = "KNOWLEDGE_BASE_ONLY"
        result["category"] = cat_upper
        result["total_sources_consulted"] = len(doc_ids)

        # Ensure deduplicated citations
        seen_cits = set()
        unique_cits = []
        for c in citations:
            ck = (c.get("document_id"), c.get("physical_page_number"), c.get("source_label"))
            if ck not in seen_cits:
                seen_cits.add(ck)
                unique_cits.append(c)

        # If answer was not found, citations must be empty
        ans_lower = (result.get("answer") or "").lower()
        if any(nf in ans_lower for nf in ["not found in the selected", "కనుగొనబడలేదు", "जानकारी नहीं मिली"]):
            result["citations"] = []
        else:
            result["citations"] = unique_cits[:6]

        # 8. Cache result
        _cache_put(cache_key, query, language, result)
        return result

    @staticmethod
    async def answer_cross_case(
        query: str,
        user: User,
        db: AsyncSession,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Mode B: Authorized Cross-Case Intelligence.
        Hierarchically scoped by user role (STATION, DISTRICT, STATE).
        Calculates SQL counts for aggregate questions.
        """
        q_lower = query.lower()

        # Check for aggregate count questions
        if any(term in q_lower for term in ["how many", "count", "total cases", "number of cases", "ఎన్ని కేసులు", "कितने मामले"]):
            base_query = select(func.count(Case.id)).where(Case.is_archived == False)
            scoped_query = apply_case_scope_filter(base_query, user, Case)
            res = await db.execute(scoped_query)
            count_val = res.scalar() or 0

            scope_desc = f"in {user.station} ({user.district})" if user.role == "STATION" else f"in {user.district} District" if user.role == "DISTRICT" else "across the State"
            if language == "te":
                ans = f"మీ అధికార పరిధిలో ({scope_desc}) మొత్తం **{count_val}** చట్టబద్ధమైన కేసులు నమోదయ్యాయి."
            elif language == "hi":
                ans = f"आपके अधिकार क्षेत्र ({scope_desc}) में कुल **{count_val}** मामले दर्ज हैं।"
            else:
                ans = f"According to authorized departmental database records, a total of **{count_val}** cases are registered {scope_desc}."

            return {
                "answer": ans,
                "citations": [],
                "mode": "CROSS_CASE",
                "is_aggregate_count": True,
                "count": count_val
            }

        # Extract search terms and specific patterns (FIR number, vehicle, person names)
        words = re.findall(r'\b[a-zA-Z0-9_\u0C00-\u0C7F\u0900-\u097F/-]{3,}\b', query)
        stop_words = {"what", "when", "where", "which", "does", "have", "with", "from", "that", "this", "tell", "explain", "about", "case", "cases", "section", "under", "history", "records", "search", "show", "find", "give"}
        search_terms = [w for w in words if w.lower() not in stop_words][:6]

        base_case_query = select(Case).where(Case.is_archived == False)

        # Keyword filtering across case fields
        if search_terms:
            conds = []
            for t in search_terms:
                pat = f"%{t}%"
                conds.extend([
                    Case.fir_number.ilike(pat),
                    Case.offence_nature.ilike(pat),
                    Case.contraband_type.ilike(pat),
                    Case.vehicle_details.ilike(pat),
                    Case.witnesses_summary.ilike(pat),
                    Case.narrative.ilike(pat),
                    Case.location_description.ilike(pat),
                    Case.village.ilike(pat),
                    Case.mandal.ilike(pat),
                ])
            base_case_query = base_case_query.where(or_(*conds))

        scoped_cases = apply_case_scope_filter(base_case_query, user, Case).order_by(Case.created_at.desc()).limit(10)
        res = await db.execute(scoped_cases)
        cases = res.scalars().all()

        # Also retrieve relevant document chunks from authorized FIR documents
        doc_stmt = select(Document).where(
            Document.is_archived == False,
            or_(
                Document.doc_category.in_(["FIR", "HISTORICAL_FIR", "EVIDENCE"]),
                Document.case_id.isnot(None),
            )
        )
        if user.role == "STATION":
            doc_stmt = doc_stmt.where(
                or_(
                    and_(Document.district == user.district, or_(Document.station == user.station, Document.station.is_(None))),
                    and_(Document.district.is_(None), Document.station.is_(None))
                )
            )
        elif user.role == "DISTRICT":
            doc_stmt = doc_stmt.where(or_(Document.district == user.district, Document.district.is_(None)))

        doc_res = await db.execute(doc_stmt.limit(50))
        auth_docs = {d.id: d for d in doc_res.scalars().all()}
        auth_doc_ids = list(auth_docs.keys())

        matching_chunks = []
        if auth_doc_ids and search_terms:
            chunk_conds = []
            for t in search_terms:
                chunk_conds.append(DocumentChunk.chunk_text.ilike(f"%{t}%"))
            chunk_stmt = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id.in_(auth_doc_ids[:50]),
                    or_(*chunk_conds)
                )
                .limit(8)
            )
            c_res = await db.execute(chunk_stmt)
            matching_chunks = c_res.scalars().all()

        if not cases and not matching_chunks:
            no_rec_msg = (
                "మీ అధికార పరిధిలో సంబంధిత రికార్డులు ఏవీ కనుగొనబడలేదు." if language == "te"
                else "आपके अधिकार क्षेत्र में कोई प्रासंगिक रिकॉर्ड नहीं मिला।" if language == "hi"
                else "No relevant authorized historical FIR records were found within your jurisdiction."
            )
            return {"answer": no_rec_msg, "citations": [], "mode": "CROSS_CASE"}

        snippets = []
        citations = []
        seen_citations = set()

        # Add case snippets
        for c in cases:
            snippet_text = (
                f"FIR: {c.fir_number} | Year: {c.year} | District: {c.district} | Station: {c.station} | "
                f"Offence: {c.offence_nature} | Contraband: {c.contraband_type or 'None'} ({c.seized_quantity or 0} {c.seized_unit or ''}) | "
                f"Vehicle: {c.vehicle_details or 'None'} | Persons: {c.witnesses_summary or 'Not specified'} | "
                f"Narrative: {(c.narrative or 'No narrative')[:400]}"
            )
            snippets.append({
                "fir_number": c.fir_number,
                "case_id": c.id,
                "text": snippet_text
            })
            cit_key = f"case-{c.id}"
            if cit_key not in seen_citations:
                seen_citations.add(cit_key)
                citations.append({
                    "case_id": c.id,
                    "fir_number": c.fir_number,
                    "district": c.district,
                    "station": c.station,
                    "source_label": f"FIR Case: {c.fir_number} ({c.district})"
                })

        # Add chunk snippets from documents
        for ch in matching_chunks:
            d = auth_docs.get(ch.document_id)
            if not d:
                continue
            p_num = ch.physical_page_number or 1
            snippets.append({
                "document_id": ch.document_id,
                "text": f"Document: {d.original_filename} (Page {p_num}): {ch.chunk_text[:350]}"
            })
            cit_key = f"doc-{ch.document_id}-p{p_num}"
            if cit_key not in seen_citations:
                seen_citations.add(cit_key)
                is_img = bool(d.mime_type and d.mime_type.startswith("image/"))
                citations.append({
                    "document_id": ch.document_id,
                    "document_name": d.original_filename,
                    "physical_page_number": p_num,
                    "district": d.district,
                    "station": d.station,
                    "source_label": f"Evidence: {d.original_filename} ({'Image Record' if is_img else f'Page {p_num}'})"
                })

        result = gemini_service.generate_grounded_answer(
            query=query,
            context_snippets=snippets,
            mode="CROSS_CASE",
            language=language
        )
        result["mode"] = "CROSS_CASE"
        result["citations"] = citations[:10]
        return result

    @staticmethod
    async def answer_fir_plus_legal(
        document_id: str,
        query: str,
        user: User,
        db: AsyncSession,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Mode C: FIR + Legal Corpus Combined RAG.
        Grounds the answer in both the selected FIR document and the indexed legal corpus.
        Sources cited separately: FIR pages and legal act sections.
        Never hallucinated — if not found in either source, returns standard not-found message.
        """
        from ..models.legal import LegalCorpus

        citations = []
        context_snippets = []

        # 1. Load FIR document chunks (same authorization as Mode A)
        doc_res = await db.execute(select(Document).where(Document.id == document_id))
        doc = doc_res.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        # Authorization: station-scoped
        if user.role == "STATION" and doc.case_id:
            from ..models.case import Case
            case_res = await db.execute(select(Case).where(Case.id == doc.case_id))
            c = case_res.scalar_one_or_none()
            if c and (c.district != user.district or c.station != user.station):
                raise PermissionError("Access denied: document is outside your jurisdiction")

        fir_chunk_res = await db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id).limit(30)
        )
        fir_chunks = fir_chunk_res.scalars().all()

        doc_name = doc.document_title or doc.original_filename
        words = re.findall(r'\b[a-zA-Z0-9_\u0C00-\u0C7F\u0900-\u097F]{3,}\b', query.lower())
        stop_words = {"what", "when", "where", "which", "does", "have", "with", "from", "that", "this", "tell", "explain", "about", "case", "section", "act", "under"}
        search_terms = [w for w in words if w not in stop_words][:8]

        # Score FIR chunks by keyword relevance
        scored_fir = []
        for ch in fir_chunks:
            text_lower = (ch.chunk_text or "").lower()
            hits = sum(1 for t in search_terms if t in text_lower)
            if hits > 0:
                scored_fir.append((hits, ch))
        scored_fir.sort(key=lambda x: x[0], reverse=True)

        for hits, ch in scored_fir[:5]:
            p_num = ch.physical_page_number or 1
            context_snippets.append({
                "source_type": "FIR",
                "chunk_id": ch.id,
                "document_id": document_id,
                "physical_page_number": p_num,
                "text": ch.chunk_text,
                "score": hits
            })
            citations.append({
                "document_name": doc_name,
                "document_id": document_id,
                "physical_page_number": p_num,
                "category": "FIR",
                "source_label": f"FIR: {doc_name} (Page {p_num})",
                "source_type": "FIR"
            })

        # 2. Load relevant LegalCorpus sections — filter by keyword in DB, not in Python
        from sqlalchemy import or_ as sql_or
        legal_stmt = select(LegalCorpus).where(LegalCorpus.verification_status == "VERIFIED")
        # Apply keyword filter at DB level to avoid pulling all 500 records into Python
        if search_terms:
            keyword_conditions = []
            for term in search_terms[:5]:  # limit to avoid overly complex query
                pattern = f"%{term}%"
                keyword_conditions.append(LegalCorpus.act_name.ilike(pattern))
                keyword_conditions.append(LegalCorpus.section_title.ilike(pattern))
                keyword_conditions.append(LegalCorpus.full_text.ilike(pattern))
            legal_stmt = legal_stmt.where(sql_or(*keyword_conditions))
        legal_stmt = legal_stmt.limit(50)  # cap to 50 most relevant, not all 500
        legal_res = await db.execute(legal_stmt)
        all_legal = legal_res.scalars().all()

        scored_legal = []
        for lc in all_legal:
            combined = f"{lc.act_name} {lc.section_number} {lc.section_title} {lc.full_text} {lc.explanation or ''}"
            text_lower = combined.lower()
            hits = sum(1 for t in search_terms if t in text_lower)
            if hits > 0:
                scored_legal.append((hits, lc))
        scored_legal.sort(key=lambda x: x[0], reverse=True)

        for hits, lc in scored_legal[:5]:
            sec_text = f"{lc.act_name} - {lc.section_number}: {lc.section_title}\n{lc.full_text}"
            if lc.explanation:
                sec_text += f"\nApplication: {lc.explanation}"
            if lc.penalty_text:
                sec_text += f"\nPenalty: {lc.penalty_text}"
            context_snippets.append({
                "source_type": "LEGAL",
                "chunk_id": f"legal-{lc.id}",
                "document_id": lc.document_id or "legal-corpus",
                "physical_page_number": 1,
                "text": sec_text,
                "score": hits
            })
            status_label = "REPEALED" if lc.repeal_date else "ACTIVE"
            citations.append({
                "document_name": f"{lc.act_name}",
                "section": f"{lc.section_number}: {lc.section_title}",
                "document_id": lc.document_id or "legal-corpus",
                "physical_page_number": 1,
                "category": lc.category or "LEGAL_ACT",
                "source_label": f"Legal: {lc.act_name} {lc.section_number} [{status_label}]",
                "source_type": "LEGAL",
                "source_url": lc.source_url,
                "is_historical": bool(lc.repeal_date),
            })

        if not context_snippets:
            not_found_msg = (
                "ఎంచుకున్న FIR డాక్యుమెంట్ మరియు అధికారిక చట్టపు కార్పస్‌లో సంబంధిత సమాచారం కనుగొనబడలేదు." if language == "te"
                else "चुने गए FIR दस्तावेज़ और विधिक कोष में कोई प्रासंगिक जानकारी नहीं मिली।" if language == "hi"
                else "The requested information was not found in the selected FIR document or the authorized Legal Corpus."
            )
            return {
                "answer": not_found_msg,
                "citations": [],
                "mode": "FIR_PLUS_LEGAL"
            }

        result = gemini_service.generate_grounded_answer(
            query=query,
            context_snippets=context_snippets,
            mode="FIR_PLUS_LEGAL",
            language=language
        )
        result["mode"] = "FIR_PLUS_LEGAL"
        result["citations"] = citations[:8]
        result["fir_citations"] = [c for c in citations if c.get("source_type") == "FIR"]
        result["legal_citations"] = [c for c in citations if c.get("source_type") == "LEGAL"]
        return result


rag_engine = RAGEngine()
