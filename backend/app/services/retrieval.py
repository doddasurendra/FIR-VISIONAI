"""
Hybrid retrieval over document chunks: keyword (full-text) + vector similarity, fused with
reciprocal rank fusion. Every search is restricted to an explicit list of authorised document ids;
callers resolve that list with document_access before searching.

Backends:
- SQLite (local/offline): FTS5 bm25 for keywords; cosine over embedding_json for vectors.
- PostgreSQL (Supabase): ts_rank_cd over the generated content_tsv column; pgvector <=> for vectors.
  If the migration has not been applied yet, keyword search falls back to ILIKE term matching.
"""
import json
import logging
import re
from typing import Dict, List, Optional, Sequence

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.document import Document, DocumentChunk
from .embeddings import cosine, embedding_service, to_pgvector

logger = logging.getLogger(__name__)

RRF_K = 60
# Provenance tie-breaker for reference material (laws, circulars, guides, references): when an
# official text and an unverified summary are about equally relevant, the official one ranks first.
# Kept small because reciprocal-rank-fusion scores differ by only ~0.00025 per rank; case records
# (FIRs, evidence) are never weighted.
SOURCE_WEIGHTS = {"OFFICIAL": 1.03, "SECONDARY": 1.0, "UNVERIFIED": 0.97, "SYNTHETIC": 0.97}
REFERENCE_CATEGORIES = {"LEGAL_ACT", "CIRCULAR", "INVESTIGATION_GUIDE", "REFERENCE"}
_STOP = {
    "what", "which", "where", "when", "who", "whom", "whose", "how", "many", "much", "the", "and", "this",
    "that", "with", "from", "for", "are", "was", "were", "is", "be", "been", "being", "tell", "show", "give",
    "please", "about", "into", "does", "did", "have", "has", "had", "there", "their", "them", "they", "any",
    "all", "can", "could", "would", "should", "shall", "may", "not", "its", "per", "under", "upon", "than",
    "then", "also", "such", "these", "those", "document", "documents", "fir", "firs", "record", "records",
    "mentioned", "listed", "described", "according", "explain", "details", "detail", "uploaded", "selected",
    "say", "says", "said", "state", "states", "stated", "mean", "means", "provide", "provides", "contain", "contains",
}
_LEGACY_PREFIXES = ("GOVERNMENT OF ANDHRA PRADESH - LAW ENFORCEMENT EVIDENCE RECORD",)
_pg_tsv_column: Optional[bool] = None


def query_terms(query: str, limit: int = 10) -> List[str]:
    """Content words from a question, in order, de-duplicated. Keeps Telugu/Hindi words."""
    words = re.findall(r"[A-Za-z0-9ఀ-౿ऀ-ॿ]+(?:\(\d+\))?", query.lower())
    out: List[str] = []
    for w in words:
        base = re.sub(r"\(\d+\)$", "", w)
        if len(base) < 3 and not base.isdigit():
            continue
        if base in _STOP or base in out:
            continue
        out.append(base)
    return out[:limit]


def named_provisions(query: str) -> set:
    """Provisions named in a question, normalised like chunk section refs: {"section 303", "article 21a"}."""
    found = re.findall(r"\b(section|sec\.?|article|art\.?|rule)\s*(\d{1,3}[a-z]?)\b", query.lower())
    canon = {"sec": "section", "sec.": "section", "art": "article", "art.": "article"}
    return {f"{canon.get(kind, kind)} {num}" for kind, num in found}


def _title_core(title: str) -> str:
    """"The Bharatiya Nyaya Sanhita, 2023 (Act No. 45 of 2023)" -> "bharatiya nyaya sanhita"."""
    t = re.sub(r"[\(\[].*?[\)\]]", " ", (title or "").lower())
    t = re.sub(r",?\s*\b(1[89]|20)\d\d\b.*$", " ", t)
    t = re.sub(r"^\s*the\s+", "", t)
    return " ".join(re.findall(r"[a-z]+", t))


def title_named_in(question: str, title: str) -> Optional[set]:
    """
    The title words if the question names this document: its full name ("Bharatiya Nyaya Sanhita"),
    its name without "of India" ("the Constitution"), or its initials ("BNS", "BNSS", "BSA").
    Returns None when the document is not named.
    """
    core = _title_core(title)
    words = core.split()
    if not words:
        return None
    q = " ".join(re.findall(r"[a-z0-9]+", question.lower()))
    short = re.sub(r"\s+of india$", "", core)
    if len(short) >= 6 and re.search(rf"\b{re.escape(short)}\b", q):
        return set(words)
    initials = "".join(w[0] for w in words if w not in ("of", "and", "the", "for"))
    if len(initials) >= 3 and re.search(rf"\b{initials}\b", q):
        return set(words) | {initials}
    return None


