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
) -> List[Dict]:
    """Ranked full-text matches restricted to document_ids. Returns chunk dicts with keyword_rank."""
    terms = query_terms(query)
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
    kw = await keyword_search(db, query, document_ids=document_ids, limit=limit * 3)
    if query_vec is None and embedding_service.is_available():
        import asyncio
        query_vec = await asyncio.to_thread(embedding_service.embed_query, query)
    vec = []
    if query_vec:
        # Vectors from different models are not comparable: only search documents embedded by the
        # model that embedded this question
        same_model_ids = [r[0] for r in (await db.execute(
            select(Document.id).where(Document.id.in_(list(document_ids)),
                                      Document.embedding_model == embedding_service.model)
        )).fetchall()]
        if same_model_ids:
            vec = await vector_search(db, query_vec, document_ids=same_model_ids, limit=limit * 3)

    fused: Dict[str, Dict] = {}
    # Provisions named in the question are looked up directly, so "Article 21" is always a candidate
    named_refs = named_provisions(query)
    if named_refs:
        named_rows = (await db.execute(
            select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.physical_page_number, DocumentChunk.chunk_text)
            .where(DocumentChunk.document_id.in_(list(document_ids)), func.lower(DocumentChunk.section_ref).in_(named_refs))
            .order_by(DocumentChunk.chunk_index).limit(6)
        )).fetchall()
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
    ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)[:limit]
    return {
        "results": ranked,
        "diagnostics": {
            "documents_in_scope": len(document_ids),
            "keyword_hits": len(kw),
            "vector_hits": len(vec),
            "semantic_search": bool(query_vec),
            "returned": len(ranked),
        },
    }


async def _attach_metadata(db: AsyncSession, rows: List[Dict]) -> None:
    if not rows:
        return
    chunk_meta = {
        r[0]: (r[1], r[2]) for r in (await db.execute(
            select(DocumentChunk.id, DocumentChunk.section_ref, DocumentChunk.section_title)
            .where(DocumentChunk.id.in_([x["chunk_id"] for x in rows]))
        )).fetchall()
    }
    docs = {
        d.id: d for d in (await db.execute(
            select(Document).where(Document.id.in_({x["document_id"] for x in rows}))
        )).scalars().all()
    }
    for r in rows:
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
