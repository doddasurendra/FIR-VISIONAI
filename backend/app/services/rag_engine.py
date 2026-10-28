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
import asyncio
import collections
import hashlib
import logging
import re
import time
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.case import Case
from ..models.document import Document
from ..models.user import User
from .auth import apply_case_scope_filter, enforce_data_scope
from .document_access import apply_document_scope, get_authorized_document
from .gemini import gemini_service
from . import fact_answers
from .retrieval import REFERENCE_CATEGORIES, hybrid_search, id_tokens, query_terms, text_has_id, whole_document_passages

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
# The AI could not be used and no passage matched the question's words: say that, not "no evidence"
AI_UNAVAILABLE = {
    "en": ("The AI answering service is not responding right now ({reason}), and no passage of the selected "
           "documents matches the words of your question, so I cannot answer it reliably. Nothing was guessed. "
           "Try again in a minute, or ask using words that appear in the FIR (for example \"district\" or "
           "\"FIR No\")."),
    "te": ("AI సమాధాన సేవ ప్రస్తుతం స్పందించడం లేదు ({reason}), మరియు ఎంచుకున్న పత్రాల్లో మీ ప్రశ్నలోని పదాలతో "
           "సరిపోలే భాగం లేదు, కాబట్టి నమ్మదగిన సమాధానం ఇవ్వలేను. ఏదీ ఊహించలేదు. ఒక నిమిషం తర్వాత మళ్లీ "
           "ప్రయత్నించండి."),
    "hi": ("AI उत्तर सेवा अभी प्रतिक्रिया नहीं दे रही है ({reason}), और चयनित दस्तावेज़ों का कोई अंश आपके प्रश्न के "
           "शब्दों से मेल नहीं खाता, इसलिए मैं विश्वसनीय उत्तर नहीं दे सकता। कुछ भी अनुमान नहीं लगाया गया। एक मिनट "
           "बाद फिर प्रयास करें।"),
}
PROVIDER_REASONS = {
    "PROVIDER_TIMEOUT": "it did not answer in time",
    "PROVIDER_UNREACHABLE": "it could not be reached",
    "PROVIDER_OVERLOADED": "it is overloaded",
    "QUOTA_EXHAUSTED": "its usage quota is exhausted",
    "PROVIDER_NOT_CONFIGURED": "no AI key is configured",
    "PROVIDER_ERROR": "it returned an error",
}

# ── Time budget ──────────────────────────────────────────────────────────────
# A supported question should be answered within ~10 s end to end. Sign-in before this function and
# the audit write after it take another 1-3 s over a slow link to the database, so answering itself
# gets ANSWER_BUDGET_S: retrieval normally takes 1-2 s and the AI call gets what is left (never less
# than MIN_GENERATION_S). When it cannot answer in time, the officer gets the exact matching passages
# instead of a long wait or an error.
ANSWER_BUDGET_S = 7.0
MIN_GENERATION_S = 3.0
TRANSLATION_TIMEOUT_S = 3.0
SLOW_ANSWER_S = 10.0

# Recent request outcomes for the readiness endpoint (no question or document text)
_RECENT: Deque[Dict[str, Any]] = collections.deque(maxlen=200)


def recent_stats() -> Dict[str, Any]:
    items = list(_RECENT)
    if not items:
        return {"requests": 0}
    totals = sorted(i["total_ms"] for i in items)
    p95 = totals[max(0, int(round(0.95 * len(totals))) - 1)]
    return {
        "requests": len(items),
        "avg_ms": round(sum(totals) / len(totals)),
        "p95_ms": p95,
        "slow": sum(1 for t in totals if t > SLOW_ANSWER_S * 1000),
        "ai_unavailable": sum(1 for i in items if i.get("generation") == "UNAVAILABLE"),
        "last_provider_problem": next((i["provider_reason"] for i in reversed(items) if i.get("provider_reason")), None),
    }


class _Stages:
    """Milliseconds spent per stage of one request."""
    def __init__(self):
        self.start = self.last = time.perf_counter()
        self.ms: Dict[str, int] = {}

    def mark(self, name: str) -> None:
        now = time.perf_counter()
        self.ms[name] = self.ms.get(name, 0) + round((now - self.last) * 1000)
        self.last = now

    def elapsed(self) -> float:
        return time.perf_counter() - self.start

    def total_ms(self) -> int:
        return round(self.elapsed() * 1000)

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
                 "define", "defines", "contain", "contains", "describe", "describes", "mention", "mentions",
                 # generic nouns that say nothing about which fact is wanted
                 "person", "persons", "details", "detail"}
