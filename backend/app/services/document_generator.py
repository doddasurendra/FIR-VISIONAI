import os
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from jinja2 import Template
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from ..config import settings
from ..models.case import Case, CaseField
from ..models.document import Document, DocumentChunk
from ..models.entity import Entity, EntityMention
from ..models.legal import CaseLegalSection
from .auth import enforce_data_scope
from .legal_service import CaseAccessDenied
from ..models.generation import GeneratedDocument, DocumentApprovalHistory
from ..models.user import User

logger = logging.getLogger(__name__)

# Register Indic font for Telugu & Hindi if available on Windows or Linux
INDIC_FONT_NAME = "Helvetica"
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\Nirmala.ttf",
    r"C:\Windows\Fonts\NirmalaB.ttf",
    r"C:\Windows\Fonts\Arial.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
]
for fp in FONT_CANDIDATES:
    if os.path.exists(fp):
        try:
            pdfmetrics.registerFont(TTFont("IndicFont", fp))
            INDIC_FONT_NAME = "IndicFont"
            break
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────────────────
# 1. ENGLISH TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────
CASE_DIARY_TEMPLATE_EN = """
ANDHRA PRADESH LAW ENFORCEMENT & PROHIBITION EXCISE
INVESTIGATION CASE DIARY (SECTION 172 CrPC / SECTION 192 BNSS)
======================================================
[STATE: DRAFT | EVIDENCE-GROUNDED INVESTIGATION DRAFT]

Case Crime No: {{ case.fir_number or 'UNASSIGNED — OFFICER ENTRY REQUIRED' }}
Jurisdiction Station: {{ case.station or 'Station Pending Verification' }}, {{ case.district }} District
Date of Entry: {{ entry_date }}
Investigating Officer: {{ officer.full_name }} ({{ officer.designation or 'Officer' }})

1. RECORDED CASE PARTICULARS:
   - Nature of Offence: {{ case.offence_nature or 'Not specified — verification required' }}
   - Date & Time of Offence: {{ facts.when or 'Not recorded in the FIR — officer to enter' }}
   - Occurrence Location: {{ facts.place or 'Not recorded in the FIR — officer to enter' }}
   {% if facts.accused %}
   - Accused: {{ facts.accused | join(', ') }}
   {% elif facts.accused_unknown %}
   - Accused: {{ facts.accused_unknown }} (as recorded in the FIR) — identification pending
   {% endif %}
   {% if facts.complainant %}
   - Complainant / Informant: {{ facts.complainant }}
   {% endif %}
   {% if case.contraband_type %}
   - Seized Property / Contraband: {{ case.contraband_type }}{% if case.seized_quantity %} (Quantity: {{ case.seized_quantity }} {{ case.seized_unit or 'units' }}){% endif %}
   {% else %}
   - Seized Property / Contraband: None recorded in primary FIR
   {% endif %}
   - Conveyance / Vehicle Details: {{ case.vehicle_details or 'None recorded' }}

2. APPLICABLE STATUTORY PROVISIONS:
   {% for c in charges %}
   - {{ c.ref }}{% if c.title %}: {{ c.title }}{% endif %} [{{ c.status_label }}]
   {% else %}
   - No section is recorded or suggested yet.
   {% endfor %}
   {% if not charges or charges[0].status != 'ACCEPTED' %}
   - Review and accept sections in Legal Section Assistance: {{ legal_link }}
   {% endif %}

3. INVESTIGATION RECORD & PRELIMINARY FACTS (FROM THE FIR):
   {% if facts.fir_text %}
   {{ facts.fir_text }}
   {% else %}
   - The FIR text is not available in the system; attach the FIR document to this case.
   {% endif %}

4. VERIFICATION STATUS & PENDING ACTIONS:
   {% if not case.witnesses_summary %}
   - [ACTION NEEDED] Examination of eyewitnesses and recording of Section 161 CrPC / BNSS statements.
   {% endif %}
   {% if case.contraband_type and not case.seized_quantity %}
   - [ACTION NEEDED] Exact quantification and chemical/forensic examination report.
   {% endif %}
   {% if case.vehicle_details %}
   - [ACTION NEEDED] Verification of conveyance ownership records from Transport Department.
   {% endif %}
   - Production of case diary before jurisdictional magistrate as per statutory timeline.

DRAFT PREPARED ON: {{ generation_time }}
DISCLAIMER: AI-Assisted evidence draft prepared from recorded case facts. Requires official signature and review.
{{ template_tag }}
"""

