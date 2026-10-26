"""
FIR VisionAI voice assistant: answers spoken or typed questions about the application.

Routing:
- live counts, an FIR's status or workflow, summary coverage -> queried for this user, with the same
  jurisdiction rules as the rest of the application (never from static text);
- legal questions -> the existing grounded RAG over the Knowledge Base;
- requests to approve, submit or delete -> refused with instructions (the assistant never acts);
- everything else -> the verified application guide.
Only the intent and language are logged (audit); no transcript or audio is stored.
"""
import re
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.case import Case
from ..models.user import User
from .app_guide import GUIDE, search_guide
from .auth import apply_case_scope_filter

LANGS = ("en", "te", "hi")

_COUNT_WORDS = ("how many", "number of", "count", "total", "ఎన్ని", "ఎంత", "మొత్తం", "कितने", "कितनी", "कितना",
                "संख्या", "कुल")
_DRAFT_WORDS = ("draft", "drafts", "డ్రాఫ్ట్", "ముసాయిదా", "ड्राफ्ट", "मसौदा")
_REVIEW_WORDS = ("under review", "in review", "review", "pending verification", "సమీక్ష", "समीक्षा")
_APPROVED_WORDS = ("approved", "approval", "ఆమోద", "स्वीकृत", "अनुमोदित")
_SUMMARY_WORDS = ("summar", "సారాంశ", "सारांश")
_WORKFLOW_WORDS = ("workflow", "stage", "stages", "వర్క్‌ఫ్లో", "దశ", "वर्कफ़्लो", "चरण")
_STATUS_WORDS = ("status", "state of", "స్థితి", "స్టేటస్", "स्थिति", "स्टेटस")
_LEGAL_WORDS = ("punishment", "penalty", "under section", "section ", "what does section", "article ", "bns", "bnss", "ipc",
                "ndps", "excise act", "offence of", "శిక్ష", "సెక్షన్", "ఆర్టికల్", "सजा", "धारा", "अनुच्छेद", "दंड")
_HELP_WORDS = ("how do i", "how to", "where", "which button", "explain how", "help", "use ", "open ", "dashboard", "page",
               "ఎలా", "ఎక్కడ", "कैसे", "कहाँ", "कहां")
_ACTION_WORDS = ("approve this", "approve the", "approve case", "approve fir", "delete", "remove the case", "submit the",
                 "submit case", "archive this", "archive the", "register the case", "ఆమోదించు", "తొలగించు", "సమర్పించు",
                 "स्वीकृत करो", "स्वीकृत करें", "हटाओ", "हटाएं", "जमा करो", "जमा करें")
_REFERS_BACK = ("it", "this case", "that case", "this fir", "that fir", "its", "దాని", "ఈ కేసు", "ఆ కేసు", "इसका", "इस केस", "उस केस")
_FIR_NUMBER = re.compile(r"\b(?:[A-Z]{1,8}[-/]?)?\d{1,5}\s*/\s*(?:[A-Z0-9-]+/\s*)*\d{2,4}\b|\b[A-Z]{2,}-[A-Z0-9-]{3,}\b")


def detect_language(text: str) -> str:
    if re.search(r"[ఀ-౿]", text or ""):
        return "te"
    if re.search(r"[ऀ-ॿ]", text or ""):
        return "hi"
    return "en"


def _has(text: str, words) -> bool:
    low = text.lower()
    return any(w in low for w in words)


def find_fir_number(text: str) -> Optional[str]:
    m = _FIR_NUMBER.search(text or "")
    return re.sub(r"\s+", "", m.group(0)) if m else None


