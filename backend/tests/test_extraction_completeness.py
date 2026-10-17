import pytest
from app.services.gemini import gemini_service

def test_comprehensive_regex_extraction_cyber_crime():
    """Verify regex fallback extracts complete details for non-excise cases with colon-patterns."""
    sample_text = """
    GOVERNMENT OF TAMIL NADU - POLICE DEPARTMENT
    FIRST INFORMATION REPORT
    FIR No: 142/2024
    District: Chennai
    Police Station: Cyber Crime Police Station
    Date of Occurrence: 12/03/2024
    Registration Date: 13/03/2024
    Place of Occurrence: Anna Salai, Chennai Near Gemini Flyover
    Complainant: S. Ramanathan s/o Sundaram
    Accused Person: Victor Daniel age 32 years
    Witness: K. Murugan
    Offence: Online Banking Phishing Fraud
    Amount: Rs. 15,000
    Phone: 9876543210
    Section: 66D IT Act and 420 IPC
    """
    res = gemini_service._rule_based_fallback_extraction(sample_text)

    assert res["fir_number"] == "142/2024"
    assert res["district"] == "Chennai"
    assert "Cyber Crime" in res["station"]
    assert res["offence_date"] == "2024-03-12"
    assert res["registration_date"] == "2024-03-13"
    assert res["complainant_name"] == "S. Ramanathan"
    assert "Victor Daniel" in res["accused_names"]
    assert "K. Murugan" in res["witness_names"]
    assert res["financial_loss_amount"] == "15000"
    assert res["place_of_occurrence"] == "Anna Salai, Chennai Near Gemini Flyover"
    assert res["phone_number"] == "9876543210"
    assert "Online Banking Phishing Fraud" in res["offence_nature"]
    assert res["narrative_summary"] is not None

def test_missing_fields_stay_null():
    """Verify that absent fields stay null or empty without fabrication."""
    minimal_text = """
    FIR No: 99/2024
    District: Kurnool
    Station: Kurnool Town Police Station
    """
    res = gemini_service._rule_based_fallback_extraction(minimal_text)

    assert res["fir_number"] == "99/2024"
    assert res["district"] == "Kurnool"
    assert res["contraband_type"] is None
    assert res["seized_quantity"] is None
    assert res["seized_unit"] is None
    assert res["accused_names"] == []
    assert res["witness_names"] == []
    assert res["financial_loss_amount"] is None
    assert res["vehicle_details"] is None
