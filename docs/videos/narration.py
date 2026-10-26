"""
Narration for the FIR VisionAI walkthrough videos (English and Telugu).

Each chapter lists scenes: a screenshot id (captured by make_walkthrough.py, or None for a title
card) and one narrated sentence per language. Every statement describes behaviour verified in the
application's code; on-screen labels are kept in English because that is what officers see.
"""

CHAPTERS = [
    {
        "title": {"en": "Welcome", "te": "స్వాగతం"},
        "scenes": [
            (None, {"en": "Welcome to FIR VisionAI, the u-FIR platform of the Andhra Pradesh Prohibition and Excise Department.",
                    "te": "FIR VisionAI కు స్వాగతం. ఇది ఆంధ్రప్రదేశ్ ప్రొహిబిషన్ మరియు ఎక్సైజ్ శాఖకు చెందిన u-FIR వేదిక."}),
            (None, {"en": "This video walks you through every part of the application, chapter by chapter.",
                    "te": "ఈ వీడియో అప్లికేషన్‌లోని ప్రతి భాగాన్ని అధ్యాయాల వారీగా మీకు పరిచయం చేస్తుంది."}),
        ],
    },
    {
        "title": {"en": "Signing in", "te": "లాగిన్ అవ్వడం"},
        "scenes": [
            ("login", {"en": "Sign in on the Sign In tab with your username and password.",
                       "te": "సైన్ ఇన్ ట్యాబ్‌లో మీ యూజర్‌నేమ్ మరియు పాస్‌వర్డ్‌తో లాగిన్ అవ్వండి."}),
            ("login", {"en": "Your role, station, district or state, decides which records you can see, everywhere in the application.",
                       "te": "మీ పాత్ర, అంటే స్టేషన్, జిల్లా లేదా రాష్ట్ర స్థాయి, అప్లికేషన్ అంతటా మీరు ఏ రికార్డులను చూడగలరో నిర్ణయిస్తుంది."}),
            ("login", {"en": "New officers can request an account on the registration tab; an administrator must approve it before it can be used.",
                       "te": "కొత్త అధికారులు రిజిస్ట్రేషన్ ట్యాబ్‌లో ఖాతా కోసం దరఖాస్తు చేయవచ్చు; అడ్మినిస్ట్రేటర్ ఆమోదించిన తర్వాతే అది పనిచేస్తుంది."}),
        ],
    },
    {
        "title": {"en": "Home dashboard", "te": "హోమ్ డాష్‌బోర్డ్"},
        "scenes": [
            ("dashboard_top", {"en": "After signing in, the Home dashboard shows your name, your jurisdiction scope and your station, with shortcuts to New Case Intake and AI FIR Assistance.",
                               "te": "లాగిన్ అయిన తర్వాత హోమ్ డాష్‌బోర్డ్ మీ పేరు, మీ అధికార పరిధి మరియు స్టేషన్‌ను చూపిస్తుంది. New Case Intake, AI FIR Assistance కు షార్ట్‌కట్‌లు కూడా ఉంటాయి."}),
            ("dashboard_top", {"en": "Quick Access has four cards: Existing or Old FIRs, New FIRs, Laws and Sections, and the AI FIR Chatbot.",
                               "te": "Quick Access లో నాలుగు కార్డులు ఉన్నాయి: Existing లేదా Old FIRs, New FIRs, Laws and Sections, మరియు AI FIR Chatbot."}),
            ("dashboard_kpi", {"en": "The count cards show Total Scoped Cases, cases Under Review, Approved FIRs and Pending Drafts, always limited to your jurisdiction. Click a card to open those cases.",
                               "te": "కౌంట్ కార్డులు Total Scoped Cases, Under Review, Approved FIRs మరియు Pending Drafts ను చూపిస్తాయి; ఇవి ఎప్పుడూ మీ అధికార పరిధికే పరిమితం. ఆ కేసులను తెరవడానికి కార్డుపై క్లిక్ చేయండి."}),
            ("dashboard_kpi", {"en": "The Action Items and Verification Queue lists extracted fields waiting for your sign-off and duplicate entities to review.",
                               "te": "Action Items and Verification Queue మీ ఆమోదం కోసం వేచి ఉన్న ఫీల్డ్‌లను, సమీక్షించాల్సిన నకిలీ ఎంటిటీలను చూపిస్తుంది."}),
        ],
    },
    {
        "title": {"en": "Case Management", "te": "కేసు నిర్వహణ"},
        "scenes": [
            ("cases", {"en": "Case Management lists every case in your jurisdiction, with tabs for All Cases, Under Review, Approved FIRs, Pending Drafts and Archived.",
                       "te": "Case Management మీ అధికార పరిధిలోని ప్రతి కేసును చూపిస్తుంది. All Cases, Under Review, Approved FIRs, Pending Drafts, Archived అనే ట్యాబ్‌లు ఉన్నాయి."}),
            ("cases", {"en": "Search by FIR number, contraband, offence or vehicle to find any record, including old FIRs.",
                       "te": "పాత ఎఫ్‌ఐఆర్‌లతో సహా ఏ రికార్డునైనా కనుగొనడానికి ఎఫ్‌ఐఆర్ సంఖ్య, సరుకు, నేరం లేదా వాహనం ద్వారా వెతకండి."}),
            ("case_detail", {"en": "Opening a case shows its particulars, the linked accused and vehicles, the original evidence documents, and where each extracted value came from.",
                             "te": "కేసును తెరిస్తే దాని వివరాలు, సంబంధిత నిందితులు మరియు వాహనాలు, అసలు సాక్ష్య పత్రాలు, ప్రతి విలువ ఎక్కడి నుండి వచ్చిందో కనిపిస్తుంది."}),
            ("case_detail", {"en": "From here you can edit fields, replace a document, open the case diary and chargesheet, export the case, or archive it. Every change is recorded in the audit trail.",
                             "te": "ఇక్కడి నుండి ఫీల్డ్‌లను సవరించవచ్చు, పత్రాన్ని మార్చవచ్చు, కేస్ డైరీ మరియు ఛార్జ్‌షీట్ తెరవవచ్చు, కేసును ఎగుమతి చేయవచ్చు లేదా ఆర్కైవ్ చేయవచ్చు. ప్రతి మార్పు ఆడిట్ ట్రైల్‌లో నమోదవుతుంది."}),
        ],
    },
    {
        "title": {"en": "New Case Intake", "te": "కొత్త కేసు నమోదు"},
        "scenes": [
            ("intake", {"en": "New Case Intake registers a new FIR. Upload the FIR image or PDF on the Evidence Upload and OCR tab, or type the narrative on the Typed Narrative tab.",
                        "te": "New Case Intake ద్వారా కొత్త ఎఫ్‌ఐఆర్ నమోదు చేస్తారు. Evidence Upload and OCR ట్యాబ్‌లో ఎఫ్‌ఐఆర్ చిత్రం లేదా PDF అప్‌లోడ్ చేయండి, లేదా Typed Narrative ట్యాబ్‌లో వివరణ టైప్ చేయండి."}),
            ("intake", {"en": "The system reads the text and proposes the fields. Review every field, correct anything wrong, and confirm to sign off.",
                        "te": "సిస్టమ్ పాఠ్యాన్ని చదివి ఫీల్డ్‌లను సూచిస్తుంది. ప్రతి ఫీల్డ్‌ను సమీక్షించి, తప్పులను సరిచేసి, ఆమోదించడానికి నిర్ధారించండి."}),
            ("intake", {"en": "The case is registered as Under Review and is never approved automatically.",
                        "te": "కేసు Under Review గా నమోదవుతుంది; ఇది ఎప్పుడూ స్వయంచాలకంగా ఆమోదించబడదు."}),
            ("intake", {"en": "Six stages track the work: upload and OCR, officer review, AI and legal intelligence, investigation drafts, administration, and network intelligence. A failed stage can be retried.",
                        "te": "ఆరు దశలు పనిని ట్రాక్ చేస్తాయి: అప్‌లోడ్ మరియు OCR, అధికారి సమీక్ష, AI మరియు చట్ట విశ్లేషణ, దర్యాప్తు ముసాయిదాలు, అడ్మినిస్ట్రేషన్, నెట్‌వర్క్ ఇంటెలిజెన్స్. విఫలమైన దశను మళ్లీ ప్రయత్నించవచ్చు."}),
            ("intake", {"en": "If processing fails or is interrupted, press Retry processing; the file does not need to be uploaded again.",
                        "te": "ప్రాసెసింగ్ విఫలమైతే లేదా ఆగిపోతే Retry processing నొక్కండి; ఫైల్‌ను మళ్లీ అప్‌లోడ్ చేయాల్సిన అవసరం లేదు."}),
            ("intake", {"en": "Note that the Voice Intake tab is still a placeholder and does not record real audio; use Typed Narrative instead.",
                        "te": "గమనిక: Voice Intake ట్యాబ్ ఇంకా పూర్తి కాలేదు, ఇది నిజమైన ఆడియోను రికార్డ్ చేయదు; బదులుగా Typed Narrative ఉపయోగించండి."}),
        ],
    },
    {
        "title": {"en": "AI Extraction", "te": "AI ఎక్స్‌ట్రాక్షన్"},
        "scenes": [
            ("extraction", {"en": "FIR Document Extraction shows the document beside the extracted fields and entities, each with a confidence value.",
                            "te": "FIR Document Extraction పత్రాన్ని, దాని నుండి తీసిన ఫీల్డ్‌లు మరియు ఎంటిటీలను పక్కపక్కనే చూపిస్తుంది; ప్రతిదానికీ విశ్వసనీయత విలువ ఉంటుంది."}),
            ("extraction", {"en": "Correct uncertain values before using them. The extracted text is a reading of the original, and the original file always remains the evidence.",
                            "te": "అనిశ్చిత విలువలను ఉపయోగించే ముందు సరిచేయండి. తీసిన పాఠ్యం అసలు పత్రం యొక్క పఠనం మాత్రమే; అసలు ఫైలే ఎప్పుడూ సాక్ష్యం."}),
        ],
    },
    {
        "title": {"en": "AI FIR Assistance", "te": "AI FIR Assistance"},
        "scenes": [
            ("ai_assist", {"en": "AI FIR Assistance answers questions only from documents you are allowed to see, and cites the document and page for every statement.",
                           "te": "AI FIR Assistance మీకు అనుమతి ఉన్న పత్రాల నుండి మాత్రమే సమాధానాలు ఇస్తుంది, ప్రతి వాక్యానికి పత్రం మరియు పేజీని ఆధారంగా చూపిస్తుంది."}),
            ("ai_assist", {"en": "Choose a scope: Current FIR, Case plus evidence, FIR plus Law, Knowledge Base, or All authorised. Ask in English, Telugu or Hindi.",
                           "te": "పరిధిని ఎంచుకోండి: Current FIR, Case plus evidence, FIR plus Law, Knowledge Base, లేదా All authorised. ఇంగ్లీష్, తెలుగు లేదా హిందీలో అడగవచ్చు."}),
            ("ai_assist", {"en": "If the documents do not contain the answer, it says so instead of guessing.",
                           "te": "పత్రాలలో సమాధానం లేకపోతే, ఊహించకుండా ఆ విషయాన్నే స్పష్టంగా చెబుతుంది."}),
        ],
    },
    {
        "title": {"en": "Knowledge Base", "te": "నాలెడ్జ్ బేస్"},
        "scenes": [
            ("kb", {"en": "The Knowledge Base holds official laws and sections, circulars and orders, seizure reports, investigation guides, reference material, historical FIR records and approved evidence.",
                    "te": "నాలెడ్జ్ బేస్‌లో అధికారిక చట్టాలు మరియు సెక్షన్లు, సర్క్యులర్లు మరియు ఉత్తర్వులు, స్వాధీన నివేదికలు, దర్యాప్తు మార్గదర్శకాలు, రిఫరెన్స్ పత్రాలు, చారిత్రక ఎఫ్‌ఐఆర్ రికార్డులు మరియు ఆమోదించిన సాక్ష్యాలు ఉంటాయి."}),
            ("kb", {"en": "Filter by category, source and status, search inside documents, or browse acts section by section. Source badges show which texts are official and which are unverified.",
                    "te": "వర్గం, మూలం మరియు స్థితి ద్వారా ఫిల్టర్ చేయండి, పత్రాల లోపల వెతకండి, లేదా చట్టాలను సెక్షన్ల వారీగా చూడండి. ఏ పాఠ్యం అధికారికమో, ఏది ధృవీకరించబడలేదో సోర్స్ బ్యాడ్జ్‌లు చూపిస్తాయి."}),
        ],
    },
    {
        "title": {"en": "AI Case Summaries", "te": "AI కేసు సారాంశాలు"},
        "scenes": [
            ("summaries", {"en": "AI Case Summaries writes cited summaries of historical FIR records in English, Telugu and Hindi, all from the same source text.",
                           "te": "AI Case Summaries చారిత్రక ఎఫ్‌ఐఆర్ రికార్డులకు ఇంగ్లీష్, తెలుగు, హిందీలో ఆధారాలతో కూడిన సారాంశాలను ఒకే మూల పాఠ్యం నుండి తయారు చేస్తుంది."}),
            ("summaries", {"en": "Missing details are marked as not available in the source, and records without readable text are flagged for OCR or review instead of being guessed.",
                           "te": "లేని వివరాలు మూలంలో అందుబాటులో లేవని గుర్తించబడతాయి; చదవగలిగే పాఠ్యం లేని రికార్డులు ఊహించకుండా OCR లేదా సమీక్ష కోసం గుర్తించబడతాయి."}),
            ("summaries", {"en": "A batch can summarise many records at once, with a progress bar, and resumes where it stopped.",
                           "te": "బ్యాచ్ ద్వారా చాలా రికార్డులను ఒకేసారి, ప్రోగ్రెస్ బార్‌తో సంగ్రహించవచ్చు; ఆగిన చోటు నుండి మళ్లీ కొనసాగుతుంది."}),
        ],
    },
    {
        "title": {"en": "Legal Section Assistance", "te": "చట్ట సెక్షన్ సహాయం"},
        "scenes": [
            ("legal", {"en": "Legal Section Assistance suggests sections for a case and shows which ingredients are supported by the facts and which are not yet established.",
                       "te": "Legal Section Assistance కేసుకు సెక్షన్లను సూచిస్తుంది; ఏ అంశాలకు వాస్తవాల మద్దతు ఉందో, ఏవి ఇంకా నిరూపించబడలేదో చూపిస్తుంది."}),
            ("legal", {"en": "You accept or reject each suggestion. These are decision support, not legal advice, so verify every section against its official text.",
                       "te": "ప్రతి సూచనను మీరు అంగీకరించవచ్చు లేదా తిరస్కరించవచ్చు. ఇవి నిర్ణయ సహాయం మాత్రమే, చట్ట సలహా కాదు; ప్రతి సెక్షన్‌ను దాని అధికారిక పాఠ్యంతో సరిచూడండి."}),
        ],
    },
    {
        "title": {"en": "Investigation Tools", "te": "దర్యాప్తు సాధనాలు"},
        "scenes": [
            ("network", {"en": "Entity Network shows people, vehicles, locations and phone numbers linked across cases. Treat links and risk scores as leads to verify, not findings.",
                         "te": "Entity Network కేసుల మధ్య సంబంధం ఉన్న వ్యక్తులు, వాహనాలు, ప్రదేశాలు, ఫోన్ నంబర్లను చూపిస్తుంది. సంబంధాలు మరియు రిస్క్ స్కోర్లను నిర్ధారణలుగా కాకుండా, ధృవీకరించాల్సిన ఆధారాలుగా పరిగణించండి."}),
            ("entity_review", {"en": "The Entity Review Queue lists possible duplicate persons and vehicles; merge them only when they are the same entity.",
                               "te": "Entity Review Queue నకిలీ కావచ్చని అనిపించే వ్యక్తులు, వాహనాలను చూపిస్తుంది; అవి ఒకటే అయినప్పుడు మాత్రమే విలీనం చేయండి."}),
            ("case_diary", {"en": "The Case Diary and Chargesheet generators draft documents from verified case facts. Drafts stay drafts until an officer approves them.",
                            "te": "Case Diary మరియు Chargesheet జనరేటర్లు ధృవీకరించిన కేసు వివరాల నుండి ముసాయిదాలను తయారు చేస్తాయి. అధికారి ఆమోదించే వరకు అవి ముసాయిదాలుగానే ఉంటాయి."}),
        ],
    },
    {
        "title": {"en": "Administration", "te": "అడ్మినిస్ట్రేషన్"},
        "scenes": [
            ("employees", {"en": "Employee Management, available to district and state officers, provisions officer accounts, approves registration requests and resets passwords.",
                           "te": "జిల్లా మరియు రాష్ట్ర అధికారులకు అందుబాటులో ఉండే Employee Management ద్వారా అధికారుల ఖాతాలు సృష్టించవచ్చు, రిజిస్ట్రేషన్ అభ్యర్థనలను ఆమోదించవచ్చు, పాస్‌వర్డ్‌లను రీసెట్ చేయవచ్చు."}),
            ("audit", {"en": "The Audit Trail records important actions, such as registrations, edits, approvals and document replacements, in a tamper-evident hash chain.",
                       "te": "Audit Trail నమోదులు, సవరణలు, ఆమోదాలు, పత్రాల మార్పులు వంటి ముఖ్యమైన చర్యలను మార్చలేని హాష్ చైన్‌లో నమోదు చేస్తుంది."}),
        ],
    },
    {
        "title": {"en": "All FIR Folders", "te": "అన్ని ఎఫ్‌ఐఆర్ ఫోల్డర్లు"},
        "scenes": [
            ("folders_menu", {"en": "The All FIR Folders menu groups cases by offence, by status and by person.",
                              "te": "All FIR Folders మెనూ కేసులను నేరం, స్థితి మరియు వ్యక్తి ఆధారంగా వర్గీకరిస్తుంది."}),
            ("folder_view", {"en": "Each folder has its own search, and Open Case takes you to the full record with its documents.",
                             "te": "ప్రతి ఫోల్డర్‌కు ప్రత్యేక శోధన ఉంటుంది; Open Case నొక్కితే పత్రాలతో సహా పూర్తి రికార్డు తెరుచుకుంటుంది."}),
        ],
    },
    {
        "title": {"en": "Voice assistant", "te": "వాయిస్ సహాయకుడు"},
        "scenes": [
            ("voice", {"en": "The headphones button at the bottom right opens the voice assistant on every page. Speak or type in English, Telugu or Hindi.",
                       "te": "ప్రతి పేజీలో కుడి వైపు కింద ఉన్న హెడ్‌ఫోన్స్ బటన్ వాయిస్ సహాయకుడిని తెరుస్తుంది. ఇంగ్లీష్, తెలుగు లేదా హిందీలో మాట్లాడవచ్చు లేదా టైప్ చేయవచ్చు."}),
            ("voice", {"en": "It explains how to use the application, tells you live counts and FIR status within your jurisdiction, and answers legal questions with citations. It never approves, submits or deletes records.",
                       "te": "ఇది అప్లికేషన్‌ను ఎలా ఉపయోగించాలో వివరిస్తుంది, మీ పరిధిలోని ప్రత్యక్ష కేసుల సంఖ్యలు, ఎఫ్‌ఐఆర్ స్థితిని చెబుతుంది, ఆధారాలతో చట్ట ప్రశ్నలకు సమాధానం ఇస్తుంది. ఇది రికార్డులను ఎప్పుడూ ఆమోదించదు, సమర్పించదు, తొలగించదు."}),
        ],
    },
    {
        "title": {"en": "Thank you", "te": "ధన్యవాదాలు"},
        "scenes": [
            (None, {"en": "That completes the tour of FIR VisionAI. For help at any time, open the voice assistant or ask your administrator.",
                    "te": "FIR VisionAI పరిచయం ఇంతటితో పూర్తయింది. ఎప్పుడైనా సహాయం కావాలంటే వాయిస్ సహాయకుడిని తెరవండి లేదా మీ అడ్మినిస్ట్రేటర్‌ను సంప్రదించండి."}),
        ],
    },
]