_COUNT_HINTS = ("how many", "number of cases", "total cases", "count of cases", "cases per", "cases by",
                "case count", "count cases", "ఎన్ని కేసులు", "कितने मामले")

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

# FIR forms label fields differently from how officers ask ("FIR No" for "FIR number", "Occurrence of
# offence" for "incident"), so passage matching without the AI accepts the form's wording too
_TERM_ALIASES = {
    "number": ("number", "no"),
    "incident": ("incident", "occurrence"),
    "date": ("date", "day"),
    "seized": ("seiz", "recovered"),
    "complainant": ("complainant", "informant"),
    "location": ("location", "place of occurrence", "address"),
    "place": ("place", "address"),
    "sections": ("section",),
}


def _term_present(term: str, low: str) -> bool:
    alternatives = _TERM_ALIASES.get(term)
    if alternatives:
        return any(_word_present(alt, low) for alt in alternatives)
    return _word_present(term, low)


def _word_present(term: str, low: str) -> bool:
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
    for i in range(len(sentences)):
        # Score a few fragments together: forms split a label from its value at ":" ("Occurrence of
        # Offence:" / "Day : 14.08.2024"), and the excerpt must show the value the question asks for
        score = _coverage(" ".join(sentences[i:i + 3]), terms)
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


async def _aggregate_count(db: AsyncSession, user: User, language: str, query: str = "") -> Dict[str, Any]:
    q = query.lower()
    by = (Case.station if any(w in q for w in ("station", "స్టేషన్", "थाना", "स्टेशन"))
          else Case.district if any(w in q for w in ("district", "జిల్లా", "ज़िला", "जिला")) else None)
    if by is not None:
        # Counts per station / district, only over the cases the user may see
        stmt = apply_case_scope_filter(
            select(by, func.count(Case.id)).where(Case.is_archived == False).group_by(by), user, Case)  # noqa: E712
        rows = sorted((await db.execute(stmt)).all(), key=lambda r: (-r[1], r[0] or ""))
        label = "station" if by is Case.station else "district"
        total = sum(r[1] for r in rows)
        lines = [f"**{total}** active case(s) in your jurisdiction, by {label}:", ""]
        lines += [f"- {name or 'not recorded'}: **{n}**" for name, n in rows]
        return {"answer": "\n".join(lines), "citations": [], "scope": "ALL_AUTHORIZED", "not_found": False,
                "is_aggregate_count": True, "count": total, "breakdown": [{label: r[0], "cases": r[1]} for r in rows],
                "answer_method": "DATABASE_COUNT", "can_expand_scope": False, "suggested_scope": None,
                "retrieval": {"outcome": "SQL_COUNT"}}
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


