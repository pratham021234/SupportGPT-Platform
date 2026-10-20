"""DOCX text extraction using python-docx preserving headings, paragraphs, and tables."""

import io

import docx

from app.core.errors import DocumentExtractionException
from app.services.extraction.base import BaseExtractor, ExtractionResult


class DocxExtractor(BaseExtractor):
    """Text extractor for Microsoft Word (DOCX) documents."""

    @property
    def name(self) -> str:
        return "python-docx"

    @property
    def version(self) -> str:
        return getattr(docx, "__version__", "1.2.0")

    def extract(self, content_bytes: bytes, filename: str | None = None) -> ExtractionResult:
        """Extract text from Word document paragraphs, headings, and tables."""
        try:
            doc = docx.Document(io.BytesIO(content_bytes))
        except Exception as exc:
            raise DocumentExtractionException(
                f"Failed to parse Word (DOCX) document structure: {exc}"
            ) from exc

        content_elements: list[str] = []

        # 1. Extract paragraphs and preserve heading styles
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name.lower() if para.style and para.style.name else ""
            if "heading 1" in style_name:
                content_elements.append(f"# {text}")
            elif "heading 2" in style_name:
                content_elements.append(f"## {text}")
            elif "heading 3" in style_name:
                content_elements.append(f"### {text}")
            elif "heading" in style_name:
                content_elements.append(f"#### {text}")
            elif "title" in style_name:
                content_elements.append(f"# {text}")
            else:
                content_elements.append(text)

        # 2. Extract tables into structured markdown representations
        for table in doc.tables:
            table_rows: list[str] = []
            for row in table.rows:
                row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                if any(row_cells):
                    table_rows.append(" | ".join(row_cells))
            if table_rows:
                content_elements.append("\n".join(table_rows))

        full_text = "\n\n".join(content_elements).strip()
        if not full_text:
            return ExtractionResult(
                text="",
                extractor_name=self.name,
                extractor_version=self.version,
                word_count=0,
                character_count=0,
                is_empty=True,
                metadata={"paragraphs_count": len(doc.paragraphs), "tables_count": len(doc.tables)},
            )

        words = full_text.split()
        return ExtractionResult(
            text=full_text,
            extractor_name=self.name,
            extractor_version=self.version,
            word_count=len(words),
            character_count=len(full_text),
            is_empty=False,
            metadata={"paragraphs_count": len(doc.paragraphs), "tables_count": len(doc.tables)},
        )