CHARGESHEET_TEMPLATE_EN = """
{% if is_incomplete %}
================================================================================
DRAFT CANNOT BE COMPLETED — ADDITIONAL VERIFIED INFORMATION REQUIRED
================================================================================
Case Crime No: {{ case.fir_number or 'MISSING' }}
Station: {{ case.station or 'MISSING' }}, {{ case.district or 'MISSING' }} District

The formal chargesheet / final report under Section 173 CrPC / Section 193 BNSS cannot
be compiled because mandatory verified case information is missing:
{% for field in missing_fields %}
  * {{ field }}
{% endfor %}

Please verify and complete the missing case details before generating the court chargesheet.
{% else %}
IN THE COURT OF THE JUDICIAL MAGISTRATE OF FIRST CLASS
FINAL POLICE / DEPARTMENTAL REPORT UNDER SECTION 173 CrPC / SECTION 193 BNSS
==================================================================
[DEPARTMENTAL WORKING DRAFT — REVIEWS AND APPROVALS REQUIRED]

State of Andhra Pradesh (Through Station: {{ case.station }})
Versus
Accused Persons: {% if facts.accused %}{% for a in facts.accused %}A-{{ loop.index }} {{ a }}{% if not loop.last %}, {% endif %}{% endfor %}{% elif facts.accused_unknown %}{{ facts.accused_unknown }} (as recorded in the FIR) — identification pending{% else %}Not yet identified — the investigating officer must add the accused{% endif %}

1. Crime Details:
   - Case Crime No: {{ case.fir_number }}
   - Year: {{ facts.year }}
   - Nature of Offence: {{ case.offence_nature }}
   - Date & Time of Offence: {{ facts.when or 'Not recorded in the FIR — officer to enter' }}
   - Occurrence Location: {{ facts.place or 'Not recorded in the FIR — officer to enter' }}

2. Charges Framed Under Laws:
   {% for c in charges %}
   * {{ c.ref }}{% if c.title %} ({{ c.title }}){% endif %} [{{ c.status_label }}]
   {% else %}
   * No section is recorded or suggested yet.
   {% endfor %}
   {% if not charges or charges[0].status != 'ACCEPTED' %}
   * Pending officer acceptance — review and accept sections in Legal Section Assistance: {{ legal_link }}
   {% endif %}

3. Prosecution Facts (Grounded in Verified Case Record):
   {{ facts.fir_text or 'The FIR text is not available in the system; attach the FIR document to this case.' }}

4. Seized Material Objects / Evidence:
   {% if case.contraband_type %}
   - M.O. 1: {{ case.contraband_type }}{% if case.seized_quantity %} ({{ case.seized_quantity }} {{ case.seized_unit or 'units' }}){% endif %}
   {% else %}
   - M.O. 1: No physical contraband / property seized in this case.
   {% endif %}
   {% if case.vehicle_details %}
   - M.O. 2: Conveyance {{ case.vehicle_details }}
   {% endif %}

5. Witnesses for Prosecution:
   {% if facts.complainant and not facts.complainant_is_officer %}
   - L.W. 1: {{ facts.complainant }} (Complainant / Informant)
   - L.W. 2: {{ case.seizing_officer_name or officer.full_name }} (Investigating Officer)
   {% else %}
   - L.W. 1: {{ case.seizing_officer_name or officer.full_name }} (Complainant / Investigating Officer)
   {% endif %}
   {% if case.witnesses_summary %}
   - Additional Witnesses: {{ case.witnesses_summary }}
   {% elif facts.witnesses %}
   - Independent witnesses named in the FIR: {{ facts.witnesses | join(', ') }}
   {% else %}
   - Independent witnesses: Subject to Section 161 statements during trial.
   {% endif %}

PRAYER: It is humbly prayed that the Hon'ble Court may be pleased to take cognizance of the offence against the accused and conduct trial in accordance with law.

Prepared by: {{ officer.full_name }} ({{ officer.designation or 'Investigating Officer' }})
Date of Draft: {{ entry_date }}
{% endif %}
{{ template_tag }}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 2. TELUGU TEMPLATES (తెలుగు)
# ─────────────────────────────────────────────────────────────────────────────
CASE_DIARY_TEMPLATE_TE = """
ఆంధ్రప్రదేశ్ ప్రభుత్వం — ప్రొహిబిషన్ & ఎక్సైజ్ శాఖ
దర్యాప్తు కేస్ డైరీ (సెక్షన్ 172 Cr.P.C. / సెక్షన్ 192 BNSS)
======================================================
[స్థితి: డ్రాఫ్ట్ | ఆధారాలతో ధృవీకరించబడిన దర్యాప్తు ముసాయిదా]

కేసు నేర సంఖ్య (Cr. No.): {{ case.fir_number or 'కేటాయించబడలేదు — అధికారి నమోదు అవసరం' }}
అధికారిక స్టేషన్: {{ case.station or 'పరిశీలనలో ఉంది' }}, {{ case.district }} జిల్లా
నమోదు తేదీ: {{ entry_date }}
దర్యాప్తు అధికారి: {{ officer.full_name }} ({{ officer.designation or 'అధికారి' }})

1. నమోదైన కేసు ప్రాథమిక వివరాలు:
   - నేర స్వభావం: {{ case.offence_nature or 'ధృవీకరణ పెండింగ్‌లో ఉంది' }}
   - సంఘటన తేదీ & సమయం: {{ facts.when or 'FIRలో నమోదు కాలేదు — అధికారి నమోదు చేయాలి' }}
   - సంఘటనా స్థలం (Incident Location): {{ facts.place or 'FIRలో నమోదు కాలేదు — అధికారి నమోదు చేయాలి' }}
   {% if facts.accused %}
   - నిందితులు: {{ facts.accused | join(', ') }}
   {% elif facts.accused_unknown %}
   - నిందితులు: {{ facts.accused_unknown }} (FIRలో నమోదైనట్లు) — గుర్తింపు పెండింగ్‌లో ఉంది
   {% endif %}
   {% if facts.complainant %}
   - ఫిర్యాదుదారు / సమాచారకర్త: {{ facts.complainant }}
   {% endif %}
   {% if case.contraband_type %}
   - స్వాధీనం చేసుకున్న నిషేధిత వస్తువులు: {{ case.contraband_type }}{% if case.seized_quantity %} (పరిమాణం: {{ case.seized_quantity }} {{ case.seized_unit or 'యూనిట్లు' }}){% endif %}
   {% else %}
   - స్వాధీనం చేసుకున్న నిషేధిత వస్తువులు: ప్రాథమిక FIRలో ఏమీ నమోదు కాలేదు
   {% endif %}
   - రవాణా వాహన వివరాలు: {{ case.vehicle_details or 'ఏమీ నమోదు కాలేదు' }}

2. వర్తించే చట్ట నిబంధనలు (Statutory Provisions):
   {% for c in charges %}
   - {{ c.ref }}{% if c.title %}: {{ c.title }}{% endif %} [{{ c.status_label }}]
   {% else %}
   - ఇంకా ఏ సెక్షన్ నమోదు కాలేదు లేదా సూచించబడలేదు.
   {% endfor %}
   {% if not charges or charges[0].status != 'ACCEPTED' %}
   - చట్టపరమైన సెక్షన్ సహాయం (Legal Section Assistance) లో సెక్షన్లను సమీక్షించి ఆమోదించండి: {{ legal_link }}
   {% endif %}