MAX_QUESTION_CHARS = 2000


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
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Answer a question from the authorised documents in scope. Every call is logged once with its trace id,
    outcome and the milliseconds spent per stage (never the question or document text).
    """
    import uuid
    stages = _Stages()
    trace_id = trace_id or uuid.uuid4().hex[:8]
    outcome, generation, provider_reason = "ERROR", None, None
    try:
        result = await _answer(db, user, query, stages, scope=scope, document_id=document_id, case_id=case_id,
                               categories=categories, language=language)
        outcome = (result.get("retrieval") or {}).get("outcome") or result.get("answer_method")
        generation = (result.get("generation") or {}).get("status")
        provider_reason = (result.get("generation") or {}).get("reason")
        result["trace_id"] = trace_id
        result["timings"] = {**stages.ms, "total_ms": stages.total_ms()}
        return result
    except HTTPException as e:
        outcome = f"HTTP_{e.status_code}"
        raise
    finally:
        total = stages.total_ms()
        slow = total > SLOW_ANSWER_S * 1000
        logger.log(logging.WARNING if (slow or outcome == "ERROR") else logging.INFO,
                   f"RAG trace={trace_id} scope={scope} lang={language} outcome={outcome} generation={generation} "
                   f"provider_reason={provider_reason} total_ms={total} stages={stages.ms}" + (" SLOW" if slow else ""))
        _RECENT.append({"total_ms": total, "outcome": outcome, "generation": generation,
                        "provider_reason": provider_reason})


async def _answer(
    db: AsyncSession,
    user: User,
    query: str,
    stages: _Stages,
    *,
    scope: str,
    document_id: Optional[str],
    case_id: Optional[str],
    categories: Optional[Sequence[str]],
    language: str,
) -> Dict[str, Any]:
    query = (query or "").strip()
    if not query:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter a question.")
    if len(query) > MAX_QUESTION_CHARS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"The question is too long ({len(query)} characters); keep it under {MAX_QUESTION_CHARS}.")
    language = language if language in NOT_FOUND else "en"

    if scope == "ALL_AUTHORIZED" and any(h in query.lower() for h in _COUNT_HINTS):
        return await _aggregate_count(db, user, language, query)

    resolved = await resolve_scope(db, user, scope, document_id, case_id, categories)
    stages.mark("authorize_scope")
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

    # A question naming a vehicle, FIR or phone number across several documents is answered from the
    # case records by exact match: complete, cited and within jurisdiction, with no model involved
    if scope != "CURRENT_FIR" and id_tokens(query):
        by_id = await fact_answers.answer_by_identifier(db, user, query, doc_ids, language)
        stages.mark("identifier_lookup")
        if by_id:
            wider = WIDER_SCOPE.get(scope)
            by_id.update({"scope": scope, "not_found": False, "can_expand_scope": wider is not None,
                          "suggested_scope": wider, "legal_mode": False,
                          "generation": {"status": "NOT_NEEDED", "reason": None},
                          "retrieval": {"documents_in_scope": len(doc_ids), "id_matches": len(by_id["citations"]),
                                        "outcome": "ANSWERED", "search": "EXACT_IDENTIFIER"}})
            _store(key, by_id, doc_ids)
            return by_id

    if not doc_ids:
        return _not_found(scope, language, {"documents_in_scope": 0}, "NO_SEARCHABLE_DOCUMENTS_IN_SCOPE")

    # Short case records are given to the model in full and in reading order, so questions about
    # the selected FIR do not depend on sharing words with its text
    record_ids = [primary.id] if primary is not None else (doc_ids if scope == "CASE" else [])
    whole = await whole_document_passages(db, record_ids,
                                          known_docs={primary.id: primary} if primary is not None else None)
    stages.mark("read_record")

    retrieval_query, translated = query, False
    if whole and set(record_ids) >= set(doc_ids):
        # The whole scope is already in hand: searching it again (question embedding plus several
        # database round trips) could only return passages that are already here
        sources = whole
        diagnostics = {"documents_in_scope": len(doc_ids), "keyword_hits": 0, "vector_hits": 0,
                       "semantic_search": False, "named_documents": 0, "title_hits": 0,
                       "returned": len(whole), "search": "SKIPPED_WHOLE_SCOPE_READ"}
    else:
        # Telugu/Hindi questions are searched in English when a translator is available; the answer
        # is still written in the officer's language.
        if re.search(r"[ఀ-౿ऀ-ॿ]", query):
            try:
                english = await asyncio.wait_for(
                    asyncio.to_thread(gemini_service.translate_for_search, query, TRANSLATION_TIMEOUT_S),
                    TRANSLATION_TIMEOUT_S + 1)
            except asyncio.TimeoutError:
                english = None
            if english:
                retrieval_query, translated = english, True
            stages.mark("translate")
        search = await hybrid_search(db, retrieval_query, document_ids=doc_ids, limit=8)
        stages.mark("search")
        sources, diagnostics = search["results"], search["diagnostics"]
        if whole:
            whole_ids = {w["chunk_id"] for w in whole}
            sources = whole + [s for s in sources if s["chunk_id"] not in whole_ids]
    diagnostics["query_translated"] = translated
    diagnostics["whole_record_passages"] = len(whole)
    if not sources:
        result = _not_found(scope, language, diagnostics, "NO_MATCHING_PASSAGES")
        _store(key, result, doc_ids)
        return result

    terms = query_terms(retrieval_query)
    legal_mode = any(h in retrieval_query.lower() for h in _LEGAL_HINTS) and any(
        s.get("doc_category") == "LEGAL_ACT" for s in sources)

    budget = max(MIN_GENERATION_S, ANSWER_BUDGET_S - stages.elapsed())
    # In a worker thread: the SDK call is blocking and would otherwise stall every other request.
    # The provider's own deadline cannot go below 10 s, so the budget is enforced here.
    generation_task = asyncio.ensure_future(asyncio.wait_for(
        asyncio.to_thread(gemini_service.answer_from_sources, query, sources,
                          language=language, legal_mode=legal_mode, timeout_s=budget),
        budget + 0.5))

    # Hand the connection back while the model works. Holding it (inside an open transaction) while
    # the provider was slow let the pooler drop it, and the audit write that followed then failed with
    # "connection was closed in the middle of operation" (error reference 0127eb95).
    if db.in_transaction():
        try:
            await db.commit()
        except Exception as e:
            # Read-only work: nothing is lost. The audit write gets a fresh connection.
            logger.warning(f"Releasing the database connection failed: {type(e).__name__}: {str(e)[:120]}")
            try:
                await db.rollback()
            except Exception:
                pass
    stages.mark("release_db")

    try:
        generated = await generation_task
    except asyncio.TimeoutError:
        generated = {"status": "UNAVAILABLE", "text": "", "used": [], "reason": "PROVIDER_TIMEOUT"}
    stages.mark("generate")
    generation = {"status": generated["status"], "model": generated.get("model"), "reason": generated.get("reason"),
                  "budget_s": round(budget, 1)}

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
        result["generation"] = generation
        _store(key, result, doc_ids)
        return result
    else:
        # No generation available. First, the facts the question asks for from the case record,
        # each cited with the passage containing it; then plain quotes of covering passages.
        transient = generated.get("reason") not in (None, "PROVIDER_NOT_CONFIGURED")
        case_id = primary.case_id if primary is not None else (resolved.get("case_id") if scope == "CASE" else None)
        record = getattr(primary, "_authorized_case", None) if primary is not None else None
        if record is None and case_id:
            record = await db.get(Case, case_id)
        stages.mark("read_case_record")
        facts = await fact_answers.answer_from_case(db, user, record, query, sources, language) if record else None
        if facts:
            facts["generation"] = generation
            facts.update({"scope": scope, "not_found": False, "can_expand_scope": WIDER_SCOPE.get(scope) is not None,
                          "suggested_scope": WIDER_SCOPE.get(scope), "legal_mode": legal_mode,
                          "retrieval": {**diagnostics, "outcome": "ANSWERED"}})
            if transient:
                facts["can_retry"] = True
            if primary is not None:
                facts["document_id"] = primary.id
                facts["original_filename"] = primary.original_filename
            if not transient:
                _store(key, facts, doc_ids)
            return facts

        def _coverage_text(s):
            # A passage's section label and document title count too ("Article 21", "Constitution")
            return " ".join(filter(None, (s.get("section_ref"), s.get("section_title"),
                                          s.get("document_title"), s.get("chunk_text", ""))))
        content_terms = [t for t in terms if t not in _FILLER_VERBS] or terms
        # Quotes are shown as the answer, so they must carry the question's subject: a passage about
        # the accused that lacks "bank account" does not answer "accused's bank account number"
        threshold = 1.0 if len(content_terms) <= 3 else 0.75
        strong = [(i, s) for i, s in enumerate(sources, start=1) if _coverage(_coverage_text(s), content_terms) >= threshold]
        # A passage containing an identifier the question names (exact match) answers it directly
        ids = [t["norm"] for t in id_tokens(query)]
        if ids:
            strong = [(i, s) for i, s in enumerate(sources, start=1)
                      if any(text_has_id(s.get("chunk_text") or "", n) for n in ids)] + strong
            strong = list({i: (i, s) for i, s in strong}.values())
        if not strong:
            if not transient:
                result = _not_found(scope, language, diagnostics, "PASSAGES_DO_NOT_COVER_QUESTION")
                _store(key, result, doc_ids)
                return result
            # The provider failed: say so instead of claiming the documents lack the answer. Not cached,
            # so the same question is answered normally once the provider recovers.
            result = _not_found(scope, language, diagnostics, "AI_UNAVAILABLE_NO_MATCHING_PASSAGE")
            result["answer"] = AI_UNAVAILABLE.get(language, AI_UNAVAILABLE["en"]).format(
                reason=PROVIDER_REASONS.get(generated["reason"], generated["reason"]))
            result["can_retry"] = True
            result["generation"] = generation
            return result
        strong = strong[:3]
        citations = [_citation(s, i, terms) for i, s in strong]
        lines = [EXTRACTIVE_INTRO[language]]
        for c in citations:
            lines.append(f"- [S{c['source_number']}] “{c['evidence_excerpt']}” — {c['source_label']}")
        result = {"answer": "\n".join(lines), "citations": citations, "answer_method": "EXTRACTIVE_QUOTES"}
        if transient:
            result["can_retry"] = True

    result["generation"] = generation
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
    if not result.get("can_retry"):
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
