"""
FIR VisionAI research assistant: scoped, authorised, citation-grounded RAG.

Flow for every question:
1. Resolve the search scope to an explicit list of document ids the user may access.
2. Hybrid retrieval (full-text + vector) restricted to those ids.
3. Answer only from the retrieved passages (Gemini with mandatory [S#] citations; without Gemini,
   quote the matching passages directly).
4. Return citations naming document, page, section and excerpt; or the standard not-found reply
   with an option to widen the scope.

Scopes: CURRENT_FIR, CASE, FIR_AND_LAW, KNOWLEDGE_BASE, ALL_AUTHORIZED.
"""
import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.case import Case
from ..models.document import Document
from ..models.user import User
from .auth import apply_case_scope_filter, enforce_data_scope
from .document_access import apply_document_scope, get_authorized_document
from .gemini import gemini_service
from .retrieval import REFERENCE_CATEGORIES, hybrid_search, query_terms, whole_document_passages

logger = logging.getLogger(__name__)

NOT_FOUND = {
    "en": "I could not find sufficient supporting information in the selected FIR VisionAI documents to answer this question.",
    "te": "ఎంచుకున్న FIR VisionAI పత్రాల్లో ఈ ప్రశ్నకు సమాధానం ఇవ్వడానికి తగిన ఆధార సమాచారం నాకు కనుగొనబడలేదు.",
    "hi": "चयनित FIR VisionAI दस्तावेज़ों में इस प्रश्न का उत्तर देने के लिए मुझे पर्याप्त सहायक जानकारी नहीं मिली।",
}
EXTRACTIVE_INTRO = {
    "en": "AI summarisation is unavailable, so the matching passages are quoted directly:",
    "te": "AI సారాంశం అందుబాటులో లేదు; సరిపోలిన భాగాలను యథాతథంగా ఇస్తున్నాము:",
    "hi": "AI सारांश उपलब्ध नहीं है, इसलिए मेल खाने वाले अंश सीधे उद्धृत किए गए हैं:",
}

UNSUPPORTED_NOTE = {
    "en": "⚠️ Check before relying on this: the answer mentions {refs}, which does not appear in the cited source text.",
    "te": "⚠️ దీనిపై ఆధారపడే ముందు తనిఖీ చేయండి: సమాధానంలో పేర్కొన్న {refs} ఉదహరించిన మూల పాఠ్యంలో లేదు.",
    "hi": "⚠️ इस पर भरोसा करने से पहले जाँच करें: उत्तर में उल्लिखित {refs} उद्धृत स्रोत पाठ में नहीं है।",
}
_PROVISION_REF = re.compile(r"\b(sections?|articles?|rules?)\s+(\d{1,3}[A-Z]?)\b", re.I)

KB_CATEGORIES = ("LEGAL_ACT", "CIRCULAR", "SEIZURE_REPORT", "INVESTIGATION_GUIDE", "REFERENCE", "EVIDENCE", "HISTORICAL_FIR")
SCOPES = ("CURRENT_FIR", "CASE", "FIR_AND_LAW", "KNOWLEDGE_BASE", "ALL_AUTHORIZED")
LEGACY_MODES = {
    "PDF_ONLY": "CURRENT_FIR", "IMAGE_ONLY": "CURRENT_FIR", "SELECTED_FIR_ONLY": "CURRENT_FIR",
    "KNOWLEDGE_BASE_ONLY": "KNOWLEDGE_BASE", "KNOWLEDGE_BASE": "KNOWLEDGE_BASE",
    "FIR_PLUS_LEGAL": "FIR_AND_LAW", "FIR_LEGAL": "FIR_AND_LAW", "CROSS_CASE": "ALL_AUTHORIZED",
}
WIDER_SCOPE = {"CURRENT_FIR": "CASE", "CASE": "ALL_AUTHORIZED", "FIR_AND_LAW": "ALL_AUTHORIZED",
               "KNOWLEDGE_BASE": "ALL_AUTHORIZED", "ALL_AUTHORIZED": None}