3. ప్రాథమిక వాస్తవాలు & దర్యాప్తు రికార్డు (FIR నుండి):
   {% if facts.fir_text %}
   {{ facts.fir_text }}
   {% else %}
   - FIR పాఠం వ్యవస్థలో అందుబాటులో లేదు; ఈ కేసుకు FIR పత్రాన్ని జత చేయండి.
   {% endif %}

4. ధృవీకరణ స్థితి & పెండింగ్ చర్యలు:
   {% if not case.witnesses_summary %}
   - [చర్య అవసరం] ప్రత్యక్ష సాక్షుల విచారణ మరియు సెక్షన్ 161 CrPC / BNSS వాంగ్మూలాల నమోదు.
   {% endif %}
   {% if case.contraband_type and not case.seized_quantity %}
   - [చర్య అవసరం] ఖచ్చితమైన పరిమాణ నిర్ధారణ మరియు ఫోరెన్సిక్ రసాయన ప్రయోగశాల పరీక్ష నివేదిక.
   {% endif %}
   {% if case.vehicle_details %}
   - [చర్య అవసరం] రవాణా శాఖ నుండి వాహన యాజమాన్య రికార్డుల ధృవీకరణ.
   {% endif %}
   - చట్టపరమైన కాలపరిమితి ప్రకారం అధికార న్యాయస్థానం (కోర్టు) ముందు కేస్ డైరీ సమర్పణ.

డ్రాఫ్ట్ తయారీ సమయం: {{ generation_time }}
గమనిక: కేస్ రికార్డుల నుండి AI సహాయంతో రూపొందించబడిన అధికారిక ముసాయిదా. అధికారి సంతకం మరియు ఆమోదం అవసరం.
{{ template_tag }}
"""

CHARGESHEET_TEMPLATE_TE = """
{% if is_incomplete %}
================================================================================
ముసాయిదా పూర్తి కాలేదు — అదనపు ధృవీకరించబడిన సమాచారం అవసరం
================================================================================
కేసు నేర సంఖ్య: {{ case.fir_number or 'తప్పిపోయింది' }}
స్టేషన్: {{ case.station or 'తప్పిపోయింది' }}, {{ case.district or 'తప్పిపోయింది' }} జిల్లా

ఈ క్రింది తప్పనిసరి సమాచారం నమోదు కాకపోవడం వల్ల సెక్షన్ 173 CrPC / సెక్షన్ 193 BNSS కింద
తుది నివేదిక / చార్జిషీట్‌ను రూపొందించడం సాధ్యం కాలేదు:
{% for field in missing_fields %}
  * {{ field }}
{% endfor %}

కోర్టు చార్జిషీట్‌ను రూపొందించే ముందు దయచేసి తప్పిపోయిన కేసు వివరాలను పూర్తి చేసి ధృవీకరించండి.
{% else %}
గౌరవనీయ జ్యుడీషియల్ ఫస్ట్ క్లాస్ మేజిస్ట్రేట్ వారి న్యాయస్థానంలో
సెక్షన్ 173 CrPC / సెక్షన్ 193 BNSS కింద పోలీసు / శాఖాపరమైన తుది నివేదిక (చార్జిషీట్)
==================================================================
[శాఖాపరమైన ముసాయిదా — అధికారిక సమీక్ష మరియు ఆమోదం అవసరం]

ఆంధ్రప్రదేశ్ ప్రభుత్వం (స్టేషన్ ద్వారా: {{ case.station }})
ఎదిరి
నిందితులు (Accused Persons): {% if facts.accused %}{% for a in facts.accused %}A-{{ loop.index }} {{ a }}{% if not loop.last %}, {% endif %}{% endfor %}{% elif facts.accused_unknown %}{{ facts.accused_unknown }} (FIRలో నమోదైనట్లు) — గుర్తింపు పెండింగ్‌లో ఉంది{% else %}ఇంకా గుర్తించబడలేదు — దర్యాప్తు అధికారి నిందితులను చేర్చాలి{% endif %}

1. నేర వివరాలు (Crime Details):
   - కేసు క్రైమ్ నంబర్: {{ case.fir_number }}
   - నమోదు సంవత్సరం: {{ facts.year }}
   - నేర స్వభావం: {{ case.offence_nature }}
   - సంఘటన తేదీ & సమయం: {{ facts.when or 'FIRలో నమోదు కాలేదు — అధికారి నమోదు చేయాలి' }}
   - సంఘటనా స్థలం: {{ facts.place or 'FIRలో నమోదు కాలేదు — అధికారి నమోదు చేయాలి' }}

2. చట్టాల కింద మోపిన అభియోగాలు (Charges Framed Under Laws):
   {% for c in charges %}
   * {{ c.ref }}{% if c.title %} ({{ c.title }}){% endif %} [{{ c.status_label }}]
   {% else %}
   * ఇంకా ఏ సెక్షన్ నమోదు కాలేదు లేదా సూచించబడలేదు.
   {% endfor %}
   {% if not charges or charges[0].status != 'ACCEPTED' %}
   * అధికారి ఆమోదం పెండింగ్‌లో ఉంది — చట్టపరమైన సెక్షన్ సహాయం (Legal Section Assistance) లో సెక్షన్లను సమీక్షించి ఆమోదించండి: {{ legal_link }}
   {% endif %}

3. ప్రాసిక్యూషన్ వాస్తవాలు (ధృవీకరించబడిన కేస్ రికార్డు ఆధారంగా):
   {{ facts.fir_text or 'FIR పాఠం వ్యవస్థలో అందుబాటులో లేదు; ఈ కేసుకు FIR పత్రాన్ని జత చేయండి.' }}

4. స్వాధీనం చేసుకున్న వస్తువులు / సాక్ష్యాలు (Material Objects):
   {% if case.contraband_type %}
   - M.O. 1: {{ case.contraband_type }}{% if case.seized_quantity %} ({{ case.seized_quantity }} {{ case.seized_unit or 'యూనిట్లు' }}){% endif %}
   {% else %}
   - M.O. 1: ఈ కేసులో ఎటువంటి నిషేధిత వస్తువులు స్వాధీనం చేసుకోబడలేదు.
   {% endif %}
   {% if case.vehicle_details %}
   - M.O. 2: రవాణా వాహనం {{ case.vehicle_details }}
   {% endif %}

