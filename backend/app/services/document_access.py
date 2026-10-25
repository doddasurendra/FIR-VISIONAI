"""
Single source of truth for document-level authorization.

Every route that returns document content (list, pages, view, download, extraction, search and
chatbot context) must use these helpers so a user cannot reach another jurisdiction's records by
changing a URL, query parameter or document id.

Rules, in order:
1. STATE role: all documents.
2. Statewide reference categories (laws, circulars, guides, reference material): all roles.
3. Documents explicitly marked statewide (district = STATE / ALL / Statewide): all roles.
4. Documents linked to a case: the case's district/station scope.
5. Unlinked documents with a district: that district (and station, for STATION users).
6. Unlinked documents with no district: the uploader's jurisdiction (or the uploader themself).
"""
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.case import Case
from ..models.document import Document
from ..models.user import User
from .auth import enforce_data_scope

STATEWIDE_CATEGORIES = ("LEGAL_ACT", "CIRCULAR", "INVESTIGATION_GUIDE", "REFERENCE")
STATEWIDE_DISTRICT_MARKERS = ("state", "all", "statewide", "all districts")


def _same(a: Optional[str], b: Optional[str]) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def can_access_document(
    user: User,
    doc: Document,
    case: Optional[Case] = None,
    creator: Optional[User] = None,
) -> bool:
    """Pure check; pass the linked case and uploader when the document has them."""
    if user.role == "STATE":
        return True
    if (doc.doc_category or "").upper() in STATEWIDE_CATEGORIES:
        return True
    if doc.district and doc.district.strip().lower() in STATEWIDE_DISTRICT_MARKERS:
        return True
    if doc.case_id:
        # A linked case decides access; a dangling case link fails closed
        return case is not None and enforce_data_scope(user, case.district, case.station)
    if doc.district:
        if user.role == "DISTRICT":
            return _same(doc.district, user.district)
        if user.role == "STATION":
            return _same(doc.district, user.district) and (doc.station is None or _same(doc.station, user.station))
        return False
    if doc.created_by == user.id:
        return True
    if creator is None:
        return False
    if user.role == "DISTRICT":
        return _same(creator.district, user.district)
    if user.role == "STATION":
        return _same(creator.district, user.district) and _same(creator.station, user.station)
    return False


async def user_can_access_document(db: AsyncSession, user: User, doc: Document) -> bool:
    """Load the case/uploader as needed and apply can_access_document."""
    case = None
    creator = None
    if doc.case_id:
        case = (await db.execute(select(Case).where(Case.id == doc.case_id))).scalar_one_or_none()
    elif not doc.district and doc.created_by and doc.created_by != user.id:
        creator = (await db.execute(select(User).where(User.id == doc.created_by))).scalar_one_or_none()
    return can_access_document(user, doc, case=case, creator=creator)


async def get_authorized_document(db: AsyncSession, user: User, document_id: str) -> Document:
    """Fetch a document or raise 404/403. Use in every route that serves document content."""
    doc = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if not await user_can_access_document(db, user, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: this document belongs to a jurisdiction outside your authorization.",
        )
    return doc


def _lower_eq(column, value: Optional[str]):
    return func.lower(column) == (value or "").strip().lower()


def document_scope_condition(user: User):
    """SQL condition equivalent to can_access_document, for list, search and retrieval queries."""
    if user.role == "STATE":
        return None
    if user.role == "DISTRICT":
        case_scope = select(Case.id).where(_lower_eq(Case.district, user.district))
        own_area = _lower_eq(Document.district, user.district)
        peer_users = select(User.id).where(_lower_eq(User.district, user.district))
    elif user.role == "STATION":
        case_scope = select(Case.id).where(
            _lower_eq(Case.district, user.district), _lower_eq(Case.station, user.station)
        )
        own_area = and_(
            _lower_eq(Document.district, user.district),
            or_(Document.station.is_(None), _lower_eq(Document.station, user.station)),
        )
        peer_users = select(User.id).where(
            _lower_eq(User.district, user.district), _lower_eq(User.station, user.station)
        )
    else:
        return Document.id == "__no_access__"

    return or_(
        Document.doc_category.in_(STATEWIDE_CATEGORIES),
        func.lower(Document.district).in_(STATEWIDE_DISTRICT_MARKERS),
        and_(Document.case_id.isnot(None), Document.case_id.in_(case_scope)),
        and_(Document.case_id.is_(None), Document.district.isnot(None), own_area),
        and_(
            Document.case_id.is_(None),
            Document.district.is_(None),
            or_(Document.created_by == user.id, Document.created_by.in_(peer_users)),
        ),
    )


def apply_document_scope(stmt, user: User):
    """Restrict a select(Document ...) statement to documents the user may access."""
    cond = document_scope_condition(user)
    return stmt if cond is None else stmt.where(cond)
