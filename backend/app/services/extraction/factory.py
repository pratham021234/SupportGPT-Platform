"""Extractor factory for mapping validated MIME media types to extractors."""

from app.core.errors import UnsupportedMediaTypeException
from app.models.enums import DocumentMediaType
from app.services.extraction.base import BaseExtractor
from app.services.extraction.docx_extractor import DocxExtractor
from app.services.extraction.pdf_extractor import PdfExtractor
from app.services.extraction.text_extractor import TextExtractor

_EXTRACTORS: dict[str, BaseExtractor] = {
    DocumentMediaType.PDF: PdfExtractor(),
    DocumentMediaType.DOCX: DocxExtractor(),
    DocumentMediaType.TXT: TextExtractor(format_type="text"),
    DocumentMediaType.MARKDOWN: TextExtractor(format_type="markdown"),
}


def get_extractor(media_type: str) -> BaseExtractor:
    """Return extractor instance registered for the given media type."""
    extractor = _EXTRACTORS.get(media_type)
    if not extractor:
        raise UnsupportedMediaTypeException(
            f"No text extractor implemented for media type '{media_type}'."
        )
    return extractor