5. ప్రాసిక్యూషన్ సాక్షులు (Witnesses for Prosecution):
   {% if facts.complainant and not facts.complainant_is_officer %}
   - L.W. 1: {{ facts.complainant }} (ఫిర్యాదుదారు / సమాచారకర్త)
   - L.W. 2: {{ case.seizing_officer_name or officer.full_name }} (దర్యాప్తు అధికారి)
   {% else %}
   - L.W. 1: {{ case.seizing_officer_name or officer.full_name }} (ఫిర్యాదుదారు / దర్యాప్తు అధికారి)
   {% endif %}
   {% if case.witnesses_summary %}
   - ఇతర సాక్షులు: {{ case.witnesses_summary }}
   {% elif facts.witnesses %}
   - FIRలో పేర్కొన్న స్వతంత్ర సాక్షులు: {{ facts.witnesses | join(', ') }}
   {% else %}
   - స్వతంత్ర సాక్షులు: విచారణ సమయంలో సెక్షన్ 161 వాంగ్మూలాలకు లోబడి ఉంటారు.
   {% endif %}

ప్రార్థన (PRAYER): నిందితులపై మోపబడిన నేరారోపణలను గౌరవనీయ న్యాయస్థానం పరిగణనలోకి తీసుకుని, చట్టప్రకారం న్యాయ విచారణ జరిపించవలసిందిగా వినయపూర్వకంగా ప్రార్థించడమైనది.

తయారు చేసిన అధికారి: {{ officer.full_name }} ({{ officer.designation or 'దర్యాప్తు అధికారి' }})
ముసాయిదా తేదీ: {{ entry_date }}
{% endif %}
{{ template_tag }}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 3. HINDI TEMPLATES (हिन्दी)
# ─────────────────────────────────────────────────────────────────────────────
CASE_DIARY_TEMPLATE_HI = """
आंध्र प्रदेश सरकार — मद्यनिषेध एवं आबकारी विभाग
अन्वेषण केस डायरी (धारा 172 Cr.P.C. / धारा 192 BNSS)
======================================================
[स्थिति: प्रारूप | साक्ष्यों पर आधारित अन्वेषण प्रारूप]

मामला अपराध संख्या (Cr. No.): {{ case.fir_number or 'अनावंटित — अधिकारी प्रविष्टि आवश्यक' }}
अधिकार क्षेत्र स्टेशन: {{ case.station or 'सत्यापनाधीन' }}, {{ case.district }} जिला
प्रविष्टि तिथि: {{ entry_date }}
अन्वेषण अधिकारी: {{ officer.full_name }} ({{ officer.designation or 'अधिकारी' }})

1. दर्ज मामले का विवरण:
   - अपराध की प्रकृति: {{ case.offence_nature or 'सत्यापन आवश्यक' }}
   - अपराध की तिथि व समय: {{ facts.when or 'प्राथमिकी में दर्ज नहीं — अधिकारी दर्ज करें' }}
   - घटनास्थल (Incident Location): {{ facts.place or 'प्राथमिकी में दर्ज नहीं — अधिकारी दर्ज करें' }}
   {% if facts.accused %}
   - अभियुक्त: {{ facts.accused | join(', ') }}
   {% elif facts.accused_unknown %}
   - अभियुक्त: {{ facts.accused_unknown }} (प्राथमिकी में दर्ज अनुसार) — पहचान लंबित
   {% endif %}
   {% if facts.complainant %}
   - शिकायतकर्ता / सूचनाकर्ता: {{ facts.complainant }}
   {% endif %}
   {% if case.contraband_type %}
   - जब्त की गई सामग्री: {{ case.contraband_type }}{% if case.seized_quantity %} (मात्रा: {{ case.seized_quantity }} {{ case.seized_unit or 'इकाइयां' }}){% endif %}
   {% else %}
   - जब्त की गई सामग्री: प्राथमिकी में दर्ज नहीं
   {% endif %}
   - वाहन का विवरण: {{ case.vehicle_details or 'कोई विवरण नहीं' }}

2. लागू वैधानिक धाराएं (Statutory Provisions):
   {% for c in charges %}
   - {{ c.ref }}{% if c.title %}: {{ c.title }}{% endif %} [{{ c.status_label }}]
   {% else %}
   - अभी तक कोई धारा दर्ज या सुझाई नहीं गई है।
   {% endfor %}
   {% if not charges or charges[0].status != 'ACCEPTED' %}
   - विधिक धारा सहायता (Legal Section Assistance) में धाराओं की समीक्षा कर स्वीकार करें: {{ legal_link }}
   {% endif %}

3. अन्वेषण विवरण व प्रारंभिक तथ्य (प्राथमिकी से):
   {% if facts.fir_text %}
   {{ facts.fir_text }}
   {% else %}
   - प्राथमिकी का पाठ सिस्टम में उपलब्ध नहीं है; इस मामले में प्राथमिकी दस्तावेज़ संलग्न करें।
   {% endif %}

4. सत्यापन स्थिति व लंबित कार्रवाई:
   {% if not case.witnesses_summary %}
   - [कार्रवाई आवश्यक] चश्मदीद गवाहों की जांच तथा धारा 161 CrPC / BNSS के तहत बयान दर्ज करना।
   {% endif %}
   {% if case.contraband_type and not case.seized_quantity %}
   - [कार्रवाई आवश्यक] सटीक मात्रा निर्धारण एवं रासायनिक प्रयोगशाला परीक्षण रिपोर्ट।
   {% endif %}
   {% if case.vehicle_details %}
   - [कार्रवाई आवश्यक] परिवहन विभाग से वाहन स्वामित्व का सत्यापन।
   {% endif %}
   - वैधानिक समय-सीमा के भीतर सक्षम न्यायालय के समक्ष केस डायरी प्रस्तुत करना।

प्रारूप निर्माण समय: {{ generation_time }}
नोट: दर्ज केस रिकॉर्ड से AI-सहायता द्वारा तैयार आधिकारिक प्रारूप। सक्षम अधिकारी के हस्ताक्षर व अनुमोदन आवश्यक।
{{ template_tag }}
"""

