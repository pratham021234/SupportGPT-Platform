"""Extraction abstractions and structured extraction results for SupportGPT."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractionResult:
    """Standardized representation of extracted document content."""

    text: str
    extractor_name: str
    extractor_version: str
    word_count: int
    character_count: int
    metadata: dict[str, Any] = field(default_factory=dict)
    is_empty: bool = False
    warning: str | None = None


class BaseExtractor(ABC):
    """Abstract base extractor interface for document formats."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the extractor."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Version of the extractor component or underlying library."""
        pass

    @abstractmethod
    def extract(self, content_bytes: bytes, filename: str | None = None) -> ExtractionResult:
        """Extract plain structural text and metadata from raw binary content."""
        pass
