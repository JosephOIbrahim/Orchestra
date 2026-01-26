"""
Checkpoint Manager

Pipeline resumability through stage-level checkpointing.
Enables recovery from failures without reprocessing completed stages.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
ThinkingMachines [He2025] Production Hardening.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .errors import CheckpointError, ErrorContext

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Pipeline stages for checkpointing."""

    NOT_STARTED = "not_started"
    INGESTED = "ingested"
    QUERIES_GENERATED = "queries_generated"
    ANSWERS_GENERATED = "answers_generated"
    PRIMS_EXTRACTED = "prims_extracted"
    TRIGGERS_GENERATED = "triggers_generated"
    VALIDATED = "validated"
    SCORED = "scored"
    WRITTEN = "written"
    BENCHMARKED = "benchmarked"
    COMPLETED = "completed"


# Stage order for progression tracking
STAGE_ORDER = [
    PipelineStage.NOT_STARTED,
    PipelineStage.INGESTED,
    PipelineStage.QUERIES_GENERATED,
    PipelineStage.ANSWERS_GENERATED,
    PipelineStage.PRIMS_EXTRACTED,
    PipelineStage.TRIGGERS_GENERATED,
    PipelineStage.VALIDATED,
    PipelineStage.SCORED,
    PipelineStage.WRITTEN,
    PipelineStage.BENCHMARKED,
    PipelineStage.COMPLETED,
]


@dataclass
class StageData:
    """Data stored for a completed stage."""

    stage: str
    completed_at: str
    item_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    data_file: str | None = None  # Path to serialized data


