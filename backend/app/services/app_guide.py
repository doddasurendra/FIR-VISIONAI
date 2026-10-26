"""
Verified guide to the FIR VisionAI application, used by the voice assistant.

Every entry describes what the application actually implements (checked against the frontend
routes, page labels and backend rules). Where a requested feature does not exist or is only a
placeholder, the entry says so and names the real alternative. Live numbers (case counts,
statuses, workflow progress) are never written here: the assistant queries them per user.
Keywords include Telugu and Hindi terms so spoken questions in those languages find an entry.
"""
import re
from typing import Dict, List

GUIDE: List[Dict] = [
    {
        "id": "home_dashboard", "title": "Home dashboard", "path": "/",
        "keywords": ["dashboard", "home", "overview", "welcome", "banner", "main page", "డాష్‌బోర్డ్", "డాష్బోర్డ్", "హోమ్",
                     "ముఖ్య పేజీ", "डैशबोर्ड", "होम", "मुख्य पृष्ठ"],
        "text": "The Home dashboard opens at the start page. The top banner shows your name, your role as 'Jurisdiction "
                "Scoped' (STATE, DISTRICT or STATION) and your authorised station, with two buttons: New Case Intake and "
                "AI FIR Assistance. Below it are the Quick Access cards, then four count cards (Total Scoped Cases, Under "
                "Review, Approved FIRs, Pending Drafts), a 'Contraband Seizures by Volume' panel and an 'Action Items & "
                "Verification Queue' panel. Clicking a count card opens Case Management filtered to that status. The "
                "dashboard has no notifications panel and no recent-cases list; use the Action Items panel and Case "
                "Management for pending work.",
    },
    {
        "id": "quick_access", "title": "Quick Access cards", "path": "/",
        "keywords": ["quick access", "shortcut", "shortcuts", "cards", "క్విక్ యాక్సెస్", "త్వరిత", "షార్ట్‌కట్", "क्विक एक्सेस",
                     "त्वरित पहुँच", "शॉर्टकट"],
        "text": "Quick Access on the dashboard has four cards: 'Existing / Old FIRs' opens Case Management to view, search "
                "and review registered FIRs; 'New FIRs' opens New Case Intake to register an FIR and upload documents; "
                "'Laws & Sections' opens Legal Section Assistance; 'AI FIR Chatbot' opens AI FIR Assistance to ask "
                "questions about an uploaded FIR or authorised records.",
    },
    {
        "id": "dashboard_metrics", "title": "Dashboard count cards", "path": "/",
        "keywords": ["total scoped cases", "scoped", "under review", "approved", "approved firs", "approved first",
                     "pending drafts", "drafts", "metrics", "kpi", "count", "counts", "మొత్తం కేసులు", "సమీక్షలో",
                     "ఆమోదించిన", "డ్రాఫ్ట్", "కౌంట్", "कुल केस", "समीक्षाधीन", "स्वीकृत", "ड्राफ्ट", "मसौदा", "गिनती"],
        "text": "The four count cards are: Total Scoped Cases, all cases recorded within your jurisdiction; Under Review, "
                "cases with status IN_REVIEW that await officer verification and sign-off; Approved FIRs, cases with "
                "status APPROVED, formally verified and ready for court filing; Pending Drafts, cases saved as DRAFT and "
                "not yet submitted. There is no card called 'Approved First'; the approval card is 'Approved FIRs'. A "
                "STATE officer's counts cover all districts, a DISTRICT officer's cover their district and a STATION "
                "officer's cover their station. The browser may show counts up to 60 seconds old; ask me for the current "
                "count and I will query it.",
    },
    {
        "id": "navigation", "title": "Main menu", "path": "/",
        "keywords": ["menu", "navigation", "where is", "find", "module", "modules", "located", "మెనూ", "ఎక్కడ", "మాడ్యూల్",
                     "मेनू", "कहाँ", "मॉड्यूल"],
        "text": "The top menu has five groups. Home: Dashboard, Reports and Analytics, Settings and System Health. Case "
                "Management: Case Management, FIR Document Extraction, New Case Intake, Bulk Document Ingestion. AI & Legal "
                "Intelligence: Knowledge Base & Legal Corpus, AI FIR Assistance, AI Case Summaries, Legal Section "
                "Assistance. Investigation Tools: Entity Network, Entity Review Queue, Case Diary Generator, Chargesheet "
                "Generator. Administration: Employee Management (district and state officers only) and Audit Trail. An "
                "'All FIR Folders' menu sits next to these groups.",
    },
    {
        "id": "case_management", "title": "Case Management", "path": "/cases",
        "keywords": ["case management", "cases", "case list", "search case", "filter", "open case", "existing fir",
                     "old fir", "archived", "కేసు నిర్వహణ", "కేసులు", "పాత ఎఫ్‌ఐఆర్", "వెతకండి", "केस प्रबंधन", "केस",
                     "पुरानी एफआईआर", "खोज"],
        "text": "Case Management lists the cases in your jurisdiction with tabs All Cases, Under Review, Approved FIRs, "
                "Pending Drafts and Archived, and a search box for FIR number, contraband, offence or vehicle. Drafts "
                "show 'Continue Draft'; other cases show 'Review Case' and 'Details'. 'Resume or Start New Draft' starts "
                "or continues an FIR application form.",
    },
    {
        "id": "case_detail", "title": "Case detail page", "path": "/cases",
        "keywords": ["case detail", "edit case", "edit fields", "case history", "evidence documents", "export", "archive case",
                     "replace document", "provenance", "override", "కేసు వివరాలు", "సవరించు", "ఎగుమతి", "केस विवरण", "संपादित",
                     "निर्यात"],
        "text": "Opening a case shows its particulars with buttons Edit Fields, Replace Doc, Legal Sections, Case Diary, "
                "Chargesheet and Archive (Restore for archived cases). It lists Linked Accused & Conveyances, Original "
                "Evidence Documents with View PDF, and Extracted Field Provenance where an extracted value can be "
                "overridden. Official Case Export downloads Excel, Word, PDF or JSON. 'Inspect Repeat Offender & Network "
                "Graph' opens the network view. Edits and replacements are recorded in the audit trail.",
    },
    {
        "id": "case_status_review", "title": "Case status and approval", "path": "/cases",
        "keywords": ["status", "approve", "approval", "review", "sign off", "submit", "draft", "in review", "permission",
                     "ఆమోదం", "స్థితి", "సమర్పించు", "అనుమతి", "स्वीकृति", "स्थिति", "जमा", "अनुमति"],
        "text": "Case statuses are DRAFT (saved, not submitted), IN_REVIEW (registered and awaiting officer "
                "verification) and APPROVED (formally verified). A newly confirmed intake case starts as IN_REVIEW; the "
                "system never approves a case automatically. Case diaries and chargesheets generated by the workflow stay "
                "DRAFT until an officer approves them on the Case Diary or Chargesheet page. This assistant cannot "
                "submit, approve, delete or change records; it can only explain how to do it.",
    },
    {
        "id": "new_case_intake", "title": "New Case Intake", "path": "/intake",
        "keywords": ["new case", "intake", "register fir", "new fir", "upload evidence", "typed narrative", "confirm",
                     "registration", "కొత్త కేసు", "నమోదు", "కొత్త ఎఫ్‌ఐఆర్", "అప్‌లోడ్", "नया केस", "पंजीकरण", "नई एफआईआर",
                     "अपलोड"],
        "text": "New Case Intake has three input tabs: Evidence Upload / OCR (upload an FIR image or PDF; the text is "
                "extracted and fields are proposed), Typed Narrative (type or paste the occurrence in English, Telugu or "
                "Hindi and press 'Extract Structured Case Fields') and Voice Intake. Review every proposed field, correct "
                "it, then press the confirm button to register the case; FIR number, district, station and offence are "
                "required. Registration needs your sign-off and places the case in IN_REVIEW.",
    },
    {
        "id": "voice_intake", "title": "Voice Intake tab", "path": "/intake",
        "keywords": ["voice intake", "record voice", "dictate fir", "voice fir", "వాయిస్ ఇన్‌టేక్", "వాయిస్", "आवाज़",
                     "वॉयस इनटेक"],
        "text": "The Voice Intake tab on New Case Intake is not a working recorder: its button sends a placeholder "
                "instead of microphone audio and the server answers with a fixed sample transcript, so it cannot capture "
                "a real statement. Use the Typed Narrative tab, or upload the written FIR on Evidence Upload / OCR. This "
                "voice assistant answers questions; it does not register cases.",
    },
    {
        "id": "intake_workflow", "title": "Intake workflow stages", "path": "/intake",
        "keywords": ["workflow", "stage", "stages", "running", "pipeline", "officer review", "sign-off", "ai & legal",
                     "investigation tools", "administration & existing firs", "repeat offender", "retry", "needs review",
                     "వర్క్‌ఫ్లో", "దశ", "దశలు", "चरण", "वर्कफ़्लो"],
        "text": "The intake page tracks six stages: 1 Evidence Upload / OCR, 2 Officer Review & Sign-Off, 3 AI & Legal "
                "Intelligence (suggested legal sections), 4 Investigation Tools (draft case diary and chargesheet), 5 "
                "Administration & Existing FIRs (readiness check, case listed in Existing FIRs), 6 Repeat Offender & "
                "Criminal Network Intelligence. Stages 3 to 6 run only after the case is registered. Each shows PENDING, "
                "RUNNING, COMPLETED, FAILED or NEEDS REVIEW from the server; NEEDS REVIEW on stage 5 means some automated "
                "stages did not complete. A failed stage can be retried: the retry runs only stages that did not "
                "complete. An AI failure never undoes the registration.",
    },
    {
        "id": "confirmation_errors", "title": "Confirmation errors", "path": "/intake",
        "keywords": ["confirmation failed", "error", "500", "failed", "cannot confirm", "duplicate", "too long", "jurisdiction",
                     "లోపం", "విఫలం", "ధృవీకరణ", "त्रुटि", "विफल", "पुष्टि"],
        "text": "If confirmation fails, the page now shows the reason and marks the fields to correct. 'Missing required "
                "fields' lists fields to fill. 'Fields need correction' with TOO LONG means a value exceeds its limit "
                "(for example the seized-quantity unit allows 20 characters). OUT OF JURISDICTION means the station or "
                "district is not yours. 'FIR number already registered' means another case uses that number. 'Database "
                "could not be reached' means nothing was saved; confirm again. Confirming the same review twice returns "
                "the same case and never creates a duplicate.",
    },
    {
        "id": "ai_extraction", "title": "FIR Document Extraction (AI Extraction)", "path": "/document-extraction",
        "keywords": ["extraction", "ai extraction", "ocr", "extract", "fields", "entities", "confidence", "scan", "pdf", "image",
                     "upload image", "ఎక్స్‌ట్రాక్షన్", "ఓసీఆర్", "సంగ్రహణ", "निष्कर्षण", "ओसीआर", "स्कैन"],
        "text": "FIR Document Extraction is an AI workspace: choose an image or PDF with 'Choose File from Computer', "
                "and the page shows the document beside the extraction results, structured fields and entities "
                "(people, places, dates, vehicles, contraband, sections) with confidence values. Correct uncertain "
                "values before using them; 'Confirm & Register Case' registers the reviewed case. The Config tab edits "
                "extraction schemas. Extracted text is OCR and may contain reading errors; the original file remains "
                "the evidence. Unreadable or unsupported files are reported instead of being guessed.",
    },
    {
        "id": "knowledge_base", "title": "Knowledge Base & Legal Corpus", "path": "/knowledge-base",
        "keywords": ["knowledge base", "legal corpus", "laws", "circulars", "orders", "seizure reports", "guides", "sop",
                     "reference", "historical fir records", "approved evidence", "upload document", "నాలెడ్జ్ బేస్",
                     "చట్టాలు", "సర్క్యులర్", "జ్ఞాన", "ज्ञान", "कानून", "परिपत्र", "दस्तावेज़"],
        "text": "Knowledge Base & Legal Corpus holds Official Laws & Sections, Circulars & Orders, Seizure Reports, "
                "Investigation Guides & SOPs, Reference Materials, Historical FIR Records and Approved Evidence. Filter "
                "by category, index status, source, legal status and jurisdiction, search inside documents, or use the "
                "Act & Section Browser. Each document shows a source badge (Official source, Secondary, Synthetic / demo "
                "or Unverified) and an index status; 'Partially indexed' or 'Needs review' means its text is incomplete. "
                "Uploading laws, circulars and guides is limited to district and state officers.",
    },
    {
        "id": "rag_assistant", "title": "AI FIR Assistance (RAG chatbot)", "path": "/ai-fir-assistance",
        "keywords": ["ai fir assistance", "chatbot", "rag", "ask question", "scope", "current fir", "case + evidence",
                     "fir + law", "all authorised", "citations", "చాట్‌బాట్", "ప్రశ్న", "చాట్", "चैटबॉट", "प्रश्न", "चैट"],
        "text": "AI FIR Assistance answers only from documents you may access, with citations. Choose a scope: Current "
                "FIR (only the selected FIR), Case + evidence (the selected case's documents), FIR + Law (the FIR plus "
                "the legal corpus, keeping the two apart), Knowledge Base (laws, circulars, guides, references, approved "
                "evidence) or All authorised (everything in your jurisdiction). Ask in English, Telugu or Hindi. If the "
                "sources do not contain the answer it says it could not find sufficient information instead of "
                "guessing; widen the scope if you are authorised. A system error is reported as an error, never as an "
                "answer.",
    },
    {
        "id": "citations", "title": "Source citations", "path": "/ai-fir-assistance",
        "keywords": ["citation", "citations", "source", "page reference", "verify section", "official", "unverified",
                     "మూలం", "పేజీ", "ఆధారం", "स्रोत", "पृष्ठ", "संदर्भ"],
        "text": "Answers and summaries cite their sources as [S1], [S2]; each citation names the document and the page "
                "or section. To verify a legal section, open the cited document in the Knowledge Base and read the "
                "provision on the cited page. Official sources are marked 'Official source'; summaries marked "
                "'Unverified' are not the authoritative text. A warning is added when an answer mentions a section that "
                "is not in its sources.",
    },
    {
        "id": "ai_case_summaries", "title": "AI Case Summaries", "path": "/summaries",
        "keywords": ["summary", "summaries", "case summary", "historical fir", "batch", "translate summary", "సారాంశం",
                     "సారాంశాలు", "सारांश"],
        "text": "AI Case Summaries summarises historical FIR records: FIR documents and registered cases without an FIR "
                "document. Search and filter by FIR number, district, station, case status, dates and summary state. "
                "Choose English, Telugu or Hindi; all three are produced from the same sources with citations to "
                "document and page, and missing details are shown as 'Not available in the source'. Records without "
                "readable text are marked as needing OCR or review. 'Summarise all pending' or 'Summarise selected' runs "
                "a batch with a progress bar; it pauses when the AI quota runs out and resumes when started again. A "
                "summary marked outdated was written before its source changed.",
    },
    {
        "id": "legal_sections", "title": "Legal Section Assistance", "path": "/legal",
        "keywords": ["legal section", "laws and sections", "section", "act", "applicable law", "recommend section",
                     "సెక్షన్", "చట్టం", "धारा", "अधिनियम", "कानून"],
        "text": "Legal Section Assistance suggests statutory sections for a case and shows, for each, the evidenced "
                "facts that match its ingredients and the ingredients not yet established, with an India Code citation. "
                "You decide with 'Accept Section' or 'Reject'. Suggestions are decision support, not legal advice: verify "
                "each section against its official text before relying on it.",
    },
    {
        "id": "network", "title": "Entity Network and Open Network Intelligence", "path": "/network",
        "keywords": ["network", "entity network", "graph", "network intelligence", "open network intelligence", "connections",
                     "syndicate", "repeat offender", "నెట్‌వర్క్", "సంబంధాలు", "పునరావృత", "नेटवर्क", "संबंध", "बार-बार"],
        "text": "Entity Network (Investigation Tools) shows an interactive graph of persons, vehicles, locations, "
                "organisations and phone numbers linked across cases; selecting a node shows its links and an 'Open FIR' "
                "link. 'Open Network Intelligence' is a button on New Case Intake after registration (stage 6, Repeat "
                "Offender & Criminal Network Intelligence); the case page has 'Inspect Repeat Offender & Network Graph'. "
                "Links and risk scores are investigative leads to verify, not findings.",
    },
    {
        "id": "entity_review", "title": "Entity Review Queue", "path": "/entity-review",
        "keywords": ["entity review", "duplicate", "merge", "duplicates", "review queue", "నకిలీ", "విలీనం", "डुप्लिकेट",
                     "विलय"],
        "text": "Entity Review Queue lists possible duplicate persons and vehicles. Compare the candidates and use "
                "'Confirm Merge into Canonical Profile' only when they are the same entity; the dashboard's 'Entity "
                "Duplicate Resolution' item links here.",
    },
    {
        "id": "case_diary_chargesheet", "title": "Case Diary and Chargesheet", "path": "/case-diary",
        "keywords": ["case diary", "chargesheet", "charge sheet", "diary", "investigation progress", "కేస్ డైరీ", "ఛార్జ్‌షీట్",
                     "केस डायरी", "चार्जशीट", "आरोप पत्र"],
        "text": "Case Diary Generator drafts the investigation diary and Chargesheet Generator compiles a chargesheet "
                "from verified case facts. Each has Regenerate, an approve button (Approve Document or Approve "
                "Chargesheet) and a DOCX download. Drafts created by the intake workflow stay DRAFT until an officer "
                "approves them.",
    },
    {
        "id": "administration", "title": "Administration, roles and jurisdiction", "path": "/employees",
        "keywords": ["administration", "admin", "employee", "employees", "roles", "role", "permissions", "jurisdiction",
                     "station", "district", "state", "password", "registration request", "అడ్మిన్", "ఉద్యోగులు", "పాత్ర",
                     "అధికార పరిధి", "प्रशासन", "कर्मचारी", "भूमिका", "अधिकार क्षेत्र"],
        "text": "There are three roles. STATE officers see every district; DISTRICT officers see their district; "
                "STATION officers see their station. The server enforces this on every list, search, document and "
                "answer, so records outside your jurisdiction are never shown. Employee Management (district and state "
                "officers only) provisions officers, approves or rejects pending registrations and resets passwords.",
    },
    {
        "id": "audit", "title": "Audit Trail", "path": "/audit-trail",
        "keywords": ["audit", "audit trail", "log", "history", "verification", "ఆడిట్", "చరిత్ర", "ऑडिट", "इतिहास"],
        "text": "Audit Trail lists recorded actions (case creation and confirmation, edits, document replacements, "
                "approvals, summary generation) in a tamper-evident SHA-256 hash chain.",
    },
    {
        "id": "fir_folders", "title": "All FIR Folders", "path": "/folders",
        "keywords": ["folder", "folders", "all fir folders", "category", "illicit distillation", "ndps", "persons",
                     "ఫోల్డర్", "ఫోల్డర్లు", "फ़ोल्डर", "फोल्डर"],
        "text": "The 'All FIR Folders' menu groups cases into offence folders (for example Illicit Distillation, NDPS / "
                "Drug Transport, Non-Duty-Paid Liquor, Vehicle Seizure, Theft, Cheating / Fraud, Cyber Crime), status "
                "folders (Pending Classification, Under Investigation, Closed / Charge-sheeted) and person folders "
                "(Single-FIR and Multiple-FIR Persons). Each folder can be searched by FIR number or offence, and 'Open "
                "Case' opens the case with its documents and extracted text.",
    },
    {
        "id": "evidence_viewer", "title": "Original evidence and extracted text", "path": "/cases",
        "keywords": ["evidence", "original", "view pdf", "viewer", "document missing", "file not found", "extracted text",
                     "missing file", "సాక్ష్యం", "అసలు", "ఫైల్", "साक्ष्य", "मूल", "फ़ाइल"],
        "text": "Open a case and use View PDF under Original Evidence Documents to see the original file; images can be "
                "zoomed and PDFs paged. Extracted (OCR) text is a reading of the original and may contain errors. If the "
                "viewer says 'Original File Not in Storage', the extracted text is still available and an authorised "
                "officer can re-upload the original through the audited replace option.",
    },
    {
        "id": "bulk_ingestion", "title": "Bulk Document Ingestion", "path": "/bulk-ingestion",
        "keywords": ["bulk", "bulk ingestion", "batch upload", "legacy records", "csv", "బల్క్", "సామూహిక", "बल्क", "थोक"],
        "text": "Bulk Document Ingestion uploads historical datasets (PDFs, CSV or scanned FIRs) in one job and lists "
                "processing jobs with their history.",
    },
    {
        "id": "language", "title": "Language settings", "path": "/",
        "keywords": ["language", "telugu", "hindi", "english", "translate", "భాష", "తెలుగు", "హిందీ", "भाषा", "हिंदी",
                     "तेलुगु"],
        "text": "Use the EN / తెలుగు / हिंदी buttons in the top header to change the interface language. AI FIR "
                "Assistance and AI Case Summaries also have their own language choice, and this voice assistant has a "
                "language selector; names, FIR numbers and section numbers are kept as written in the source.",
    },
    {
        "id": "reports_settings", "title": "Reports and Settings", "path": "/reports",
        "keywords": ["reports", "analytics", "hotspots", "settings", "system health", "backup", "రిపోర్ట్", "నివేదిక",
                     "సెట్టింగ్", "रिपोर्ट", "सेटिंग"],
        "text": "Reports and Analytics shows district and state trends, geospatial hotspots and risk-model evaluation. "
                "Settings and System Health shows service status, backup snapshot creation and downloadable guides.",
    },
    {
        "id": "troubleshooting", "title": "Common troubleshooting", "path": "/",
        "keywords": ["not working", "problem", "trouble", "help", "microphone", "mic", "permission denied", "network error",
                     "could not find", "not found", "quota", "సమస్య", "సహాయం", "మైక్", "समस्या", "मदद", "माइक"],
        "text": "'Could not find sufficient supporting information' means the selected sources do not contain the "
                "answer; try a wider scope. 'The server could not be reached' means the backend or network is down. An "
                "AI quota message means the AI provider's daily limit was reached; stored answers and summaries remain "
                "available and generation resumes later. For the voice assistant, allow microphone access in the "
                "browser's address bar; speech recognition works in Chrome or Edge, and the text box works everywhere.",
    },
]

_WORD = re.compile(r"[\wఀ-౿ऀ-ॿ]+", re.UNICODE)
_STOP = {"the", "a", "an", "is", "are", "what", "how", "do", "i", "to", "of", "in", "on", "for", "and", "or", "my",
         "me", "can", "use", "does", "this", "that", "it", "with", "where", "which", "about", "tell", "explain",
         "please", "show", "there", "be", "you", "your", "from", "at", "by", "as"}


def _tokens(text: str) -> List[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOP]


def search_guide(question: str, limit: int = 3) -> List[Dict]:
    """Guide entries ranked by overlap with the question; keyword phrases weigh most."""
    q = (question or "").lower()
    q_tokens = set(_tokens(q))
    scored = []
    for entry in GUIDE:
        score = 0.0
        for kw in entry["keywords"]:
            kw_l = kw.lower()
            if " " in kw_l or not kw_l.isascii():
                if kw_l in q:
                    score += 3.0 + len(kw_l.split())
            elif kw_l in q_tokens:
                score += 2.5
        title_tokens = set(_tokens(entry["title"]))
        score += 1.5 * len(q_tokens & title_tokens)
        score += 0.3 * len(q_tokens & set(_tokens(entry["text"])))
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]
