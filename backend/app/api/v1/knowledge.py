"""FastAPI router for knowledge bases, document uploads, revisions, chunk provenance, and lifecycle management."""

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Path,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrganizationContext, require_permission
from app.core.rbac import Permission
from app.db.session import get_db_session
from app.schemas.knowledge import (
    CitationResponse,
    DocumentChunkListResponse,
    DocumentChunkResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
    DocumentVersionResponse,
    EvidenceItemResponse,
    KnowledgeAnswerRequest,
    KnowledgeAnswerResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.services.document_service import DocumentService
from app.services.rag.answer import GroundedAnswerService
from app.services.rag.retrieval import RetrievalService

router = APIRouter(prefix="/organizations/{organization_id}", tags=["Knowledge Base"])


# ==========================================
# Knowledge Base Collections
# ==========================================


@router.post(
    "/knowledge-bases",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create knowledge base",
    description="Create an organization-scoped logical knowledge base collection.",
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    context: Annotated[
        OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_WRITE))
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeBaseResponse:
    service = DocumentService(db)
    kb = await service.create_knowledge_base(
        organization_id=context.organization.id,
        name=payload.name,
        description=payload.description,
        config=payload.config,
        user_id=context.user.id,
    )
    return KnowledgeBaseResponse.model_validate(kb)


@router.get(
    "/knowledge-bases",
    response_model=KnowledgeBaseListResponse,
    status_code=status.HTTP_200_OK,
    summary="List knowledge bases",
    description="List all knowledge base collections for the organization.",
)
async def list_knowledge_bases(
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> KnowledgeBaseListResponse:
    service = DocumentService(db)
    items, total = await service.list_knowledge_bases(
        organization_id=context.organization.id, limit=limit, offset=offset
    )
    return KnowledgeBaseListResponse(
        items=[KnowledgeBaseResponse.model_validate(k) for k in items],
        total=total,
    )


@router.get(
    "/knowledge-bases/{knowledge_base_id}",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Get knowledge base details",
    description="Retrieve a single knowledge base by ID strictly scoped to the tenant.",
)
async def get_knowledge_base(
    knowledge_base_id: Annotated[uuid.UUID, Path(..., description="Target knowledge base ID")],
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeBaseResponse:
    service = DocumentService(db)
    kb = await service.get_knowledge_base(
        organization_id=context.organization.id, kb_id=knowledge_base_id
    )
    return KnowledgeBaseResponse.model_validate(kb)


# ==========================================
# Document Upload and Management
# ==========================================


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload document to knowledge base",
    description="Upload, validate, and durably store a document version in a knowledge base, queueing processing.",
)
async def upload_document(
    knowledge_base_id: Annotated[uuid.UUID, Path(..., description="Target knowledge base ID")],
    context: Annotated[
        OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_WRITE))
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    file: UploadFile = File(..., description="Document binary file (PDF, DOCX, TXT, or Markdown)"),
    title: str | None = Form(default=None, description="Optional document display title"),
) -> DocumentUploadResponse:
    content_bytes = await file.read()
    service = DocumentService(db)
    doc, version = await service.upload_document(
        organization_id=context.organization.id,
        knowledge_base_id=knowledge_base_id,
        filename=file.filename or "unnamed_document",
        content_bytes=content_bytes,
        title=title,
        user_id=context.user.id,
    )
    return DocumentUploadResponse(
        document=DocumentResponse.model_validate(doc),
        version=DocumentVersionResponse.model_validate(version),
    )


@router.get(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List documents in knowledge base",
    description="List active documents contained within a specific knowledge base.",
)
async def list_kb_documents(
    knowledge_base_id: Annotated[uuid.UUID, Path(..., description="Target knowledge base ID")],
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    service = DocumentService(db)
    items, total = await service.list_documents(
        organization_id=context.organization.id,
        kb_id=knowledge_base_id,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in items],
        total=total,
    )


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all organization documents",
    description="List active documents across all knowledge bases for the organization.",
)
async def list_documents(
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    service = DocumentService(db)
    items, total = await service.list_documents(
        organization_id=context.organization.id,
        kb_id=None,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in items],
        total=total,
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document details",
    description="Retrieve canonical document record strictly scoped to the tenant.",
)
async def get_document(
    document_id: Annotated[uuid.UUID, Path(..., description="Target document ID")],
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentResponse:
    service = DocumentService(db)
    doc = await service.get_document(
        organization_id=context.organization.id, document_id=document_id
    )
    return DocumentResponse.model_validate(doc)


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[DocumentVersionResponse],
    status_code=status.HTTP_200_OK,
    summary="List document versions",
    description="Retrieve chronological history of revisions for a document.",
)
async def list_document_versions(
    document_id: Annotated[uuid.UUID, Path(..., description="Target document ID")],
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[DocumentVersionResponse]:
    service = DocumentService(db)
    versions = await service.list_document_versions(
        organization_id=context.organization.id, document_id=document_id
    )
    return [DocumentVersionResponse.model_validate(v) for v in versions]


@router.post(
    "/documents/{document_id}/versions",
    response_model=DocumentVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload new document version",
    description="Upload a new immutable version for an existing document without altering prior working versions.",
)
async def upload_new_version(
    document_id: Annotated[uuid.UUID, Path(..., description="Target document ID")],
    context: Annotated[
        OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_WRITE))
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    file: UploadFile = File(..., description="New version document binary file"),
) -> DocumentVersionResponse:
    content_bytes = await file.read()
    service = DocumentService(db)
    version = await service.upload_new_version(
        organization_id=context.organization.id,
        document_id=document_id,
        filename=file.filename or "unnamed_document",
        content_bytes=content_bytes,
        user_id=context.user.id,
    )
    return DocumentVersionResponse.model_validate(version)


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=DocumentVersionResponse,
    status_code=status.HTTP_200_OK,
    summary="Reprocess document",
    description="Queue reprocessing for a document version without corrupting source data.",
)
async def reprocess_document(
    document_id: Annotated[uuid.UUID, Path(..., description="Target document ID")],
    context: Annotated[
        OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_WRITE))
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    version_id: uuid.UUID | None = Query(
        default=None, description="Optional specific version ID to reprocess"
    ),
) -> DocumentVersionResponse:
    service = DocumentService(db)
    ver = await service.reprocess_document(
        organization_id=context.organization.id,
        document_id=document_id,
        version_id=version_id,
    )
    return DocumentVersionResponse.model_validate(ver)


