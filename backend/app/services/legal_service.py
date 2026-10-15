import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from ..models.case import Case, CaseField
from ..models.legal import LegalCorpus, CaseLegalSection
from ..models.user import User

BNS_COMMENCEMENT_DATE = "2024-07-01"

class LegalService:
    @staticmethod
    async def recommend_sections_for_case(
        case_id: str,
        user: User,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Section 27: Case Facts -> Candidate Sections Workflow.
        Identifies offence category, evaluates statutory ingredients,
        and enforces incident-date-aware Acts (AP Excise Act, BNS 2023 vs IPC).
        """
        # 1. Fetch authorized case
        stmt = select(Case).where(Case.id == case_id)
        res = await db.execute(stmt)
        case = res.scalar_one_or_none()
        if not case:
            return {"error": "Case not found", "candidates": []}

        # 2. Date-Aware Act Selection
        is_date_ambiguous = case.offence_date is None
        is_post_bns = False
        if case.offence_date:
            offence_date_str = case.offence_date.strftime("%Y-%m-%d")
            is_post_bns = offence_date_str >= BNS_COMMENCEMENT_DATE

        # 3. Retrieve verified legal corpus
        corpus_stmt = select(LegalCorpus).where(LegalCorpus.verification_status == "VERIFIED")
        corpus_res = await db.execute(corpus_stmt)
        all_sections = corpus_res.scalars().all()

        candidates = []
        narrative_lower = (case.narrative or "").lower()
        offence_nature_lower = (case.offence_nature or "").lower()
        contraband_lower = (case.contraband_type or "").lower()
        full_facts_text = f"{narrative_lower} {offence_nature_lower} {contraband_lower}"

        for sec in all_sections:
            # Check date applicability
            if "Bharatiya Nyaya Sanhita" in sec.act_name and not is_post_bns and not is_date_ambiguous:
                continue # Skip BNS if incident explicitly happened before 1 July 2024
            if "Indian Penal Code" in sec.act_name and is_post_bns:
                continue # Skip IPC if incident occurred on/after 1 July 2024

            matched_facts = []
            missing_elements = []
            
            try:
                ingredients = json.loads(sec.essential_ingredients_json)
            except Exception:
                ingredients = []

            # Fact matching against statutory elements
            # Excise matching
            if "Excise" in sec.act_name:
                if sec.section_number == "Section 34(a)":
                    if any(t in full_facts_text for t in ["liquor", "distill", "transport", "id liquor", "possession", "gudumba"]):
                        matched_facts.append(f"Recorded contraband '{case.contraband_type or 'liquor'}' seized: {case.seized_quantity or 'Unspecified'} {case.seized_unit or 'units'}.")
                    if not case.seized_quantity:
                        missing_elements.append("Exact chemical lab test report / proof of alcoholic concentration.")
                elif sec.section_number == "Section 34(b)":
                    if any(t in full_facts_text for t in ["ganja", "cannabis", "hemp", "cultivation"]):
                        matched_facts.append(f"Recorded possession/cultivation of cannabis or hemp related substance.")
                    else:
                        continue
                elif sec.section_number == "Section 37A":
                    if any(t in full_facts_text for t in ["death", "injury", "poison", "methanol", "hospital", "hooch"]):
                        matched_facts.append("Recorded hooch poisoning / injurious adulteration mentioned in narrative.")
                    else:
                        continue
                elif sec.section_number == "Section 45":
                    if case.vehicle_details:
                        matched_facts.append(f"Conveyance identified: {case.vehicle_details} used in transport.")
                    else:
                        missing_elements.append("Conveyance / vehicle details not yet established in FIR.")

            # General Criminal Law matching (BNS / IPC)
            elif "Theft" in sec.section_title:
                if any(t in full_facts_text for t in ["theft", "stolen", "snatched", "dacoity"]):
                    matched_facts.append("Dishonest taking of movable property recorded.")
                else:
                    continue
            elif "Rash driving" in sec.section_title:
                if any(t in full_facts_text for t in ["rash", "speed", "negligent", "accident", "collided", "hit"]):
                    matched_facts.append("Rash or negligent vehicular operation recorded.")
                else:
                    continue
            elif "death by negligence" in sec.section_title.lower():
                if any(t in full_facts_text for t in ["died", "deceased", "death", "fatal"]):
                    matched_facts.append("Fatality recorded from vehicular impact or negligence.")
                else:
                    continue

            # If any matched facts exist, add as candidate
            if matched_facts:
                candidates.append({
                    "legal_corpus_id": sec.id,
                    "act_name": sec.act_name,
                    "section_number": sec.section_number,
                    "section_title": sec.section_title,
                    "full_text": sec.full_text,
                    "explanation": sec.explanation,
                    "penalty_text": sec.penalty_text,
                    "effective_date": sec.effective_date,
                    "source_url": sec.source_url,
                    "matched_facts": matched_facts,
                    "missing_elements": missing_elements,
                    "confidence_score": 0.90 if not missing_elements else 0.75,
                    "requires_officer_review": True,
                    "status_label": "Potentially relevant — officer review required"
                })

        return {
            "case_id": case.id,
            "fir_number": case.fir_number,
            "offence_date": case.offence_date.strftime("%Y-%m-%d") if case.offence_date else None,
            "is_date_ambiguous": is_date_ambiguous,
            "applicable_regime": "Bharatiya Nyaya Sanhita (BNS 2023)" if is_post_bns else "Indian Penal Code (IPC Historical)" if not is_date_ambiguous else "Ambiguous incident date — Officer verification required",
            "candidates": candidates
        }

    @staticmethod
    async def record_officer_decision(
        case_id: str,
        legal_corpus_id: str,
        decision: str, # ACCEPTED, REJECTED
        reason: str,
        user: User,
        db: AsyncSession
    ) -> CaseLegalSection:
        """
        Record authorized officer's human verification of a legal section.
        Preserves decision and audit history.
        """
        # Fetch corpus info
        c_stmt = select(LegalCorpus).where(LegalCorpus.id == legal_corpus_id)
        res = await db.execute(c_stmt)
        corpus = res.scalar_one_or_none()
        if not corpus:
            raise ValueError("Legal corpus provision not found")

        # Check existing
        existing_stmt = select(CaseLegalSection).where(
            CaseLegalSection.case_id == case_id,
            CaseLegalSection.legal_corpus_id == legal_corpus_id
        )
        existing_res = await db.execute(existing_stmt)
        record = existing_res.scalar_one_or_none()

        if not record:
            record = CaseLegalSection(
                case_id=case_id,
                legal_corpus_id=legal_corpus_id,
                act_name=corpus.act_name,
                section_number=corpus.section_number,
                section_title=corpus.section_title,
                recommendation_type="HUMAN_VERIFIED",
                officer_decision=decision,
                decision_reason=reason,
                reviewed_by=user.id,
                reviewed_at=datetime.utcnow()
            )
            db.add(record)
        else:
            record.officer_decision = decision
            record.decision_reason = reason
            record.reviewed_by = user.id
            record.reviewed_at = datetime.utcnow()

        await db.commit()
        await db.refresh(record)
        return record

legal_service = LegalService()
