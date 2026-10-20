"""Text and Markdown document extractor with encoding safety and line normalization."""

from app.core.errors import DocumentExtractionException
from app.services.extraction.base import BaseExtractor, ExtractionResult


class TextExtractor(BaseExtractor):
    """Extractor for plain text (.txt) and markdown (.md) documents."""

    def __init__(self, format_type: str = "text") -> None:
        self.format_type = format_type

    @property
    def name(self) -> str:
        return "builtin_markdown" if self.format_type == "markdown" else "builtin_text"

    @property
    def version(self) -> str:
        return "1.0.0"

    def extract(self, content_bytes: bytes, filename: str | None = None) -> ExtractionResult:
        """Decode raw bytes into normalized text preserving Markdown and paragraph boundaries."""
        if not content_bytes:
            return ExtractionResult(
                text="",
                extractor_name=self.name,
                extractor_version=self.version,
                word_count=0,
                character_count=0,
                is_empty=True,
                metadata={"encoding": "utf-8"},
            )

        # Attempt UTF-8 with BOM support first, then standard UTF-8, then fallback
        text: str
        encoding = "utf-8"
        try:
            text = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content_bytes.decode("latin-1")
                encoding = "latin-1"
            except Exception as exc:
                raise DocumentExtractionException(
                    f"Failed to decode text document encoding: {exc}"
                ) from exc

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        stripped_text = text.strip()

        if not stripped_text:
            return ExtractionResult(
                text="",
                extractor_name=self.name,
                extractor_version=self.version,
                word_count=0,
                character_count=0,
                is_empty=True,
                metadata={"encoding": encoding},
            )

        words = stripped_text.split()
        return ExtractionResult(
            text=stripped_text,
            extractor_name=self.name,
            extractor_version=self.version,
            word_count=len(words),
            character_count=len(stripped_text),
            is_empty=False,
            metadata={"encoding": encoding},
        )