CHARGESHEET_TEMPLATE_HI = """
{% if is_incomplete %}
================================================================================
प्रारूप पूर्ण नहीं हो सका — अतिरिक्त सत्यापित जानकारी आवश्यक है
================================================================================
मामला अपराध संख्या: {{ case.fir_number or 'लापता' }}
थाना: {{ case.station or 'लापता' }}, {{ case.district or 'लापता' }} जिला

अनिवार्य जानकारी दर्ज न होने के कारण धारा 173 CrPC / धारा 193 BNSS के तहत
अंतिम पुलिस रिपोर्ट / आरोप पत्र तैयार नहीं किया जा सका:
{% for field in missing_fields %}
  * {{ field }}
{% endfor %}

न्यायालय हेतु आरोप पत्र तैयार करने से पूर्व कृपया छूटी हुई जानकारी पूर्ण व सत्यापित करें।
{% else %}
माननीय न्यायिक प्रथम श्रेणी मजिस्ट्रेट के न्यायालय में
धारा 173 CrPC / धारा 193 BNSS के तहत अंतिम पुलिस / विभागीय रिपोर्ट (आरोप पत्र)
==================================================================
[विभागीय कार्य प्रारूप — आधिकारिक समीक्षा एवं अनुमोदन अनिवार्य]

आंध्र प्रदेश राज्य (थाना: {{ case.station }} द्वारा)
बनाम
अभियुक्तगण (Accused Persons): {% if facts.accused %}{% for a in facts.accused %}A-{{ loop.index }} {{ a }}{% if not loop.last %}, {% endif %}{% endfor %}{% elif facts.accused_unknown %}{{ facts.accused_unknown }} (प्राथमिकी में दर्ज अनुसार) — पहचान लंबित{% else %}अभी पहचान नहीं हुई — अन्वेषण अधिकारी अभियुक्तों को जोड़ें{% endif %}

1. अपराध का विवरण (Crime Details):
   - मामला अपराध संख्या: {{ case.fir_number }}
   - वर्ष: {{ facts.year }}
   - अपराध की प्रकृति: {{ case.offence_nature }}
   - अपराध की तिथि व समय: {{ facts.when or 'प्राथमिकी में दर्ज नहीं — अधिकारी दर्ज करें' }}
   - घटनास्थल: {{ facts.place or 'प्राथमिकी में दर्ज नहीं — अधिकारी दर्ज करें' }}

2. विधि के अंतर्गत विरचित आरोप (Charges Framed Under Laws):
   {% for c in charges %}
   * {{ c.ref }}{% if c.title %} ({{ c.title }}){% endif %} [{{ c.status_label }}]
   {% else %}
   * अभी तक कोई धारा दर्ज या सुझाई नहीं गई है।
   {% endfor %}
   {% if not charges or charges[0].status != 'ACCEPTED' %}
   * अधिकारी स्वीकृति लंबित — विधिक धारा सहायता (Legal Section Assistance) में धाराओं की समीक्षा कर स्वीकार करें: {{ legal_link }}
   {% endif %}

3. अभियोजन पक्ष के तथ्य (सत्यापित केस रिकॉर्ड पर आधारित):
   {{ facts.fir_text or 'प्राथमिकी का पाठ सिस्टम में उपलब्ध नहीं है; इस मामले में प्राथमिकी दस्तावेज़ संलग्न करें।' }}

4. जब्त भौतिक साक्ष्य (Material Objects):
   {% if case.contraband_type %}
   - M.O. 1: {{ case.contraband_type }}{% if case.seized_quantity %} ({{ case.seized_quantity }} {{ case.seized_unit or 'इकाइयां' }}){% endif %}
   {% else %}
   - M.O. 1: इस मामले में कोई भौतिक सामग्री जब्त नहीं हुई।
   {% endif %}
   {% if case.vehicle_details %}
   - M.O. 2: प्रयुक्त वाहन {{ case.vehicle_details }}
   {% endif %}

5. अभियोजन पक्ष के गवाह (Witnesses for Prosecution):
   {% if facts.complainant and not facts.complainant_is_officer %}
   - L.W. 1: {{ facts.complainant }} (शिकायतकर्ता / सूचनाकर्ता)
   - L.W. 2: {{ case.seizing_officer_name or officer.full_name }} (अन्वेषण अधिकारी)
   {% else %}
   - L.W. 1: {{ case.seizing_officer_name or officer.full_name }} (शिकायतकर्ता / अन्वेषण अधिकारी)
   {% endif %}
   {% if case.witnesses_summary %}
   - अन्य गवाह: {{ case.witnesses_summary }}
   {% elif facts.witnesses %}
   - प्राथमिकी में नामित स्वतंत्र गवाह: {{ facts.witnesses | join(', ') }}
   {% else %}
   - स्वतंत्र गवाह: परीक्षण के दौरान धारा 161 के बयानों के अधीन।
   {% endif %}

प्रार्थना (PRAYER): माननीय न्यायालय से विनम्र प्रार्थना है कि अभियुक्त के विरुद्ध अपराध का संज्ञान लें तथा विधि सम्मत विचारण करें।

तैयारकर्ता: {{ officer.full_name }} ({{ officer.designation or 'अन्वेषण अधिकारी' }})
प्रारूप तिथि: {{ entry_date }}
{% endif %}
{{ template_tag }}
"""

# Drafts made by an older template (wrong section numbers, empty charges) are regenerated on open
TEMPLATE_VERSION = "2026.10"
TEMPLATE_TAG = f"[Template {TEMPLATE_VERSION}]"

