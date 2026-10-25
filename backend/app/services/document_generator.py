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
from sqlalchemy import select, desc
from ..config import settings
from ..models.case import Case
from ..models.legal import CaseLegalSection
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
INVESTIGATION CASE DIARY (SECTION 172 CrPC / 193 BNSS)
======================================================
[STATE: DRAFT | EVIDENCE-GROUNDED INVESTIGATION DRAFT]

Case Crime No: {{ case.fir_number or 'UNASSIGNED — OFFICER ENTRY REQUIRED' }}
Jurisdiction Station: {{ case.station or 'Station Pending Verification' }}, {{ case.district }} District
Date of Entry: {{ entry_date }}
Investigating Officer: {{ officer.full_name }} ({{ officer.designation or 'Officer' }})

1. RECORDED CASE PARTICULARS:
   - Nature of Offence: {{ case.offence_nature or 'Not specified — verification required' }}
   - Date & Time of Offence: {{ case.offence_date or 'Under investigation' }}
   - Occurrence Location: {{ case.incident_location_normalized or case.location_description or (case.village ~ ', ' ~ case.mandal if case.village else 'Location details under investigation') }}
   {% if case.contraband_type %}
   - Seized Property / Contraband: {{ case.contraband_type }}{% if case.seized_quantity %} (Quantity: {{ case.seized_quantity }} {{ case.seized_unit or 'units' }}){% endif %}
   {% else %}
   - Seized Property / Contraband: None recorded in primary FIR
   {% endif %}
   - Conveyance / Vehicle Details: {{ case.vehicle_details or 'None recorded' }}

2. APPLICABLE STATUTORY PROVISIONS:
   {% for sec in sections %}
   - {{ sec.act_name }} {{ sec.section_number }}: {{ sec.section_title }} [{{ sec.officer_decision }}]
   {% else %}
   - Statutory provisions subject to ongoing investigation and officer confirmation.
   {% endfor %}

3. INVESTIGATION RECORD & PRELIMINARY FACTS:
   {% if case.narrative %}
   {{ case.narrative }}
   {% else %}
   - Initial FIR registered based on incident report. Detailed investigative steps pending recording.
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
"""

CHARGESHEET_TEMPLATE_EN = """
{% if is_incomplete %}
================================================================================
DRAFT CANNOT BE COMPLETED — ADDITIONAL VERIFIED INFORMATION REQUIRED
================================================================================
Case Crime No: {{ case.fir_number or 'MISSING' }}
Station: {{ case.station or 'MISSING' }}, {{ case.district or 'MISSING' }} District

The formal chargesheet / final report under Section 173 CrPC / 193 BNSS cannot
be compiled because mandatory verified case information is missing:
{% for field in missing_fields %}
  * {{ field }}
{% endfor %}

Please verify and complete the missing case details before generating the court chargesheet.
{% else %}
IN THE COURT OF THE JUDICIAL MAGISTRATE OF FIRST CLASS
FINAL POLICE / DEPARTMENTAL REPORT UNDER SECTION 173 CrPC / 193 BNSS
==================================================================
[DEPARTMENTAL WORKING DRAFT — REVIEWS AND APPROVALS REQUIRED]

State of Andhra Pradesh (Through Station: {{ case.station }})
Versus
Accused Persons

1. Crime Details:
   - Case Crime No: {{ case.fir_number }}
   - Year: {{ case.year }}
   - Nature of Offence: {{ case.offence_nature }}
   - Occurrence Location: {{ case.incident_location_normalized or case.location_description or (case.village ~ ', ' ~ case.mandal if case.village else 'Jurisdiction area') }}

2. Statutory Charges:
   {% for sec in sections %}
   * {{ sec.act_name }} {{ sec.section_number }} ({{ sec.section_title }})
   {% else %}
   * Applicable penal sections subject to judicial submission.
   {% endfor %}

