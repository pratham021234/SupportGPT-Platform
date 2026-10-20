# ADR 0008: Enterprise Knowledge Base, Document Processing, Versioning & Retrieval Foundation

## Status
Accepted

## Context
SupportGPT AI requires a trusted evidence foundation for retrieval-augmented generation (RAG), AI-assisted customer support, citation provenance, and human-in-the-loop verification.

A production-grade enterprise knowledge subsystem must satisfy stringent security, engineering, and reliability standards:
1. **Canonical Knowledge Models & Immutability**: Knowledge collections (`KnowledgeBase`), source documents (`Document`), immutable revision histories (`DocumentVersion`), and retrieval chunks (`DocumentChunk`) must be modeled with clear domain boundaries.
2. **Safe Object Storage**: Source binary files must be stored outside database rows using opaque, non-guessable storage keys. Storage implementations must guard against path traversal, symlink attacks, and partial write corruption.
3. **Strict Validation & Format Allowlist**: File types cannot be trusted from client extensions or MIME headers. Genuine magic byte signatures must be inspected. Compression bombs (DOCX) and executable scripts disguised as text must be rejected.
4. **Authentic Text Extraction**: Text extraction must genuinely extract structural document content (PDF, DOCX, TXT, Markdown) rather than hardcoded or simulated text. Scanned or image-only PDFs must be detected, explicitly reporting that OCR is unavailable.
5. **Deterministic Normalization & Provenance Chunking**: Text normalization must preserve technical tokens, URLs, code blocks, and section headings. Chunks must be deterministic, versioned, ordered with stable sequence numbers, bounded by character offsets, and tracked with heading hierarchy breadcrumbs.
6. **Prior Version Preservation & Atomic Reprocessing**: Failed processing of a new document version must never corrupt or deactivate an existing usable version. Reprocessing must atomically replace chunks without leaving orphaned partial sets.
7. **Strict Multi-Tenant Isolation**: Knowledge bases, documents, versions, and chunks must inherit organization boundaries, protected by composite foreign key constraints and PostgreSQL 16 Row-Level Security (RLS).
8. **Vector Indexing Readiness**: Vector database integration (Phase 06) must remain decoupled from canonical relational persistence. No simulated vectors or fake embeddings may be stored in Phase 05.

## Decision

### 1. Domain Entities & Relational Schema
Implemented four canonical entities in `backend/app/models/`:
- `KnowledgeBase`: Organization-owned logical collection of knowledge with status (`active`, `archived`) and configuration JSONB.
- `Document`: Canonical document entity tracking verified MIME type, original filename, processing status, lifecycle state (`active`, `archived`, `deleted`), and current usable version reference (`current_version_id`).
- `DocumentVersion`: Immutable file revision tracking monotonic `version_number`, internal `storage_key`, SHA-256 binary checksum, byte size, processing state, extractor metadata, chunk count, word count, character count, worker lease lock, and attempt count.
- `DocumentChunk`: Persisted retrieval partition tracking `sequence_number`, normalized content, word count, character count, exact `start_char_idx` and `end_char_idx`, structural `heading_hierarchy` breadcrumbs, chunk content SHA-256 digest, and `pipeline_version`.

### 2. Storage Subsystem & Path Traversal Guards
- Created `StorageBackend` abstraction in `backend/app/services/storage/base.py` and `LocalStorageBackend` in `backend/app/services/storage/local.py`.
- **Storage Keys**: Opaque and non-predictable, formatted as `org_{org_id}/docs/{doc_id}/v{version_number}_{uuid}.bin`.
- **Path Traversal Defense**: Enforces that storage keys contain no leading slashes, backslashes, drive letters, or `..` components. Verifies that `Path(target).resolve().is_relative_to(base_dir)`.
- **Atomic Streaming Writes**: Streams bytes directly to a temporary `.tmp_{uuid}` file within the target directory while simultaneously computing the running SHA-256 checksum and checking byte limits (`max_bytes`). Atomically calls `os.replace` to commit the file only upon verified integrity.