@router.delete(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft delete document",
    description="Soft delete a document removing it from active search and retrieval sets.",
)
async def delete_document(
    document_id: Annotated[uuid.UUID, Path(..., description="Target document ID")],
    context: Annotated[
        OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_MANAGE))
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentResponse:
    service = DocumentService(db)
    doc = await service.soft_delete_document(
        organization_id=context.organization.id, document_id=document_id
    )
    return DocumentResponse.model_validate(doc)


@router.get(
    "/documents/{document_id}/chunks",
    response_model=DocumentChunkListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document chunks with provenance",
    description="Retrieve persisted text chunks with exact section hierarchy and offsets.",
)
async def get_document_chunks(
    document_id: Annotated[uuid.UUID, Path(..., description="Target document ID")],
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    version_id: uuid.UUID | None = Query(default=None, description="Optional version ID"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentChunkListResponse:
    service = DocumentService(db)
    chunks, total = await service.get_document_chunks(
        organization_id=context.organization.id,
        document_id=document_id,
        version_id=version_id,
        limit=limit,
        offset=offset,
    )
    return DocumentChunkListResponse(
        items=[DocumentChunkResponse.model_validate(c) for c in chunks],
        total=total,
    )


# ==========================================
# Retrieval & Grounded Answering
# ==========================================


@router.post(
    "/knowledge-bases/{knowledge_base_id}/search",
    response_model=KnowledgeSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search knowledge base",
    description="Execute authorized semantic and hybrid search over knowledge base documents.",
)
async def search_knowledge_base(
    knowledge_base_id: Annotated[uuid.UUID, Path(..., description="Target knowledge base ID")],
    payload: KnowledgeSearchRequest,
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeSearchResponse:
    # 1. Verify parent knowledge base exists and belongs to this organization
    doc_service = DocumentService(db)
    await doc_service.get_knowledge_base(context.organization.id, knowledge_base_id)

    # 2. Execute authoritative retrieval
    retrieval_service = RetrievalService(db)
    evidence, latency_ms = await retrieval_service.retrieve(
        query=payload.query,
        organization_id=context.organization.id,
        knowledge_base_ids=[knowledge_base_id],
        top_k=payload.top_k,
        min_score=payload.min_score,
        enable_hybrid=payload.enable_hybrid,
    )

    return KnowledgeSearchResponse(
        query=payload.query,
        evidence=[EvidenceItemResponse.model_validate(ev.model_dump()) for ev in evidence],
        total_results=len(evidence),
        retrieval_latency_ms=round(latency_ms, 2),
    )


@router.post(
    "/knowledge-bases/{knowledge_base_id}/answer",
    response_model=KnowledgeAnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask grounded question",
    description="Generate an evidence-grounded answer with verified citations and abstention handling.",
)
async def answer_knowledge_question(
    knowledge_base_id: Annotated[uuid.UUID, Path(..., description="Target knowledge base ID")],
    payload: KnowledgeAnswerRequest,
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeAnswerResponse:
    # 1. Verify parent knowledge base exists and belongs to this organization
    doc_service = DocumentService(db)
    await doc_service.get_knowledge_base(context.organization.id, knowledge_base_id)

    # 2. Execute authoritative retrieval
    retrieval_service = RetrievalService(db)
    evidence, retrieval_latency_ms = await retrieval_service.retrieve(
        query=payload.question,
        organization_id=context.organization.id,
        knowledge_base_ids=[knowledge_base_id],
        top_k=payload.top_k,
        min_score=payload.min_score,
        enable_hybrid=payload.enable_hybrid,
    )

    # 3. Generate grounded answer
    answer_service = GroundedAnswerService()
    result = await answer_service.generate_answer(
        question=payload.question,
        evidence=evidence,
        retrieval_latency_ms=retrieval_latency_ms,
    )

    return KnowledgeAnswerResponse(
        question=result.question,
        answer=result.answer,
        citations=[CitationResponse.model_validate(c.model_dump()) for c in result.citations],
        evidence=[EvidenceItemResponse.model_validate(ev.model_dump()) for ev in result.evidence],
        abstention_status=result.abstention_status,
        abstention_reason=result.abstention_reason,
        model_name=result.model_name,
        retrieval_latency_ms=result.retrieval_latency_ms,
        generation_latency_ms=result.generation_latency_ms,
        total_latency_ms=result.total_latency_ms,
    )


@router.post(
    "/knowledge/search",
    response_model=KnowledgeSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Organization-wide knowledge search",
    description="Execute authorized semantic and hybrid search across all active knowledge bases.",
)
async def search_organization_knowledge(
    payload: KnowledgeSearchRequest,
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeSearchResponse:
    retrieval_service = RetrievalService(db)
    evidence, latency_ms = await retrieval_service.retrieve(
        query=payload.query,
        organization_id=context.organization.id,
        knowledge_base_ids=None,
        top_k=payload.top_k,
        min_score=payload.min_score,
        enable_hybrid=payload.enable_hybrid,
    )

    return KnowledgeSearchResponse(
        query=payload.query,
        evidence=[EvidenceItemResponse.model_validate(ev.model_dump()) for ev in evidence],
        total_results=len(evidence),
        retrieval_latency_ms=round(latency_ms, 2),
    )


@router.post(
    "/knowledge/answer",
    response_model=KnowledgeAnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Organization-wide grounded question answering",
    description="Generate an evidence-grounded answer across all active knowledge collections.",
)
async def answer_organization_knowledge(
    payload: KnowledgeAnswerRequest,
    context: Annotated[OrganizationContext, Depends(require_permission(Permission.KNOWLEDGE_READ))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeAnswerResponse:
    retrieval_service = RetrievalService(db)
    evidence, retrieval_latency_ms = await retrieval_service.retrieve(
        query=payload.question,
        organization_id=context.organization.id,
        knowledge_base_ids=None,
        top_k=payload.top_k,
        min_score=payload.min_score,
        enable_hybrid=payload.enable_hybrid,
    )

    answer_service = GroundedAnswerService()
    result = await answer_service.generate_answer(
        question=payload.question,
        evidence=evidence,
        retrieval_latency_ms=retrieval_latency_ms,
    )

    return KnowledgeAnswerResponse(
        question=result.question,
        answer=result.answer,
        citations=[CitationResponse.model_validate(c.model_dump()) for c in result.citations],
        evidence=[EvidenceItemResponse.model_validate(ev.model_dump()) for ev in result.evidence],
        abstention_status=result.abstention_status,
        abstention_reason=result.abstention_reason,
        model_name=result.model_name,
        retrieval_latency_ms=result.retrieval_latency_ms,
        generation_latency_ms=result.generation_latency_ms,
        total_latency_ms=result.total_latency_ms,
    )