3. Prosecution Facts (Grounded in Verified Case Record):
   {{ case.narrative or 'Facts as recorded in initial First Information Report.' }}

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
   - L.W. 1: {{ case.seizing_officer_name or officer.full_name }} (Complainant / Investigating Officer)
   {% if case.witnesses_summary %}
   - Additional Witnesses: {{ case.witnesses_summary }}
   {% else %}
   - Independent witnesses: Subject to Section 161 statements during trial.
   {% endif %}

PRAYER: It is humbly prayed that the Hon'ble Court may be pleased to take cognizance of the offence against the accused and conduct trial in accordance with law.

Prepared by: {{ officer.full_name }} ({{ officer.designation or 'Investigating Officer' }})
Date of Draft: {{ entry_date }}
{% endif %}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 2. TELUGU TEMPLATES (తెలుగు)
# ─────────────────────────────────────────────────────────────────────────────
CASE_DIARY_TEMPLATE_TE = """
ఆంధ్రప్రదేశ్ ప్రభుత్వం — ప్రొహిబిషన్ & ఎక్సైజ్ శాఖ
దర్యాప్తు కేస్ డైరీ (సెక్షన్ 172 Cr.P.C. / 193 BNSS)
======================================================
[స్థితి: డ్రాఫ్ట్ | ఆధారాలతో ధృవీకరించబడిన దర్యాప్తు ముసాయిదా]

కేసు నేర సంఖ్య (Cr. No.): {{ case.fir_number or 'కేటాయించబడలేదు — అధికారి నమోదు అవసరం' }}
అధికారిక స్టేషన్: {{ case.station or 'పరిశీలనలో ఉంది' }}, {{ case.district }} జిల్లా
నమోదు తేదీ: {{ entry_date }}
దర్యాప్తు అధికారి: {{ officer.full_name }} ({{ officer.designation or 'అధికారి' }})

1. నమోదైన కేసు ప్రాథమిక వివరాలు:
   - నేర స్వభావం: {{ case.offence_nature or 'ధృవీకరణ పెండింగ్‌లో ఉంది' }}
   - సంఘటన తేదీ & సమయం: {{ case.offence_date or 'విచారణలో ఉంది' }}
   - సంఘటనా స్థలం (Incident Location): {{ case.incident_location_normalized or case.location_description or (case.village ~ ', ' ~ case.mandal if case.village else 'దర్యాప్తులో ఉంది') }}
   {% if case.contraband_type %}
   - స్వాధీనం చేసుకున్న నిషేధిత వస్తువులు: {{ case.contraband_type }}{% if case.seized_quantity %} (పరిమాణం: {{ case.seized_quantity }} {{ case.seized_unit or 'యూనిట్లు' }}){% endif %}
   {% else %}
   - స్వాధీనం చేసుకున్న నిషేధిత వస్తువులు: ప్రాథమిక FIRలో ఏమీ నమోదు కాలేదు
   {% endif %}
   - రవాణా వాహన వివరాలు: {{ case.vehicle_details or 'ఏమీ నమోదు కాలేదు' }}

2. వర్తించే చట్ట నిబంధనలు (Statutory Provisions):
   {% for sec in sections %}
   - {{ sec.act_name }} సెక్షన్ {{ sec.section_number }}: {{ sec.section_title }} [{{ sec.officer_decision }}]
   {% else %}
   - చట్టపరమైన నిబంధనలు దర్యాప్తులో ఉన్నాయి.
   {% endfor %}

3. ప్రాథమిక వాస్తవాలు & దర్యాప్తు రికార్డు:
   {% if case.narrative %}
   {{ case.narrative }}
   {% else %}
   - సంఘటన నివేదిక ఆధారంగా ప్రాథమిక FIR నమోదు చేయబడింది. వివరణాత్మక దర్యాప్తు చర్యలు నమోదు చేయబడుతున్నాయి.
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
"""

