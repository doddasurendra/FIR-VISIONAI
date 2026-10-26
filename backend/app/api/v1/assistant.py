"""FIR VisionAI voice assistant API (questions arrive as text: speech is transcribed in the browser)."""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models.user import User
from ...services import voice_assistant
from ...services.audit import log_audit_event
from ...services.auth import get_current_user

router = APIRouter(prefix="/assistant", tags=["Voice Assistant"])


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class AssistantQuery(BaseModel):
    question: str = Field(max_length=1000)
    language: Literal["auto", "en", "te", "hi"] = "auto"
    history: List[Turn] = Field(default_factory=list, max_length=12)
    input_mode: Literal["voice", "text"] = "text"


@router.post("/query")
async def ask(req: AssistantQuery, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Ask a question.")
    result = await voice_assistant.answer(db, current_user, question, req.language,
                                          [t.model_dump() for t in req.history][-6:])
    # Metadata only: no transcript, answer text or audio is stored
    try:
        await log_audit_event(db=db, actor_id=current_user.id, actor_username=current_user.username,
                              action_type="VOICE_ASSISTANT_QUERY", object_type="ASSISTANT", object_id=result["intent"],
                              after_state={"language": result["language"], "intent": result["intent"],
                                           "input_mode": req.input_mode, "grounding": result.get("grounding")})
    except Exception:
        await db.rollback()
    return result
