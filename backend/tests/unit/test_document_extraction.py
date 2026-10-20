"""Unit tests for text extraction: real PDF, DOCX, TXT, and Markdown extractors with OCR detection."""

import io

import docx
import pypdf
import pytest

from app.core.errors import DocumentExtractionException
from app.services.extraction.docx_extractor import DocxExtractor
from app.services.extraction.pdf_extractor import PdfExtractor
from app.services.extraction.text_extractor import TextExtractor


def create_minimal_pdf_with_text(text_content: str) -> bytes:
    """Generate a minimal valid PDF binary containing extractable text."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=300, height=300)
    # Using pypdf's annotation or minimal text stream
    # A standard minimalist PDF with text operator:
    pdf_template = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 55 >>\nstream\n"
        b"BT\n/F1 12 Tf\n100 700 Td\n(SupportGPT Enterprise Policy) Tj\nET\n"
        b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000244 00000 n \n0000000350 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n435\n%%EOF"
    )
    return pdf_template


def create_blank_pdf() -> bytes:
    """Generate a valid PDF with pages but zero text (simulating scanned / image-only)."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    bio = io.BytesIO()
    writer.write(bio)
    return bio.getvalue()


def create_real_docx() -> bytes:
    """Generate a real DOCX file with headings, paragraphs, and tables."""
    doc = docx.Document()
    doc.add_heading("Customer Support Procedures", level=1)
    doc.add_paragraph("This guide documents standard operating procedures for escalations.")
    doc.add_heading("Severity Classification", level=2)
    doc.add_paragraph("Severity 1 indicates complete platform outage.")

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Priority"
    table.cell(0, 1).text = "SLA Target"
    table.cell(1, 0).text = "Urgent"
    table.cell(1, 1).text = "1 hour"

    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()


def test_real_pdf_extraction():
    pdf_bytes = create_minimal_pdf_with_text("SupportGPT Enterprise Policy")
    extractor = PdfExtractor()
    result = extractor.extract(pdf_bytes, "policy.pdf")

    assert result.is_empty is False
    assert "SupportGPT Enterprise Policy" in result.text
    assert result.word_count > 0
    assert result.character_count > 0
    assert result.extractor_name == "pypdf"
    assert result.metadata["page_count"] == 1


def test_scanned_pdf_detection_ocr_unavailable():
    blank_pdf = create_blank_pdf()
    extractor = PdfExtractor()

    with pytest.raises(
        DocumentExtractionException,
        match="Optical character recognition \\(OCR\\) is not available",
    ):
        extractor.extract(blank_pdf, "scanned.pdf")


def test_real_docx_extraction():
    docx_bytes = create_real_docx()
    extractor = DocxExtractor()
    result = extractor.extract(docx_bytes, "procedures.docx")

    assert result.is_empty is False
    assert "# Customer Support Procedures" in result.text
    assert "## Severity Classification" in result.text
    assert "Severity 1 indicates complete platform outage." in result.text
    assert "Priority | SLA Target" in result.text
    assert result.word_count > 10
    assert result.extractor_name == "python-docx"


def test_text_and_markdown_extraction():
    extractor_txt = TextExtractor(format_type="text")
    txt_content = "Line 1\r\nLine 2\r\nLine 3"
    res_txt = extractor_txt.extract(txt_content.encode("utf-8"), "test.txt")

    assert res_txt.is_empty is False
    assert res_txt.text == "Line 1\nLine 2\nLine 3"
    assert res_txt.word_count == 6

    extractor_md = TextExtractor(format_type="markdown")
    md_content = "# Title\n\n**Bold statement** and `code block`."
    res_md = extractor_md.extract(md_content.encode("utf-8"), "test.md")

    assert res_md.is_empty is False
    assert "# Title" in res_md.text
    assert "`code block`" in res_md.text


def test_empty_document_handling():
    extractor_txt = TextExtractor(format_type="text")
    res = extractor_txt.extract(b"", "empty.txt")
    assert res.is_empty is True
    assert res.text == ""
    assert res.word_count == 0


def test_malformed_docx_handling():
    extractor = DocxExtractor()
    with pytest.raises(DocumentExtractionException, match="Failed to parse Word"):
        extractor.extract(b"Not A Real Zip At All", "corrupt.docx")
