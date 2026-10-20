"""Semantic Vector Embedding Provider Integration.

Provides vendor-neutral embedding generation with strict dimension validation,
batching, non-finite vector rejection, and operational metadata tracking.
"""

import logging
import math
import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.errors import (
    EmbeddingGenerationException,
    VectorDimensionMismatchException,
)

logger = logging.getLogger(__name__)

# Suppress HuggingFace symlinks warning on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"


class EmbeddingMetadata(BaseModel):
    """Operational metadata tracked for every vector generation event."""

    provider_name: str
    model_name: str
    dimensions: int
    pipeline_version: str = "v1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BaseEmbeddingProvider(ABC):
    """Vendor-neutral interface for semantic vector generation."""

    def __init__(self, model_name: str, dimensions: int) -> None:
        self.model_name = model_name
        self.dimensions = dimensions

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate normalized vector embeddings for an ordered batch of text strings."""
        pass

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        """Generate a normalized vector embedding for a single search or retrieval query."""
        pass

    def validate_vector(self, vector: list[float]) -> list[float]:
        """Validate that a vector has exact expected dimensions and finite real numbers.

        SECURITY & INTEGRITY INVARIANT:
        Rejects non-finite (NaN, Inf) floats and malformed dimensions to prevent
        corrupting Qdrant HNSW index graphs or failing distance calculations.
        """
        if len(vector) != self.dimensions:
            raise VectorDimensionMismatchException(
                f"Generated vector length ({len(vector)}) does not match expected "
                f"dimensions ({self.dimensions})."
            )

        for i, val in enumerate(vector):
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise EmbeddingGenerationException(
                    f"Vector contains invalid or non-finite element at index {i}: {val}"
                )

        return vector


class FastEmbedEmbeddingProvider(BaseEmbeddingProvider):
    """Real local embedding provider using FastEmbed ONNX Runtime.

    Executes state-of-the-art dense embedding models (e.g. BAAI/bge-small-en-v1.5)
    locally without requiring external network calls, GPU acceleration, or API keys.
    """

    def __init__(
        self,
        model_name: str = settings.EMBEDDING_MODEL_NAME,
        dimensions: int = settings.EMBEDDING_DIMENSIONS,
    ) -> None:
        super().__init__(model_name=model_name, dimensions=dimensions)
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(model_name=self.model_name)
            except Exception as exc:
                logger.error(f"Failed to load FastEmbed model '{self.model_name}': {exc}")
                raise EmbeddingGenerationException(
                    f"FastEmbed model initialization failed: {exc}"
                ) from exc
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of text chunks."""
        if not texts:
            return []

        # Validate that texts are non-empty strings
        sanitized_texts: list[str] = []
        for i, text in enumerate(texts):
            if not text or not text.strip():
                raise EmbeddingGenerationException(
                    f"Cannot generate embedding for empty or whitespace-only text at index {i}."
                )
            sanitized_texts.append(text.strip())

        try:
            model = self._get_model()
            # FastEmbed model.embed returns a generator of numpy float arrays
            raw_embeddings = list(
                model.embed(
                    sanitized_texts,
                    batch_size=settings.EMBEDDING_BATCH_SIZE,
                )
            )

            validated_vectors: list[list[float]] = []
            for raw_vec in raw_embeddings:
                float_vec = [float(x) for x in raw_vec]
                validated_vectors.append(self.validate_vector(float_vec))

            return validated_vectors
        except Exception as exc:
            if isinstance(exc, (EmbeddingGenerationException, VectorDimensionMismatchException)):
                raise
            logger.error(f"FastEmbed text embedding generation error: {exc}")
            raise EmbeddingGenerationException(
                f"Local text embedding generation failed: {exc}"
            ) from exc

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single search query."""
        if not query or not query.strip():
            raise EmbeddingGenerationException("Cannot generate embedding for empty query.")

        vectors = await self.embed_texts([query])
        return vectors[0]


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Remote OpenAI embedding provider using async HTTPX client."""

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        dimensions: int = 1536,
        api_key: str | None = settings.EMBEDDING_API_KEY,
        endpoint: str | None = settings.EMBEDDING_ENDPOINT,
    ) -> None:
        super().__init__(model_name=model_name, dimensions=dimensions)
        self.api_key = api_key
        self.endpoint = endpoint or "https://api.openai.com/v1/embeddings"

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise EmbeddingGenerationException(
                "OpenAI embedding provider requested but EMBEDDING_API_KEY is not configured."
            )

        if not texts:
            return []

        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "input": [t.strip() for t in texts],
            "model": self.model_name,
            "dimensions": self.dimensions,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
                if response.status_code != 200:
                    raise EmbeddingGenerationException(
                        f"OpenAI API returned HTTP {response.status_code}: {response.text}"
                    )
                data = response.json()
                sorted_data = sorted(data["data"], key=lambda item: item["index"])
                vectors = [self.validate_vector(item["embedding"]) for item in sorted_data]
                return vectors
        except Exception as exc:
            if isinstance(exc, (EmbeddingGenerationException, VectorDimensionMismatchException)):
                raise
            raise EmbeddingGenerationException(f"OpenAI embedding request failed: {exc}") from exc

    async def embed_query(self, query: str) -> list[float]:
        vectors = await self.embed_texts([query])
        return vectors[0]


class DeterministicMockEmbeddingProvider(BaseEmbeddingProvider):
    """Explicit test double for unit tests requiring deterministic offline vectors.

    NEVER used in live production indexing.
    """

    def __init__(self, dimensions: int = settings.EMBEDDING_DIMENSIONS) -> None:
        super().__init__(model_name="deterministic-mock-v1", dimensions=dimensions)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        import hashlib

        results: list[list[float]] = []
        for text in texts:
            if not text or not text.strip():
                raise EmbeddingGenerationException("Cannot embed empty text.")
            # Generate deterministic unit vector from text sha256
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw = [((digest[i % len(digest)] / 255.0) * 2.0 - 1.0) for i in range(self.dimensions)]
            # Normalize to unit length
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            results.append([x / norm for x in raw])
        return results

    async def embed_query(self, query: str) -> list[float]:
        vectors = await self.embed_texts([query])
        return vectors[0]


_embedding_provider_instance: BaseEmbeddingProvider | None = None


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Factory retrieving the configured embedding provider singleton."""
    global _embedding_provider_instance
    if _embedding_provider_instance is None:
        provider_name = settings.EMBEDDING_PROVIDER.lower().strip()
        if provider_name == "fastembed":
            _embedding_provider_instance = FastEmbedEmbeddingProvider(
                model_name=settings.EMBEDDING_MODEL_NAME,
                dimensions=settings.EMBEDDING_DIMENSIONS,
            )
        elif provider_name == "openai":
            _embedding_provider_instance = OpenAIEmbeddingProvider(
                model_name=settings.EMBEDDING_MODEL_NAME,
                dimensions=settings.EMBEDDING_DIMENSIONS,
            )
        elif provider_name == "mock":
            _embedding_provider_instance = DeterministicMockEmbeddingProvider(
                dimensions=settings.EMBEDDING_DIMENSIONS,
            )
        else:
            raise EmbeddingGenerationException(
                f"Unsupported embedding provider configured: '{settings.EMBEDDING_PROVIDER}'"
            )
    return _embedding_provider_instance


def reset_embedding_provider() -> None:
    """Reset the cached provider singleton (used in testing)."""
    global _embedding_provider_instance
    _embedding_provider_instance = None
