"""Re-extraction plans and the extraction quality check for 178/2024 and FIR-2024-EXC-IMAGE-01."""
from datetime import datetime

from app.models.case import Case
from app.services.case_reextraction import planned_fields, planned_updates
from app.services.extraction_quality import check_case_against_text
from app.services.fir_form_parser import parse_fir_text
from app.services.jurisdiction import master_district_for_station
from app.services.text_processing import clean_extracted_text
from tests.test_fir_form_parser import EXC_IMAGE_01
from tests.test_ocr_text_quality import FIR_178_OCR

TEXT_178 = clean_extracted_text(FIR_178_OCR)


def case_178():
    return Case(id="c178", fir_number="178/2024", district="Guntur", station="Tenali PS", offence_nature="gold lost",
                contraband_type=None, seized_quantity=0, seized_unit="Litres", offence_date=None,
                incident_place_raw=", , Guntur", seizing_officer_name="Lead System Architect", narrative=FIR_178_OCR)


def case_exc():
    return Case(id="cexc", fir_number="FIR-2024-EXC-IMAGE-01", district="Kurnool", station="Kurnool Town Station",
                offence_nature="Intercepted vehicle transporting contraband without valid transit permit",
                contraband_type="without valid transit permit", seized_quantity=40, seized_unit="Litres",
                vehicle_details="vehicle transporting contraband without valid transit permit",
                incident_place_raw="Kurnool Town Station")


def test_quality_check_flags_178_contradictions():
    codes = {f["check_code"] for f in check_case_against_text(case_178(), [], TEXT_178, None)}
    assert {"DATE_MISSING", "PLACE_MISSING", "OFFENCE_NOT_IN_TEXT", "SECTIONS_MISSING", "OFFICER_INVALID"} <= codes


def test_reextraction_plan_for_178():
    up = planned_updates(case_178(), parse_fir_text(TEXT_178), TEXT_178)
    assert up["offence_date"] == datetime(2024, 9, 20, 10, 30)
    assert up["offence_nature"].lower().startswith("cheating") and "forg" in up["offence_nature"]
    assert "State Bank of India" in up["incident_place_raw"] and "Market Road" in up["incident_place_raw"]
    assert "null" not in up["incident_place_raw"]
    assert up["contraband_type"] == "Not applicable" and up["seized_unit"] is None
    assert up["seizing_officer_name"] is None
    assert "emblem" not in up["narrative"] and "178/2024" in up["narrative"]
    fields = planned_fields(case_178(), parse_fir_text(TEXT_178))
    assert fields["complainant"] == "K. Lakshmi Prasad"
    assert fields["accused"] == "Ramesh Kumar"
    assert fields["law_sections"] == "IPC 420, IPC 468, IPC 471, IT Act 66C, IT Act 66D"
    assert fields["offence_time"] == "10:30 to 11:30"


def test_reextraction_plan_for_exc_image_01():
    case = case_exc()
    assert "CONTRABAND_INVALID" in {f["check_code"] for f in check_case_against_text(case, [], EXC_IMAGE_01, None)}
    up = planned_updates(case, parse_fir_text(EXC_IMAGE_01), EXC_IMAGE_01)
    assert up["contraband_type"] == "ID Liquor (Arrack)"
    assert up["vehicle_details"] == "Auto Rickshaw AP21TY4567"
    assert "seized_quantity" not in up      # already 40 Litres
    assert planned_fields(case, parse_fir_text(EXC_IMAGE_01))["accused"] == "Ramu Naidu"


def test_station_district_rule():
    assert master_district_for_station("Kurnool Town Station") == "Kurnool"
    flags = check_case_against_text(Case(id="x", fir_number="FIR-2024-FIR-3341", district="Amaravati Headquarters",
                                         station="Kurnool Town Station", contraband_type="ID Liquor"),
                                    [], "Seized ID liquor near Kurnool.", "Kurnool")
    assert any(f["check_code"] == "DISTRICT_STATION_MISMATCH" for f in flags)