def probe_terms(sample: str, n: int = 4) -> List[str]:
    """Distinctive words from a chunk, used to verify a freshly indexed document is searchable."""
    words = [w.lower() for w in re.findall(r"[A-Za-z]{6,}", sample)]
    uniq = [w for w in dict.fromkeys(words) if w not in _STOP]
    return sorted(uniq, key=len, reverse=True)[:n]


def _is_sqlite(db: AsyncSession) -> bool:
    try:
        return db.get_bind().dialect.name == "sqlite"
    except Exception:
        return False


async def _has_pg_tsv(db: AsyncSession) -> bool:
    global _pg_tsv_column
    if _pg_tsv_column is None:
        try:
            row = (await db.execute(text(
                "SELECT 1 FROM information_schema.columns WHERE table_name='document_chunks' AND column_name='content_tsv'"
            ))).first()
            _pg_tsv_column = row is not None
        except Exception:
            _pg_tsv_column = False
    return _pg_tsv_column


def _usable(text_: str) -> bool:
    return bool(text_) and not text_.startswith(_LEGACY_PREFIXES)


async def keyword_search(
    db: AsyncSession,
    query: str,
    *,
    document_ids: Sequence[str],
    limit: int = 20,
    terms: Optional[List[str]] = None,
) -> List[Dict]:
    """Ranked full-text matches restricted to document_ids. Returns chunk dicts with keyword_rank."""
    terms = terms or query_terms(query)
    if not terms or not document_ids:
        return []
    ids = list(document_ids)
    rows: List[Dict] = []

    def _merge(new_rows):
        # Passages matching all terms come first; any-term matches only fill the remaining slots
        seen = {r["chunk_id"] for r in rows}
        rows.extend(r for r in new_rows if r["chunk_id"] not in seen)

    if _is_sqlite(db):
        quoted = ['"' + t.replace('"', "") + '"' for t in terms]
        # The FTS row also holds the section heading; quote the stored chunk text, not the index text
        stmt = text(
            "SELECT f.chunk_id, f.document_id, f.physical_page_number, c.chunk_text, bm25(document_chunks_fts) AS score "
            "FROM document_chunks_fts f JOIN document_chunks c ON c.id = f.chunk_id "
            "WHERE document_chunks_fts MATCH :q AND f.document_id IN :ids "
            "ORDER BY score LIMIT :lim"
        ).bindparams(bindparam("ids", expanding=True))
        try:
            for fts in ([" AND ".join(quoted)] if len(quoted) > 1 else []) + [" OR ".join(quoted)]:
                if len(rows) >= limit:
                    break
                res = await db.execute(stmt, {"q": fts, "ids": ids, "lim": limit * 2})
                _merge([{"chunk_id": r[0], "document_id": r[1], "physical_page_number": int(r[2] or 1),
                         "chunk_text": r[3], "keyword_score": -float(r[4])} for r in res.fetchall()])
        except Exception as e:
            logger.warning(f"FTS5 search failed, using term matching: {e}")
    elif await _has_pg_tsv(db):
        # Normalisation 1 divides the rank by 1 + log(document length) so long passages don't dominate
        stmt = text(
            "SELECT c.id, c.document_id, c.physical_page_number, c.chunk_text, "
            "ts_rank_cd(c.content_tsv, q, 1) AS score "
            "FROM document_chunks c, websearch_to_tsquery('english', :q) q "
            "WHERE c.content_tsv @@ q AND c.document_id IN :ids ORDER BY score DESC LIMIT :lim"
        ).bindparams(bindparam("ids", expanding=True))
        for q in ([" ".join(terms)] if len(terms) > 1 else []) + [" OR ".join(terms)]:
            if len(rows) >= limit:
                break
            res = await db.execute(stmt, {"q": q, "ids": ids, "lim": limit * 2})
            _merge([{"chunk_id": r[0], "document_id": r[1], "physical_page_number": int(r[2] or 1),
                     "chunk_text": r[3], "keyword_score": float(r[4])} for r in res.fetchall()])

    if not rows:
        # Term-overlap fallback (non-English text, or PostgreSQL before the search migration)
        from sqlalchemy import or_
        conds = [DocumentChunk.chunk_text.ilike(f"%{t}%") for t in terms[:6]]
        res = await db.execute(
            select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.physical_page_number,
                   DocumentChunk.chunk_text)
            .where(DocumentChunk.document_id.in_(ids), or_(*conds)).limit(400)
        )
        for r in res.fetchall():
            low = (r[3] or "").lower()
            hits = sum(1 for t in terms if t in low)
            if hits:
                rows.append({"chunk_id": r[0], "document_id": r[1], "physical_page_number": int(r[2] or 1),
                             "chunk_text": r[3], "keyword_score": float(hits)})
        rows.sort(key=lambda x: x["keyword_score"], reverse=True)

    rows = [r for r in rows if _usable(r["chunk_text"])][:limit]
    for i, r in enumerate(rows):
        r["keyword_rank"] = i + 1
    return rows