_LEGAL_HINTS = ("section", "act", "law", "legal", "provision", "article", "offence", "penalty", "punish",
                "bns", "bnss", "ipc", "crpc", "sanhita", "adhiniyam", "charge", "సెక్షన్", "చట్టం", "धारा", "कानून")
# Verbs that describe the question rather than its subject ("What does Article 21 say?")
_FILLER_VERBS = {"say", "says", "said", "state", "states", "stated", "mean", "means", "provide", "provides",
                 "define", "defines", "contain", "contains", "describe", "describes", "mention", "mentions"}
_COUNT_HINTS = ("how many", "number of cases", "total cases", "count of cases", "ఎన్ని కేసులు", "कितने मामले")

# ── Answer cache (keyed by scope + document set + query + language) ─────────
_CACHE: Dict[str, Tuple[Dict[str, Any], float, frozenset]] = {}
_CACHE_TTL = 300
_CACHE_MAX = 200


def _cache_key(scope: str, doc_ids: Sequence[str], query: str, language: str) -> str:
    raw = f"{scope}|{','.join(sorted(doc_ids))}|{query.strip().lower()}|{language}"
    return hashlib.sha256(raw.encode()).hexdigest()


def invalidate_cache(document_id: Optional[str] = None) -> None:
    if document_id is None:
        _CACHE.clear()
        return
    for k in [k for k, v in _CACHE.items() if document_id in v[2]]:
        _CACHE.pop(k, None)


# ── Scope resolution ─────────────────────────────────────────────────────────

def _searchable(stmt):
    """Exclude archived documents and those whose text/index could not be verified."""
    return stmt.where(
        Document.is_archived == False,  # noqa: E712
        Document.ingestion_status == "COMPLETED",
        or_(Document.index_status.is_(None), Document.index_status.notin_(("NEEDS_REVIEW", "FAILED"))),
    )


async def resolve_scope(
    db: AsyncSession, user: User, scope: str, document_id: Optional[str], case_id: Optional[str],
    categories: Optional[Sequence[str]],
) -> Dict[str, Any]:
    """Return {"document_ids": [...], "case_id": ..., "label": ...}; raises HTTP errors for bad requests."""
    if scope not in SCOPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown search scope '{scope}'.")

    if scope in ("CURRENT_FIR", "FIR_AND_LAW"):
        if not document_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select an FIR document for this search scope.")
        doc = await get_authorized_document(db, user, document_id)
        if doc.ingestion_status == "PROCESSING":
            raise HTTPException(status.HTTP_409_CONFLICT, "The document is still being processed. Try again shortly.")
        ids = [doc.id]
        if scope == "FIR_AND_LAW":
            law = await db.execute(_searchable(select(Document.id).where(Document.doc_category == "LEGAL_ACT")))
            ids += [r[0] for r in law.fetchall()]
        return {"document_ids": ids, "case_id": doc.case_id, "primary_document": doc}

    if scope == "CASE":
        if not case_id and document_id:
            doc = await get_authorized_document(db, user, document_id)
            case_id = doc.case_id
            if not case_id:
                return {"document_ids": [doc.id], "case_id": None, "primary_document": doc}
        if not case_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select a case for this search scope.")
        case = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
        if not case:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found.")
        if not enforce_data_scope(user, case.district, case.station):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied: this case is outside your jurisdiction.")
        res = await db.execute(_searchable(select(Document.id).where(Document.case_id == case_id)))
        return {"document_ids": [r[0] for r in res.fetchall()], "case_id": case_id, "primary_document": None}

    stmt = _searchable(select(Document.id))
    if scope == "KNOWLEDGE_BASE":
        cats = [c.upper() for c in (categories or []) if c and c.upper() != "ALL"] or list(KB_CATEGORIES)
        if "HISTORICAL_FIR" in cats:
            cats.append("FIR")
        stmt = stmt.where(Document.doc_category.in_(cats))
    stmt = apply_document_scope(stmt, user)
    res = await db.execute(stmt)
    return {"document_ids": [r[0] for r in res.fetchall()], "case_id": None, "primary_document": None}


# ── Answer construction ──────────────────────────────────────────────────────