CHARGESHEET_TEMPLATE_TE = """
{% if is_incomplete %}
================================================================================
ముసాయిదా పూర్తి కాలేదు — అదనపు ధృవీకరించబడిన సమాచారం అవసరం
================================================================================
కేసు నేర సంఖ్య: {{ case.fir_number or 'తప్పిపోయింది' }}
స్టేషన్: {{ case.station or 'తప్పిపోయింది' }}, {{ case.district or 'తప్పిపోయింది' }} జిల్లా

ఈ క్రింది తప్పనిసరి సమాచారం నమోదు కాకపోవడం వల్ల సెక్షన్ 173 CrPC / 193 BNSS కింద
తుది నివేదిక / చార్జిషీట్‌ను రూపొందించడం సాధ్యం కాలేదు:
{% for field in missing_fields %}
  * {{ field }}
{% endfor %}

కోర్టు చార్జిషీట్‌ను రూపొందించే ముందు దయచేసి తప్పిపోయిన కేసు వివరాలను పూర్తి చేసి ధృవీకరించండి.
{% else %}
గౌరవనీయ జ్యుడీషియల్ ఫస్ట్ క్లాస్ మేజిస్ట్రేట్ వారి న్యాయస్థానంలో
సెక్షన్ 173 CrPC / 193 BNSS కింద పోలీసు / శాఖాపరమైన తుది నివేదిక (చార్జిషీట్)
==================================================================
[శాఖాపరమైన ముసాయిదా — అధికారిక సమీక్ష మరియు ఆమోదం అవసరం]

ఆంధ్రప్రదేశ్ ప్రభుత్వం (స్టేషన్ ద్వారా: {{ case.station }})
ఎదిరి
నిందితులు (Accused Persons)

1. నేర వివరాలు (Crime Details):
   - కేసు క్రైమ్ నంబర్: {{ case.fir_number }}
   - నమోదు సంవత్సరం: {{ case.year }}
   - నేర స్వభావం: {{ case.offence_nature }}
   - సంఘటనా స్థలం: {{ case.incident_location_normalized or case.location_description or (case.village ~ ', ' ~ case.mandal if case.village else 'అధికార పరిధి') }}

2. చట్టపరమైన అభియోగాలు (Statutory Charges):
   {% for sec in sections %}
   * {{ sec.act_name }} సెక్షన్ {{ sec.section_number }} ({{ sec.section_title }})
   {% else %}
   * వర్తించే చట్ట నిబంధనలు న్యాయస్థానానికి సమర్పించబడతాయి.
   {% endfor %}

3. ప్రాసిక్యూషన్ వాస్తవాలు (ధృవీకరించబడిన కేస్ రికార్డు ఆధారంగా):
   {{ case.narrative or 'ప్రథమ సమాచార నివేదిక (FIR)లో నమోదైన వాస్తవాలు.' }}

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
   - L.W. 1: {{ case.seizing_officer_name or officer.full_name }} (ఫిర్యాదుదారు / దర్యాప్తు అధికారి)
   {% if case.witnesses_summary %}
   - ఇతర సాక్షులు: {{ case.witnesses_summary }}
   {% else %}
   - స్వతంత్ర సాక్షులు: విచారణ సమయంలో సెక్షన్ 161 వాంగ్మూలాలకు లోబడి ఉంటారు.
   {% endif %}

ప్రార్థన (PRAYER): నిందితులపై మోపబడిన నేరారోపణలను గౌరవనీయ న్యాయస్థానం పరిగణనలోకి తీసుకుని, చట్టప్రకారం న్యాయ విచారణ జరిపించవలసిందిగా వినయపూర్వకంగా ప్రార్థించడమైనది.

తయారు చేసిన అధికారి: {{ officer.full_name }} ({{ officer.designation or 'దర్యాప్తు అధికారి' }})
ముసాయిదా తేదీ: {{ entry_date }}
{% endif %}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 3. HINDI TEMPLATES (हिन्दी)
# ─────────────────────────────────────────────────────────────────────────────
CASE_DIARY_TEMPLATE_HI = """
आंध्र प्रदेश सरकार — मद्यनिषेध एवं आबकारी विभाग
अन्वेषण केस डायरी (धारा 172 Cr.P.C. / 193 BNSS)
======================================================
[स्थिति: प्रारूप | साक्ष्यों पर आधारित अन्वेषण प्रारूप]