async def vector_search(db: AsyncSession, query_vec: List[float], *, document_ids: Sequence[str],
                        limit: int = 20) -> List[Dict]:
    """Nearest chunks by cosine similarity, restricted to document_ids."""
    if not query_vec or not document_ids:
        return []
    ids = list(document_ids)
    rows: List[Dict] = []
    from .ingestion import has_pg_vector_column
    if await has_pg_vector_column(db):
        # Schema-qualified so it works whatever the connecting role's search_path is
        stmt = text(
            "SELECT id, document_id, physical_page_number, chunk_text, "
            "1 - (embedding OPERATOR(extensions.<=>) CAST(:v AS extensions.vector)) AS sim "
            "FROM document_chunks WHERE embedding IS NOT NULL AND document_id IN :ids "
            "ORDER BY embedding OPERATOR(extensions.<=>) CAST(:v AS extensions.vector) LIMIT :lim"
        ).bindparams(bindparam("ids", expanding=True))
        res = await db.execute(stmt, {"v": to_pgvector(query_vec), "ids": ids, "lim": limit})
        rows = [{"chunk_id": r[0], "document_id": r[1], "physical_page_number": int(r[2] or 1),
                 "chunk_text": r[3], "vector_score": float(r[4])} for r in res.fetchall()]
    else:
        res = await db.execute(
            select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.physical_page_number,
                   DocumentChunk.chunk_text, DocumentChunk.embedding_json)
            .where(DocumentChunk.document_id.in_(ids), DocumentChunk.embedding_json.isnot(None)).limit(20000)
        )
        scored = []
        for r in res.fetchall():
            try:
                sim = cosine(query_vec, json.loads(r[4]))
            except Exception:
                continue
            scored.append({"chunk_id": r[0], "document_id": r[1], "physical_page_number": int(r[2] or 1),
                           "chunk_text": r[3], "vector_score": sim})
        scored.sort(key=lambda x: x["vector_score"], reverse=True)
        rows = scored[:limit]
    rows = [r for r in rows if _usable(r["chunk_text"])]
    for i, r in enumerate(rows):
        r["vector_rank"] = i + 1
    return rows


