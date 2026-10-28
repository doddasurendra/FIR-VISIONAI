"""OCR text quality: image descriptions are stripped, placeholder text never counts as readable."""
from app.services.text_processing import clean_extracted_text, is_placeholder_text, strip_image_descriptions

FIR_178_OCR = """A.P.P.M. Orders 470, 500

The image depicts the emblem of the Maharashtra Police. The emblem is circular in shape and predominantly black and white. At the center of the emblem is a wheel with 24 spokes, which is reminiscent of the Ashoka Chakra, a symbol found on the Indian national flag. This wheel is encircled by a thick black border.

Surrounding the central wheel, there is a ring of text written in capital letters. The text reads: "महाराष्ट्र राज्य पोलीस" (Maharashtra Rajya Police), which translates to "Maharashtra State Police" in English. This text is in Marathi, the official language of the state of Maharashtra in India.

Below the central wheel, there is a ribbon-like banner that contains additional text. The text on this banner reads: "सत्यमेव जयते" (Satyameva Jayate), which translates to "Truth Alone Triumphs" in English. This phrase is a national motto of India and is also inscribed on the emblem of India.

The overall design of the emblem is symmetrical and balanced, with the wheel at the center and the text evenly distributed around it. The use of the Ashoka Chakra symbolizes the continuity of the ancient Indian tradition and the commitment to truth and justice, which are core values of the police force.

The emblem is a representation of the authority and responsibility of the Maharashtra Police, tasked with maintaining law and order in the state of Maharashtra. The presence of the Ashoka Chakra and the national motto underscores the alignment of the police force with the broader principles of the Indian state.

In summary, the emblem of the Maharashtra Police features:
1. A central wheel with 24 spokes (Ashoka Chakra).
2. Text in Marathi around the wheel: "महाराष्ट्र राज्य पोलीस" (Maharashtra State Police).
3. A ribbon banner below the wheel with the text: "सत्यमेव जयते" (Truth Alone Triumphs).

This emblem encapsulates the essence of the Maharashtra Police's mission to uphold justice and maintain law and order, guided by the principles of truth and integrity.

1. District : Guntur

FIRST INFORMATION REPORT
(Under Sections 154 & 157 Cr.P.C)

Police Year : FIR No : Date : Station : Tenali PS 2024 178/2024 22.09.2024

2. (i) Act, the Prevention of Corruption Act, 1988 : - Nil -
(ii) Act, Indian Penal Code : Sections 420, 468, 471 IPC.
(iii) Other Acts & Sections : Section 66C, 66D of IT Act, 2000.

3. (a) Occurrence of Offence: Day : 20.09.2024 (Friday)
Time Period : Between 10.30 hrs and 11.30 hrs

5. Place of occurrence : Near State Bank of India, Tenali, Guntur District.
(b) Address : SBI Main Branch, Market Road, Tenali.

6. Complainant / Informant : (a) Name : K. Lakshmi Prasad

7. Details of known / suspected / unknown accused with full particulars:
(a) Name : Ramesh Kumar
(e) Particulars : The above named person cheated the complainant by using forged documents and obtained a personal loan of Rs. 2,50,000/- from SBI Tenali branch by furnishing fake identity proofs."""


def test_emblem_description_is_removed_and_fir_text_kept():
    out = strip_image_descriptions(FIR_178_OCR)
    for gone in ("image depicts", "Maharashtra", "Ashoka Chakra", "ribbon", "encapsulates", "24 spokes"):
        assert gone not in out
    for kept in ("A.P.P.M. Orders 470, 500", "178/2024", "Sections 420, 468, 471 IPC", "66C, 66D of IT Act",
                 "20.09.2024", "Between 10.30 hrs and 11.30 hrs", "Market Road, Tenali", "K. Lakshmi Prasad",
                 "Ramesh Kumar", "2,50,000"):
        assert kept in out


def test_clean_extracted_text_strips_descriptions():
    assert "emblem" not in clean_extracted_text(FIR_178_OCR)


def test_ordinary_fir_text_is_untouched():
    text = ("FIRST INFORMATION REPORT\n\nCrime No: FIR-2024-EXC-IMAGE-01 | Station: Kurnool Town Station\n\n"
            "Seized 40 Litres ID Arrack. Vehicle: Auto Rickshaw AP21TY4567 | Accused: Ramu Naidu (A-1)")
    assert strip_image_descriptions(text) == text


def test_placeholders_are_not_readable_text():
    assert is_placeholder_text("GOVERNMENT OF ANDHRA PRADESH - LAW ENFORCEMENT EVIDENCE RECORD EVIDENCE PHOTOGRAPH: "
                               "x_fir.jpg Visual evidence document authenticated via cryptographic SHA-256 hash. "
                               "Document classification: Single-surface evidence photograph record.")
    assert is_placeholder_text("[Physical Page 1 Official Evidence Record] Scanned document record transcribed for "
                               "physical page 1 of test_fir.pdf.")
    assert is_placeholder_text("No visible text was found in the provided image. The image appears to be a solid green background.")
    assert is_placeholder_text("")
    assert not is_placeholder_text(FIR_178_OCR)
    assert not is_placeholder_text("GOVERNMENT OF ANDHRA PRADESH - PROHIBITION & EXCISE DEPARTMENT FIRST INFORMATION "
                                   "REPORT Crime No: FIR-2024-EXC-IMAGE-01")
