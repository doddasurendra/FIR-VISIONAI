"""
Answers from structured case records, without the AI model.

Used when the AI cannot answer (no key, quota, timeout) and for exact-identifier questions
("Which cases involve vehicle AP21TY4567?"), which a model reading eight passages cannot answer
completely anyway. Every fact comes from a case record the user may see (STATION / DISTRICT /
STATE scope) and is cited with the FIR passage that contains it; a value the FIR text does not
contain is shown as "case record only", never as quoted evidence.
"""
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.case import Case
from ..models.document import Document
from ..models.entity import Entity, EntityMention
from ..models.user import User
from .auth import apply_case_scope_filter
from .retrieval import exact_id_passages, id_tokens, normalise_id, text_has_id

NO_AI_LABEL = {
    "en": "_AI summary unavailable — answered from the case records; each value is quoted from the FIR where it appears._",
    "te": "_AI సారాంశం అందుబాటులో లేదు — కేసు రికార్డుల నుండి సమాధానం; ప్రతి విలువ FIRలో ఉన్న చోట ఉదహరించబడింది._",
    "hi": "_AI सारांश उपलब्ध नहीं — उत्तर केस रिकॉर्ड से; हर मान FIR में जहाँ है वहाँ से उद्धृत है।_",
}
# Identifier questions are answered from the records by exact match even when the AI works
EXACT_MATCH_LABEL = {
    "en": "_Answered from the case records by exact match; each value is quoted from the FIR where it appears._",
    "te": "_కేసు రికార్డుల నుండి ఖచ్చితమైన సరిపోలికతో సమాధానం; ప్రతి విలువ FIRలో ఉన్న చోట ఉదహరించబడింది._",
    "hi": "_केस रिकॉर्ड से सटीक मिलान द्वारा उत्तर; हर मान FIR में जहाँ है वहाँ से उद्धृत है।_",
}
RECORD_ONLY = {"en": "case record only; not found in the FIR text", "te": "కేసు రికార్డులో మాత్రమే; FIR పాఠ్యంలో లేదు",
               "hi": "केवल केस रिकॉर्ड में; FIR पाठ में नहीं मिला"}
PLACEHOLDER_NAMES = {"unknown", "unknown suspect", "unknown person", "unknown person(s)", "unknown persons",
                     "n/a", "na", "nil", "none", "not known", "unidentified", "-"}

# What a question asks for. Telugu/Hindi words cover the common field questions.
INTENTS: List[Tuple[str, Tuple[str, ...]]] = [
    ("seized", ("seiz", "quantity", "contraband", "items", "recovered", "liquor", "ganja", "arrack",
                "స్వాధీన", "పరిమాణం", "ज़ब्त", "जब्त", "मात्रा")),
    ("vehicle", ("vehicle", "conveyance", "auto", "lorry", "truck", "bike", "registration", "వాహన", "वाहन")),
    ("accused", ("accused", "suspect", "offender", "arrested", "నిందిత", "आरोपी", "अभियुक्त")),
    ("complainant", ("complainant", "informant", "ఫిర్యాదు", "शिकायत")),
    ("witness", ("witness", "panch", "mediator", "సాక్ష", "गवाह")),
    ("fir_number", ("fir number", "fir no", "crime number", "crime no", "case number", "ఎఫ్ఐఆర్ సంఖ్య",
                    "ఎఫ్‌ఐఆర్ నంబర్", "एफआईआर संख्या", "एफआईआर नंबर")),
    ("district", ("district", "జిల్లా", "ज़िला", "जिला")),
    ("station", ("police station", "which station", "station", "పోలీస్ స్టేషన్", "थाना", "स्टेशन")),
    ("date", ("date", "when", "time of", "తేదీ", "తారీఖు", "तारीख", "तिथि")),
    ("place", ("place", "where", "location", "occur", "ఎక్కడ", "స్థలం", "कहाँ", "स्थान")),
]

LABELS = {
    "seized": "Seized", "vehicle": "Vehicle", "accused": "Accused", "complainant": "Complainant",
    "witness": "Witnesses", "fir_number": "FIR number", "district": "District", "station": "Police station",
    "date": "Date of offence", "place": "Place of occurrence",
}