async def hybrid_search(db: AsyncSession, query: str, *, document_ids: Sequence[str], limit: int = 8,
                        query_vec: Optional[List[float]] = None) -> Dict:
    """
    Fuse keyword and vector rankings (RRF). Returns {"results": [...], "diagnostics": {...}}.
    Diagnostics hold counts and methods only, never document text.
    """
    # A question that names an Act ("under the Bharatiya Nyaya Sanhita", "BNS") is searched in that
    # Act; other reference material is left out, case records in scope stay. The Act's name is not a
    # search term: thousands of passages in other Acts cite it and would outrank the Act itself.
    search_ids, terms = list(document_ids), query_terms(query)
    named_docs: List[str] = []
    meta = (await db.execute(
        select(Document.id, func.coalesce(Document.document_title, Document.original_filename), Document.doc_category)
        .where(Document.id.in_(list(document_ids)))
    )).fetchall()
    title_words: set = set()
    for doc_id, title, category in meta:
        if category in REFERENCE_CATEGORIES:
            words = title_named_in(query, title)
            if words:
                named_docs.append(doc_id)
                title_words |= words
    if named_docs:
        search_ids = named_docs + [d for d, _, c in meta if c not in REFERENCE_CATEGORIES]
        terms = [t for t in terms if t not in title_words] or terms
    kw = await keyword_search(db, query, document_ids=search_ids, limit=limit * 3, terms=terms)
    if named_docs and not kw:
        kw = await keyword_search(db, query, document_ids=document_ids, limit=limit * 3)
    title_hits = await _title_matches(db, query, terms, [(d, t) for d, t, _ in meta if d in set(search_ids)], limit)
    if query_vec is None and embedding_service.is_available():
        import asyncio
        query_vec = await asyncio.to_thread(embedding_service.embed_query, query)
    vec = []
    if query_vec:
        # Vectors from different models are not comparable: only search documents embedded by the
        # model that embedded this question
        same_model_ids = [r[0] for r in (await db.execute(
            select(Document.id).where(Document.id.in_(search_ids),
                                      Document.embedding_model == embedding_service.model)
        )).fetchall()]
        if same_model_ids:
            vec = await vector_search(db, query_vec, document_ids=same_model_ids, limit=limit * 3)

    fused: Dict[str, Dict] = {}
    # Provisions named in the question are looked up directly, so "Article 21" is always a candidate
    named_refs = named_provisions(query)
    if named_refs:
        rows_all = (await db.execute(
            select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.physical_page_number,
                   DocumentChunk.chunk_text, DocumentChunk.chunk_index,
                   func.coalesce(Document.document_title, Document.original_filename))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(search_ids), func.lower(DocumentChunk.section_ref).in_(named_refs))
            .limit(60)
        )).fetchall()
        # Several Acts have a "Section 63": prefer the Act whose title the question names
        q_terms = set(query_terms(query, limit=20))
        def _title_overlap(title):
            return len(q_terms & set(re.findall(r"[a-z0-9]+", (title or "").lower())))
        named_rows = sorted(rows_all, key=lambda r: (-_title_overlap(r[5]), r[4]))[:6]
        for r in named_rows:
            if _usable(r[3]):
                fused[r[0]] = {"chunk_id": r[0], "document_id": r[1], "physical_page_number": int(r[2] or 1),
                               "chunk_text": r[3], "rrf": 1.0 / (RRF_K + 1), "named_match": True}
    for r in kw:
        entry = fused.setdefault(r["chunk_id"], dict(r))
        entry["keyword_rank"] = r["keyword_rank"]
        entry["rrf"] = entry.get("rrf", 0.0) + 1.0 / (RRF_K + r["keyword_rank"])
    for r in vec:
        entry = fused.setdefault(r["chunk_id"], dict(r))
        entry["vector_score"] = r["vector_score"]
        entry["vector_rank"] = r["vector_rank"]
        entry["rrf"] = entry.get("rrf", 0.0) + 1.0 / (RRF_K + r["vector_rank"])
    for r in title_hits:
        entry = fused.setdefault(r["chunk_id"], dict(r))
        entry["title_rank"] = r["title_rank"]
        entry["rrf"] = entry.get("rrf", 0.0) + 1.0 / (RRF_K + r["title_rank"])
    candidates = list(fused.values())
    await _attach_metadata(db, candidates)
    for c in candidates:
        # Prefer authoritative text when an official source and a summary match equally well
        c["source_weight"] = (SOURCE_WEIGHTS.get(c.get("source_type") or "UNVERIFIED", 1.0)
                              if c.get("doc_category") in REFERENCE_CATEGORIES else 1.0)
        c["score"] = c["rrf"] * c["source_weight"]
        # A provision named in the question ("Section 4", "Article 21") outranks its neighbours
        if named_refs and (c.get("section_ref") or "").lower() in named_refs:
            c["score"] *= 1.5
    ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)
    top = ranked[:limit]
    # A document whose title carries most of the question's words is what the question is about,
    # but a title match alone ranks below passages that match on both words and meaning. Keep a
    # slot, right after the best result, for the best passage of up to two such documents.
    shown = {c["document_id"] for c in top}
    reserved = []
    for c in sorted((c for c in ranked if c.get("title_rank")), key=lambda c: c["title_rank"]):
        if len(reserved) == 2:
            break
        if c["document_id"] not in shown:
            reserved.append(c)
            shown.add(c["document_id"])
    if reserved:
        top = top[:1] + reserved + top[1:limit - len(reserved)]
    ranked = top
    return {
        "results": ranked,
        "diagnostics": {
            "documents_in_scope": len(document_ids),
            "keyword_hits": len(kw),
            "vector_hits": len(vec),
            "semantic_search": bool(query_vec),
            "named_documents": len(named_docs),
            "title_hits": len(title_hits),
            "returned": len(ranked),
        },
    }


