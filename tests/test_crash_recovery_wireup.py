"""Tests that crash recovery is actually wired into orchestrator startup.

Before this fix, recover_from_crash() existed and was exported, but
FrameworkOrchestrator never called it — every prior crash was silently
abandoned. This test guards against the silent-failure regression by
constructing an orchestrator with a pre-seeded interrupted checkpoint
and verifying the orchestrator surfaces it.
"""

import asyncio
from pathlib import Path

import pytest

from orchestra.checkpoint import OrchestrationCheckpoint
from orchestra.config import OrchestratorConfig
from orchestra.framework_orchestrator import FrameworkOrchestrator


@pytest.fixture
def ckpt_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a fresh checkpoint directory and route config to it."""
    d = tmp_path / "checkpoints"
    d.mkdir()
    monkeypatch.setenv("FO_CHECKPOINT_DIR", str(d))
    return d


def _seed_interrupted_checkpoint(checkpoint_dir: Path) -> str:
    """Write an in-progress checkpoint to disk, simulating a prior crash."""
    cp = OrchestrationCheckpoint(checkpoint_dir=checkpoint_dir)

    async def _start():
        return await cp.start_orchestration(
            task="prior task that crashed mid-flight",
            iteration=1,
            context={},
        )

    return asyncio.run(_start())


class TestCrashRecoveryWireup:
    def test_orchestrator_records_interrupted_on_startup(self, ckpt_dir: Path):
        cp_id = _seed_interrupted_checkpoint(ckpt_dir)
        assert cp_id

        cfg = OrchestratorConfig()
        cfg.checkpoint_enabled = True

        orch = FrameworkOrchestrator(config=cfg)
        # The wire-up must populate startup_interrupted with the seeded
        # checkpoint. Before the fix this attribute didn't even exist.
        assert hasattr(orch, "startup_interrupted")
        assert any(
            cp.checkpoint_id == cp_id for cp in orch.startup_interrupted
        ), "interrupted checkpoint not detected at startup"

    def test_orchestrator_with_no_prior_interruptions(self, ckpt_dir: Path):
        cfg = OrchestratorConfig()
        cfg.checkpoint_enabled = True

        orch = FrameworkOrchestrator(config=cfg)
        assert orch.startup_interrupted == []

    def test_orchestrator_with_checkpointing_disabled(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        # Even with no env override, disabling checkpointing must yield
        # a defined startup_interrupted attribute (empty list) so callers
        # can rely on it.
        cfg = OrchestratorConfig()
        cfg.checkpoint_enabled = False

        orch = FrameworkOrchestrator(config=cfg)
        assert orch.startup_interrupted == []
        assert orch.checkpoint is None
