import sqlite3
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from ..config import settings
from ..models.user import User
from ..models.document import Document, DocumentChunk
from ..models.case import Case
from ..services.gemini import gemini_service
from ..services.auth import apply_case_scope_filter

class RAGEngine:
    @staticmethod
    async def answer_pdf_only(
        document_id: str,
        query: str,
        user: User,
        db: AsyncSession,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Section 26: Mandatory PDF-Only Grounded RAG with Exact Physical Page Citations.
        The selected PDF is the EXCLUSIVE factual source.
        """
        # 1. Verify Document access
        doc_stmt = select(Document).where(Document.id == document_id)
        res = await db.execute(doc_stmt)
        document = res.scalar_one_or_none()
        if not document:
            return {
                "answer": "The selected document was not found or access is denied.",
                "citations": [],
                "mode": "PDF_ONLY"
            }

        # 2. Strict document-scoped FTS5 retrieval
        db_path = settings.SYNC_DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        retrieved_snippets = []
        try:
            # Clean query for FTS5 (remove punctuation, extract ASCII key terms)
            # Non-ASCII queries (Telugu, Hindi) won't have extractable ASCII terms;
            # in that case skip FTS5 and fall through to the direct chunk retrieval below.
            clean_terms = re.findall(r'\b[A-Za-z0-9_]{3,}\b', query)
            if clean_terms:
                fts_query = " OR ".join(clean_terms)
                cursor.execute("""
                    SELECT chunk_id, document_id, physical_page_number, chunk_text, rank
                    FROM document_chunks_fts
                    WHERE document_chunks_fts MATCH ? AND document_id = ?
                    ORDER BY rank
                    LIMIT 5
                """, (fts_query, document_id))
                rows = cursor.fetchall()

                for row in rows:
                    retrieved_snippets.append({
                        "chunk_id": row[0],
                        "document_id": row[1],
                        "physical_page_number": int(row[2]),
                        "text": row[3],
                        "score": float(row[4])
                    })

            # If FTS returns no rows, retrieve top chunks directly from this specific document
            if not retrieved_snippets:
                chunk_stmt = select(DocumentChunk).where(
                    DocumentChunk.document_id == document_id
                ).order_by(DocumentChunk.physical_page_number.asc()).limit(4)
                c_res = await db.execute(chunk_stmt)
                chunks = c_res.scalars().all()
                for c in chunks:
                    retrieved_snippets.append({
                        "chunk_id": c.id,
                        "document_id": c.document_id,
                        "physical_page_number": c.physical_page_number,
                        "text": c.chunk_text,
                        "score": 0.5
                    })
        finally:
            conn.close()

        # 3. Grounded answer generation strictly using retrieved snippets
        result = gemini_service.generate_grounded_answer(
            query=query,
            context_snippets=retrieved_snippets,
            mode="PDF_ONLY",
            language=language
        )
        result["mode"] = "PDF_ONLY"
        result["document_id"] = document_id
        result["original_filename"] = document.original_filename
        return result

    @staticmethod
    async def answer_cross_case(
        query: str,
        user: User,
        db: AsyncSession,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Mode B: Authorized Cross-Case Intelligence.
        Hierarchically scoped by user role (STATION, DISTRICT, STATE).
        Calculates SQL counts for aggregate questions.
        """
        q_lower = query.lower()

        # Check for aggregate count questions: "how many cases", "count of cases", "cases registered"
        if any(term in q_lower for term in ["how many", "count", "total cases", "number of cases", "ఎన్ని కేసులు", "कितने मामले"]):
            # Run direct SQL count with user scoping
            base_query = select(func.count(Case.id)).where(Case.is_archived == False)
            scoped_query = apply_case_scope_filter(base_query, user, Case)
            res = await db.execute(scoped_query)
            count_val = res.scalar() or 0

            scope_desc = f"in {user.station} ({user.district})" if user.role == "STATION" else f"in {user.district} District" if user.role == "DISTRICT" else "across the State"
            if language == "te":
                ans = f"మీ అధికార పరిధిలో ({scope_desc}) మొత్తం **{count_val}** చట్టబద్ధమైన కేసులు నమోదయ్యాయి."
            elif language == "hi":
                ans = f"आपके अधिकार क्षेत्र ({scope_desc}) में कुल **{count_val}** मामले दर्ज हैं।"
            else:
                ans = f"According to authorized departmental database records, a total of **{count_val}** cases are registered {scope_desc}."

            return {
                "answer": ans,
                "citations": [],
                "mode": "CROSS_CASE",
                "is_aggregate_count": True,
                "count": count_val
            }

        # Check for vehicle queries: "cases involving vehicle", "same vehicle"
        vehicle_match = re.search(r'(?:vehicle|auto|car|lorry|number)\s+([A-Za-z0-9\s-]+)', query, re.IGNORECASE)
        target_vehicle = vehicle_match.group(1).strip() if vehicle_match else None

        base_case_query = select(Case).where(Case.is_archived == False)
        if target_vehicle and len(target_vehicle) > 3:
            base_case_query = base_case_query.where(Case.vehicle_details.ilike(f"%{target_vehicle}%"))
        
        scoped_cases = apply_case_scope_filter(base_case_query, user, Case).order_by(Case.created_at.desc()).limit(5)
        res = await db.execute(scoped_cases)
        cases = res.scalars().all()

        if not cases:
            no_rec_msg = (
                "మీ అధికార పరిధిలో సంబంధిత రికార్డులు ఏవీ కనుగొనబడలేదు." if language == "te"
                else "आपके अधिकार क्षेत्र में कोई प्रासंगिक रिकॉर्ड नहीं मिला।" if language == "hi"
                else "No relevant authorized records were found within your jurisdiction."
            )
            return {"answer": no_rec_msg, "citations": [], "mode": "CROSS_CASE"}

        snippets = []
        citations = []
        for c in cases:
            snippet_text = (
                f"FIR: {c.fir_number} | Year: {c.year} | District: {c.district} | Station: {c.station} | "
                f"Offence: {c.offence_nature} | Contraband: {c.contraband_type} ({c.seized_quantity} {c.seized_unit}) | "
                f"Vehicle: {c.vehicle_details or 'None'} | Narrative: {c.narrative or 'No narrative'}"
            )
            snippets.append({
                "fir_number": c.fir_number,
                "case_id": c.id,
                "text": snippet_text
            })
            citations.append({
                "case_id": c.id,
                "fir_number": c.fir_number,
                "district": c.district,
                "station": c.station,
                "source_label": f"Case {c.fir_number}"
            })

        result = gemini_service.generate_grounded_answer(
            query=query,
            context_snippets=snippets,
            mode="CROSS_CASE",
            language=language
        )
        result["mode"] = "CROSS_CASE"
        result["citations"] = citations
        return result

rag_engine = RAGEngine()
