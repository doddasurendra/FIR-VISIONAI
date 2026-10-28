"""The deterministic FIR form reader on the two badly extracted cases (178/2024, FIR-2024-EXC-IMAGE-01)."""
from datetime import datetime

from app.services.fir_form_parser import normalise_registration, parse_fir_text
from app.services.text_processing import clean_extracted_text
from tests.test_ocr_text_quality import FIR_178_OCR

EXC_IMAGE_01 = """GOVERNMENT OF ANDHRA PRADESH - PROHIBITION & EXCISE DEPARTMENT
FIRST INFORMATION REPORT & SEIZURE EVIDENCE PHOTOGRAPH: de601e921d23_ap_logo_test.jpg
Crime No: FIR-2024-EXC-IMAGE-01 | Station: Kurnool Town Station
Occurrence: Intercepted vehicle transporting contraband without valid transit permit.
Contraband Seized: 40 Litres ID Arrack / Illicit Liquor in vehicle boot.
Vehicle: Auto Rickshaw AP21TY4567 | Accused: Ramu Naidu (A-1).
Statutory Provision: Section 34(a) Andhra Pradesh Excise Act, 1968."""


def test_fir_178_2024_fields():
    p = parse_fir_text(clean_extracted_text(FIR_178_OCR))
    assert p.offence_date == datetime(2024, 9, 20)
    assert (p.time_from, p.time_to) == ("10:30", "11:30")
    assert "State Bank of India" in p.place and "Tenali" in p.place
    assert "Market Road" in p.address
    assert p.district == "Guntur" and p.town == "Tenali"
    assert p.complainant == "K. Lakshmi Prasad"
    assert p.accused == ["Ramesh Kumar"]
    assert p.sections == [("IPC", "420"), ("IPC", "468"), ("IPC", "471"), ("IT Act", "66C"), ("IT Act", "66D")]
    assert "cheating" in p.offence_label() and "forg" in p.offence_label()
    assert "2,50,000" in p.particulars
    assert p.contraband_type is None and p.vehicle_registration is None


def test_exc_image_01_fields():
    p = parse_fir_text(EXC_IMAGE_01)
    assert p.contraband_raw == "ID Arrack"
    assert p.contraband_type == "ID Liquor (Arrack)"
    assert (p.seized_quantity, p.seized_unit) == (40.0, "Litres")
    assert p.vehicle_details == "Auto Rickshaw AP21TY4567"
    assert p.vehicle_registration == "AP21TY4567"
    assert p.accused == ["Ramu Naidu"]
    assert ("AP Excise Act", "34(a)") in p.sections


def test_registration_normalised():
    assert normalise_registration("Auto AP 21 TY 4567") == "AP21TY4567"
    assert normalise_registration("vehicle transporting contraband without valid transit permit") is None
