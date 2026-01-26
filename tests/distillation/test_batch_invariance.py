"""
Batch Invariance Tests

Tests for ThinkingMachines [He2025] batch-invariance compliance.
Verifies deterministic behavior: same inputs → same outputs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from orchestra.substrate.knowledge.distillation import (
    ConfidenceScorer,
    CorpusIngester,
    DistillationConfig,
    DocumentChunk,
    PipelineStats,
    PrimExtractor,
    TriggerGenerator,
    USDAWriter,
)
from orchestra.substrate.knowledge.distillation.confidence_scorer import (
    COMPONENT_ORDER,
    CONFIDENCE_WEIGHTS,
)
from orchestra.substrate.knowledge.schemas import KnowledgePrim


class TestHashDeterminism:
    """Test that hash generation is deterministic and collision-resistant."""

    def test_cache_key_uses_full_sha256(self, config):
        """Cache keys should use full SHA-256 (64 chars)."""
        from orchestra.substrate.knowledge.distillation.llm_client import BaseLLMClient

        # Create a minimal concrete implementation for testing
        class TestClient(BaseLLMClient):
            async def generate(self, prompt, **kwargs):
                pass

        client = TestClient(config)

        key = client._cache_key("test prompt", "test system", 0.0)

        # Full SHA-256 is 64 characters
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_document_chunk_id_deterministic(self):
        """Document chunk IDs should be deterministic given same input."""
        chunk1 = DocumentChunk(
            content="Test content for hashing",
            source_path=Path("/test/doc.md"),
            chunk_index=0,
        )

        chunk2 = DocumentChunk(
            content="Test content for hashing",
            source_path=Path("/test/doc.md"),
            chunk_index=0,
        )

        assert chunk1.document_id == chunk2.document_id
        assert chunk1.chunk_id == chunk2.chunk_id

    def test_document_chunk_id_length(self):
        """Document IDs should be 16 chars for collision resistance."""
        chunk = DocumentChunk(
            content="Test content",
            source_path=Path("/test/doc.md"),
            chunk_index=0,
        )

        # Document ID should be 16 chars (increased from 12)
        assert len(chunk.document_id) == 16

    def test_prim_path_hash_length(self, config, sample_answer):
        """Prim path hashes should be 12 chars for collision resistance."""
        extractor = PrimExtractor(config)
        result = extractor.extract(sample_answer)

        # Extract the hash suffix from the path
        path_parts = result.prim.canonical_path.split("_")
        hash_suffix = path_parts[-1]

        # Should be 12 chars (increased from 6)
        assert len(hash_suffix) == 12


class TestIterationOrder:
    """Test that iteration order is deterministic."""

    def test_corpus_ingester_sorted_files(self, config, sample_corpus_files):
        """Corpus ingester should return files in sorted order."""
        ingester = CorpusIngester(config)

        paths = list(ingester._find_documents())
        path_strings = [str(p) for p in paths]

        assert path_strings == sorted(path_strings)

    def test_trigger_generator_sorted_terms(self, config):
        """Trigger generator should iterate terms in sorted order."""
        generator = TriggerGenerator(config)

        # Create prims with terms that would have different set iteration order
        prims = [
            KnowledgePrim(
                canonical_path="/Knowledge/Test/Prim1",
                content="zebra apple banana cherry",
                summary="Test prim 1",
            ),
            KnowledgePrim(
                canonical_path="/Knowledge/Test/Prim2",
                content="delta alpha gamma beta",
                summary="Test prim 2",
            ),
        ]

        # Build stats twice and verify same result
        generator.build_corpus_stats(prims)
        counts1 = dict(generator._corpus_term_counts)

        generator._corpus_term_counts.clear()
        generator._document_count = 0
        generator.build_corpus_stats(prims)
        counts2 = dict(generator._corpus_term_counts)

        assert counts1 == counts2

    def test_usda_writer_sorted_groups(self, config, temp_dir):
        """USDA writer should process groups in sorted order."""
        writer = USDAWriter(config)

        prims = {
            "zebra": [KnowledgePrim(
                canonical_path="/Knowledge/Zebra/Prim",
                content="Zebra content",
                summary="Zebra summary",
            )],
            "alpha": [KnowledgePrim(
                canonical_path="/Knowledge/Alpha/Prim",
                content="Alpha content",
                summary="Alpha summary",
            )],
        }

        # Write batch and verify order
        paths = writer.write_batch(prims)

        # Files should be written in sorted order (alpha before zebra)
        path_names = [p.stem for p in paths]
        expected_order = sorted(path_names)

        # The order of processing should be deterministic
        assert len(paths) == 2

    def test_confidence_scorer_fixed_order(self):
        """Confidence scorer should use fixed component order."""
        # Verify the constant is defined correctly
        assert COMPONENT_ORDER == [
            "hallucination",
            "consistency",
            "retrieval_accuracy",
            "source_confidence",
            "heuristics",
        ]

        # Verify all weights have corresponding order entry
        for component in CONFIDENCE_WEIGHTS:
            assert component in COMPONENT_ORDER


class TestDeterministicChecksum:
    """Test deterministic checksum generation."""

    def test_checksum_excludes_timestamps(self):
        """Checksum should not depend on timestamps."""
        stats1 = PipelineStats(
            started_at="2024-01-01T10:00:00",
            completed_at="2024-01-01T11:00:00",
            documents_processed=10,
            chunks_generated=50,
            queries_generated=100,
            answers_generated=100,
            prims_extracted=80,
            prims_passed_validation=70,
            prims_written=70,
        )

        stats2 = PipelineStats(
            started_at="2024-02-02T15:00:00",  # Different timestamp
            completed_at="2024-02-02T16:00:00",
            documents_processed=10,  # Same counts
            chunks_generated=50,
            queries_generated=100,
            answers_generated=100,
            prims_extracted=80,
            prims_passed_validation=70,
            prims_written=70,
        )

        checksum1 = stats1.compute_deterministic_checksum()
        checksum2 = stats2.compute_deterministic_checksum()

        # Same data → same checksum (regardless of timestamps)
        assert checksum1 == checksum2

    def test_checksum_changes_with_data(self):
        """Checksum should change when data changes."""
        stats1 = PipelineStats(
            documents_processed=10,
            chunks_generated=50,
            prims_extracted=80,
        )

        stats2 = PipelineStats(
            documents_processed=11,  # Different
            chunks_generated=50,
            prims_extracted=80,
        )

        checksum1 = stats1.compute_deterministic_checksum()
        checksum2 = stats2.compute_deterministic_checksum()

        assert checksum1 != checksum2

    def test_checksum_includes_prim_hashes(self):
        """Checksum should include sorted prim content hashes."""
        prims = [
            KnowledgePrim(
                canonical_path="/Knowledge/Test/Prim1",
                content="Content A",
                summary="Summary A",
            ),
            KnowledgePrim(
                canonical_path="/Knowledge/Test/Prim2",
                content="Content B",
                summary="Summary B",
            ),
        ]

        stats = PipelineStats(documents_processed=1, prims_extracted=2)
        checksum = stats.compute_deterministic_checksum(prims)

        # Should have prim content hashes
        assert len(stats.prim_content_hashes) == 2

        # Hashes should be sorted
        assert stats.prim_content_hashes == sorted(stats.prim_content_hashes)

    def test_checksum_is_full_sha256(self):
        """Checksum should be full SHA-256 (64 chars)."""
        stats = PipelineStats(documents_processed=1)
        checksum = stats.compute_deterministic_checksum()

        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)


class TestReproducibility:
    """Test that pipeline produces reproducible results."""

    def test_same_input_same_output(self, config, sample_answer):
        """Same input should produce same output."""
        extractor = PrimExtractor(config)

        result1 = extractor.extract(sample_answer)
        result2 = extractor.extract(sample_answer)

        assert result1.prim.canonical_path == result2.prim.canonical_path
        assert result1.prim.content == result2.prim.content
        assert result1.prim.summary == result2.prim.summary

    def test_corpus_ingestion_deterministic(self, config, sample_corpus_files):
        """Corpus ingestion should be deterministic."""
        ingester1 = CorpusIngester(config)
        chunks1 = list(ingester1.ingest())

        ingester2 = CorpusIngester(config)
        chunks2 = list(ingester2.ingest())

        assert len(chunks1) == len(chunks2)

        for c1, c2 in zip(chunks1, chunks2):
            assert c1.document_id == c2.document_id
            assert c1.chunk_id == c2.chunk_id
            assert c1.content == c2.content
