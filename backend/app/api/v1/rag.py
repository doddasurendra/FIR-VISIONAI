from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import get_db
from ...models.user import User
from ...schemas.schemas import RAGQueryRequest, RAGQueryResponse
from ...services.auth import get_current_user
from ...services.rag_engine import rag_engine
from ...services.audit import log_audit_event

router = APIRouter(prefix="/rag", tags=["AI FIR Assistance & Grounded RAG"])

@router.post("/query", response_model=RAGQueryResponse)
async def query_rag(
    req: RAGQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    AI FIR Assistance Chatbot API.
    - Mode A: SELECTED_FIR_ONLY / PDF_ONLY / IMAGE_ONLY — Grounded exclusively from selected FIR document with physical page citations.
    - Mode B: KNOWLEDGE_BASE_ONLY — Grounded exclusively from authorized Knowledge Base documents (acts, circulars, reference guides).
    - Mode C: FIR_PLUS_LEGAL / FIR_LEGAL — Combines selected FIR with authorized Legal Corpus sections, citing both separately.
    - Mode D: CROSS_CASE — Authorized cross-case intelligence scoped to user jurisdiction.
    """
    if req.mode in ("SELECTED_FIR_ONLY", "PDF_ONLY", "IMAGE_ONLY"):
        if not req.document_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="In document-grounded Mode A, a valid document_id is required as the exclusive factual source."
            )
        result = await rag_engine.answer_from_active_fir(
            document_id=req.document_id,
            query=req.query,
            user=current_user,
            db=db,
            language=req.language or "en"
        )
    elif req.mode in ("KNOWLEDGE_BASE_ONLY", "KNOWLEDGE_BASE"):
        result = await rag_engine.answer_from_knowledge_base(
            query=req.query,
            user=current_user,
            db=db,
            language=req.language or "en",
            category=req.category or "ALL"
        )
    elif req.mode in ("FIR_PLUS_LEGAL", "FIR_LEGAL"):
        if not req.document_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="In FIR + Legal Corpus mode, a valid document_id is required for the selected FIR."
            )
        result = await rag_engine.answer_fir_plus_legal(
            document_id=req.document_id,
            query=req.query,
            user=current_user,
            db=db,
            language=req.language or "en"
        )
    else:
        # Cross-case intelligence mode
        result = await rag_engine.answer_cross_case(
            query=req.query,
            user=current_user,
            db=db,
            language=req.language or "en"
        )

    # Log audit event for AI intelligence access (without leaking sensitive text)
    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="RAG_QUERY_EXECUTED",
        object_type="RAG_SESSION",
        object_id=req.document_id or (f"KB_{req.category or 'ALL'}" if req.mode in ("KNOWLEDGE_BASE_ONLY", "KNOWLEDGE_BASE") else "CROSS_CASE"),
        after_state={"mode": req.mode, "category": req.category, "language": req.language, "citations_count": len(result.get("citations", []))}
    )

    return result