def detect_intents(question: str) -> List[str]:
    q = question.lower()
    found = []
    for name, keys in INTENTS:
        if name == "fir_number":
            hit = any(k in q for k in keys)
        else:
            hit = any(re.search(rf"(?<![a-z]){re.escape(k)}", q) for k in keys)
        if hit:
            found.append(name)
    return found


# Words that only frame a question ("which vehicle was used", "names of the persons")
_FRAMING = {"used", "use", "person", "persons", "people", "name", "names", "number", "incident", "occurred",
            "happened", "involved", "registered", "recorded", "case", "cases", "what", "which", "whom", "and"}


def _asks_for_more(question: str, intents: List[str], sources: Sequence[Dict[str, Any]]) -> bool:
    """
    True when the question asks about something the recognised facts do not cover and the record does
    not mention ("criminal history of the accused", "accused's bank account"): answering with the
    accused's names would look like an answer while not being one.
    """
    from .retrieval import query_terms
    keys = [k for name, ks in INTENTS if name in intents for k in ks if " " not in k]
    corpus = " ".join((s.get("chunk_text") or "") for s in sources).lower()
    for term in query_terms(question):
        if term in _FRAMING or any(term.startswith(k) or k.startswith(term) for k in keys):
            continue
        if term not in corpus:
            return True
    return False


def is_placeholder(name: Optional[str]) -> bool:
    return (name or "").strip().lower().rstrip(".") in PLACEHOLDER_NAMES or not (name or "").strip()


def clean_name(name: str) -> str:
    return re.sub(r"\s*\((verified|unverified|review pending)\)\s*$", "", name or "", flags=re.I).strip()


def _quantity_variants(q: Optional[float]) -> List[str]:
    if q is None:
        return []
    out = {f"{q:g}", f"{q:.1f}", f"{q:.2f}"}
    if float(q).is_integer():
        out.add(str(int(q)))
    return sorted(out, key=len, reverse=True)


def _find_passage(sources: Sequence[Dict[str, Any]], *needles: str, ident: Optional[str] = None) -> Optional[int]:
    """1-based number of the first source containing ident (normalised) or every needle (case-insensitive)."""
    for i, s in enumerate(sources, start=1):
        txt = s.get("chunk_text") or ""
        if ident and text_has_id(txt, ident):
            return i
        low = txt.lower()
        if needles and all(n and n.lower() in low for n in needles):
            return i
    return None


async def _mentions(db: AsyncSession, case_ids: Sequence[str], roles: Sequence[str]) -> Dict[str, List[str]]:
    if not case_ids:
        return {}
    rows = (await db.execute(
        select(EntityMention.case_id, EntityMention.mention_text, Entity.canonical_name)
        .join(Entity, Entity.id == EntityMention.entity_id)
        .where(EntityMention.case_id.in_(list(case_ids)), func.upper(EntityMention.role_in_case).in_(list(roles)))
    )).fetchall()
    out: Dict[str, List[str]] = {}
    for case_id, mention, canonical in rows:
        name = clean_name(mention or canonical)
        if not is_placeholder(name) and name not in out.setdefault(case_id, []):
            out[case_id].append(name)
    return out


async def _people_by_role(db: AsyncSession, case_id: str) -> Dict[str, List[str]]:
    """{"ACCUSED": [...], "COMPLAINANT": [...], "WITNESS": [...]} for one case, placeholders left out."""
    rows = (await db.execute(
        select(EntityMention.role_in_case, EntityMention.mention_text, Entity.canonical_name)
        .join(Entity, Entity.id == EntityMention.entity_id)
        .where(EntityMention.case_id == case_id)
    )).fetchall()
    out: Dict[str, List[str]] = {"ACCUSED": [], "COMPLAINANT": [], "WITNESS": []}
    for role, mention, canonical in rows:
        role = (role or "").upper()
        role = "COMPLAINANT" if role == "INFORMANT" else role
        name = clean_name(mention or canonical)
        if role in out and not is_placeholder(name) and name not in out[role]:
            out[role].append(name)
    return out


def _fmt_date(value) -> Optional[str]:
    if not value:
        return None
    return value.strftime("%d %B %Y, %H:%M").replace(", 00:00", "") if hasattr(value, "strftime") else str(value)