CHARGE_STATUS_LABELS = {
    "en": {"ACCEPTED": "Accepted by officer", "PENDING": "Pending officer acceptance"},
    "te": {"ACCEPTED": "అధికారి ఆమోదించారు", "PENDING": "అధికారి ఆమోదం పెండింగ్‌లో ఉంది (Pending officer acceptance)"},
    "hi": {"ACCEPTED": "अधिकारी द्वारा स्वीकृत", "PENDING": "अधिकारी स्वीकृति लंबित (Pending officer acceptance)"},
}

_PAGE_MARK = re.compile(r"-{2,}\s*Page\s+\d+\s*-{2,}\s*", re.I)
_OCCURRENCE = re.compile(r"occurrence of offence|date of offence|date of occurrence", re.I)
_TIME_TEXT = re.compile(r"time(?:\s+period)?\s*:\s*((?:between\s+)?\d{1,2}[.:]\d{2}\s*(?:hrs|hours)?"
                        r"(?:\s*(?:and|to|-)\s*\d{1,2}[.:]\d{2}\s*(?:hrs|hours)?)?)", re.I)
_UNKNOWN_ACCUSED = re.compile(r"accused[^\n:]{0,60}:?\s*(?:\(a\)\s*)?Name\s*:[\s:]*(unknown[^\n]{0,40})", re.I)
_ACCUSED_AGE = re.compile(r"\(c\)\s*Age\s*:[\s:]*([^\n]{2,40})", re.I)
_PLACE_TEXT = re.compile(r"place\s+of\s+(?:occurrence|offence|incident)\s*:\s*([^\n]{4,160})", re.I)
DATE_FIELDS = ("offence_date", "incident_date", "date_of_offence", "occurrence_date")
TIME_FIELDS = ("offence_time", "incident_time", "time_of_offence", "occurrence_time")
PLACE_FIELDS = ("place_of_occurrence", "incident_location", "occurrence_location", "location", "place")
FIR_TEXT_LIMIT = 4000


def _section_ref(act: str, number: str) -> str:
    number = (number or "").strip()
    if not re.match(r"(?i)sec", number):
        number = f"Section {number}"
    return f"{number} {act}".strip()


def _occurrence_time(text: str) -> Optional[str]:
    """The offence time from the FIR's occurrence block (not the time the information was received)."""
    m = _OCCURRENCE.search(text or "")
    if not m:
        return None
    t = _TIME_TEXT.search(text[m.start():m.start() + 400])
    return re.sub(r"\s+", " ", t.group(1)).strip() if t else None


async def gather_case_facts(case: Case, db: AsyncSession) -> Dict[str, Any]:
    """
    Facts for the case diary and chargesheet: date, time and place of the offence from the case record,
    then the extracted fields, then the FIR text; accused and complainant from resolved entities, then
    the FIR text (placeholders such as "Unknown Suspect" excluded); and the FIR text itself.
    """
    from . import legal_rules as rules
    from .entity_resolution import is_placeholder
    from .fir_text_facts import find_people_and_identifiers

    fields: Dict[str, List[str]] = {}
    for name, value in (await db.execute(
        select(CaseField.field_name,
               func.coalesce(CaseField.human_override_value, CaseField.normalized_value, CaseField.original_value))
        .where(CaseField.case_id == case.id)
    )).all():
        if value not in (None, ""):
            fields.setdefault((name or "").lower(), []).append(str(value))

    def field(names):
        return next((v for n in names for v in fields.get(n, [])), None)

    doc_text = "\n".join(r[0] or "" for r in (await db.execute(
        select(DocumentChunk.chunk_text)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.case_id == case.id, Document.is_archived == False)  # noqa: E712
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index).limit(60)
    )).all())
    fir_text = _PAGE_MARK.sub("", case.narrative or doc_text or "").strip()
    all_text = f"{case.narrative or ''}\n{doc_text}"

    # Date and time
    when, when_source = None, None
    if case.offence_date:
        d = case.offence_date
        when = d.strftime("%d-%m-%Y") + (d.strftime(", %H:%M hrs") if (d.hour, d.minute) != (0, 0) else "")
        when_source = "case record"
    else:
        day = next((x for x in (rules.parse_date_value(v) for v in [field(DATE_FIELDS)] if v) if x), None)
        when_source = "extracted field" if day else None
        if not day:
            day = rules.incident_date_from_text(all_text)
            when_source = "FIR text" if day else None
        if day:
            when = day.strftime("%d-%m-%Y")
    if when and "hrs" not in when:
        tm = field(TIME_FIELDS) or _occurrence_time(all_text)
        if tm:
            when = f"{when}, {tm}"

    # Place
    place, place_source = field(PLACE_FIELDS) or case.location_description, "extracted field"
    if not place and case.village:
        place = ", ".join(filter(None, [case.village, case.mandal, case.district]))
    if not place:
        m = _PLACE_TEXT.search(all_text)
        place, place_source = (m.group(1).strip(" .") if m else None), "FIR text"
    if not place and case.incident_location_normalized:
        place, place_source = case.incident_location_normalized, "geocoded location"

    # People
    accused: List[str] = []
    for (name,) in (await db.execute(
        select(Entity.canonical_name).join(EntityMention, EntityMention.entity_id == Entity.id)
        .where(EntityMention.case_id == case.id, func.upper(EntityMention.role_in_case) == "ACCUSED")
        .order_by(EntityMention.created_at)
    )).all():
        if name and not is_placeholder(name) and name.lower() not in {a.lower() for a in accused}:
            accused.append(name)
    people = find_people_and_identifiers(all_text)
    if not accused:
        accused = people["accused"]
    accused = [re.sub(r"\s*\((?:verified|unverified|suspected?|absconding)\)\s*$", "", a, flags=re.I) for a in accused]
    complainant = people["complainant"][0] if people["complainant"] else None
    # An FIR against unknown persons: describe them as the FIR does ("Unknown person(s), about 25 to 30 years")
    accused_unknown = None
    if not accused:
        plain = all_text.replace("*", "")
        m = _UNKNOWN_ACCUSED.search(plain)
        if m:
            age = _ACCUSED_AGE.search(plain[m.end():m.end() + 300])
            accused_unknown = m.group(1).strip(" .") + (f", age {age.group(1).strip(' .')}" if age else "")

    if len(fir_text) > FIR_TEXT_LIMIT:
        fir_text = fir_text[:FIR_TEXT_LIMIT].rsplit("\n", 1)[0] + "\n[…FIR text continues in the attached FIR document]"
    # Indented under its section heading, without the OCR's empty lines
    fir_text = "\n   ".join(line.strip() for line in fir_text.splitlines() if line.strip())
    officer = (case.seizing_officer_name or "").lower()
    complainant_is_officer = bool(complainant and officer and
                                  (complainant.lower() in officer or officer.split(",")[0].strip() in complainant.lower()))
    # The FIR's own year ("89/2024") over a registration year that may have been entered later
    m = re.search(r"/((?:19|20)\d{2})\s*$", case.fir_number or "")
    year = int(m.group(1)) if m else case.year
    return {"when": when, "when_source": when_source, "year": year, "place": place, "place_source": place_source if place else None,
            "accused": accused, "accused_unknown": accused_unknown, "complainant": complainant,
            "complainant_is_officer": complainant_is_officer, "witnesses": people["witnesses"], "fir_text": fir_text}


