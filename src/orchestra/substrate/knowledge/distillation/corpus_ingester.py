"""
Corpus Ingester

Reads and chunks documents from a corpus directory.
Handles markdown, text, and other document formats.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .config import DistillationConfig

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """A chunk of a document ready for processing.

    Attributes:
        content: The text content of the chunk
        source_path: Path to the source document
        chunk_index: Index of this chunk within the document
        total_chunks: Total number of chunks from this document
        document_id: Unique identifier for the source document
        chunk_id: Unique identifier for this chunk
        metadata: Additional metadata (headers, section, etc.)
    """
    content: str
    source_path: Path
    chunk_index: int = 0
    total_chunks: int = 1
    document_id: str = ""
    chunk_id: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Generate IDs if not provided.

        Uses content-addressable hashing for determinism.
        ThinkingMachines [He2025] batch-invariance compliant.
        """
        if not self.document_id:
            # Include content hash for content-addressability
            content_sample = self.content[:500] if self.content else ""
            hash_input = f"{self.source_path}:{content_sample}"
            self.document_id = hashlib.sha256(
                hash_input.encode()
            ).hexdigest()[:16]  # 16-char for collision resistance
        if not self.chunk_id:
            self.chunk_id = f"{self.document_id}_{self.chunk_index:04d}"

    @property
    def char_count(self) -> int:
        """Number of characters in content."""
        return len(self.content)

    @property
    def word_count(self) -> int:
        """Approximate word count."""
        return len(self.content.split())

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "content": self.content,
            "source_path": str(self.source_path),
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "char_count": self.char_count,
            "word_count": self.word_count,
            "metadata": self.metadata,
        }