async def answer_from_case(
    db: AsyncSession, user: User, case: Case, question: str, sources: List[Dict[str, Any]], language: str,
) -> Optional[Dict[str, Any]]:
    """
    Facts the question asks for, from the case record, each cited with the passage of `sources`
    that contains it. sources are the passages already given to the answer step, in [S#] order.
    Returns None when the question asks for none of the known facts.
    """
    intents = detect_intents(question)
    if not intents or _asks_for_more(question, intents, sources):
        return None
    roles = await _people_by_role(db, case.id)

    facts: List[Tuple[str, str, Optional[int]]] = []   # (label, value, source number)
    for intent in intents:
        if intent == "seized":
            if case.contraband_type or case.seized_quantity:
                value = " — ".join(filter(None, [case.contraband_type,
                                                  f"{case.seized_quantity:g} {case.seized_unit or ''}".strip()
                                                  if case.seized_quantity is not None else None]))
                n = next((_find_passage(sources, v) for v in _quantity_variants(case.seized_quantity)
                          if _find_passage(sources, v)), None) or _find_passage(sources, "seiz")
                facts.append((LABELS[intent], value, n))
        elif intent == "vehicle" and case.vehicle_details:
            regs = [t["norm"] for t in id_tokens(case.vehicle_details) if t["kind"] == "VEHICLE"]
            n = _find_passage(sources, ident=regs[0]) if regs else _find_passage(sources, case.vehicle_details)
            facts.append((LABELS[intent], case.vehicle_details, n))
        elif intent in ("accused", "complainant", "witness"):
            names = roles[{"accused": "ACCUSED", "complainant": "COMPLAINANT", "witness": "WITNESS"}[intent]]
            if intent == "complainant" and not names and case.seizing_officer_name:
                names = [case.seizing_officer_name]
            for name in names:
                facts.append((LABELS[intent], name, _find_passage(sources, name)))
        elif intent == "fir_number":
            facts.append((LABELS[intent], case.fir_number, _find_passage(sources, ident=normalise_id(case.fir_number))))
        elif intent == "district" and case.district:
            facts.append((LABELS[intent], case.district, _find_passage(sources, case.district)))
        elif intent == "station" and case.station:
            facts.append((LABELS[intent], case.station, _find_passage(sources, case.station)))
        elif intent == "date" and case.offence_date:
            day = case.offence_date
            needles = [f"{day.day}", day.strftime("%B")] if hasattr(day, "strftime") else []
            n = _find_passage(sources, *needles) if needles else None
            if n is None and hasattr(day, "strftime"):
                n = _find_passage(sources, day.strftime("%d.%m.%Y"))
            facts.append((LABELS[intent], _fmt_date(day), n))
        elif intent == "place":
            place = case.incident_place_raw or case.location_description
            if place:
                first = re.split(r"[,;]", place)[0].strip()
                facts.append((LABELS[intent], place, _find_passage(sources, first)))
    if not facts:
        return None
    return _compose(facts, sources, question, language)


def _compose(facts, sources, question, language) -> Dict[str, Any]:
    from .rag_engine import _citation  # avoid an import cycle
    from .retrieval import query_terms
    terms = query_terms(question)
    lines = [NO_AI_LABEL.get(language, NO_AI_LABEL["en"]), ""]
    used: List[int] = []
    for label, value, n in facts:
        if n:
            lines.append(f"- **{label}:** {value} [S{n}]")
            if n not in used:
                used.append(n)
        else:
            lines.append(f"- **{label}:** {value} _({RECORD_ONLY.get(language, RECORD_ONLY['en'])})_")
    citations = [_citation(sources[n - 1], n, terms) for n in used]
    if citations:
        lines.append("")
        for c in citations:
            lines.append(f"> [S{c['source_number']}] “{c['evidence_excerpt']}” — {c['source_label']}")
    return {"answer": "\n".join(lines), "citations": citations, "answer_method": "CASE_RECORDS_AND_QUOTES"}


def _like(norm: str) -> str:
    # "AP21TY4567" -> "%ap%21%ty%4567%"; the exact normalised match is checked in Python
    return "%" + "%".join(p.lower() for p in re.findall(r"[A-Z]+|\d+", norm)) + "%"


