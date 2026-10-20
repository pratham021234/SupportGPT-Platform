"""Deterministic text normalizer preserving structure, code blocks, URLs, and section headings."""

import re

PIPELINE_NORMALIZER_VERSION = "1.0.0"


class TextNormalizer:
    """Deterministic text normalization engine."""

    @property
    def version(self) -> str:
        return PIPELINE_NORMALIZER_VERSION

    def normalize(self, text: str) -> str:
        """Apply deterministic, non-destructive normalization to extracted text."""
        if not text:
            return ""

        # 1. Normalize line endings
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")

        # 2. Strip non-printable ASCII control characters (preserving \n, \t)
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)

        # 3. Strip trailing whitespace on each line
        lines = [line.rstrip() for line in normalized.split("\n")]

        # 4. Collapse runs of 3+ consecutive newlines into 2 (paragraph break)
        collapsed_text = "\n".join(lines)
        collapsed_text = re.sub(r"\n{3,}", "\n\n", collapsed_text)

        return collapsed_text.strip()
