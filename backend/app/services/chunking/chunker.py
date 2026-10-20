"""Hierarchical structural text chunker with heading hierarchy tracking and reproducible provenance."""

import hashlib
import re
from dataclasses import dataclass, field

PIPELINE_CHUNKER_VERSION = "1.0.0"


@dataclass
class ChunkData:
    """Structured representation of an extracted text chunk."""

    sequence_number: int
    content: str
    word_count: int
    character_count: int
    start_char_idx: int
    end_char_idx: int
    heading_hierarchy: list[str] = field(default_factory=list)
    checksum: str = ""
    pipeline_version: str = PIPELINE_CHUNKER_VERSION


class HierarchicalStructuralChunker:
    """Deterministic structural text chunker preserving section breadcrumbs and boundaries."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
        pipeline_version: str = PIPELINE_CHUNKER_VERSION,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and less than chunk_size.")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.pipeline_version = pipeline_version

    @property
    def version(self) -> str:
        return self.pipeline_version

    def chunk(self, text: str) -> list[ChunkData]:
        """Partition normalized text into reproducible chunks with structural breadcrumbs."""
        if not text or not text.strip():
            return []

        # Find paragraphs and structural headings with their start/end offsets
        blocks = self._parse_structural_blocks(text)
        if not blocks:
            return []

        chunks: list[ChunkData] = []
        seq = 0

        current_content_parts: list[str] = []
        current_headings: list[str] = []
        current_start_idx: int = -1
        current_end_idx: int = -1

        for block_text, b_start, b_end, headings in blocks:
            is_heading = block_text.startswith("#")

            # Flush current chunk when encountering a new heading if we already have content
            if is_heading and current_content_parts:
                chunk_text = "\n\n".join(current_content_parts)
                chunks.append(
                    self._create_chunk(
                        seq, chunk_text, current_start_idx, current_end_idx, current_headings
                    )
                )
                seq += 1
                current_content_parts = []
                current_start_idx = -1

            if current_start_idx == -1:
                current_start_idx = b_start
                current_headings = list(headings)

            potential_text = (
                "\n\n".join(current_content_parts + [block_text])
                if current_content_parts
                else block_text
            )

            if len(potential_text) <= self.chunk_size:
                current_content_parts.append(block_text)
                current_end_idx = b_end
            else:
                # Need to flush existing chunk if we have content
                if current_content_parts:
                    chunk_text = "\n\n".join(current_content_parts)
                    chunks.append(
                        self._create_chunk(
                            seq, chunk_text, current_start_idx, current_end_idx, current_headings
                        )
                    )
                    seq += 1

                    # Setup overlap from previous chunk
                    overlap_prefix = self._extract_overlap(chunk_text)
                    current_content_parts = [overlap_prefix] if overlap_prefix else []
                else:
                    current_content_parts = []

                # Now handle the block itself: what if block_text alone exceeds chunk_size?
                if len(block_text) > self.chunk_size:
                    sub_chunks = self._split_large_block(block_text, b_start, headings, seq)
                    for sc in sub_chunks:
                        chunks.append(sc)
                        seq += 1
                    current_content_parts = []
                    current_start_idx = -1
                    current_headings = list(headings)
                else:
                    current_content_parts.append(block_text)
                    current_start_idx = b_start
                    current_end_idx = b_end
                    current_headings = list(headings)

        # Flush final pending block
        if current_content_parts:
            final_text = "\n\n".join(current_content_parts).strip()
            if final_text:
                chunks.append(
                    self._create_chunk(
                        seq,
                        final_text,
                        current_start_idx if current_start_idx != -1 else 0,
                        current_end_idx if current_end_idx != -1 else len(text),
                        current_headings,
                    )
                )

        return chunks

    def _create_chunk(
        self,
        seq: int,
        content: str,
        start_idx: int,
        end_idx: int,
        headings: list[str],
    ) -> ChunkData:
        stripped = content.strip()
        checksum = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
        words = stripped.split()
        return ChunkData(
            sequence_number=seq,
            content=stripped,
            word_count=len(words),
            character_count=len(stripped),
            start_char_idx=max(0, start_idx),
            end_char_idx=max(start_idx, end_idx),
            heading_hierarchy=headings,
            checksum=checksum,
            pipeline_version=self.pipeline_version,
        )

    def _extract_overlap(self, text: str) -> str:
        """Extract up to chunk_overlap trailing characters snapped to a clean word boundary."""
        if not self.chunk_overlap or len(text) <= self.chunk_overlap:
            return ""
        candidate = text[-self.chunk_overlap :]
        # Snap to next word boundary to prevent partial words
        space_idx = candidate.find(" ")
        if space_idx != -1 and space_idx < len(candidate) - 1:
            return candidate[space_idx + 1 :].strip()
        return candidate.strip()

    def _parse_structural_blocks(self, text: str) -> list[tuple[str, int, int, list[str]]]:
        """Parse text into structural paragraphs tracking Markdown heading hierarchy."""
        blocks: list[tuple[str, int, int, list[str]]] = []
        heading_stack: list[tuple[int, str]] = []  # (level, heading_text)

        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

        pos = 0
        parts = re.split(r"(\n{2,})", text)
        for part in parts:
            start_idx = pos
            pos += len(part)
            if not part or part.startswith("\n"):
                continue

            block_text = part.strip()
            if not block_text:
                continue

            # Check if block is a heading line
            h_match = heading_pattern.match(block_text)
            if h_match:
                level = len(h_match.group(1))
                heading_title = h_match.group(2).strip()

                # Pop headings of equal or deeper level
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, heading_title))

            current_hierarchy = [h[1] for h in heading_stack]
            blocks.append((block_text, start_idx, start_idx + len(block_text), current_hierarchy))

        return blocks

    def _split_large_block(
        self,
        text: str,
        base_offset: int,
        headings: list[str],
        start_seq: int,
    ) -> list[ChunkData]:
        """Split a large single paragraph exceeding chunk_size using sentence boundaries."""
        # Split on sentence boundaries (. ! ?)
        sentence_end = re.compile(r"(?<=[.!?])\s+")
        sentences = [s.strip() for s in sentence_end.split(text) if s.strip()]

        if not sentences:
            sentences = [text]

        chunks: list[ChunkData] = []
        current_sentences: list[str] = []
        seq = start_seq
        cursor = base_offset

        for s in sentences:
            potential = " ".join(current_sentences + [s])
            if len(potential) <= self.chunk_size:
                current_sentences.append(s)
            else:
                if current_sentences:
                    chunk_text = " ".join(current_sentences)
                    end_offset = cursor + len(chunk_text)
                    chunks.append(self._create_chunk(seq, chunk_text, cursor, end_offset, headings))
                    seq += 1
                    cursor = end_offset + 1
                    current_sentences = []

                # If single sentence exceeds chunk_size, slice by characters/words
                if len(s) > self.chunk_size:
                    for i in range(0, len(s), self.chunk_size - self.chunk_overlap):
                        part = s[i : i + self.chunk_size].strip()
                        if part:
                            chunks.append(
                                self._create_chunk(
                                    seq, part, cursor + i, cursor + i + len(part), headings
                                )
                            )
                            seq += 1
                    cursor += len(s)
                else:
                    current_sentences.append(s)

        if current_sentences:
            final_text = " ".join(current_sentences)
            chunks.append(
                self._create_chunk(seq, final_text, cursor, cursor + len(final_text), headings)
            )

        return chunks