मामला अपराध संख्या (Cr. No.): {{ case.fir_number or 'अनावंटित — अधिकारी प्रविष्टि आवश्यक' }}
अधिकार क्षेत्र स्टेशन: {{ case.station or 'सत्यापनाधीन' }}, {{ case.district }} जिला
प्रविष्टि तिथि: {{ entry_date }}
अन्वेषण अधिकारी: {{ officer.full_name }} ({{ officer.designation or 'अधिकारी' }})

1. दर्ज मामले का विवरण:
   - अपराध की प्रकृति: {{ case.offence_nature or 'सत्यापन आवश्यक' }}
   - अपराध की तिथि व समय: {{ case.offence_date or 'जांच जारी' }}
   - घटनास्थल (Incident Location): {{ case.incident_location_normalized or case.location_description or (case.village ~ ', ' ~ case.mandal if case.village else 'जांच जारी') }}
   {% if case.contraband_type %}
   - जब्त की गई सामग्री: {{ case.contraband_type }}{% if case.seized_quantity %} (मात्रा: {{ case.seized_quantity }} {{ case.seized_unit or 'इकाइयां' }}){% endif %}
   {% else %}
   - जब्त की गई सामग्री: प्राथमिकी में दर्ज नहीं
   {% endif %}
   - वाहन का विवरण: {{ case.vehicle_details or 'कोई विवरण नहीं' }}

2. लागू वैधानिक धाराएं (Statutory Provisions):
   {% for sec in sections %}
   - {{ sec.act_name }} धारा {{ sec.section_number }}: {{ sec.section_title }} [{{ sec.officer_decision }}]
   {% else %}
   - वैधानिक धाराएं जांच के अधीन हैं।
   {% endfor %}

3. अन्वेषण विवरण व प्रारंभिक तथ्य:
   {% if case.narrative %}
   {{ case.narrative }}
   {% else %}
   - घटना की रिपोर्ट के आधार पर प्राथमिकी दर्ज की गई। अग्रिम अन्वेषण कार्रवाई जारी है।
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
"""

CHARGESHEET_TEMPLATE_HI = """
{% if is_incomplete %}
================================================================================
प्रारूप पूर्ण नहीं हो सका — अतिरिक्त सत्यापित जानकारी आवश्यक है
================================================================================
मामला अपराध संख्या: {{ case.fir_number or 'लापता' }}
थाना: {{ case.station or 'लापता' }}, {{ case.district or 'लापता' }} जिला

अनिवार्य जानकारी दर्ज न होने के कारण धारा 173 CrPC / 193 BNSS के तहत
अंतिम पुलिस रिपोर्ट / आरोप पत्र तैयार नहीं किया जा सका:
{% for field in missing_fields %}
  * {{ field }}
{% endfor %}

न्यायालय हेतु आरोप पत्र तैयार करने से पूर्व कृपया छूटी हुई जानकारी पूर्ण व सत्यापित करें।
{% else %}
माननीय न्यायिक प्रथम श्रेणी मजिस्ट्रेट के न्यायालय में
धारा 173 CrPC / 193 BNSS के तहत अंतिम पुलिस / विभागीय रिपोर्ट (आरोप पत्र)
==================================================================
[विभागीय कार्य प्रारूप — आधिकारिक समीक्षा एवं अनुमोदन अनिवार्य]

आंध्र प्रदेश राज्य (थाना: {{ case.station }} द्वारा)
बनाम
अभियुक्तगण (Accused Persons)

