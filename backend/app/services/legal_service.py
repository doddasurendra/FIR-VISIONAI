import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from ..models.case import Case, CaseField
from ..models.document import Document, DocumentChunk
from ..models.legal import LegalCorpus, CaseLegalSection
from ..models.user import User
from .auth import enforce_data_scope
from . import legal_rules as rules
from .legal_text import clean_statutory_text, subsection_text

BNS_COMMENCEMENT_DATE = "2024-07-01"

LABEL_RECORDED = "Recorded in FIR"
LABEL_SUGGESTED = "Suggested – not in FIR"


class CaseAccessDenied(Exception):
    pass


def _parent(number: str) -> str:
    return re.sub(r"\(.*$", "", number)


def _corpus_ingredients(row: Optional[LegalCorpus]) -> List[str]:
    try:
        items = json.loads(row.essential_ingredients_json or "[]") if row else []
    except (ValueError, TypeError):
        return []
    return [str(i) for i in items if str(i).strip()] if isinstance(items, list) else []


class LegalService:
    @staticmethod
    async def _authorized_case(case_id: str, user: User, db: AsyncSession) -> Optional[Case]:
        case = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
        if case and not enforce_data_scope(user, case.district, case.station):
            raise CaseAccessDenied("Access denied: this case is outside your jurisdiction.")
        return case

    @staticmethod
    async def recommend_sections_for_case(
        case_id: str,
        user: User,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Section 27: case facts -> candidate provisions.
        - Sections the FIR records (parsed from its wording and the law_sections field) are listed as
          "Recorded in FIR"; provisions whose ingredients match the facts but are not in the FIR as
          "Suggested – not in FIR". Each shows the ingredients established and still missing.
        - BNS applies to incidents on or after 1 July 2024, the IPC before; the incident date falls back
          to the extracted field and then the FIR text when the case has none.
        - Statutory text is shown as verified only when the corpus holds the official text.
        Only the provisions that can apply are read from the corpus (it holds ~1,700 provisions).
        """
        case = await LegalService._authorized_case(case_id, user, db)
        if not case:
            return {"error": "Case not found", "candidates": []}

        # Case text: the case's own fields plus the text of its documents (the FIR)
        field_rows = (await db.execute(
            select(CaseField.field_name,
                   func.coalesce(CaseField.human_override_value, CaseField.normalized_value, CaseField.original_value))
            .where(CaseField.case_id == case_id)
        )).all()
        fields = {}
        for name, value in field_rows:
            fields.setdefault((name or "").lower(), []).append(value)
        doc_text = " ".join(r[0] or "" for r in (await db.execute(
            select(DocumentChunk.chunk_text)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.case_id == case_id, Document.is_archived == False)  # noqa: E712
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index).limit(60)
        )).all())

        # Incident date and regime
        incident, date_source = None, None
        if case.offence_date:
            incident, date_source = case.offence_date.date(), "case record"
        else:
            for key in ("offence_date", "incident_date", "date_of_offence", "occurrence_date"):
                for v in fields.get(key, []):
                    incident = rules.parse_date_value(v)
                    if incident:
                        date_source = f"extracted field '{key}'"
                        break
                if incident:
                    break
            if not incident:
                incident = rules.incident_date_from_text(f"{case.narrative or ''} {doc_text}")
                date_source = "FIR text" if incident else None
        regime = rules.regime_for(incident)

        law_field_values = []
        for v in fields.get("law_sections", []):
            try:
                law_field_values += [str(x) for x in json.loads(v)] if isinstance(v, str) and v.startswith("[") else [str(v)]
            except (ValueError, TypeError):
                law_field_values.append(str(v))
        recorded = rules.recorded_sections([case.offence_nature or "", case.narrative or "", doc_text] + law_field_values)

        facts = " ".join(filter(None, [case.narrative, case.offence_nature, case.contraband_type, case.vehicle_details,
                                       case.witnesses_summary, doc_text])).lower()
        has_vehicle = bool(case.vehicle_details) or any(rules._cue_present(v, facts) for v in rules.VEHICLE)

        # Provisions to show: (act, numbers, rule, extra missing ingredient, recorded?)
        wanted: List[Tuple[str, List[str], Optional[dict], Optional[str], bool]] = []
        for act, number in recorded:
            wanted.append((act, [number], rules.rule_for_provision(act, number), None, True))
        # An FIR citing the IPC for an incident on/after 1 July 2024: suggest each BNS counterpart
        if regime == "BNS":
            for act, number in recorded:
                counterpart = rules.IPC_TO_BNS.get(number) if act == rules.IPC else None
                if counterpart and not any(a == rules.BNS and _parent(n) == _parent(counterpart) for a, n in recorded):
                    wanted.append((rules.BNS, [counterpart, _parent(counterpart)],
                                   rules.rule_for_provision(rules.BNS, counterpart), None, False))
        for rule in rules.RULES:
            # Suggested only when the facts evidence the provision's defining ingredients, not just a cue word
            if not rules.triggered(rule, facts, has_vehicle) or not rules.key_ingredients_met(rule, facts):
                continue
            for act, numbers, extra in rules.provisions_for(rule, regime, case):
                if any(a == act and (_parent(n) in {_parent(x) for x in numbers}) for a, n in recorded):
                    continue  # already listed as recorded
                if any(w[0] == act and w[1] == numbers for w in wanted):
                    continue
                wanted.append((act, numbers, rule, extra, False))

        # Read only those provisions (and their parent sections, which may hold the official text)
        needed = {(a, n) for a, nums, *_ in wanted for n in nums} | {(a, _parent(n)) for a, nums, *_ in wanted for n in nums}
        rows: List[LegalCorpus] = []
        if needed:
            rows = (await db.execute(
                select(LegalCorpus).where(LegalCorpus.verification_status == "VERIFIED",
                                          LegalCorpus.act_name.in_({a for a, _ in needed}),
                                          LegalCorpus.section_number.in_({n for _, n in needed}))
            )).scalars().all()
        by_key: Dict[Tuple[str, str], List[LegalCorpus]] = {}
        for r in rows:
            by_key.setdefault((r.act_name, r.section_number), []).append(r)
        decisions = {d.legal_corpus_id: d for d in (await db.execute(
            select(CaseLegalSection).where(CaseLegalSection.case_id == case_id))).scalars().all()}

        candidates = []
        for act, numbers, rule, extra, is_recorded in wanted:
            number = numbers[0]
            exact = [r for n in numbers for r in by_key.get((act, n), [])]
            parents = [r for n in numbers for r in by_key.get((act, _parent(n)), []) if r not in exact]
            official = next((r for r in exact + parents if r.source_type == "OFFICIAL"), None)
            summary = next((r for r in exact if r.source_type != "OFFICIAL"), None) or \
                next((r for r in parents if r.source_type != "OFFICIAL"), None)
            chosen = (next((r for r in exact if r.source_type == "OFFICIAL"), None) or (exact[0] if exact else None)
                      or official or summary)
            matched, missing = rules.evaluate_ingredients(rule, facts) if rule else ([], [])
            if not rule:
                # No offence rule: the corpus lists the ingredients; none is evidenced until the officer confirms it
                missing = _corpus_ingredients(summary or chosen)
            if extra:
                missing.append(extra)
            ingredient_status, ingredient_message = rules.ingredient_summary(matched, missing)
            warnings = []
            regime_applies = True
            if act == rules.IPC and regime == "BNS":
                regime_applies = False
                counterpart = rules.IPC_TO_BNS.get(number)
                warnings.append(f"The incident date ({incident:%d.%m.%Y}) is on or after 1 July 2024, so the IPC no longer "
                                f"applies; " + (f"the BNS equivalent is {counterpart}." if counterpart else "use the BNS equivalent."))
            if act == rules.BNS and regime == "IPC":
                regime_applies = False
                warnings.append(f"The incident date ({incident:%d.%m.%Y}) is before 1 July 2024, so the IPC applies, not the BNS.")
            if regime == "UNKNOWN" and act in (rules.IPC, rules.BNS):
                warnings.append("The incident date is not recorded: confirm it to choose between the IPC and the BNS.")
            official_text = None
            if official:
                official_text = clean_statutory_text(official.full_text)
                if official not in exact:
                    # The official row is the parent section: show the sub-section this candidate names
                    official_text = subsection_text(official_text, number) or official_text
            if official:
                text_status, text = "VERIFIED_STATUTORY_TEXT", official_text
            elif summary:
                text_status, text = "UNVERIFIED_SUMMARY", summary.full_text or summary.explanation
            else:
                text_status, text = "NOT_IN_CORPUS", None
                warnings.append(f"{act} {number} is not in the legal corpus yet; import its text to accept it.")
            decision = decisions.get(chosen.id) if chosen else None
            total = len(matched) + len(missing)
            label = LABEL_RECORDED if is_recorded else LABEL_SUGGESTED
            candidates.append({
                "legal_corpus_id": chosen.id if chosen else None,
                "can_accept": chosen is not None,
                "act_name": act,
                "section_number": number,
                "section_title": (summary or chosen).section_title if (summary or chosen) else (rule["offence"] if rule else number),
                "offence": rule["offence"] if rule else None,
                "text_status": text_status,
                "verified_text": official_text,
                "summary_text": (summary.full_text or summary.explanation) if (summary and not official) else None,
                "full_text": text,
                "explanation": (summary or chosen).explanation if (summary or chosen) else None,
                "penalty_text": (summary or chosen).penalty_text if (summary or chosen) else None,
                "effective_date": (official or summary).effective_date if (official or summary) else None,
                "source_url": official.source_url if official else None,
                "matched_ingredients": matched,
                "missing_ingredients": missing,
                "ingredient_status": ingredient_status,
                "ingredient_message": ingredient_message,
                "is_other_act": act not in (rules.IPC, rules.BNS),
                # Older field names, kept for existing clients
                "matched_facts": matched,
                "missing_elements": missing,
                "confidence_score": round(len(matched) / total, 2) if total else (0.95 if is_recorded else 0.5),
                "requires_officer_review": True,
                "label": label,
                "source": "RECORDED_IN_FIR" if is_recorded else "AI_SUGGESTED",  # values kept for existing clients
                "is_recorded_in_fir": is_recorded,
                "status_label": label,
                "regime_applies": regime_applies,
                "warnings": warnings,
                "officer_decision": decision.officer_decision if decision else "PENDING",
            })
        # Recorded first, then by how well the facts establish the ingredients
        candidates.sort(key=lambda c: (not c["is_recorded_in_fir"], not c["regime_applies"], -c["confidence_score"]))

        regime_label = {"BNS": "Bharatiya Nyaya Sanhita (BNS 2023)", "IPC": "Indian Penal Code (IPC Historical)",
                        "UNKNOWN": "Ambiguous incident date — Officer verification required"}[regime]
        return {
            "case_id": case.id,
            "fir_number": case.fir_number,
            "offence_date": incident.isoformat() if incident else None,
            "offence_date_source": date_source,
            "is_date_ambiguous": regime == "UNKNOWN",
            "applicable_regime": regime_label,
            "regime": regime,
            "recorded_fir_sections": [f"{n} {a}" for a, n in recorded],
            "recorded_other_act_sections": [f"{n} {a}" for a, n in recorded if a not in (rules.IPC, rules.BNS)],
            "candidates": candidates,
            "corpus_note": "Verified Statutory Text is shown only for provisions imported from an official source; "
                           "other provisions show an unverified summary.",
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
        case = await LegalService._authorized_case(case_id, user, db)
        if not case:
            raise ValueError("Case not found")
        if decision not in ("ACCEPTED", "REJECTED"):
            raise ValueError("Decision must be ACCEPTED or REJECTED")
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