def _term_present(term: str, low: str) -> bool:
    # Short and numeric terms must match whole words ("21" must not match "21-2-2002");
    # longer words match by prefix so "seized" also finds "seizure"
    if term.isdigit() or len(term) <= 3:
        return re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", low) is not None
    return (term[:6] if len(term) > 6 else term) in low


def _coverage(chunk_text: str, terms: List[str]) -> float:
    if not terms:
        return 0.0
    low = chunk_text.lower()
    return sum(1 for t in terms if _term_present(t, low)) / len(terms)


def best_excerpt(chunk_text: str, terms: List[str], max_len: int = 320) -> str:
    """The sentence window that contains the most query terms."""
    flat = " ".join(chunk_text.split())
    if len(flat) <= max_len:
        return flat
    sentences = re.split(r"(?<=[.;:])\s+", flat)
    best_i, best_score = 0, -1
    for i, s in enumerate(sentences):
        score = _coverage(s, terms)
        if score > best_score:
            best_i, best_score = i, score
    out = sentences[best_i]
    j = best_i + 1
    while j < len(sentences) and len(out) + len(sentences[j]) < max_len:
        out += " " + sentences[j]
        j += 1
    return out[:max_len].rstrip() + ("…" if len(out) > max_len else "")


def _citation(src: Dict[str, Any], number: int, terms: List[str]) -> Dict[str, Any]:
    page = None if src.get("is_image") else src.get("physical_page_number")
    title = src.get("document_title") or "Document"
    label_bits = [title]
    if src.get("section_ref"):
        label_bits.append(src["section_ref"])
    label_bits.append("Image evidence" if src.get("is_image") else f"Page {page}")
    return {
        "source_number": number,
        "document_id": src["document_id"],
        "document_name": title,
        "physical_page_number": page,
        "section_ref": src.get("section_ref"),
        "section_title": src.get("section_title"),
        "category": src.get("doc_category"),
        # Provenance labels describe reference material; FIRs and evidence are the case's own records
        "source_type": ((src.get("source_type") or "UNVERIFIED") if src.get("doc_category") in REFERENCE_CATEGORIES
                        else "CASE_RECORD"),
        "legal_status": src.get("legal_status"),
        "official_source_url": src.get("source_url"),
        "is_image": bool(src.get("is_image")),
        "case_id": src.get("case_id"),
        "evidence_excerpt": best_excerpt(src.get("chunk_text", ""), terms),
        "open_url": f"/api/v1/documents/{src['document_id']}/view" + ("" if src.get("is_image") or not page else f"#page={page}"),
        "retrieval": {"keyword_rank": src.get("keyword_rank"), "vector_rank": src.get("vector_rank"),
                      "vector_score": round(src["vector_score"], 4) if src.get("vector_score") is not None else None},
        "source_label": " · ".join(label_bits),
        "verification_status": "RETRIEVED_SOURCE_TEXT",
    }


def unsupported_references(answer_text: str, sources: List[Dict[str, Any]]) -> List[str]:
    """Section/Article/Rule numbers in an answer that occur nowhere in the passages given to the model."""
    corpus = " ".join(f"{s.get('section_ref') or ''} {s.get('chunk_text') or ''}" for s in sources).lower()
    missing = set()
    for kind, num in _PROVISION_REF.findall(answer_text):
        if not re.search(rf"(?<![\w.]){re.escape(num.lower())}(?![\w])", corpus):
            missing.add(f"{kind.rstrip('sS').title()} {num}")
    return sorted(missing)


def _not_found(scope: str, language: str, diagnostics: Dict[str, Any], reason: str) -> Dict[str, Any]:
    wider = WIDER_SCOPE.get(scope)
    return {
        "answer": NOT_FOUND.get(language, NOT_FOUND["en"]),
        "citations": [],
        "scope": scope,
        "not_found": True,
        "can_expand_scope": wider is not None,
        "suggested_scope": wider,
        "answer_method": "NONE",
        "retrieval": {**diagnostics, "outcome": reason},
    }


