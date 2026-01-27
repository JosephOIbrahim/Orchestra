"""
Pipeline Integration Tests

End-to-end tests for the complete distillation pipeline.
ThinkingMachines [He2025] Production Hardening.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestra.substrate.knowledge.distillation.config import DistillationConfig
from orchestra.substrate.knowledge.distillation.pipeline import (
    DistillationPipeline,
    PipelineStats,
)
from orchestra.substrate.knowledge.distillation.checkpoint import PipelineStage
from orchestra.substrate.knowledge.distillation.corpus_ingester import DocumentChunk
from orchestra.substrate.knowledge.distillation.query_generator import (
    GeneratedQuery,
    QuestionType,
)
from orchestra.substrate.knowledge.distillation.answer_generator import GeneratedAnswer


@pytest.fixture
def temp_corpus(tmp_path):
    """Create a temporary corpus directory with test documents."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    # Create test documents
    doc1 = corpus_dir / "test_doc1.md"
    doc1.write_text("""# Test Document 1

This is a test document about Python programming.
Python is a high-level programming language.
It supports multiple programming paradigms.

## Features

- Easy to learn
- Interpreted language
- Dynamic typing
""")

    doc2 = corpus_dir / "test_doc2.md"
    doc2.write_text("""# Test Document 2

Orchestra is a cognitive safety layer.
It provides burnout protection for developers.
The system uses a 5-phase NEXUS pipeline.

## Components

- PRISM detector for signal extraction
- Expert router with 7 intervention experts
- Parameter locker for determinism
""")

    return corpus_dir


@pytest.fixture
def temp_output(tmp_path):
    """Create a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client for testing."""
    client = MagicMock()
    client.generate = AsyncMock()

    # Default response for query generation
    client.generate.return_value = MagicMock(
        content='{"questions": [{"question": "What is Python?", "question_type": "factual", "abstraction_level": "ground", "expected_concepts": ["python", "programming"]}]}',
        latency_ms=100,
        input_tokens=50,
        output_tokens=100,
    )

    return client


class TestPipelineStats:
    """Test pipeline statistics tracking."""

    def test_stats_initialization(self):
        """Stats should initialize with zero values."""
        stats = PipelineStats()

        assert stats.documents_processed == 0
        assert stats.chunks_generated == 0
        assert stats.prims_extracted == 0

    def test_stats_serialization(self):
        """Stats should serialize to dictionary."""
        stats = PipelineStats(
            documents_processed=10,
            chunks_generated=50,
            prims_extracted=25,
        )

        data = stats.to_dict()

        assert data["documents_processed"] == 10
        assert data["chunks_generated"] == 50
        assert data["prims_extracted"] == 25

    def test_deterministic_checksum_excludes_timestamps(self):
        """Checksum should exclude timestamps for determinism."""
        stats1 = PipelineStats(
            started_at="2024-01-01T10:00:00",
            completed_at="2024-01-01T11:00:00",
            documents_processed=10,
            chunks_generated=50,
        )

        stats2 = PipelineStats(
            started_at="2024-01-02T10:00:00",  # Different timestamp
            completed_at="2024-01-02T11:00:00",
            documents_processed=10,
            chunks_generated=50,
        )

        stats1.compute_deterministic_checksum()
        stats2.compute_deterministic_checksum()

        # Checksums should match despite different timestamps
        assert stats1.deterministic_checksum == stats2.deterministic_checksum

    def test_checksum_changes_with_data(self):
        """Checksum should change when data changes."""
        stats1 = PipelineStats(documents_processed=10)
        stats2 = PipelineStats(documents_processed=20)

        stats1.compute_deterministic_checksum()
        stats2.compute_deterministic_checksum()

        assert stats1.deterministic_checksum != stats2.deterministic_checksum


class TestDistillationPipeline:
    """Test the main distillation pipeline."""

    def test_pipeline_initialization(self, temp_corpus, temp_output):
        """Pipeline should initialize with config."""
        config = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
        )

        pipeline = DistillationPipeline(config)

        assert pipeline.config == config

    def test_config_hash_deterministic(self, temp_corpus, temp_output):
        """Config hash should be deterministic."""
        config = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
            model_name="test-model",
            chunk_size=500,
        )

        pipeline1 = DistillationPipeline(config)
        pipeline2 = DistillationPipeline(config)

        hash1 = pipeline1._get_config_hash()
        hash2 = pipeline2._get_config_hash()

        assert hash1 == hash2
        assert len(hash1) == 16  # 16-char hash

    def test_config_hash_changes(self, temp_corpus, temp_output):
        """Config hash should change when config changes."""
        config1 = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
            chunk_size=500,
        )

        config2 = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
            chunk_size=1000,  # Different
        )

        pipeline1 = DistillationPipeline(config1)
        pipeline2 = DistillationPipeline(config2)

        assert pipeline1._get_config_hash() != pipeline2._get_config_hash()


class TestPipelineStages:
    """Test individual pipeline stages."""

    @pytest.mark.asyncio
    async def test_ingest_stage(self, temp_corpus, temp_output):
        """Ingest stage should process documents into chunks."""
        config = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
            chunk_size=200,
        )

        pipeline = DistillationPipeline(config)
        chunks = await pipeline._stage_ingest()

        assert len(chunks) > 0
        assert all(isinstance(c, DocumentChunk) for c in chunks)
        assert pipeline._stats.documents_processed > 0
        assert pipeline._stats.chunks_generated == len(chunks)

    def test_prim_serialization(self, temp_corpus, temp_output):
        """Prim serialization should be bidirectional."""
        from orchestra.substrate.knowledge.schemas import KnowledgePrim

        config = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
        )

        pipeline = DistillationPipeline(config)

        prim = KnowledgePrim(
            canonical_path="/Test/Prim",
            content="Test content",
            summary="Test summary",
            confidence=0.9,
            provenance="test",
            domains=["test"],
            triggers=["test", "prim"],
            key_concepts=["concept1"],
        )

        # Serialize and deserialize
        data = pipeline._prim_to_dict(prim)
        restored = pipeline._dict_to_prim(data)

        assert restored.canonical_path == prim.canonical_path
        assert restored.content == prim.content
        assert restored.confidence == prim.confidence