@dataclass
class PipelineCheckpoint:
    """Complete pipeline checkpoint state.

    Attributes:
        run_id: Unique identifier for this pipeline run
        created_at: When checkpoint was first created
        updated_at: When checkpoint was last updated
        current_stage: Current/completed stage
        config_hash: Hash of config for compatibility check
        stages: Completed stage data
        corpus_dir: Source corpus directory
        output_dir: Output directory
    """

    run_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    current_stage: str = "not_started"
    config_hash: str = ""
    stages: dict[str, StageData] = field(default_factory=dict)
    corpus_dir: str = ""
    output_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_stage": self.current_stage,
            "config_hash": self.config_hash,
            "corpus_dir": self.corpus_dir,
            "output_dir": self.output_dir,
            "stages": {
                name: asdict(data) for name, data in self.stages.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineCheckpoint:
        """Create from dictionary."""
        stages = {}
        for name, stage_data in data.get("stages", {}).items():
            stages[name] = StageData(
                stage=stage_data.get("stage", name),
                completed_at=stage_data.get("completed_at", ""),
                item_count=stage_data.get("item_count", 0),
                metadata=stage_data.get("metadata", {}),
                data_file=stage_data.get("data_file"),
            )

        return cls(
            run_id=data.get("run_id", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            current_stage=data.get("current_stage", "not_started"),
            config_hash=data.get("config_hash", ""),
            corpus_dir=data.get("corpus_dir", ""),
            output_dir=data.get("output_dir", ""),
            stages=stages,
        )


class CheckpointManager:
    """Manages pipeline checkpoints for resumability.

    Provides atomic save/load of checkpoint state and
    stage data serialization.

    Attributes:
        checkpoint_dir: Directory for checkpoint files
        enabled: Whether checkpointing is enabled
    """

    CHECKPOINT_FILE = "checkpoint.json"
    DATA_DIR = "stage_data"

    def __init__(
        self,
        checkpoint_dir: Path,
        *,
        enabled: bool = True,
    ) -> None:
        self.checkpoint_dir = Path(checkpoint_dir)
        self.enabled = enabled
        self._current: PipelineCheckpoint | None = None

    @property
    def checkpoint_file(self) -> Path:
        """Path to main checkpoint file."""
        return self.checkpoint_dir / self.CHECKPOINT_FILE

    @property
    def data_dir(self) -> Path:
        """Path to stage data directory."""
        return self.checkpoint_dir / self.DATA_DIR

    def initialize(
        self,
        run_id: str,
        config_hash: str,
        corpus_dir: Path,
        output_dir: Path,
    ) -> PipelineCheckpoint:
        """Initialize a new checkpoint for a pipeline run.

        Args:
            run_id: Unique run identifier
            config_hash: Hash of pipeline config
            corpus_dir: Source corpus directory
            output_dir: Output directory

        Returns:
            New PipelineCheckpoint
        """
        if not self.enabled:
            return PipelineCheckpoint()

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat()
        self._current = PipelineCheckpoint(
            run_id=run_id,
            created_at=now,
            updated_at=now,
            current_stage=PipelineStage.NOT_STARTED.value,
            config_hash=config_hash,
            corpus_dir=str(corpus_dir),
            output_dir=str(output_dir),
        )

        self._save_checkpoint()
        logger.info(f"Initialized checkpoint: {run_id}")

        return self._current

    def load_checkpoint(self) -> PipelineCheckpoint | None:
        """Load existing checkpoint if available.

        Returns:
            Loaded checkpoint or None if not found
        """
        if not self.enabled:
            return None

        if not self.checkpoint_file.exists():
            return None

        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._current = PipelineCheckpoint.from_dict(data)
            logger.info(
                f"Loaded checkpoint: {self._current.run_id} "
                f"at stage {self._current.current_stage}"
            )
            return self._current

        except Exception as e:
            raise CheckpointError(
                f"Failed to load checkpoint: {e}",
                checkpoint_path=str(self.checkpoint_file),
                cause=e,
            )

    def save_stage(
        self,
        stage: PipelineStage,
        item_count: int,
        data: Any = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save completion of a pipeline stage.

        Args:
            stage: Completed stage
            item_count: Number of items processed
            data: Optional data to serialize for resumption
            metadata: Optional stage metadata
        """
        if not self.enabled or not self._current:
            return

        now = datetime.now().isoformat()

        # Serialize data if provided
        data_file = None
        if data is not None:
            data_file = self._save_stage_data(stage, data)

        # Record stage completion
        stage_data = StageData(
            stage=stage.value,
            completed_at=now,
            item_count=item_count,
            metadata=metadata or {},
            data_file=data_file,
        )

        self._current.stages[stage.value] = stage_data
        self._current.current_stage = stage.value
        self._current.updated_at = now

        self._save_checkpoint()
        logger.debug(f"Saved checkpoint: stage={stage.value}, items={item_count}")

    def load_stage_data(self, stage: PipelineStage) -> Any | None:
        """Load serialized data for a stage.

        Args:
            stage: Stage to load data for

        Returns:
            Deserialized data or None if not found
        """
        if not self.enabled or not self._current:
            return None

        stage_info = self._current.stages.get(stage.value)
        if not stage_info or not stage_info.data_file:
            return None

        data_path = Path(stage_info.data_file)
        if not data_path.exists():
            return None

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load stage data for {stage.value}: {e}")
            return None

    def can_resume_from(self, stage: PipelineStage) -> bool:
        """Check if pipeline can resume from a stage.

        Args:
            stage: Stage to check

        Returns:
            True if stage is completed and has data
        """
        if not self.enabled or not self._current:
            return False

        # Check if stage is completed
        if stage.value not in self._current.stages:
            return False

        # Check if data file exists (if expected)
        stage_info = self._current.stages[stage.value]
        if stage_info.data_file:
            return Path(stage_info.data_file).exists()

        return True

    def get_resume_stage(self) -> PipelineStage | None:
        """Get the stage to resume from.

        Returns:
            Stage to resume from, or None if should start fresh
        """
        if not self.enabled or not self._current:
            return None

        try:
            current = PipelineStage(self._current.current_stage)
            if current == PipelineStage.NOT_STARTED:
                return None

            # Find the index of current stage
            current_idx = STAGE_ORDER.index(current)

            # Return the next stage after the completed one
            if current_idx < len(STAGE_ORDER) - 1:
                return STAGE_ORDER[current_idx + 1]

            return None  # Already completed

        except ValueError:
            return None

    def clear(self) -> None:
        """Clear all checkpoint data."""
        if not self.enabled:
            return

        try:
            if self.checkpoint_dir.exists():
                shutil.rmtree(self.checkpoint_dir)
            self._current = None
            logger.info("Cleared checkpoint data")
        except Exception as e:
            logger.warning(f"Failed to clear checkpoint: {e}")

    def _save_checkpoint(self) -> None:
        """Atomically save checkpoint to disk."""
        if not self._current:
            return

        try:
            # Write to temp file first (atomic)
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.checkpoint_dir,
                suffix=".json",
                delete=False,
                encoding="utf-8",
            ) as f:
                json.dump(self._current.to_dict(), f, indent=2)
                temp_path = Path(f.name)

            # Atomic rename
            temp_path.replace(self.checkpoint_file)

        except Exception as e:
            raise CheckpointError(
                f"Failed to save checkpoint: {e}",
                checkpoint_path=str(self.checkpoint_file),
                cause=e,
            )

    def _save_stage_data(self, stage: PipelineStage, data: Any) -> str:
        """Save stage data to file.

        Args:
            stage: Stage being saved
            data: Data to serialize

        Returns:
            Path to saved data file
        """
        data_file = self.data_dir / f"{stage.value}.json"

        try:
            # Write atomically
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.data_dir,
                suffix=".json",
                delete=False,
                encoding="utf-8",
            ) as f:
                json.dump(data, f, indent=2, default=str)
                temp_path = Path(f.name)

            temp_path.replace(data_file)
            return str(data_file)

        except Exception as e:
            logger.warning(f"Failed to save stage data for {stage.value}: {e}")
            return ""


def create_checkpoint_manager(
    output_dir: Path,
    *,
    enabled: bool = True,
) -> CheckpointManager:
    """Create a checkpoint manager for a pipeline run.

    Args:
        output_dir: Pipeline output directory
        enabled: Whether checkpointing is enabled

    Returns:
        Configured CheckpointManager
    """
    checkpoint_dir = output_dir / ".checkpoints"
    return CheckpointManager(checkpoint_dir, enabled=enabled)