### 3. File Validation & Decompression Safety
- Implemented `validate_document_file` in `backend/app/services/extraction/validator.py`:
  - **PDF**: Verified against `%PDF-` signature.
  - **DOCX**: Verified as a valid PKZIP container possessing `word/document.xml`. Enforces maximum uncompressed threshold (100MB) and maximum expansion ratio (50x) to prevent zip-bomb denial of service.
  - **TXT / Markdown**: Verified as valid UTF-8/UTF-8-SIG text without binary null bytes (`\x00`).
  - **Allowlist Only**: Rejects executable formats, archives, scripts, and unknown extensions.
  - **Filename Sanitization**: Cleans path traversal sequences, control characters, and dangerous characters.

### 4. Text Extraction Pipeline
- **PDF**: Extracted via `pypdf.PdfReader` with per-page text extraction and metadata retrieval. Automatically detects scanned or image-only documents (where zero text characters are found) and raises `DocumentExtractionException` classifying the error as OCR unavailable.
- **DOCX**: Extracted via `python-docx` preserving Markdown-style headings (`# Heading 1`, `## Heading 2`), paragraphs, and tabular data formatted with pipe delimiters.
- **TXT & Markdown**: Normalizes line endings (`\r\n` -> `\n`, `\r` -> `\n`) and preserves code blocks, URLs, and section formatting.

### 5. Deterministic Normalization & Hierarchical Structural Chunking
- `TextNormalizer` (`v1.0.0`): Strips non-printable ASCII control characters (preserving tabs and standard newlines), removes trailing whitespace, and collapses excessive blank lines into clean paragraph boundaries (`\n\n`).
- `HierarchicalStructuralChunker` (`v1.0.0`):
  - Tracks structural Markdown heading hierarchies (`#`, `##`, `###`) to maintain contextual section breadcrumbs on every chunk.
  - Flushes chunks when major section headings are encountered to preserve section purity.
  - Slices large blocks using sentence boundaries (`.!?`) and word boundaries.
  - Applies configurable `chunk_size` and `chunk_overlap` snapped to clean word boundaries.
  - Emits exact character offsets (`start_char_idx`, `end_char_idx`) and SHA-256 chunk checksums.
  - Guarantees zero empty chunks.

### 6. Background Worker & Version Safety
- Implemented `DocumentWorker` (`backend/app/services/document_worker.py`):
  - **Idempotent Claiming**: Uses `FOR UPDATE SKIP LOCKED` on PostgreSQL to allow multiple parallel workers to claim jobs without deadlock or double processing.
  - **Lease Reclamation**: Automatically recovers jobs from crashed workers where leases exceed `DOCUMENT_PROCESSING_LEASE_TIMEOUT_SECONDS` (300s).
  - **Prior Version Preservation**: When v2 fails extraction or chunking, parent `Document.current_version_id` continues to point to v1. Working versions are never destroyed by subsequent failed uploads.
  - **Atomic Chunk Publication**: During reprocessing, existing chunks for that version are deleted and replaced in the same database transaction.

### 7. Multi-Tenant Isolation & PostgreSQL Row-Level Security
- Migration `0006_knowledge_base_subsystem` applied to `supportgpt_db` and `supportgpt_test_db`.
- Enabled `FORCE ROW LEVEL SECURITY` and created isolation policies on `knowledge_bases`, `documents`, `document_versions`, and `document_chunks`.
- Composite foreign key constraints enforce that a document or chunk can never reference a knowledge base or version belonging to another organization.
- Cross-tenant API lookups return HTTP 404 (preventing existence disclosure).

## Consequences
- **Positive**:
  - Genuine, reproducible text extraction and structural chunking without mock or simulated logic.
  - Provenance-backed chunks ready for vector indexing in Phase 06.
  - Strict tenant isolation enforced at database engine, constraint, and application layers.
  - Resilient to worker crashes, path traversal attacks, and oversized or malformed uploads.
- **Trade-offs & Limitations**:
  - Local storage backend is intended for single-node development and staging. Multi-node cloud deployments will require an S3-compatible object store adapter in a future phase.
  - OCR is not implemented in this phase; scanned PDFs and images are reported as `OCR_UNAVAILABLE`.
  - External vector embeddings and semantic search are deferred to Phase 06.
