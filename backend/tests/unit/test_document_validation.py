"""Unit tests for document validation policy: magic bytes, zip bomb defense, and spoofing protection."""

import io
import zipfile

import pytest

from app.core.errors import (
    PayloadSizeLimitException,
    UnsupportedMediaTypeException,
)
from app.models.enums import DocumentMediaType
from app.services.extraction.validator import (
    sanitize_filename,
    validate_document_file,
)


def test_sanitize_filename():
    assert sanitize_filename("test.pdf") == "test.pdf"
    assert sanitize_filename("../../etc/passwd.txt") == "passwd.txt"
    assert sanitize_filename("..\\..\\windows\\test.docx") == "test.docx"
    assert sanitize_filename("null\x00byte.pdf") == "nullbyte.pdf"
    assert sanitize_filename("safe <name> | query:?.md") == "safe name query.md"
    assert sanitize_filename("") == "unnamed_document"
    assert sanitize_filename("..") == "unnamed_document"


def test_pdf_validation_valid():
    content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    media_type, name = validate_document_file(content, "handbook.pdf")
    assert media_type == DocumentMediaType.PDF
    assert name == "handbook.pdf"


def test_pdf_validation_spoofed_rejection():
    # Plain text file disguised as .pdf
    content = b"This is just plain text, not a real PDF file."
    with pytest.raises(UnsupportedMediaTypeException, match="signature"):
        validate_document_file(content, "spoofed.pdf")


def test_docx_validation_valid():
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("word/document.xml", "<w:document><w:body><w:p/></w:body></w:document>")
        zf.writestr("[Content_Types].xml", "<Types/>")
    docx_bytes = bio.getvalue()

    media_type, name = validate_document_file(docx_bytes, "policy.docx")
    assert media_type == DocumentMediaType.DOCX
    assert name == "policy.docx"


def test_docx_validation_not_a_zip():
    with pytest.raises(UnsupportedMediaTypeException, match="ZIP container"):
        validate_document_file(b"PKNotAZipFile", "corrupt.docx")


def test_docx_validation_zip_missing_word_structure():
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("random.txt", "Some random text in a zip archive")
    zip_bytes = bio.getvalue()

    with pytest.raises(UnsupportedMediaTypeException, match="missing standard Word OpenXML"):
        validate_document_file(zip_bytes, "fake_doc.docx")


def test_docx_zip_bomb_size_exceeded():
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 200KB of zeros compresses to ~250 bytes, yielding an expansion ratio ~800x (exceeding MAX_ZIP_COMPRESSION_RATIO=50)
        zf.writestr("word/document.xml", b"0" * 200_000)
    zip_bytes = bio.getvalue()

    with pytest.raises(PayloadSizeLimitException, match="safety threshold"):
        validate_document_file(zip_bytes, "bomb.docx")


def test_text_and_markdown_validation():
    txt_bytes = b"Support procedure guidelines for agent teams."
    media_type, name = validate_document_file(txt_bytes, "guide.txt")
    assert media_type == DocumentMediaType.TXT

    md_bytes = b"# Runbook\n\nStep 1: Check status."
    media_type, name = validate_document_file(md_bytes, "runbook.md")
    assert media_type == DocumentMediaType.MARKDOWN


def test_text_validation_null_bytes_rejection():
    # Binary executable payload disguised as text
    binary_content = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00"
    with pytest.raises(UnsupportedMediaTypeException, match="Binary data or null bytes"):
        validate_document_file(binary_content, "malware.txt")


def test_unsupported_extensions():
    unsupported = ["script.sh", "program.exe", "archive.tar.gz", "data.json", "data.csv"]
    for fname in unsupported:
        with pytest.raises(UnsupportedMediaTypeException, match="Unsupported file extension"):
            validate_document_file(b"some content", fname)