def classify(question: str) -> str:
    q = question.lower()
    if _has(q, _ACTION_WORDS):
        return "ACTION_REQUEST"
    fir = find_fir_number(question)
    if fir and _has(q, _WORKFLOW_WORDS):
        return "WORKFLOW_STATUS"
    if fir:
        return "FIR_STATUS"
    if _has(q, _COUNT_WORDS) and _has(q, _SUMMARY_WORDS):
        return "SUMMARY_COVERAGE"
    if _has(q, _COUNT_WORDS) and (_has(q, _DRAFT_WORDS + _REVIEW_WORDS + _APPROVED_WORDS)
                                 or any(w in q for w in ("case", "fir", "కేసు", "ఎఫ్‌ఐఆర్", "केस", "एफआईआर", "मामल"))):
        return "LIVE_COUNTS"
    if _has(q, _LEGAL_WORDS) and not _has(q, _HELP_WORDS):
        return "LEGAL"
    return "APP_HELP"


def speech_text(text: str, limit: int = 450) -> str:
    """What is read aloud: no citation markers, IDs, JSON or markdown; cut at a sentence boundary."""
    t = re.sub(r"\[(?:S|G)\d+\]", "", text or "")
    t = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "", t)
    t = re.sub(r"[{}\[\]`*#_>|]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= limit:
        return t
    cut = max(t.rfind(p, 0, limit) for p in (". ", "। ", "? ", "! "))
    return t[: cut + 1] if cut > 80 else t[:limit].rsplit(" ", 1)[0] + "…"


_T = {
    "counts": {
        "en": "In your jurisdiction there are {total} cases: {review} under review, {approved} approved FIRs and {drafts} pending drafts.",
        "te": "మీ అధికార పరిధిలో మొత్తం {total} కేసులు ఉన్నాయి: సమీక్షలో {review}, ఆమోదించిన ఎఫ్‌ఐఆర్‌లు {approved}, పెండింగ్ డ్రాఫ్ట్‌లు {drafts}.",
        "hi": "आपके अधिकार क्षेत्र में कुल {total} केस हैं: समीक्षाधीन {review}, स्वीकृत एफआईआर {approved} और लंबित ड्राफ्ट {drafts}।",
    },
    "count_one": {
        "en": "There are {n} {label} in your jurisdiction.",
        "te": "మీ అధికార పరిధిలో {label} {n} ఉన్నాయి.",
        "hi": "आपके अधिकार क्षेत्र में {label} {n} हैं।",
    },
    "labels": {
        "en": {"DRAFT": "pending drafts", "IN_REVIEW": "cases under review", "APPROVED": "approved FIRs", "TOTAL": "cases"},
        "te": {"DRAFT": "పెండింగ్ డ్రాఫ్ట్‌లు", "IN_REVIEW": "సమీక్షలో ఉన్న కేసులు", "APPROVED": "ఆమోదించిన ఎఫ్‌ఐఆర్‌లు", "TOTAL": "కేసులు"},
        "hi": {"DRAFT": "लंबित ड्राफ्ट", "IN_REVIEW": "समीक्षाधीन केस", "APPROVED": "स्वीकृत एफआईआर", "TOTAL": "केस"},
    },
    "fir_status": {
        "en": "FIR {fir} at {station}, {district} has status {status}.",
        "te": "{station}, {district} లోని ఎఫ్‌ఐఆర్ {fir} స్థితి: {status}.",
        "hi": "{station}, {district} की एफआईआर {fir} की स्थिति: {status}।",
    },
    "fir_missing": {
        "en": "I could not find FIR {fir} among the cases you are authorised to see. Check the number in Case Management.",
        "te": "మీకు అనుమతి ఉన్న కేసులలో ఎఫ్‌ఐఆర్ {fir} కనిపించలేదు. కేసు నిర్వహణలో సంఖ్యను తనిఖీ చేయండి.",
        "hi": "आपके अधिकृत केसों में एफआईआर {fir} नहीं मिली। केस प्रबंधन में संख्या जाँचें।",
    },
    "workflow": {
        "en": "Workflow for FIR {fir}: {overall}. {detail}",
        "te": "ఎఫ్‌ఐఆర్ {fir} వర్క్‌ఫ్లో: {overall}. {detail}",
        "hi": "एफआईआर {fir} का वर्कफ़्लो: {overall}। {detail}",
    },
    "summary_cov": {
        "en": "Of {total} historical FIR records you can access, {eligible} have readable text and {needs} need OCR or review. Summaries completed: English {en}, Telugu {te}, Hindi {hi}.",
        "te": "మీకు అందుబాటులో ఉన్న {total} చారిత్రక ఎఫ్‌ఐఆర్ రికార్డులలో {eligible} చదవగలిగే పాఠ్యం కలిగి ఉన్నాయి, {needs} కు OCR లేదా సమీక్ష అవసరం. పూర్తైన సారాంశాలు: ఇంగ్లీష్ {en}, తెలుగు {te}, హిందీ {hi}.",
        "hi": "आपके लिए उपलब्ध {total} ऐतिहासिक एफआईआर रिकॉर्ड में से {eligible} में पढ़ने योग्य पाठ है और {needs} को OCR या समीक्षा चाहिए। पूर्ण सारांश: अंग्रेज़ी {en}, तेलुगु {te}, हिंदी {hi}।",
    },
    "action": {
        "en": "I cannot approve, submit, delete or change records; only an authorised officer can, on the relevant page. ",
        "te": "నేను రికార్డులను ఆమోదించలేను, సమర్పించలేను, తొలగించలేను లేదా మార్చలేను; అనుమతి ఉన్న అధికారి మాత్రమే సంబంధిత పేజీలో చేయగలరు. ",
        "hi": "मैं रिकॉर्ड स्वीकृत, जमा, हटा या बदल नहीं सकता; केवल अधिकृत अधिकारी संबंधित पृष्ठ पर ऐसा कर सकते हैं। ",
    },
    "no_guide": {
        "en": "I don't have verified information about that in the FIR VisionAI guide. Try asking about a module, such as Case Management, New Case Intake or the Knowledge Base.",
        "te": "దాని గురించి FIR VisionAI గైడ్‌లో ధృవీకరించిన సమాచారం లేదు. కేసు నిర్వహణ, కొత్త కేసు నమోదు లేదా నాలెడ్జ్ బేస్ వంటి మాడ్యూల్ గురించి అడగండి.",
        "hi": "FIR VisionAI गाइड में इसके बारे में सत्यापित जानकारी नहीं है। केस प्रबंधन, नया केस या नॉलेज बेस जैसे किसी मॉड्यूल के बारे में पूछें।",
    },
    "no_ai_translation": {
        "en": "",
        "te": " (AI అనువాదం ప్రస్తుతం అందుబాటులో లేదు; ఇంగ్లీష్ మార్గదర్శకం చూపిస్తున్నాం.)",
        "hi": " (AI अनुवाद अभी उपलब्ध नहीं है; अंग्रेज़ी मार्गदर्शन दिखाया जा रहा है।)",
    },
}

_STATUS_NAMES = {
    "en": {"DRAFT": "draft", "IN_REVIEW": "under review", "APPROVED": "approved", "PENDING": "not started",
           "RUNNING": "running", "COMPLETED": "completed", "FAILED": "failed", "NEEDS_REVIEW": "needs review"},
    "te": {"DRAFT": "డ్రాఫ్ట్", "IN_REVIEW": "సమీక్షలో ఉంది", "APPROVED": "ఆమోదించబడింది", "PENDING": "ప్రారంభం కాలేదు",
           "RUNNING": "నడుస్తోంది", "COMPLETED": "పూర్తయింది", "FAILED": "విఫలమైంది", "NEEDS_REVIEW": "సమీక్ష అవసరం"},
    "hi": {"DRAFT": "ड्राफ्ट", "IN_REVIEW": "समीक्षाधीन", "APPROVED": "स्वीकृत", "PENDING": "शुरू नहीं हुआ",
           "RUNNING": "चल रहा है", "COMPLETED": "पूर्ण", "FAILED": "विफल", "NEEDS_REVIEW": "समीक्षा आवश्यक"},
}
_STAGE_NAMES = {"INTAKE": "Intake", "CLASSIFICATION": "Classification", "ENTITY_EXTRACTION": "Entity extraction",
                "AI_LEGAL": "AI & Legal", "INVESTIGATION": "Investigation", "REPEAT_OFFENDER_INTELLIGENCE": "Network intelligence",
                "ADMIN": "Administration"}


def _guide_citation(entry: Dict) -> Dict:
    return {"type": "guide", "title": entry["title"], "path": entry["path"]}


async def _scoped_case(db: AsyncSession, user: User, fir: str) -> Optional[Case]:
    stmt = apply_case_scope_filter(select(Case).where(Case.fir_number.ilike(fir)), user, Case)
    case = (await db.execute(stmt)).scalars().first()
    if case is None and "/" in fir:
        compact = fir.replace(" ", "")
        stmt = apply_case_scope_filter(select(Case).where(Case.fir_number.ilike(f"%{compact}%")), user, Case)
        case = (await db.execute(stmt)).scalars().first()
    return case


def _last_fir(history: List[Dict]) -> Optional[str]:
    for turn in reversed(history or []):
        fir = find_fir_number(turn.get("text", ""))
        if fir:
            return fir
    return None


async def answer(db: AsyncSession, user: User, question: str, language: str = "auto",
                 history: Optional[List[Dict]] = None) -> Dict:
    from . import fir_summaries as fs
    from . import rag_engine
    from .analytics import analytics_service
    from .gemini import gemini_service
    from .workflow import workflow_summary

    question = (question or "").strip()
    lang = language if language in LANGS else detect_language(question)
    history = history or []
    intent = classify(question)
    # Follow-ups such as "what is its workflow status?" refer to the FIR mentioned earlier
    if intent in ("APP_HELP", "LIVE_COUNTS") and not find_fir_number(question) and _has(question, _WORKFLOW_WORDS + _STATUS_WORDS) \
            and any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", question.lower()) for w in _REFERS_BACK) and _last_fir(history):
        question_fir = _last_fir(history)
        intent = "WORKFLOW_STATUS" if _has(question, _WORKFLOW_WORDS) else "FIR_STATUS"
    else:
        question_fir = find_fir_number(question)

    out: Dict = {"language": lang, "intent": intent, "citations": [], "navigate_to": None, "data": None, "grounding": None}

    if intent == "LIVE_COUNTS":
        kpis = await analytics_service.get_dashboard_kpis(user=user, db=db)
        by = kpis.get("cases_by_status") or {}
        counts = {"TOTAL": kpis.get("total_cases", 0), "IN_REVIEW": by.get("IN_REVIEW", 0),
                  "APPROVED": by.get("APPROVED", 0), "DRAFT": by.get("DRAFT", 0)}
        which = ("DRAFT" if _has(question, _DRAFT_WORDS) else "IN_REVIEW" if _has(question, _REVIEW_WORDS)
                 else "APPROVED" if _has(question, _APPROVED_WORDS) else None)
        if which:
            text = _T["count_one"][lang].format(n=counts[which], label=_T["labels"][lang][which])
            out["navigate_to"] = f"/cases?status={which}"
        else:
            text = _T["counts"][lang].format(total=counts["TOTAL"], review=counts["IN_REVIEW"],
                                             approved=counts["APPROVED"], drafts=counts["DRAFT"])
            out["navigate_to"] = "/cases"
        out.update(answer=text, data={"counts": counts, "scope": user.role}, grounding="LIVE_DATA",
                   citations=[{"type": "live", "title": "Case counts in your jurisdiction (queried now)", "path": out["navigate_to"]}])

    elif intent in ("FIR_STATUS", "WORKFLOW_STATUS"):
        case = await _scoped_case(db, user, question_fir)
        if case is None:
            out.update(answer=_T["fir_missing"][lang].format(fir=question_fir), grounding="LIVE_DATA", navigate_to="/cases")
        elif intent == "FIR_STATUS":
            out.update(answer=_T["fir_status"][lang].format(fir=case.fir_number, station=case.station, district=case.district,
                                                            status=_STATUS_NAMES[lang].get(case.status, case.status)),
                       grounding="LIVE_DATA", navigate_to=f"/cases/{case.id}",
                       data={"fir_number": case.fir_number, "status": case.status},
                       citations=[{"type": "live", "title": f"Case record {case.fir_number}", "path": f"/cases/{case.id}"}])
        else:
            wf = await workflow_summary(db, case.id)
            names = _STATUS_NAMES[lang]
            not_done = [s for s in wf["stages"] if s["status"] != "COMPLETED"]
            detail = ("; ".join(f"{_STAGE_NAMES.get(s['stage'], s['stage'])}: {names.get(s['status'], s['status'])}" for s in not_done)
                      or {"en": "All stages completed.", "te": "అన్ని దశలు పూర్తయ్యాయి.", "hi": "सभी चरण पूर्ण।"}[lang])
            out.update(answer=_T["workflow"][lang].format(fir=case.fir_number, overall=names.get(wf["status"], wf["status"]), detail=detail),
                       grounding="LIVE_DATA", navigate_to=f"/cases/{case.id}",
                       data={"fir_number": case.fir_number, "workflow": wf},
                       citations=[{"type": "live", "title": f"Workflow of {case.fir_number} (queried now)", "path": f"/cases/{case.id}"}])

    elif intent == "SUMMARY_COVERAGE":
        records = await fs.list_records(db, user)
        rows = await fs.summary_rows(db, [r["record_key"] for r in records])
        done = {l: 0 for l in LANGS}
        for r in records:
            state = fs.summary_state(r, rows.get(r["record_key"], {}))
            for l in LANGS:
                done[l] += state[l] == "COMPLETED"
        eligible = sum(r["source_chars"] >= fs.MIN_SOURCE_CHARS for r in records)
        out.update(answer=_T["summary_cov"][lang].format(total=len(records), eligible=eligible, needs=len(records) - eligible, **done),
                   grounding="LIVE_DATA", navigate_to="/summaries",
                   data={"total": len(records), "eligible": eligible, "completed": done},
                   citations=[{"type": "live", "title": "Historical FIR summary coverage (queried now)", "path": "/summaries"}])

    elif intent == "LEGAL":
        rag = await rag_engine.answer(db, user, question, scope="KNOWLEDGE_BASE", language=lang)
        out.update(answer=rag.get("answer") or "", grounding="KNOWLEDGE_BASE", navigate_to="/ai-fir-assistance",
                   not_found=bool(rag.get("not_found")),
                   citations=[{"type": "document", "title": c.get("document_name") or c.get("document_title"),
                               "section": c.get("section_ref"), "page": c.get("physical_page_number"),
                               "document_id": c.get("document_id")} for c in rag.get("citations") or []])

    else:
        entries = search_guide(question)
        if intent == "ACTION_REQUEST":
            status_entry = next(e for e in GUIDE if e["id"] == "case_status_review")
            entries = [status_entry] + [e for e in entries if e["id"] != status_entry["id"]][:2]
        prefix = _T["action"][lang] if intent == "ACTION_REQUEST" else ""
        if not entries:
            out.update(answer=prefix + _T["no_guide"][lang], grounding="APP_GUIDE")
        else:
            gen = gemini_service.answer_app_question(question, entries, language=lang, history=history)
            if gen["status"] == "ANSWERED":
                used = [entries[n - 1] for n in gen["used"]]
                text = gen["text"]
                for i in range(1, len(entries) + 1):
                    text = text.replace(f"[G{i}]", "")
                out.update(answer=prefix + re.sub(r"\s+([.,;।])", r"\1", text).strip(), citations=[_guide_citation(e) for e in used])
            elif gen["status"] == "NOT_FOUND":
                out.update(answer=prefix + _T["no_guide"][lang])
            else:
                # No AI available: read the best verified passage itself (English) rather than guessing
                out.update(answer=prefix + entries[0]["text"] + _T["no_ai_translation"][lang],
                           citations=[_guide_citation(entries[0])], ai_unavailable=True)
            out["grounding"] = "APP_GUIDE"
            out["navigate_to"] = entries[0]["path"] if entries else None

    out["speech"] = speech_text(out.get("answer", ""))
    return out
