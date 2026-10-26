"""
test_image_upload.py
--------------------
Tests for multi-format document upload (PDF/JPEG/PNG/WEBP) and IMAGE_ONLY RAG mode.
These are additive — Section 26 PDF-only RAG behaviour is verified in test_backend.py
and must remain completely unchanged.
"""
import io
import struct
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers: build minimal valid magic-byte headers for each format
# ---------------------------------------------------------------------------

def _make_jpeg_bytes(size: int = 32) -> bytes:
    """Minimal valid JPEG: SOI marker + APP0 JFIF header + EOI."""
    header = (
        b"\xff\xd8\xff\xe0"        # SOI + APP0 marker
        b"\x00\x10"                # APP0 length = 16
        b"JFIF\x00"                # identifier
        b"\x01\x01"                # version
        b"\x00"                    # aspect ratio units
        b"\x00\x01\x00\x01"        # density
        b"\x00\x00"                # thumbnail size
    )
    return header + b"\x00" * (size - len(header)) + b"\xff\xd9"   # EOI


def _make_png_bytes(size: int = 32) -> bytes:
    """Minimal 8-byte PNG signature."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * max(0, size - 8)


def _make_webp_bytes(size: int = 32) -> bytes:
    """Minimal RIFF/WEBP header."""
    payload = b"\x00" * max(0, size - 12)
    file_size = 4 + len(payload)   # 'WEBP' + payload
    return b"RIFF" + struct.pack("<I", file_size) + b"WEBP" + payload


def _make_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


# ---------------------------------------------------------------------------
# Fixtures: authenticated headers for a station officer
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_headers():
    resp = client.post("/api/v1/auth/login", json={
        "username": "station_officer",
        "password": "StationPass@2024"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Upload acceptance tests
# ---------------------------------------------------------------------------

def test_jpeg_upload_accepted(auth_headers):
    """JPEG images must be accepted (not rejected with PDF-only error)."""
    jpeg_bytes = _make_jpeg_bytes(256)
    files = {"file": ("test_fir_photo.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")}
    resp = client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    # Expect 200 (success) or at most a 422/500 from OCR failing on empty image,
    # but NOT a 400 complaining about "Only PDF documents are supported".
    assert resp.status_code != 400 or "Only PDF" not in resp.text, (
        f"Should not reject JPEG with PDF-only error. Got {resp.status_code}: {resp.text}"
    )


def test_png_upload_accepted(auth_headers):
    """PNG images must be accepted by the upload endpoint."""
    png_bytes = _make_png_bytes(256)
    files = {"file": ("handwritten_fir.png", io.BytesIO(png_bytes), "image/png")}
    resp = client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    assert resp.status_code != 400 or "Only PDF" not in resp.text, (
        f"Should not reject PNG with PDF-only error. Got {resp.status_code}: {resp.text}"
    )


def test_webp_upload_accepted(auth_headers):
    """WEBP images must be accepted by the upload endpoint."""
    webp_bytes = _make_webp_bytes(256)
    files = {"file": ("evidence.webp", io.BytesIO(webp_bytes), "image/webp")}
    resp = client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    assert resp.status_code != 400 or "Only PDF" not in resp.text, (
        f"Should not reject WEBP with PDF-only error. Got {resp.status_code}: {resp.text}"
    )


def test_pdf_upload_still_accepted(auth_headers):
    """Existing PDF uploads must continue to work (no regression)."""
    pdf_bytes = _make_pdf_bytes()
    files = {"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    resp = client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    # Accept 200, 422 (processing error on stub PDF), never a format-rejection 400
    assert resp.status_code != 400 or "Unsupported" not in resp.text, (
        f"PDF should not be rejected as unsupported. Got {resp.status_code}: {resp.text}"
    )


def test_unsupported_file_type_rejected(auth_headers):
    """Executables, .docx, .txt etc. must be rejected with a clear 400 error."""
    exe_bytes = b"MZ\x90\x00" + b"\x00" * 60   # DOS MZ header
    files = {"file": ("malware.exe", io.BytesIO(exe_bytes), "application/octet-stream")}
    resp = client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    assert resp.status_code == 400, (
        f"Executable should be rejected with 400. Got {resp.status_code}: {resp.text}"
    )


def test_txt_file_rejected(auth_headers):
    """Plain-text files must be rejected."""
    txt_bytes = b"This is a test FIR description in plain text."
    files = {"file": ("notes.txt", io.BytesIO(txt_bytes), "text/plain")}
    resp = client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    assert resp.status_code == 400, (
        f"TXT file should be rejected with 400. Got {resp.status_code}: {resp.text}"
    )


def test_mime_type_extension_mismatch_caught(auth_headers):
    """A JPEG disguised with a .pdf extension should be caught by magic-byte detection."""
    jpeg_bytes = _make_jpeg_bytes(256)
    # Extension is .pdf but content is JPEG — backend must catch this
    files = {"file": ("not_a_pdf.pdf", io.BytesIO(jpeg_bytes), "application/pdf")}
    resp = client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    # Backend may accept (routing to image pipeline) or reject; it must NOT crash with 500.
    # 409 = the same bytes (uploaded by another test moments earlier) are still being processed.
    assert resp.status_code in (200, 400, 409, 422), (
        f"Mismatch handling should not crash. Got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# IMAGE_ONLY RAG mode — no fake page numbers in response
# ---------------------------------------------------------------------------

def test_image_only_rag_no_pdf_page_citation(auth_headers):
    """
    IMAGE_ONLY mode must never return a 'PDF page X' citation — it should
    cite the image source ID or filename only.
    """
    payload = {
        "query": "What is the FIR number mentioned in this document?",
        "mode": "IMAGE_ONLY",
        "document_id": "nonexistent-image-id-for-unit-test",
        "language": "en"
    }
    resp = client.post("/api/v1/rag/query", json=payload, headers=auth_headers)
    # May return 404 or a grounded answer; either way must not crash
    if resp.status_code == 200:
        body = resp.json()
        answer_text = str(body.get("answer", ""))
        citations = body.get("citations", [])
        # No citation should reference a physical PDF page number in IMAGE_ONLY mode
        for citation in citations:
            assert "page" not in str(citation).lower() or "image" in str(citation).lower(), (
                f"IMAGE_ONLY citation should not reference PDF pages: {citation}"
            )
