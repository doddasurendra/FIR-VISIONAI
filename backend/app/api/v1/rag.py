from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import get_db
from ...models.user import User
from ...schemas.schemas import RAGQueryRequest, RAGQueryResponse
from ...services.auth import get_current_user
from ...services.rag_engine import LEGACY_MODES, SCOPES, answer
from ...services.audit import log_audit_event

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
    """
    scope = (req.scope or LEGACY_MODES.get((req.mode or "").upper(), "")).upper()
    if scope not in SCOPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown search scope or mode '{req.scope or req.mode}'.")
    categories = req.categories or ([req.category] if req.category else None)

    result = await answer(
        db, current_user, req.query,
        scope=scope, document_id=req.document_id, case_id=req.case_id,
        categories=categories, language=req.language or "en",
    )
    result.setdefault("mode", req.mode if req.scope is None else scope)
    result.setdefault("category", req.category)

    # Audit the query without storing document text
    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="RAG_QUERY_EXECUTED",
        object_type="RAG_SESSION",
        object_id=req.document_id or req.case_id or f"SCOPE_{scope}",
        after_state={
            "scope": scope,
            "language": req.language,
            "citations_count": len(result.get("citations", [])),
            "not_found": result.get("not_found", False),
            "retrieval": result.get("retrieval"),
        },
    )
    return result
