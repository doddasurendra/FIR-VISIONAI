import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import get_db
from ...models.user import User
from ...schemas.schemas import RAGQueryRequest, RAGQueryResponse
from ...services.auth import get_current_user
from ...services.rag_engine import LEGACY_MODES, SCOPES, answer
from ...services.audit import is_connection_error, log_audit_event_with_retry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["AI FIR Assistance & Grounded RAG"])

@router.post("/query", response_model=RAGQueryResponse)
async def query_rag(
    req: RAGQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    FIR VisionAI research assistant. Answers only from authorised documents in the chosen scope:
    - CURRENT_FIR: the selected FIR document (document_id required).
    - CASE: all searchable documents of a case the user may access (case_id, or document_id of a case FIR).
    - FIR_AND_LAW: the selected FIR plus the legal corpus, cited separately.
    - KNOWLEDGE_BASE: authorised Knowledge Base documents (optional categories filter).
    - ALL_AUTHORIZED: every searchable document within the user's jurisdiction.
    Legacy `mode` values (PDF_ONLY, KNOWLEDGE_BASE_ONLY, FIR_PLUS_LEGAL, CROSS_CASE, ...) map to scopes.
    The response carries a trace_id that matches the server log line for this request.
    """
    scope = (req.scope or LEGACY_MODES.get((req.mode or "").upper(), "")).upper()
    if scope not in SCOPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown search scope or mode '{req.scope or req.mode}'.")
    categories = req.categories or ([req.category] if req.category else None)
    trace_id = uuid.uuid4().hex[:8]

    try:
        result = await answer(
            db, current_user, req.query,
            scope=scope, document_id=req.document_id, case_id=req.case_id,
            categories=categories, language=req.language or "en", trace_id=trace_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        if not is_connection_error(e):
            raise
        logger.error(f"RAG trace={trace_id} database unavailable: {type(e).__name__}: {str(e)[:160]}")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"The case database could not be reached, so the question was not answered. "
                            f"Check the connection and try again (reference {trace_id}).")
    result.setdefault("mode", req.mode if req.scope is None else scope)
    result.setdefault("category", req.category)

    # Audit the query without storing document text. Retried once on a fresh connection if the
    # first one was dropped; the answer is not returned unless the query was audited.
    try:
        await log_audit_event_with_retry(
            db,
            actor_id=current_user.id,
            actor_username=current_user.username,
            action_type="RAG_QUERY_EXECUTED",
            object_type="RAG_SESSION",
            object_id=req.document_id or req.case_id or f"SCOPE_{scope}",
            after_state={
                "scope": scope,
                "language": req.language,
                "trace_id": trace_id,
                "citations_count": len(result.get("citations", [])),
                "not_found": result.get("not_found", False),
                "retrieval": result.get("retrieval"),
            },
            refresh=False,
        )
    except Exception as e:
        if not is_connection_error(e):
            raise
        logger.error(f"RAG trace={trace_id} audit write failed after retry: {type(e).__name__}: {str(e)[:160]}")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"The answer could not be recorded in the audit log because the database connection "
                            f"was lost. Ask again - the answer is kept for a few minutes, so it will be quick "
                            f"(reference {trace_id}).")
    return result