async def _aggregate_count(db: AsyncSession, user: User, language: str) -> Dict[str, Any]:
    stmt = apply_case_scope_filter(select(func.count(Case.id)).where(Case.is_archived == False), user, Case)  # noqa: E712
    count_val = (await db.execute(stmt)).scalar() or 0
    where = (f"in {user.station} ({user.district})" if user.role == "STATION"
             else f"in {user.district} District" if user.role == "DISTRICT" else "across the State")
    answer = {
        "te": f"మీ అధికార పరిధిలో ({where}) మొత్తం **{count_val}** కేసులు నమోదయ్యాయి.",
        "hi": f"आपके अधिकार क्षेत्र ({where}) में कुल **{count_val}** मामले दर्ज हैं।",
    }.get(language, f"Authorized database records show **{count_val}** active cases registered {where}.")
    return {"answer": answer, "citations": [], "scope": "ALL_AUTHORIZED", "not_found": False,
            "is_aggregate_count": True, "count": count_val, "answer_method": "DATABASE_COUNT",
            "can_expand_scope": False, "suggested_scope": None, "retrieval": {"outcome": "SQL_COUNT"}}


async def answer(
    db: AsyncSession,
    user: User,
    query: str,
    *,
    scope: str,
    document_id: Optional[str] = None,
    case_id: Optional[str] = None,
    categories: Optional[Sequence[str]] = None,
    language: str = "en",
) -> Dict[str, Any]:
    query = (query or "").strip()
    if not query:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter a question.")
    language = language if language in NOT_FOUND else "en"

    if scope == "ALL_AUTHORIZED" and any(h in query.lower() for h in _COUNT_HINTS):
        return await _aggregate_count(db, user, language)

    resolved = await resolve_scope(db, user, scope, document_id, case_id, categories)
    doc_ids = resolved["document_ids"]
    primary = resolved.get("primary_document")
    if primary is not None and (primary.ingestion_status in ("FAILED", "NEEDS_REVIEW")
                                or primary.index_status in ("FAILED", "NEEDS_REVIEW")):
        result = _not_found(scope, language, {"documents_in_scope": len(doc_ids)}, "DOCUMENT_NOT_SEARCHABLE")
        result["document_status"] = primary.index_status or primary.ingestion_status
        result["document_error"] = primary.error_message
        return result
    key = _cache_key(scope, doc_ids, query, language)
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[1] < _CACHE_TTL:
        return {**hit[0], "from_cache": True}

    if not doc_ids:
        return _not_found(scope, language, {"documents_in_scope": 0}, "NO_SEARCHABLE_DOCUMENTS_IN_SCOPE")

    # Telugu/Hindi questions are searched in English when a translator is available; the answer
    # is still written in the officer's language.
    retrieval_query, translated = query, False
    if re.search(r"[ఀ-౿ऀ-ॿ]", query):
        english = gemini_service.translate_for_search(query)
        if english:
            retrieval_query, translated = english, True

    search = await hybrid_search(db, retrieval_query, document_ids=doc_ids, limit=8)
    sources, diagnostics = search["results"], search["diagnostics"]
    diagnostics["query_translated"] = translated
    # Short case records are given to the model in full and in reading order, so questions about
    # the selected FIR do not depend on sharing words with its text
    record_ids = [primary.id] if primary is not None else (doc_ids if scope == "CASE" else [])
    whole = await whole_document_passages(db, record_ids)
    if whole:
        whole_ids = {w["chunk_id"] for w in whole}
        sources = whole + [s for s in sources if s["chunk_id"] not in whole_ids]
    diagnostics["whole_record_passages"] = len(whole)
    logger.info(f"RAG scope={scope} docs={diagnostics['documents_in_scope']} kw={diagnostics['keyword_hits']} "
                f"vec={diagnostics['vector_hits']} returned={diagnostics['returned']}")
    if not sources:
        result = _not_found(scope, language, diagnostics, "NO_MATCHING_PASSAGES")
        _store(key, result, doc_ids)
        return result

    terms = query_terms(retrieval_query)
    legal_mode = any(h in retrieval_query.lower() for h in _LEGAL_HINTS) and any(
        s.get("doc_category") == "LEGAL_ACT" for s in sources)
    generated = gemini_service.answer_from_sources(query, sources, language=language, legal_mode=legal_mode)

    if generated["status"] == "ANSWERED":
        used = generated["used"]
        citations = [_citation(sources[n - 1], n, terms) for n in used]
        text_out = generated["text"]
        # Provision numbers the model wrote must exist in the passages it was given
        unsupported = unsupported_references(text_out, sources)
        if unsupported:
            logger.warning(f"Generated answer mentions provisions not in its sources: {unsupported}")
            text_out += "\n\n" + UNSUPPORTED_NOTE.get(language, UNSUPPORTED_NOTE["en"]).format(refs=", ".join(unsupported))
        result = {"answer": text_out, "citations": citations, "answer_method": "GENERATED_FROM_SOURCES",
                  "unsupported_references": unsupported}
    elif generated["status"] == "NOT_FOUND":
        result = _not_found(scope, language, diagnostics, "MODEL_FOUND_INSUFFICIENT_SUPPORT")
        _store(key, result, doc_ids)
        return result
    else:
        # No generation available: quote passages that cover the question's key terms
        def _coverage_text(s):
            # A passage's section label and document title count too ("Article 21", "Constitution")
            return " ".join(filter(None, (s.get("section_ref"), s.get("section_title"),
                                          s.get("document_title"), s.get("chunk_text", ""))))
        content_terms = [t for t in terms if t not in _FILLER_VERBS] or terms
        threshold = 1.0 if len(content_terms) <= 2 else 0.6
        strong = [(i, s) for i, s in enumerate(sources, start=1) if _coverage(_coverage_text(s), content_terms) >= threshold]
        if not strong:
            result = _not_found(scope, language, diagnostics, "PASSAGES_DO_NOT_COVER_QUESTION")
            _store(key, result, doc_ids)
            return result
        strong = strong[:3]
        citations = [_citation(s, i, terms) for i, s in strong]
        lines = [EXTRACTIVE_INTRO[language]]
        for c in citations:
            lines.append(f"- [S{c['source_number']}] “{c['evidence_excerpt']}” — {c['source_label']}")
        result = {"answer": "\n".join(lines), "citations": citations, "answer_method": "EXTRACTIVE_QUOTES"}

    result.update({
        "scope": scope,
        "not_found": False,
        "can_expand_scope": WIDER_SCOPE.get(scope) is not None,
        "suggested_scope": WIDER_SCOPE.get(scope),
        "legal_mode": legal_mode,
        "retrieval": {**diagnostics, "outcome": "ANSWERED"},
    })
    if primary is not None:
        result["document_id"] = primary.id
        result["original_filename"] = primary.original_filename
    _store(key, result, doc_ids)
    return result


