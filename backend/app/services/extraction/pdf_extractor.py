"""PDF text extraction using pypdf with scanned document detection and structural preservation."""

import io

import pypdf

from app.core.errors import DocumentExtractionException
from app.services.extraction.base import BaseExtractor, ExtractionResult


class PdfExtractor(BaseExtractor):
    """Secure text extractor for PDF documents."""

    @property
    def name(self) -> str:
        return "pypdf"

    @property
    def version(self) -> str:
        return getattr(pypdf, "__version__", "6.21.1")

    def extract(self, content_bytes: bytes, filename: str | None = None) -> ExtractionResult:
        """Extract text from PDF pages, detecting image-only or scanned documents."""
        try:
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
        except Exception as exc:
            raise DocumentExtractionException(
                f"Failed to parse PDF document structure: {exc}"
            ) from exc

        num_pages = len(reader.pages)
        if num_pages == 0:
            return ExtractionResult(
                text="",
                extractor_name=self.name,
                extractor_version=self.version,
                word_count=0,
                character_count=0,
                is_empty=True,
                metadata={"page_count": 0},
            )

        extracted_pages: list[str] = []
        has_images = False
        total_chars = 0

        for _page_idx, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""

            # Check if page contains images
            try:
                if len(page.images) > 0:
                    has_images = True
            except Exception:
                pass

            clean_page_text = page_text.strip()
            total_chars += len(clean_page_text)
            if clean_page_text:
                extracted_pages.append(clean_page_text)

        # Scanned / Image-only detection
        if total_chars == 0:
            if has_images or num_pages > 0:
                raise DocumentExtractionException(
                    "Document appears to be scanned or image-only. Optical character recognition (OCR) is not available."
                )
            return ExtractionResult(
                text="",
                extractor_name=self.name,
                extractor_version=self.version,
                word_count=0,
                character_count=0,
                is_empty=True,
                metadata={"page_count": num_pages},
            )

        full_text = "\n\n".join(extracted_pages)
        words = full_text.split()

        # Metadata extraction
        doc_metadata: dict[str, str | int] = {"page_count": num_pages}
        if reader.metadata:
            if reader.metadata.title:
                doc_metadata["title"] = str(reader.metadata.title)
            if reader.metadata.author:
                doc_metadata["author"] = str(reader.metadata.author)

        return ExtractionResult(
            text=full_text,
            extractor_name=self.name,
            extractor_version=self.version,
            word_count=len(words),
            character_count=len(full_text),
            is_empty=False,
            metadata=doc_metadata,
        )