class CorpusIngester:
    """Ingests and chunks documents from a corpus directory.

    Attributes:
        config: Distillation configuration
        supported_extensions: File extensions to process

    Example:
        >>> ingester = CorpusIngester(config)
        >>> for chunk in ingester.ingest():
        ...     print(f"Processing chunk {chunk.chunk_id}")
    """

    SUPPORTED_EXTENSIONS = {".md", ".txt", ".rst", ".adoc"}

    def __init__(self, config: DistillationConfig) -> None:
        self.config = config
        self._documents_processed = 0
        self._chunks_generated = 0

    def ingest(self) -> Iterator[DocumentChunk]:
        """Iterate over all chunks from all documents in corpus.

        Yields:
            DocumentChunk for each chunk of each document

        Raises:
            FileNotFoundError: If corpus directory doesn't exist
        """
        if not self.config.corpus_dir.exists():
            raise FileNotFoundError(
                f"Corpus directory not found: {self.config.corpus_dir}"
            )

        for path in self._find_documents():
            try:
                yield from self._process_document(path)
                self._documents_processed += 1
            except Exception as e:
                logger.warning(f"Failed to process {path}: {e}")

        logger.info(
            f"Ingested {self._documents_processed} documents, "
            f"generated {self._chunks_generated} chunks"
        )

    def _find_documents(self) -> Iterator[Path]:
        """Find all supported documents in corpus directory.

        DETERMINISM: Results are sorted for consistent processing order.
        ThinkingMachines [He2025] batch-invariance compliant.
        """
        all_files: list[Path] = []
        for ext in sorted(self.SUPPORTED_EXTENSIONS):
            all_files.extend(self.config.corpus_dir.rglob(f"*{ext}"))
        # Sort by path string for deterministic order across platforms
        yield from sorted(all_files, key=lambda p: str(p))

    def _read_file_with_fallback(self, path: Path) -> str:
        """Read file with encoding fallbacks.

        Tries multiple encodings to handle various file sources.
        Production Hardening: Graceful handling of encoding issues.

        Args:
            path: Path to the file

        Returns:
            File content as string

        Raises:
            UnicodeDecodeError: If all encodings fail
        """
        # Encodings to try in order of preference
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]

        last_error: Exception | None = None
        for encoding in encodings:
            try:
                content = path.read_text(encoding=encoding)
                if encoding != "utf-8":
                    logger.debug(f"Read {path.name} with {encoding} encoding")
                return content
            except UnicodeDecodeError as e:
                last_error = e
                continue

        # All encodings failed
        raise last_error or UnicodeDecodeError(
            "unknown", b"", 0, 1, f"Could not decode {path}"
        )

    def _process_document(self, path: Path) -> Iterator[DocumentChunk]:
        """Process a single document into chunks.

        Args:
            path: Path to the document

        Yields:
            DocumentChunk for each chunk
        """
        logger.debug(f"Processing document: {path}")

        content = self._read_file_with_fallback(path)
        metadata = self._extract_metadata(path, content)

        # Use semantic chunking for markdown, simple chunking for others
        if path.suffix == ".md":
            chunks = list(self._chunk_markdown(content))
        else:
            chunks = list(self._chunk_simple(content))

        total_chunks = len(chunks)

        for i, chunk_content in enumerate(chunks):
            chunk = DocumentChunk(
                content=chunk_content,
                source_path=path,
                chunk_index=i,
                total_chunks=total_chunks,
                metadata=metadata,
            )
            self._chunks_generated += 1
            yield chunk

    def _extract_metadata(self, path: Path, content: str) -> dict:
        """Extract metadata from document.

        Args:
            path: Document path
            content: Document content

        Returns:
            Metadata dictionary
        """
        metadata = {
            "filename": path.name,
            "extension": path.suffix,
            "relative_path": str(path.relative_to(self.config.corpus_dir)),
        }

        # Extract title from first h1 in markdown
        if path.suffix == ".md":
            h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if h1_match:
                metadata["title"] = h1_match.group(1).strip()

        # Extract frontmatter if present
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                frontmatter = content[3:end].strip()
                metadata["frontmatter"] = frontmatter

        return metadata

    def _chunk_markdown(self, content: str) -> Iterator[str]:
        """Chunk markdown by sections, respecting headers.

        Args:
            content: Full markdown content

        Yields:
            Chunked content strings
        """
        # Split by headers (h1, h2, h3)
        sections = re.split(r"\n(?=#{1,3}\s)", content)

        current_chunk = ""
        current_header = ""

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # Extract header from section
            header_match = re.match(r"^(#{1,3}\s+.+)$", section, re.MULTILINE)
            if header_match:
                current_header = header_match.group(1)

            # Check if adding this section exceeds chunk size
            combined = current_chunk + "\n\n" + section if current_chunk else section

            if len(combined) <= self.config.chunk_size:
                current_chunk = combined
            else:
                # Yield current chunk if non-empty
                if current_chunk.strip():
                    yield current_chunk.strip()

                # Handle section larger than chunk size
                if len(section) > self.config.chunk_size:
                    yield from self._chunk_large_section(section, current_header)
                    current_chunk = ""
                else:
                    current_chunk = section

        # Yield remaining content
        if current_chunk.strip():
            yield current_chunk.strip()

    def _chunk_large_section(
        self, section: str, header: str
    ) -> Iterator[str]:
        """Break up a section larger than chunk_size.

        Args:
            section: Section content
            header: Section header to prepend

        Yields:
            Chunked content strings
        """
        # Split by paragraphs
        paragraphs = re.split(r"\n\n+", section)

        current_chunk = header if header else ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            combined = current_chunk + "\n\n" + para if current_chunk else para

            if len(combined) <= self.config.chunk_size:
                current_chunk = combined
            else:
                if current_chunk.strip():
                    yield current_chunk.strip()

                # Handle paragraph larger than chunk size
                if len(para) > self.config.chunk_size:
                    yield from self._chunk_by_sentences(para, header)
                    current_chunk = header if header else ""
                else:
                    current_chunk = para

        if current_chunk.strip():
            yield current_chunk.strip()

    def _chunk_by_sentences(
        self, text: str, header: str
    ) -> Iterator[str]:
        """Break text by sentences when paragraphs are too large.

        Args:
            text: Text content
            header: Header to prepend

        Yields:
            Chunked content strings
        """
        # Simple sentence splitting
        sentences = re.split(r"(?<=[.!?])\s+", text)

        current_chunk = header if header else ""

        for sentence in sentences:
            combined = current_chunk + " " + sentence if current_chunk else sentence

            if len(combined) <= self.config.chunk_size:
                current_chunk = combined
            else:
                if current_chunk.strip():
                    yield current_chunk.strip()
                current_chunk = sentence

        if current_chunk.strip():
            yield current_chunk.strip()

    def _chunk_simple(self, content: str) -> Iterator[str]:
        """Simple fixed-size chunking with overlap.

        Args:
            content: Document content

        Yields:
            Chunked content strings
        """
        if len(content) <= self.config.chunk_size:
            yield content.strip()
            return

        start = 0
        while start < len(content):
            end = start + self.config.chunk_size

            # Try to break at paragraph or sentence boundary
            if end < len(content):
                # Look for paragraph break
                para_break = content.rfind("\n\n", start, end)
                if para_break > start + self.config.chunk_size // 2:
                    end = para_break

                # Otherwise look for sentence break
                elif (sentence_break := content.rfind(". ", start, end)) > start + self.config.chunk_size // 2:
                    end = sentence_break + 1

            chunk = content[start:end].strip()
            if chunk:
                yield chunk

            # Move start, accounting for overlap
            start = end - self.config.chunk_overlap
            if start >= len(content):
                break

    @property
    def stats(self) -> dict:
        """Get ingestion statistics."""
        return {
            "documents_processed": self._documents_processed,
            "chunks_generated": self._chunks_generated,
            "corpus_dir": str(self.config.corpus_dir),
        }