def _store(key: str, result: Dict[str, Any], doc_ids: Sequence[str]) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        for k, _ in sorted(_CACHE.items(), key=lambda kv: kv[1][1])[:25]:
            _CACHE.pop(k, None)
    _CACHE[key] = (result, time.monotonic(), frozenset(doc_ids))


class RAGEngine:
    """Backwards-compatible facade over answer()."""

    @staticmethod
    def invalidate_cache(document_id: Optional[str] = None) -> None:
        invalidate_cache(document_id)

    @staticmethod
    async def answer_from_active_fir(document_id: str, query: str, user: User, db: AsyncSession, language: str = "en"):
        return await answer(db, user, query, scope="CURRENT_FIR", document_id=document_id, language=language)

    @staticmethod
    async def answer_fir_plus_legal(document_id: str, query: str, user: User, db: AsyncSession, language: str = "en"):
        return await answer(db, user, query, scope="FIR_AND_LAW", document_id=document_id, language=language)

    @staticmethod
    async def answer_from_knowledge_base(query: str, user: User, db: AsyncSession, language: str = "en",
                                         category: Optional[str] = "ALL"):
        return await answer(db, user, query, scope="KNOWLEDGE_BASE", categories=[category or "ALL"], language=language)

    @staticmethod
    async def answer_cross_case(query: str, user: User, db: AsyncSession, language: str = "en"):
        return await answer(db, user, query, scope="ALL_AUTHORIZED", language=language)


rag_engine = RAGEngine()