async def charges_for_case(case: Case, sections: List[CaseLegalSection], user: User, db: AsyncSession,
                           lang: str) -> List[Dict[str, Any]]:
    """
    Sections the officer accepted; when none is accepted, the sections Legal Section Assistance suggests
    for the facts (excluding rejected ones and those the incident date rules out), marked as pending.
    """
    labels = CHARGE_STATUS_LABELS.get(lang, CHARGE_STATUS_LABELS["en"])
    accepted = [s for s in sections if s.officer_decision == "ACCEPTED"]
    if accepted:
        return [{"ref": _section_ref(s.act_name, s.section_number), "title": s.section_title,
                 "status": "ACCEPTED", "status_label": labels["ACCEPTED"]} for s in accepted]
    from .legal_service import LegalService
    try:
        rec = await LegalService.recommend_sections_for_case(case.id, user, db)
    except Exception:  # the document is still produced; the officer is pointed to Legal Section Assistance
        logger.exception("Section suggestions failed for case %s", case.id)
        return []
    return [{"ref": _section_ref(c["act_name"], c["section_number"]), "title": c.get("section_title"),
             "status": "PENDING", "status_label": labels["PENDING"]}
            for c in rec.get("candidates", [])
            if c.get("regime_applies", True) and c.get("officer_decision") != "REJECTED"]


def is_outdated(doc: GeneratedDocument) -> bool:
    """A draft from an older template; approved documents are never replaced."""
    return (doc.doc_type in ("CASE_DIARY", "CHARGESHEET") and doc.status != "APPROVED"
            and TEMPLATE_TAG not in (doc.content or ""))


