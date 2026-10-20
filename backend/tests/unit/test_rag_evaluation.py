"""Unit tests for the RAG evaluation framework, metric calculations, and report compilation."""

import uuid

from app.services.rag.evaluation import (
    EVALUATION_DATASET,
    EvalTestCase,
    RAGEvaluator,
)
from app.services.rag.evidence import CitationItem, EvidenceItem, GroundedAnswerResult


def test_evaluation_metric_calculations():
    """Verify Recall@k, Reciprocal Rank, and citation validity calculations."""
    evaluator = RAGEvaluator(embedding_provider="fastembed", embedding_model="BAAI/bge-small-en-v1.5")

    doc_id = uuid.uuid4()
    chunk_1 = uuid.uuid4()

    ev_1 = EvidenceItem(
        evidence_id="ev_1",
        chunk_id=chunk_1,
        document_id=doc_id,
        document_version_id=uuid.uuid4(),
        knowledge_base_id=uuid.uuid4(),
        source_title="Enterprise Security Policy",
        relevant_excerpt="Passwords must be at least 16 characters in length.",
        retrieval_rank=1,
        retrieval_score=0.91,
        citation_reference="[citation:1]",
    )

    # 1. Test answerable query with hit at rank 1
    test_case_answerable = EvalTestCase(
        test_id="eval_01",
        question="What is the password length?",
        expected_source_title="Enterprise Security Policy",
        expected_content_keywords=["16 characters"],
        is_unanswerable=False,
        expected_abstention=False,
    )

    answer_result_good = GroundedAnswerResult(
        question="What is the password length?",
        answer="Passwords require 16 characters [citation:1].",
        citations=[
            CitationItem(
                citation_number=1,
                citation_marker="[citation:1]",
                evidence_id="ev_1",
                chunk_id=chunk_1,
                document_id=doc_id,
                source_title="Enterprise Security Policy",
                excerpt="Passwords must be at least 16 characters in length.",
                retrieval_score=0.91,
            )
        ],
        evidence=[ev_1],
        abstention_status=False,
    )

    res1 = evaluator.evaluate_query(test_case_answerable, [ev_1], answer_result_good)
    assert res1.recall_at_k == 1.0
    assert res1.reciprocal_rank == 1.0
    assert res1.citation_validity == 1.0
    assert res1.abstention_accurate is True

    # 2. Test unanswerable query with correct abstention
    test_case_unanswerable = EvalTestCase(
        test_id="eval_02",
        question="What is the CEO favorite dog breed?",
        expected_source_title=None,
        expected_content_keywords=[],
        is_unanswerable=True,
        expected_abstention=True,
    )

    answer_result_abstain = GroundedAnswerResult(
        question="What is the CEO favorite dog breed?",
        answer="I do not have sufficient information in the knowledge base.",
        citations=[],
        evidence=[],
        abstention_status=True,
        abstention_reason="NO_EVIDENCE_RETRIEVED",
    )

    res2 = evaluator.evaluate_query(test_case_unanswerable, [], answer_result_abstain)
    assert res2.recall_at_k == 0.0
    assert res2.reciprocal_rank == 0.0
    assert res2.abstention_accurate is True

    # 3. Test aggregate report compilation
    report = evaluator.compile_report([res1, res2])
    assert report.total_queries == 2
    assert report.answerable_queries == 1
    assert report.unanswerable_queries == 1
    assert report.mean_recall_at_k == 1.0
    assert report.mean_reciprocal_rank == 1.0
    assert report.abstention_accuracy == 1.0
    assert report.citation_validity_rate == 1.0
    assert report.embedding_model == "BAAI/bge-small-en-v1.5"


def test_evaluation_dataset_structure():
    """Verify reference evaluation dataset meets schema constraints."""
    assert len(EVALUATION_DATASET) >= 5
    for case in EVALUATION_DATASET:
        assert isinstance(case.question, str) and len(case.question) > 5
        if case.is_unanswerable:
            assert case.expected_abstention is True
            assert case.expected_source_title is None
        else:
            assert case.expected_abstention is False
            assert len(case.expected_content_keywords) >= 1
