"""Unit tests for semantic vector embedding providers, dimension validation, and error handling."""

import math

import pytest

from app.core.errors import (
    EmbeddingGenerationException,
    VectorDimensionMismatchException,
)
from app.services.rag.embedding import (
    DeterministicMockEmbeddingProvider,
    FastEmbedEmbeddingProvider,
    OpenAIEmbeddingProvider,
)


@pytest.mark.asyncio
async def test_fastembed_real_dense_embeddings():
    """Verify real FastEmbed generates 384-dimensional normalized vectors with finite floats."""
    provider = FastEmbedEmbeddingProvider(
        model_name="BAAI/bge-small-en-v1.5",
        dimensions=384,
    )

    texts = [
        "SupportGPT AI enterprise customer service platform.",
        "Role-based access control and tenant isolation in PostgreSQL.",
    ]
    vectors = await provider.embed_texts(texts)

    assert len(vectors) == 2
    for vec in vectors:
        assert len(vec) == 384
        for val in vec:
            assert isinstance(val, float)
            assert math.isfinite(val)
            assert not math.isnan(val)

    # Test single query embedding
    query_vec = await provider.embed_query("How does tenant isolation work?")
    assert len(query_vec) == 384
    assert all(math.isfinite(x) for x in query_vec)


@pytest.mark.asyncio
async def test_fastembed_empty_and_whitespace_rejection():
    """Verify empty or whitespace-only inputs are rejected before embedding."""
    provider = FastEmbedEmbeddingProvider(dimensions=384)

    with pytest.raises(EmbeddingGenerationException) as exc_info:
        await provider.embed_texts(["Valid text", "   ", "Another text"])
    assert "empty or whitespace-only" in str(exc_info.value.message)

    with pytest.raises(EmbeddingGenerationException) as exc_info:
        await provider.embed_query("   ")
    assert "empty query" in str(exc_info.value.message)

    # Empty list returns empty list
    assert await provider.embed_texts([]) == []


def test_vector_dimension_validation():
    """Verify strict dimension checking rejects truncated or oversized vectors."""
    provider = FastEmbedEmbeddingProvider(dimensions=384)

    # Correct dimensions
    good_vector = [0.1] * 384
    assert provider.validate_vector(good_vector) == good_vector

    # Too short
    with pytest.raises(VectorDimensionMismatchException):
        provider.validate_vector([0.1] * 383)

    # Too long
    with pytest.raises(VectorDimensionMismatchException):
        provider.validate_vector([0.1] * 385)


def test_non_finite_vector_rejection():
    """Verify vectors containing NaN or Inf are rejected to protect vector store integrity."""
    provider = FastEmbedEmbeddingProvider(dimensions=384)

    # NaN rejection
    nan_vector = [0.1] * 384
    nan_vector[10] = float("nan")
    with pytest.raises(EmbeddingGenerationException) as exc_info:
        provider.validate_vector(nan_vector)
    assert "non-finite element" in str(exc_info.value.message)

    # Inf rejection
    inf_vector = [0.1] * 384
    inf_vector[50] = float("inf")
    with pytest.raises(EmbeddingGenerationException) as exc_info:
        provider.validate_vector(inf_vector)
    assert "non-finite element" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_deterministic_mock_embedding_provider():
    """Verify deterministic mock provider generates reproducible unit-norm vectors for unit testing."""
    provider = DeterministicMockEmbeddingProvider(dimensions=384)
    v1 = await provider.embed_query("test query 1")
    v2 = await provider.embed_query("test query 1")
    v3 = await provider.embed_query("different query")

    assert len(v1) == 384
    assert v1 == v2  # Deterministic
    assert v1 != v3  # Distinct text yields distinct vector

    # Check approximate unit length
    norm = math.sqrt(sum(x * x for x in v1))
    assert math.isclose(norm, 1.0, rel_tol=1e-4)


@pytest.mark.asyncio
async def test_openai_provider_missing_key_failure():
    """Verify OpenAI provider fails cleanly when API key is not configured."""
    provider = OpenAIEmbeddingProvider(api_key=None)
    with pytest.raises(EmbeddingGenerationException) as exc_info:
        await provider.embed_texts(["Some text"])
    assert "EMBEDDING_API_KEY is not configured" in str(exc_info.value.message)