async def answer_by_identifier(
    db: AsyncSession, user: User, question: str, document_ids: Sequence[str], language: str,
    ai_unavailable: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Cases and passages that contain an identifier named in the question (vehicle, FIR or phone number),
    limited to cases the user may see and to the authorised documents in scope. None if no identifier.
    The answer says "AI summary unavailable" only when the AI really is unavailable.
    """
    tokens = id_tokens(question)
    if not tokens:
        return None
    norms = [t["norm"] for t in tokens]

    # Cases in jurisdiction whose own fields carry the identifier
    like_any = or_(*[func.lower(func.coalesce(Case.vehicle_details, "") + " " + Case.fir_number).like(_like(n))
                     for n in norms])
    scoped = apply_case_scope_filter(select(Case).where(Case.is_archived == False, like_any), user, Case)  # noqa: E712
    cases = {c.id: c for c in (await db.execute(scoped)).scalars().all()
             if any(text_has_id(f"{c.vehicle_details or ''} {c.fir_number}", n) for n in norms)}

    # Entities (vehicle / phone records) carrying the identifier, linked to cases in jurisdiction;
    # prefiltered in SQL so only candidate rows travel over the network
    ent_rows = (await db.execute(
        apply_case_scope_filter(
            select(Case, Entity.canonical_name)
            .join(EntityMention, EntityMention.case_id == Case.id)
            .join(Entity, Entity.id == EntityMention.entity_id)
            .where(Case.is_archived == False, Entity.entity_type.in_(("VEHICLE", "PHONE")),  # noqa: E712
                   or_(*[func.lower(Entity.canonical_name).like(_like(n)) for n in norms])),
            user, Case)
    )).all()
    for c, name in ent_rows:
        if any(text_has_id(name, n) for n in norms):
            cases.setdefault(c.id, c)

    # Passages in the authorised documents in scope
    passages = await exact_id_passages(db, norms, document_ids, limit=12)
    doc_case = {}
    if passages:
        doc_case = dict((await db.execute(
            select(Document.id, Document.case_id).where(Document.id.in_({p["document_id"] for p in passages}))
        )).all())
        linked = [cid for cid in set(doc_case.values()) if cid and cid not in cases]
        if linked:
            extra = apply_case_scope_filter(select(Case).where(Case.id.in_(linked), Case.is_archived == False), user, Case)  # noqa: E712
            for c in (await db.execute(extra)).scalars().all():
                cases[c.id] = c
    if not cases and not passages:
        return None

    accused = await _mentions(db, list(cases), ["ACCUSED"])
    from .rag_engine import _citation
    from .retrieval import query_terms
    terms = query_terms(question) + [t["raw"] for t in tokens]
    citations = [_citation(p, i, terms) for i, p in enumerate(passages, start=1)]
    by_case: Dict[str, List[int]] = {}
    for i, p in enumerate(passages, start=1):
        cid = doc_case.get(p["document_id"])
        if cid:
            by_case.setdefault(cid, []).append(i)

    shown = ", ".join(f"**{t['raw']}**" for t in tokens)
    label = NO_AI_LABEL if ai_unavailable else EXACT_MATCH_LABEL
    lines = [label.get(language, label["en"]), "",
             f"{shown} appears in **{len(cases)}** case(s) within your jurisdiction:" if cases
             else f"No case record within your jurisdiction carries {shown}; it appears in these documents:"]
    order = sorted(cases.values(), key=lambda c: (c.status == "DRAFT", c.fir_number))
    for c in order:
        names = accused.get(c.id) or []
        cite = "".join(f"[S{n}]" for n in by_case.get(c.id, []))
        status = "draft" if c.status == "DRAFT" else (c.status or "").replace("_", " ").lower()
        detail = []
        if c.vehicle_details:
            detail.append(f"vehicle: {c.vehicle_details}")
        detail.append("accused: " + (", ".join(names) if names else "not recorded"))
        lines.append(f"- **{c.fir_number}** ({status}) · {c.station}, {c.district} — {'; '.join(detail)}"
                     + (f" {cite}" if cite else ""))
    if citations:
        lines += ["", "Passages that contain it:"]
        for c in citations:
            lines.append(f"> [S{c['source_number']}] “{c['evidence_excerpt']}” — {c['source_label']}")
    return {
        "answer": "\n".join(lines),
        "citations": citations,
        "answer_method": "CASE_RECORDS_AND_QUOTES",
        "matched_cases": [{"case_id": c.id, "fir_number": c.fir_number, "status": c.status, "station": c.station,
                           "district": c.district, "accused": accused.get(c.id) or []} for c in order],
        "identifiers": tokens,
    }
