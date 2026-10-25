"""
Generate missing embeddings for already-indexed passages, in resumable batches.

Useful when embeddings could not be produced at ingestion time (no API key, retired model, or the
Gemini free tier's per-minute/daily quota). Each batch is committed separately, so the script can be
stopped and re-run on later days; it always continues with passages that still have no vector.
A document becomes INDEXED once all its passages have vectors from the same model and all its pages
had readable text.

Usage (from backend/):
    python scripts/backfill_embeddings.py                         # local database
    python scripts/backfill_embeddings.py --env-file ..\\..\\.env  # database and key from that env file
    python scripts/backfill_embeddings.py --env-file ..\\..\\.env --max-chunks 900 --official-first
"""
import argparse
import asyncio
import os
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env-file")
    p.add_argument("--max-chunks", type=int, default=900, help="Stop after this many passages (free tier: ~1,000/day)")
    p.add_argument("--batch-size", type=int, default=50)
    p.add_argument("--document-id", help="Only this document")
    p.add_argument("--official-first", action="store_true", help="Embed official legal sources before other documents")
    return p.parse_args()


def load_env_file(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


async def run(args):
    from sqlalchemy import case, func, or_, select, text, update
    from app.database import AsyncSessionLocal
    from app.models.document import Document, DocumentChunk, DocumentPage
    from app.services.embeddings import embedding_service, to_json, to_pgvector
    from app.services.ingestion import has_pg_vector_column

    if not embedding_service.is_available():
        sys.exit("No embedding provider: set GEMINI_API_KEY.")

    async with AsyncSessionLocal() as db:
        use_pg = await has_pg_vector_column(db)
        missing = text("embedding IS NULL") if use_pg else DocumentChunk.embedding_json.is_(None)
        docs_q = select(Document).where(Document.is_archived == False, Document.ingestion_status == "COMPLETED",  # noqa: E712
                                        or_(Document.index_status.is_(None), Document.index_status.notin_(("FAILED", "NEEDS_REVIEW"))))
        if args.document_id:
            docs_q = docs_q.where(Document.id == args.document_id)
        if args.official_first:
            docs_q = docs_q.order_by(case((Document.source_type == "OFFICIAL", 0), else_=1), Document.created_at)
        docs = (await db.execute(docs_q)).scalars().all()

        done, touched, stopped = 0, [], None
        for doc in docs:
            if done >= args.max_chunks or stopped:
                break
            if doc.embedding_model and doc.embedding_model != embedding_service.model:
                print(f"skip {doc.document_title or doc.original_filename}: embedded with {doc.embedding_model}; "
                      f"rebuild its index to switch models")
                continue
            while done < args.max_chunks:
                rows = (await db.execute(
                    select(DocumentChunk.id, DocumentChunk.chunk_text)
                    .where(DocumentChunk.document_id == doc.id, missing)
                    .order_by(DocumentChunk.chunk_index).limit(min(args.batch_size, args.max_chunks - done))
                )).all()
                if not rows:
                    break
                try:
                    vectors = await asyncio.to_thread(embedding_service._embed, [r[1] for r in rows], "RETRIEVAL_DOCUMENT")
                except Exception as e:
                    stopped = f"{type(e).__name__}: {str(e)[:200]}"
                    break
                for (cid, _), vec in zip(rows, vectors):
                    if use_pg:
                        await db.execute(text("UPDATE document_chunks SET embedding = CAST(:v AS extensions.vector) WHERE id = :id"),
                                         {"v": to_pgvector(vec), "id": cid})
                    else:
                        await db.execute(update(DocumentChunk).where(DocumentChunk.id == cid).values(embedding_json=to_json(vec)))
                doc.embedding_model = embedding_service.model
                await db.commit()
                done += len(rows)
                if doc.id not in touched:
                    touched.append(doc.id)
                print(f"  {doc.document_title or doc.original_filename}: +{len(rows)} (total this run {done})")

        # Refresh counts and promote fully embedded documents
        for doc_id in touched:
            doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one()
            total = (await db.execute(select(func.count()).where(DocumentChunk.document_id == doc_id))).scalar()
            still = (await db.execute(select(func.count()).select_from(DocumentChunk)
                                      .where(DocumentChunk.document_id == doc_id, missing))).scalar()
            pages = (await db.execute(select(func.count()).where(DocumentPage.document_id == doc_id))).scalar()
            readable = (await db.execute(select(func.count()).where(
                DocumentPage.document_id == doc_id,
                or_(DocumentPage.is_unreadable == False, DocumentPage.is_unreadable.is_(None))))).scalar()  # noqa: E712
            doc.embedded_chunk_count = total - still
            if still == 0 and readable == pages and doc.index_status in ("PARTIALLY_INDEXED", "NOT_INDEXED", None):
                doc.index_status = "INDEXED"
            await db.commit()
            print(f"{doc.document_title or doc.original_filename}: {total - still}/{total} passages embedded -> {doc.index_status}")

        remaining = (await db.execute(
            select(func.count()).select_from(DocumentChunk).join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.is_archived == False, Document.ingestion_status == "COMPLETED", missing)  # noqa: E712
        )).scalar()
        print(f"\nEmbedded {done} passages this run with {embedding_service.model}; {remaining} still without vectors.")
        if stopped:
            print(f"Stopped early: {stopped}\nRe-run later (the free tier allows about 1,000 embeddings per day).")


def main():
    args = parse_args()
    if args.env_file:
        load_env_file(args.env_file)
    sys.path.insert(0, BACKEND_DIR)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
