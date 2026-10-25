"""
Document processing entry point used by FIR upload, case evidence and replacement flows.

All extraction, chunking, embedding and indexing is done by services.ingestion; this module keeps
the original call signatures and the hash-based de-duplication those flows rely on.
"""
import hashlib
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.document import Document
from .ingestion import ingest_file, reindex_from_pages

logger = logging.getLogger(__name__)


def compute_sha256(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class PDFPipeline:
    @staticmethod
    async def process_document(
        file_path: str,
        original_filename: str,
        mime_type: str,
        user_id: str,
        db: AsyncSession,
        case_id: Optional[str] = None,
        trigger: str = "UPLOAD",
    ) -> Document:
        """
        Ingest a stored file and return its Document. A file whose hash was already ingested
        successfully returns the existing record unchanged. Raises ValueError when the file
        cannot be ingested (the failure is also recorded on the document and its ingestion job).
        """
        file_hash = compute_sha256(file_path)
        existing = (await db.execute(
            select(Document).where(Document.file_hash == file_hash).order_by(Document.created_at.desc())
        )).scalars().first()
        if existing and existing.ingestion_status == "COMPLETED":
            return existing

        if existing:
            # Re-use an unfinished record for the same file (e.g. the upload stub) instead of duplicating it
            doc = existing
            doc.original_filename = original_filename
            doc.stored_path = file_path
            doc.mime_type = mime_type
            if case_id:
                doc.case_id = case_id
        else:
            doc = Document(
                case_id=case_id,
                original_filename=original_filename,
                stored_path=file_path,
                file_hash=file_hash,
                mime_type=mime_type,
                physical_page_count=0,
                ingestion_status="PENDING",
                created_by=user_id,
            )
            db.add(doc)
        await db.commit()
        await db.refresh(doc)

        job = await ingest_file(db, doc, file_path, trigger=trigger, user_id=user_id)
        if job.status == "FAILED" and doc.ingestion_status == "FAILED":
            raise ValueError(job.error_message or "Document ingestion failed")
        return doc

    # Kept for callers that pick the pipeline by type
    @staticmethod
    async def process_pdf(file_path, original_filename, user_id, db, case_id=None) -> Document:
        return await PDFPipeline.process_document(file_path, original_filename, "application/pdf", user_id, db, case_id)

    @staticmethod
    async def process_image(file_path, original_filename, mime_type, user_id, db, case_id=None) -> Document:
        return await PDFPipeline.process_document(file_path, original_filename, mime_type, user_id, db, case_id)


async def reindex_document(doc_id: str, db: AsyncSession) -> None:
    """Rebuild chunks and embeddings from stored page text."""
    doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
    if doc:
        await reindex_from_pages(db, doc)


pdf_pipeline = PDFPipeline()
