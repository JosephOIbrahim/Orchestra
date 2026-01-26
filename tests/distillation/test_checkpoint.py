"""
Checkpoint Tests

Tests for pipeline checkpointing and resumability.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestra.substrate.knowledge.distillation.checkpoint import (
    CheckpointManager,
    PipelineCheckpoint,
    PipelineStage,
    StageData,
    create_checkpoint_manager,
)


class TestPipelineStage:
    """Test pipeline stage enumeration."""

    def test_stage_order(self):
        """Stages should be in correct execution order."""
        from orchestra.substrate.knowledge.distillation.checkpoint import STAGE_ORDER

        assert STAGE_ORDER[0] == PipelineStage.NOT_STARTED
        assert STAGE_ORDER[-1] == PipelineStage.COMPLETED
        assert PipelineStage.INGESTED in STAGE_ORDER
        assert STAGE_ORDER.index(PipelineStage.INGESTED) < STAGE_ORDER.index(PipelineStage.QUERIES_GENERATED)


class TestPipelineCheckpoint:
    """Test checkpoint data structure."""

    def test_checkpoint_serialization(self):
        """Checkpoint should serialize to dict and back."""
        checkpoint = PipelineCheckpoint(
            run_id="test-run-123",
            created_at="2024-01-01T10:00:00",
            updated_at="2024-01-01T11:00:00",
            current_stage="ingested",
            config_hash="abc123",
            corpus_dir="/test/corpus",
            output_dir="/test/output",
        )

        data = checkpoint.to_dict()
        restored = PipelineCheckpoint.from_dict(data)

        assert restored.run_id == checkpoint.run_id
        assert restored.current_stage == checkpoint.current_stage
        assert restored.config_hash == checkpoint.config_hash

    def test_checkpoint_with_stages(self):
        """Checkpoint with stage data should serialize correctly."""
        checkpoint = PipelineCheckpoint(
            run_id="test-run",
            current_stage="queries_generated",
        )

        checkpoint.stages["ingested"] = StageData(
            stage="ingested",
            completed_at="2024-01-01T10:00:00",
            item_count=50,
            metadata={"documents": 10},
        )

        data = checkpoint.to_dict()
        restored = PipelineCheckpoint.from_dict(data)

        assert "ingested" in restored.stages
        assert restored.stages["ingested"].item_count == 50


class TestCheckpointManager:
    """Test checkpoint manager functionality."""

    def test_initialize_creates_checkpoint(self, temp_dir):
        """Initialize should create checkpoint file."""
        manager = CheckpointManager(temp_dir / "checkpoints")

        checkpoint = manager.initialize(
            run_id="test-123",
            config_hash="hash123",
            corpus_dir=Path("/corpus"),
            output_dir=Path("/output"),
        )

        assert manager.checkpoint_file.exists()
        assert checkpoint.run_id == "test-123"

    def test_load_checkpoint(self, temp_dir):
        """Should load existing checkpoint."""
        manager = CheckpointManager(temp_dir / "checkpoints")

        # Initialize first
        manager.initialize(
            run_id="test-123",
            config_hash="hash123",
            corpus_dir=Path("/corpus"),
            output_dir=Path("/output"),
        )

        # Load in new manager
        manager2 = CheckpointManager(temp_dir / "checkpoints")
        checkpoint = manager2.load_checkpoint()

        assert checkpoint is not None
        assert checkpoint.run_id == "test-123"

    def test_load_missing_checkpoint(self, temp_dir):
        """Loading non-existent checkpoint should return None."""
        manager = CheckpointManager(temp_dir / "checkpoints")

        checkpoint = manager.load_checkpoint()

        assert checkpoint is None

    def test_save_stage(self, temp_dir):
        """Should save stage completion."""
        manager = CheckpointManager(temp_dir / "checkpoints")
        manager.initialize(
            run_id="test-123",
            config_hash="hash123",
            corpus_dir=Path("/corpus"),
            output_dir=Path("/output"),
        )

        manager.save_stage(
            PipelineStage.INGESTED,
            item_count=50,
            metadata={"documents": 10},
        )

        # Reload and verify
        manager2 = CheckpointManager(temp_dir / "checkpoints")
        checkpoint = manager2.load_checkpoint()

        assert checkpoint.current_stage == "ingested"
        assert "ingested" in checkpoint.stages
        assert checkpoint.stages["ingested"].item_count == 50

    def test_save_stage_with_data(self, temp_dir):
        """Should save stage data to separate file."""
        manager = CheckpointManager(temp_dir / "checkpoints")
        manager.initialize(
            run_id="test-123",
            config_hash="hash123",
            corpus_dir=Path("/corpus"),
            output_dir=Path("/output"),
        )

        stage_data = {"chunks": [{"id": 1}, {"id": 2}]}
        manager.save_stage(
            PipelineStage.INGESTED,
            item_count=2,
            data=stage_data,
        )

        # Should have created data file
        assert manager.data_dir.exists()
        data_file = manager.data_dir / "ingested.json"
        assert data_file.exists()

        # Load and verify data
        loaded_data = manager.load_stage_data(PipelineStage.INGESTED)
        assert loaded_data == stage_data

    def test_can_resume_from_completed_stage(self, temp_dir):
        """Should be able to resume from completed stage."""
        manager = CheckpointManager(temp_dir / "checkpoints")
        manager.initialize(
            run_id="test-123",
            config_hash="hash123",
            corpus_dir=Path("/corpus"),
            output_dir=Path("/output"),
        )

        manager.save_stage(PipelineStage.INGESTED, item_count=50)

        assert manager.can_resume_from(PipelineStage.INGESTED)
        assert not manager.can_resume_from(PipelineStage.QUERIES_GENERATED)

    def test_get_resume_stage(self, temp_dir):
        """Should return next stage after completed one."""
        manager = CheckpointManager(temp_dir / "checkpoints")
        manager.initialize(
            run_id="test-123",
            config_hash="hash123",
            corpus_dir=Path("/corpus"),
            output_dir=Path("/output"),
        )

        manager.save_stage(PipelineStage.INGESTED, item_count=50)

        resume_stage = manager.get_resume_stage()

        assert resume_stage == PipelineStage.QUERIES_GENERATED

    def test_clear_checkpoint(self, temp_dir):
        """Should clear all checkpoint data."""
        manager = CheckpointManager(temp_dir / "checkpoints")
        manager.initialize(
            run_id="test-123",
            config_hash="hash123",
            corpus_dir=Path("/corpus"),
            output_dir=Path("/output"),
        )

        manager.save_stage(PipelineStage.INGESTED, item_count=50)

        manager.clear()

        assert not manager.checkpoint_file.exists()
        assert not manager.checkpoint_dir.exists()

    def test_disabled_manager(self, temp_dir):
        """Disabled manager should be a no-op."""
        manager = CheckpointManager(temp_dir / "checkpoints", enabled=False)

        checkpoint = manager.initialize(
            run_id="test-123",
            config_hash="hash123",
            corpus_dir=Path("/corpus"),
            output_dir=Path("/output"),
        )

        # Should return empty checkpoint
        assert checkpoint.run_id == ""

        # File should not be created
        assert not manager.checkpoint_file.exists()

    def test_atomic_write(self, temp_dir):
        """Checkpoint writes should be atomic."""
        manager = CheckpointManager(temp_dir / "checkpoints")
        manager.initialize(
            run_id="test-123",
            config_hash="hash123",
            corpus_dir=Path("/corpus"),
            output_dir=Path("/output"),
        )

        # Write multiple stages
        for stage in [PipelineStage.INGESTED, PipelineStage.QUERIES_GENERATED]:
            manager.save_stage(stage, item_count=50)

        # File should be valid JSON
        with open(manager.checkpoint_file) as f:
            data = json.load(f)

        assert data["current_stage"] == "queries_generated"


class TestCreateCheckpointManager:
    """Test the factory function."""

    def test_creates_in_checkpoints_subdir(self, temp_dir):
        """Should create manager with .checkpoints subdirectory."""
        manager = create_checkpoint_manager(temp_dir)

        assert manager.checkpoint_dir == temp_dir / ".checkpoints"

    def test_respects_enabled_flag(self, temp_dir):
        """Should respect enabled flag."""
        manager = create_checkpoint_manager(temp_dir, enabled=False)

        assert not manager.enabled
