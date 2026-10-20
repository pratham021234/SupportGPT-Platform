"""Unit tests for deterministic text normalizer and hierarchical structural chunker."""

from app.services.chunking.chunker import HierarchicalStructuralChunker
from app.services.chunking.normalizer import TextNormalizer


def test_normalizer_line_endings_and_whitespace():
    normalizer = TextNormalizer()
    raw = "Line 1  \r\n\r\n\r\n\r\nLine 2 with trailing spaces   \r\n\tTabbed line\r"
    normalized = normalizer.normalize(raw)

    # Must collapse 4 newlines into 2
    assert "Line 1\n\nLine 2 with trailing spaces\n\tTabbed line" in normalized
    assert "\r" not in normalized


def test_normalizer_preserves_urls_and_code():
    normalizer = TextNormalizer()
    content = (
        "# Security Policy\n\n"
        "Reference URL: https://security.supportgpt.internal/v1/auth?strict=true\n\n"
        "```python\n"
        "def authenticate(token: str) -> bool:\n"
        "    return token == 'valid_token'\n"
        "```"
    )
    normalized = normalizer.normalize(content)
    assert "https://security.supportgpt.internal/v1/auth?strict=true" in normalized
    assert "def authenticate(token: str) -> bool:" in normalized


def test_chunker_heading_hierarchy_breadcrumbs():
    text = (
        "# Section 1: Overview\n\n"
        "This is the introductory overview of the platform.\n\n"
        "## Subsection 1.1: Authentication\n\n"
        "Authentication uses bearer tokens and session cookies.\n\n"
        "### Sub-subsection 1.1.1: RBAC\n\n"
        "Roles include Owner, Admin, Agent, and Viewer.\n\n"
        "# Section 2: Ingestion\n\n"
        "Ingestion accepts webhooks and events."
    )

    chunker = HierarchicalStructuralChunker(chunk_size=200, chunk_overlap=30)
    chunks = chunker.chunk(text)

    assert len(chunks) > 0
    # Every chunk must have content and valid offsets
    for i, c in enumerate(chunks):
        assert c.sequence_number == i
        assert len(c.content) > 0
        assert c.start_char_idx >= 0
        assert c.end_char_idx >= c.start_char_idx
        assert len(c.checksum) == 64

    # Check breadcrumb evolution
    first_chunk = chunks[0]
    assert "Section 1: Overview" in first_chunk.heading_hierarchy

    # Verify that Section 2 chunk has Section 2 heading and has popped Section 1
    sec2_chunks = [c for c in chunks if "Section 2: Ingestion" in c.content]
    assert len(sec2_chunks) > 0
    assert "Section 2: Ingestion" in sec2_chunks[0].heading_hierarchy
    assert "Section 1: Overview" not in sec2_chunks[0].heading_hierarchy


def test_chunker_deterministic_reproducibility():
    text = (
        "# API Reference\n\n"
        "The following endpoints are supported by the platform:\n\n"
        "- GET /health\n"
        "- POST /tickets\n"
        "- GET /tickets/{id}\n\n"
        "All responses follow RFC 7807 problem details specifications."
    )

    chunker1 = HierarchicalStructuralChunker(chunk_size=100, chunk_overlap=20)
    chunker2 = HierarchicalStructuralChunker(chunk_size=100, chunk_overlap=20)

    run1 = chunker1.chunk(text)
    run2 = chunker2.chunk(text)

    assert len(run1) == len(run2)
    for c1, c2 in zip(run1, run2, strict=True):
        assert c1.sequence_number == c2.sequence_number
        assert c1.content == c2.content
        assert c1.checksum == c2.checksum
        assert c1.start_char_idx == c2.start_char_idx
        assert c1.end_char_idx == c2.end_char_idx


def test_chunker_no_empty_chunks():
    text = "\n\n\n\n   \n\n# Heading Only\n\n   \n\n"
    chunker = HierarchicalStructuralChunker(chunk_size=100, chunk_overlap=10)
    chunks = chunker.chunk(text)

    for c in chunks:
        assert len(c.content.strip()) > 0


def test_chunker_large_paragraph_split():
    long_para = "This is a sentence. " * 30  # ~600 chars
    chunker = HierarchicalStructuralChunker(chunk_size=150, chunk_overlap=20)
    chunks = chunker.chunk(long_para)

    assert len(chunks) > 1
    for c in chunks:
        assert len(c.content) <= 180  # Reasonable boundary bound