class DocumentGeneratorService:
    @staticmethod
    async def generate_draft(
        case_id: str,
        doc_type: str, # CASE_DIARY, CHARGESHEET, CASE_SUMMARY
        user: User,
        db: AsyncSession,
        language: str = "en"
    ) -> GeneratedDocument:
        stmt = select(Case).where(Case.id == case_id)
        res = await db.execute(stmt)
        case = res.scalar_one_or_none()
        if not case:
            raise ValueError("Case not found")
        if not enforce_data_scope(user, case.district, case.station):
            raise CaseAccessDenied("Access denied: this case is outside your jurisdiction.")

        lang = (language or "en").lower().strip()
        if lang not in ("en", "te", "hi"):
            lang = "en"

        # Fetch sections
        sec_stmt = select(CaseLegalSection).where(CaseLegalSection.case_id == case_id)
        sec_res = await db.execute(sec_stmt)
        sections = sec_res.scalars().all()
        facts = await gather_case_facts(case, db)
        charges = await charges_for_case(case, sections, user, db, lang)

        # Evaluate completeness for court chargesheet
        missing_fields = []
        if not case.fir_number or case.fir_number.strip().upper() in ("UNKNOWN", "PENDING", ""):
            missing_fields.append("FIR Crime Number (MANDATORY)" if lang == "en" else ("FIR క్రైమ్ నంబర్ (తప్పనిసరి)" if lang == "te" else "प्राथमिकी अपराध संख्या (अनिवार्य)"))
        if not case.district or case.district.strip().upper() in ("UNKNOWN", ""):
            missing_fields.append("District Jurisdiction (MANDATORY)" if lang == "en" else ("జిల్లా అధికార పరిధి (తప్పనిసరి)" if lang == "te" else "जिला अधिकार क्षेत्र (अनिवार्य)"))
        if not case.station or case.station.strip().upper() in ("UNKNOWN", ""):
            missing_fields.append("Police / Excise Station Jurisdiction (MANDATORY)" if lang == "en" else ("స్టేషన్ అధికార పరిధి (తప్పనిసరి)" if lang == "te" else "थाना अधिकार क्षेत्र (अनिवार्य)"))
        if not case.offence_nature or len(case.offence_nature.strip()) < 5:
            missing_fields.append("Specific Offence Description (MANDATORY)" if lang == "en" else ("నిర్దిష్ట నేర స్వభావ వివరణ (తప్పనిసరి)" if lang == "te" else "विशिष्ट अपराध विवरण (अनिवार्य)"))
        # Sections not yet accepted do not block the draft: they are listed as pending officer acceptance

        is_incomplete = (len(missing_fields) > 0 and doc_type == "CHARGESHEET")

        # Select template by doc_type and language
        if doc_type == "CASE_DIARY":
            if lang == "te":
                template_str = CASE_DIARY_TEMPLATE_TE
            elif lang == "hi":
                template_str = CASE_DIARY_TEMPLATE_HI
            else:
                template_str = CASE_DIARY_TEMPLATE_EN
        else:
            if lang == "te":
                template_str = CHARGESHEET_TEMPLATE_TE
            elif lang == "hi":
                template_str = CHARGESHEET_TEMPLATE_HI
            else:
                template_str = CHARGESHEET_TEMPLATE_EN

        # A line holding only {% if %} / {% for %} / ... renders as nothing, not as an empty line
        template = Template(re.sub(r"(?m)^[ \t]*({%[^%]*%})[ \t]*\n", r"\1", template_str))
        rendered_content = template.render(
            case=case,
            sections=sections,
            charges=charges,
            facts=facts,
            legal_link=f"/legal?caseId={case.id}",
            template_tag=TEMPLATE_TAG,
            officer=user,
            entry_date=datetime.utcnow().strftime("%d-%m-%Y"),
            generation_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            is_incomplete=is_incomplete,
            missing_fields=missing_fields
        )
        rendered_content = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", rendered_content)  # blank lines left by {% if %}

        lang_suffix = " (తెలుగు)" if lang == "te" else (" (हिन्दी)" if lang == "hi" else "")
        title_str = f"{doc_type.replace('_', ' ').title()} - {case.fir_number}{lang_suffix}"

        # Each regeneration is a new version; earlier versions (and officer edits) are kept
        latest = (await db.execute(select(func.max(GeneratedDocument.version)).where(
            GeneratedDocument.case_id == case_id,
            GeneratedDocument.doc_type == doc_type,
            GeneratedDocument.language == lang
        ))).scalar()

        doc = GeneratedDocument(
            case_id=case_id,
            doc_type=doc_type,
            language=lang,
            title=title_str,
            content=rendered_content,
            version=(latest or 0) + 1,
            status="DRAFT",
            created_by=user.id
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    def export_pdf(doc: GeneratedDocument, output_path: str):
        """Generate PDF using ReportLab with font support for English, Telugu, and Hindi."""
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter

        # Watermark
        c.saveState()
        c.setFont("Helvetica-Bold", 38)
        c.setFillColor(colors.Color(0.85, 0.85, 0.85, alpha=0.30))
        c.translate(width / 2, height / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, f"DRAFT - {doc.status}")
        c.restoreState()

        # Header bar
        c.setFont("Helvetica-Bold", 12)
        c.drawString(45, height - 45, "GOVERNMENT OF ANDHRA PRADESH - PROHIBITION & EXCISE DEPARTMENT")
        c.setFont(INDIC_FONT_NAME if INDIC_FONT_NAME != "Helvetica" else "Helvetica-Bold", 11)
        c.drawString(45, height - 65, doc.title)
        c.setFont("Helvetica", 8)
        lang_str = "TELUGU" if doc.language == "te" else ("HINDI" if doc.language == "hi" else "ENGLISH")
        c.drawString(45, height - 80, f"Language: {lang_str} | Version: {doc.version} | Status: {doc.status} | Date: {datetime.utcnow().strftime('%d-%m-%Y')}")
        c.line(45, height - 87, width - 45, height - 87)

        # Body text
        text_obj = c.beginText(45, height - 110)
        text_obj.setFont(INDIC_FONT_NAME, 9)
        text_obj.setLeading(13)

        lines = doc.content.split("\n")
        lines_written = 0
        for line in lines:
            if lines_written > 48:
                c.drawText(text_obj)
                c.showPage()
                # Next page setup
                text_obj = c.beginText(45, height - 50)
                text_obj.setFont(INDIC_FONT_NAME, 9)
                text_obj.setLeading(13)
                lines_written = 0

            # Wrap long lines
            line_clean = line.rstrip()
            if len(line_clean) > 85:
                # simple word wrap
                words = line_clean.split(" ")
                cur = ""
                for w in words:
                    if len(cur) + len(w) + 1 <= 85:
                        cur += (" " if cur else "") + w
                    else:
                        text_obj.textLine(cur)
                        lines_written += 1
                        cur = w
                if cur:
                    text_obj.textLine(cur)
                    lines_written += 1
            else:
                text_obj.textLine(line_clean)
                lines_written += 1

        c.drawText(text_obj)
        c.showPage()
        c.save()

    @staticmethod
    def export_docx(doc: GeneratedDocument, output_path: str):
        """Generate DOCX document supporting full English, Telugu, and Hindi Unicode text."""
        import docx
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        d = docx.Document()
        for section in d.sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.8)
            section.right_margin = Inches(0.8)

        # Header Title
        title_p = d.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_dept = title_p.add_run("GOVERNMENT OF ANDHRA PRADESH\nPROHIBITION & EXCISE DEPARTMENT\n")
        run_dept.bold = True
        run_dept.font.size = Pt(13)
        run_dept.font.color.rgb = RGBColor(15, 81, 50)

        run_title = title_p.add_run(f"{doc.title}\n")
        run_title.bold = True
        run_title.font.size = Pt(12)

        meta_p = d.add_paragraph()
        meta_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        lang_label = "తెలుగు (Telugu)" if doc.language == "te" else ("हिन्दी (Hindi)" if doc.language == "hi" else "English")
        meta_run = meta_p.add_run(f"Status: {doc.status} | Version: {doc.version} | Language: {lang_label}\n")
        meta_run.font.size = Pt(9)
        meta_run.font.italic = True

        d.add_paragraph("―" * 50)

        # Content lines
        for line in doc.content.split("\n"):
            line_str = line.strip()
            if not line_str:
                d.add_paragraph("")
                continue
            if line_str.startswith("=") or line_str.startswith("---"):
                continue
            p = d.add_paragraph()
            # If header/section line
            if re.match(r'^\d+\.\s+', line_str) or (len(line_str) < 40 and line_str.endswith(":")):
                run = p.add_run(line_str)
                run.bold = True
                run.font.size = Pt(11)
            else:
                run = p.add_run(line_str)
                run.font.size = Pt(10)

        # Signature section
        d.add_paragraph("\n\n")
        sig_p = d.add_paragraph()
        sig_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        sig_run = sig_p.add_run("______________________________\nAuthorized Investigating Officer\nAndhra Pradesh Prohibition & Excise")
        sig_run.font.size = Pt(10)
        sig_run.bold = True

        d.save(output_path)

document_generator = DocumentGeneratorService()
