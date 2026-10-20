"""Secure file validation policy: magic bytes inspection, zip bomb protection, and media type verification."""

import io
import re
import zipfile
from pathlib import Path

from app.core.errors import (
    PayloadSizeLimitException,
    UnsupportedMediaTypeException,
)
from app.models.enums import DocumentMediaType

# Maximum allowed uncompressed size for archive-based documents (DOCX)
MAX_UNCOMPRESSED_ZIP_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_ZIP_COMPRESSION_RATIO = 50.0  # Max expansion ratio

SUPPORTED_EXTENSIONS = {
    ".pdf": DocumentMediaType.PDF,
    ".docx": DocumentMediaType.DOCX,
    ".txt": DocumentMediaType.TXT,
    ".text": DocumentMediaType.TXT,
    ".md": DocumentMediaType.MARKDOWN,
    ".markdown": DocumentMediaType.MARKDOWN,
}


def sanitize_filename(filename: str) -> str:
    """Sanitize original filename removing directory traversal characters and unsafe characters."""
    if not filename:
        return "unnamed_document"

    # Strip path components and null characters
    clean_name = Path(filename).name.replace("\x00", "").strip()

    # Normalize whitespace and strip dangerous characters
    clean_name = re.sub(r'[\\/*?:"<>|]', "", clean_name)
    clean_name = re.sub(r"\s+", " ", clean_name)

    if not clean_name or clean_name in (".", ".."):
        return "unnamed_document"

    # Enforce maximum length
    return clean_name[:255]


def validate_document_file(content_bytes: bytes, filename: str) -> tuple[str, str]:
    """Validate document content against signature allowlist and return (verified_media_type, sanitized_filename).

    Raises:
        UnsupportedMediaTypeException: If file is unsupported, malformed, or spoofed.
        PayloadSizeLimitException: If decompressed size exceeds safety threshold (zip bomb).
    """
    clean_filename = sanitize_filename(filename)
    suffix = Path(clean_filename).suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedMediaTypeException(
            f"Unsupported file extension '{suffix}'. Supported formats are: PDF, DOCX, TXT, and Markdown."
        )

    # 1. PDF Verification
    if suffix == ".pdf":
        if not content_bytes.startswith(b"%PDF-"):
            raise UnsupportedMediaTypeException(
                "Invalid PDF file: header does not match PDF specification signature (%PDF-)."
            )
        return DocumentMediaType.PDF, clean_filename

    # 2. DOCX Verification (PKZIP with OpenXML Word document structure)
    if suffix == ".docx":
        if not content_bytes.startswith(b"PK\x03\x04"):
            raise UnsupportedMediaTypeException(
                "Invalid DOCX file: header signature does not match ZIP container."
            )
        try:
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
                # Zip bomb / resource limit defense
                total_uncompressed = 0
                for info in zf.infolist():
                    total_uncompressed += info.file_size
                    if total_uncompressed > MAX_UNCOMPRESSED_ZIP_BYTES:
                        raise PayloadSizeLimitException(
                            "Decompressed document size exceeds maximum allowed safety threshold."
                        )

                compressed_len = max(len(content_bytes), 1)
                if (total_uncompressed / compressed_len) > MAX_ZIP_COMPRESSION_RATIO:
                    raise PayloadSizeLimitException(
                        "Document rejected: compression ratio exceeds safety threshold."
                    )

                # Ensure it is a valid OpenXML Word document
                namelist = zf.namelist()
                if "word/document.xml" not in namelist and not any(n.startswith("word/") for n in namelist):
                    raise UnsupportedMediaTypeException(
                        "Invalid DOCX file: missing standard Word OpenXML document structure."
                    )
        except zipfile.BadZipFile:
            raise UnsupportedMediaTypeException("Invalid DOCX file: corrupted ZIP archive.") from None

        return DocumentMediaType.DOCX, clean_filename

    # 3. Plain Text and Markdown Verification
    if suffix in (".txt", ".text", ".md", ".markdown"):
        # Check for binary null bytes which indicate binary executable / binary file disguised as text
        if b"\x00" in content_bytes:
            raise UnsupportedMediaTypeException(
                "Binary data or null bytes detected in text document. Only UTF-8/plain text is supported."
            )

        # Attempt decoding
        try:
            content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                # Allow fallback for latin-1 if utf-8 fails, but verify printable structure
                text = content_bytes.decode("latin-1")
                # Basic sanity: reject if excessive unprintable control characters
                control_chars = sum(1 for c in text if ord(c) < 32 and c not in ("\n", "\r", "\t"))
                if len(text) > 0 and (control_chars / len(text)) > 0.05:
                    raise UnsupportedMediaTypeException(
                        "Text file contains excessive binary control characters."
                    )
            except Exception:
                raise UnsupportedMediaTypeException("Unable to decode text document encoding.") from None

        media_type = DocumentMediaType.MARKDOWN if suffix in (".md", ".markdown") else DocumentMediaType.TXT
        return media_type, clean_filename

    raise UnsupportedMediaTypeException("Unsupported or unrecognized document format.")