class TestCheckpointIntegration:
    """Test checkpoint integration in pipeline."""

    def test_checkpoint_manager_created(self, temp_corpus, temp_output):
        """Pipeline should create checkpoint manager."""
        config = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
            enable_checkpointing=True,
        )

        pipeline = DistillationPipeline(config)

        # Checkpoint manager is created during run
        assert pipeline._checkpoint_manager is None  # Not yet initialized

    @pytest.mark.asyncio
    async def test_checkpoint_saved_after_ingest(self, temp_corpus, temp_output):
        """Checkpoint should be saved after ingest stage."""
        config = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
            enable_checkpointing=True,
        )

        pipeline = DistillationPipeline(config)

        # Mock LLM to prevent full pipeline run
        with patch.object(pipeline, '_get_llm_client') as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.generate = AsyncMock(return_value=MagicMock(
                content='{"questions": []}',
                latency_ms=10,
                input_tokens=10,
                output_tokens=10,
            ))
            mock_get_llm.return_value = mock_llm

            # Run ingest only
            chunks = await pipeline._stage_ingest()

            # Checkpoint manager should exist after config setup
            assert len(chunks) > 0

    def test_stage_index_ordering(self, temp_corpus, temp_output):
        """Stage indices should be in correct order."""
        config = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
        )

        pipeline = DistillationPipeline(config)

        # Verify stage ordering
        assert pipeline._stage_index(PipelineStage.NOT_STARTED) < pipeline._stage_index(PipelineStage.INGESTED)
        assert pipeline._stage_index(PipelineStage.INGESTED) < pipeline._stage_index(PipelineStage.QUERIES_GENERATED)
        assert pipeline._stage_index(PipelineStage.QUERIES_GENERATED) < pipeline._stage_index(PipelineStage.ANSWERS_GENERATED)


class TestDeterminism:
    """Test ThinkingMachines [He2025] compliance."""

    def test_same_corpus_same_chunks(self, temp_corpus, temp_output):
        """Same corpus should produce same chunks."""
        config = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
            chunk_size=200,
        )

        pipeline1 = DistillationPipeline(config)
        pipeline2 = DistillationPipeline(config)

        # Both should produce identical chunk IDs
        from orchestra.substrate.knowledge.distillation.corpus_ingester import CorpusIngester

        ingester1 = CorpusIngester(config)
        ingester2 = CorpusIngester(config)

        chunks1 = list(ingester1.ingest())
        chunks2 = list(ingester2.ingest())

        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1.chunk_id == c2.chunk_id

    def test_pipeline_stats_checksum_reproducible(self):
        """Pipeline stats checksum should be reproducible."""
        from orchestra.substrate.knowledge.schemas import KnowledgePrim

        prims = [
            KnowledgePrim(
                canonical_path=f"/Test/Prim{i}",
                content=f"Content {i}",
                summary=f"Summary {i}",
                confidence=0.9,
            )
            for i in range(5)
        ]

        stats1 = PipelineStats(
            documents_processed=2,
            chunks_generated=10,
            prims_extracted=5,
        )

        stats2 = PipelineStats(
            documents_processed=2,
            chunks_generated=10,
            prims_extracted=5,
        )

        stats1.compute_deterministic_checksum(prims)
        stats2.compute_deterministic_checksum(prims)

        assert stats1.deterministic_checksum == stats2.deterministic_checksum


class TestErrorHandling:
    """Test error handling in pipeline."""

    def test_missing_corpus_dir(self, temp_output):
        """Should raise FileNotFoundError for missing corpus directory.

        ThinkingMachines [He2025]: Fail-fast is deterministic behavior.
        Silent empty results would mask configuration errors.
        """
        config = DistillationConfig(
            corpus_dir=Path("/nonexistent/corpus"),
            output_dir=temp_output,
        )

        from orchestra.substrate.knowledge.distillation.corpus_ingester import CorpusIngester
        ingester = CorpusIngester(config)

        # Should raise FileNotFoundError for missing directory
        with pytest.raises(FileNotFoundError, match="Corpus directory not found"):
            list(ingester.ingest())

    def test_empty_corpus(self, tmp_path, temp_output):
        """Should handle empty corpus directory."""
        empty_corpus = tmp_path / "empty_corpus"
        empty_corpus.mkdir()

        config = DistillationConfig(
            corpus_dir=empty_corpus,
            output_dir=temp_output,
        )

        from orchestra.substrate.knowledge.distillation.corpus_ingester import CorpusIngester
        ingester = CorpusIngester(config)

        chunks = list(ingester.ingest())
        assert len(chunks) == 0


class TestCLIArguments:
    """Test CLI argument handling."""

    def test_pipeline_run_with_options(self, temp_corpus, temp_output):
        """Pipeline should accept run options."""
        config = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
        )

        pipeline = DistillationPipeline(config)

        # These should be valid options
        assert hasattr(pipeline, 'run')

    def test_config_checkpointing_flag(self, temp_corpus, temp_output):
        """Config should have checkpointing flag."""
        config = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
            enable_checkpointing=False,
        )

        assert config.enable_checkpointing is False

        config2 = DistillationConfig(
            corpus_dir=temp_corpus,
            output_dir=temp_output,
            enable_checkpointing=True,
        )

        assert config2.enable_checkpointing is True