1. अपराध का विवरण (Crime Details):
   - मामला अपराध संख्या: {{ case.fir_number }}
   - वर्ष: {{ case.year }}
   - अपराध की प्रकृति: {{ case.offence_nature }}
   - घटनास्थल: {{ case.incident_location_normalized or case.location_description or (case.village ~ ', ' ~ case.mandal if case.village else 'अधिकार क्षेत्र') }}

2. वैधानिक आरोप (Statutory Charges):
   {% for sec in sections %}
   * {{ sec.act_name }} धारा {{ sec.section_number }} ({{ sec.section_title }})
   {% else %}
   * लागू वैधानिक धाराएं न्यायालय के समक्ष प्रस्तुत की जाएंगी।
   {% endfor %}

3. अभियोजन पक्ष के तथ्य (सत्यापित केस रिकॉर्ड पर आधारित):
   {{ case.narrative or 'प्रथम सूचना रिपोर्ट (FIR) में दर्ज तथ्य।' }}

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
   - L.W. 1: {{ case.seizing_officer_name or officer.full_name }} (शिकायतकर्ता / अन्वेषण अधिकारी)
   {% if case.witnesses_summary %}
   - अन्य गवाह: {{ case.witnesses_summary }}
   {% else %}
   - स्वतंत्र गवाह: परीक्षण के दौरान धारा 161 के बयानों के अधीन।
   {% endif %}

प्रार्थना (PRAYER): माननीय न्यायालय से विनम्र प्रार्थना है कि अभियुक्त के विरुद्ध अपराध का संज्ञान लें तथा विधि सम्मत विचारण करें।

तैयारकर्ता: {{ officer.full_name }} ({{ officer.designation or 'अन्वेषण अधिकारी' }})
प्रारूप तिथि: {{ entry_date }}
{% endif %}
"""

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

        lang = (language or "en").lower().strip()
        if lang not in ("en", "te", "hi"):
            lang = "en"

        # Fetch sections
        sec_stmt = select(CaseLegalSection).where(CaseLegalSection.case_id == case_id)
        sec_res = await db.execute(sec_stmt)
        sections = sec_res.scalars().all()

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
        if not sections or not any(s.officer_decision == "ACCEPTED" for s in sections):
            missing_fields.append("Verified Legal Penal Sections (Officer Acceptance Required)" if lang == "en" else ("ధృవీకరించబడిన చట్ట నిబంధనలు (అధికారి ఆమోదం అవసరం)" if lang == "te" else "सत्यापित वैधानिक धाराएं (अधिकारी अनुमोदन आवश्यक)"))

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

        template = Template(template_str)
        rendered_content = template.render(
            case=case,
            sections=sections,
            officer=user,
            entry_date=datetime.utcnow().strftime("%d-%m-%Y"),
            generation_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            is_incomplete=is_incomplete,
            missing_fields=missing_fields
        )

        lang_suffix = " (తెలుగు)" if lang == "te" else (" (हिन्दी)" if lang == "hi" else "")
        title_str = f"{doc_type.replace('_', ' ').title()} - {case.fir_number}{lang_suffix}"

        # Idempotent: check if doc of same type and language already exists for case
        check_stmt = select(GeneratedDocument).where(
            GeneratedDocument.case_id == case_id,
            GeneratedDocument.doc_type == doc_type,
            GeneratedDocument.language == lang
        ).order_by(desc(GeneratedDocument.version))
        check_res = await db.execute(check_stmt)
        # Older data can hold several rows per case/type/language; update the latest version
        existing_doc = check_res.scalars().first()

        if existing_doc:
            existing_doc.content = rendered_content
            existing_doc.version += 1
            existing_doc.status = "DRAFT"
            await db.commit()
            await db.refresh(existing_doc)
            return existing_doc

        doc = GeneratedDocument(
            case_id=case_id,
            doc_type=doc_type,
            language=lang,
            title=title_str,
            content=rendered_content,
            version=1,
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