async def _title_matches(db: AsyncSession, query: str, terms: List[str], docs: List[tuple], limit: int) -> List[Dict]:
    """
    Passages from documents whose title carries most of the question's words ("checkpost protocol
    circular" -> "Circular 08/2024 - Border Checkpost Vehicle Inspection Protocol"). Titles are not
    part of the passage text, so plain keyword search misses words that only the title contains.
    Returns ranked chunk dicts with title_rank.
    """
    if len(terms) < 2:
        return []
    need = max(2, (len(terms) + 1) // 2)
    scored = []
    for doc_id, title in docs:
        low = (title or "").lower()
        n = sum(1 for t in terms if (t[:6] if len(t) > 6 else t) in low)
        if n >= need:
            scored.append((n, doc_id))
    title_docs = [d for _, d in sorted(scored, reverse=True)[:5]]
    if not title_docs:
        return []
    rows = await keyword_search(db, query, document_ids=title_docs, limit=limit, terms=terms)
    for r in rows:
        # Ranked by title here; the passage's own keyword rank comes from the main keyword search
        r.pop("keyword_rank", None)
        r.pop("keyword_score", None)
    found = {r["document_id"] for r in rows}
    missing = [d for d in title_docs if d not in found]
    if missing:
        # The best passage of a title match may share no words with the question: use its opening passage
        first = (await db.execute(
            select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.physical_page_number,
                   DocumentChunk.chunk_text, DocumentChunk.chunk_index)
            .where(DocumentChunk.document_id.in_(missing)).order_by(DocumentChunk.chunk_index)
        )).fetchall()
        seen = set()
        for r in first:
            if r[1] not in seen and _usable(r[3]):
                seen.add(r[1])
                rows.append({"chunk_id": r[0], "document_id": r[1], "physical_page_number": int(r[2] or 1),
                             "chunk_text": r[3]})
    order = {d: i for i, d in enumerate(title_docs)}
    rows.sort(key=lambda r: order[r["document_id"]])
    rows = rows[:limit]
    for i, r in enumerate(rows):
        r["title_rank"] = i + 1
    return rows


async def whole_document_passages(db: AsyncSession, document_ids: Sequence[str], max_chunks: int = 16,
                                  known_docs: Optional[Dict[str, Document]] = None) -> List[Dict]:
    """
    Every passage of short case records (an FIR image is typically 2-6 passages), in reading order;
    [] when they are longer than max_chunks. A general question about "this FIR" ("What incident is
    described?") may share no words with the form's text, so short records are read in full.
    known_docs: Document rows the caller already loaded (saves a database round trip).
    """
    if not document_ids:
        return []
    rows = (await db.execute(
        select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.physical_page_number,
               DocumentChunk.chunk_text, DocumentChunk.section_ref, DocumentChunk.section_title)
        .where(DocumentChunk.document_id.in_(list(document_ids)))
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        .limit(max_chunks + 1)
    )).fetchall()
    if len(rows) > max_chunks:
        return []
    out = [{"chunk_id": r[0], "document_id": r[1], "physical_page_number": int(r[2] or 1), "chunk_text": r[3],
            "section_ref": r[4], "section_title": r[5],
            "rrf": 0.0, "score": 0.0, "whole_document": True} for r in rows if _usable(r[3])]
    await _attach_metadata(db, out, known_docs=known_docs)
    return out


async def _attach_metadata(db: AsyncSession, rows: List[Dict],
                           known_docs: Optional[Dict[str, Document]] = None) -> None:
    if not rows:
        return
    # Rows read with their section fields already have them; only look up the others
    need_sections = [x["chunk_id"] for x in rows if "section_ref" not in x]
    chunk_meta = {
        r[0]: (r[1], r[2]) for r in (await db.execute(
            select(DocumentChunk.id, DocumentChunk.section_ref, DocumentChunk.section_title)
            .where(DocumentChunk.id.in_(need_sections))
        )).fetchall()
    } if need_sections else {}
    docs = dict(known_docs or {})
    missing_docs = {x["document_id"] for x in rows} - set(docs)
    if missing_docs:
        docs.update({
            d.id: d for d in (await db.execute(
                select(Document).where(Document.id.in_(missing_docs))
            )).scalars().all()
        })
    for r in rows:
        if "section_ref" not in r:
            r["section_ref"], r["section_title"] = chunk_meta.get(r["chunk_id"], (None, None))
        d = docs.get(r["document_id"])
        if d:
            r.update({
                "document_title": d.document_title or d.original_filename,
                "original_filename": d.original_filename,
                "doc_category": d.doc_category,
                "source_type": d.source_type,
                "legal_status": d.legal_status,
                "source_url": d.source_url,
                "case_id": d.case_id,
                "is_image": bool(d.mime_type and d.mime_type.startswith("image/")),
                "record_kind": d.record_kind,
            })
