"""
BCM Integration Adapter for Orchestra Pipeline
===============================================

Provides the adapter layer for wiring BCM trail data into Orchestra's
8-phase NEXUS pipeline.

Functions:
- load_trail() / save_trail() - Persistence
- integrate_with_pipeline() - Wire trail into components
- collect_feedback() - Gather outcome data for trail updates

ThinkingMachines [He2025] Compliance:
- Trail loading happens BEFORE processing (Phase 0)
- Trail updates are QUEUED during processing
- Updates applied AFTER processing complete (batch-invariant)

Author: [User] + Claude
Date: 2026-01-31
Version: 0.1.0
"""

import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, TYPE_CHECKING

from .bcm_trail import OrchestraTrail
from .file_ops import atomic_write_json, safe_read_json

if TYPE_CHECKING:
    from .cognitive_orchestrator import CognitiveOrchestrator

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

BCM_STATE_DIR = Path.home() / ".orchestra" / "bcm"
DEFAULT_TRAIL_FILE = "trail.json"


# =============================================================================
# Persistence Functions
# =============================================================================

def load_trail(session_id: str = "default") -> OrchestraTrail:
    """
    Load trail from persistent storage.

    Creates fresh trail if none exists. Applies decay based on
    time since last update.

    Args:
        session_id: Session identifier for trail file

    Returns:
        OrchestraTrail instance
    """
    trail_path = BCM_STATE_DIR / f"trail_{session_id}.json"

    if not trail_path.exists():
        logger.info(f"No existing trail at {trail_path}, creating fresh")
        return OrchestraTrail()

    try:
        data = safe_read_json(trail_path)
        if data:
            trail = OrchestraTrail.from_dict(data)

            # Apply decay since last update
            elapsed_minutes = (time.time() - trail.last_update) / 60.0
            if elapsed_minutes > 0:
                trail.apply_session_decay(elapsed_minutes)
                logger.info(f"Applied {elapsed_minutes:.1f} min decay to trail")

            logger.info(f"Loaded trail: {trail.checksum()}")
            return trail
    except Exception as e:
        logger.error(f"Failed to load trail from {trail_path}: {e}")

    return OrchestraTrail()


def save_trail(trail: OrchestraTrail, session_id: str = "default") -> bool:
    """
    Persist trail to storage.

    Uses atomic writes to prevent corruption.

    Args:
        trail: OrchestraTrail to save
        session_id: Session identifier for trail file

    Returns:
        True if save successful, False otherwise
    """
    BCM_STATE_DIR.mkdir(parents=True, exist_ok=True)
    trail_path = BCM_STATE_DIR / f"trail_{session_id}.json"

    try:
        atomic_write_json(trail_path, trail.to_dict())
        logger.info(f"Saved trail to {trail_path}: {trail.checksum()}")
        return True
    except Exception as e:
        logger.error(f"Failed to save trail to {trail_path}: {e}")
        return False


def get_trail_path(session_id: str = "default") -> Path:
    """Get path to trail file."""
    return BCM_STATE_DIR / f"trail_{session_id}.json"


def trail_exists(session_id: str = "default") -> bool:
    """Check if trail file exists."""
    return get_trail_path(session_id).exists()


# =============================================================================
# Pipeline Integration
# =============================================================================

class BCMPipelineAdapter:
    """
    Adapter for integrating BCM trails into Orchestra pipeline.

    Provides a clean interface for:
    - Loading trail at session start
    - Querying trail during routing (confidence metadata)
    - Recording outcomes for learning
    - Flushing updates at session end

    ThinkingMachines Compliance:
    - All trail queries are read-only during processing
    - Updates queued, not applied during message handling
    - Flush happens at well-defined points (session end)
    """

    def __init__(self, session_id: str = "default"):
        """
        Initialize BCM adapter.

        Args:
            session_id: Session identifier for trail persistence
        """
        self.session_id = session_id
        self.trail: Optional[OrchestraTrail] = None
        self._loaded = False

    def ensure_loaded(self) -> OrchestraTrail:
        """
        Ensure trail is loaded (lazy loading).

        Returns:
            Loaded OrchestraTrail
        """
        if not self._loaded:
            self.trail = load_trail(self.session_id)
            self._loaded = True
        return self.trail

    def get_trail(self) -> Optional[OrchestraTrail]:
        """Get current trail (may be None if not loaded)."""
        return self.trail

    # =========================================================================
    # Routing Integration
    # =========================================================================

    def get_expert_confidence(self, expert_name: str) -> float:
        """
        Get BCM confidence for expert.

        For use in routing results (metadata only, doesn't change selection).

        Args:
            expert_name: Name of the expert

        Returns:
            Confidence value in [0.0, 1.0]
        """
        if not self.trail:
            return 1.0
        return self.trail.get_expert_confidence(expert_name)

    def get_all_expert_confidences(self) -> Dict[str, float]:
        """
        Get confidence values for all known experts.

        Returns:
            Dict mapping expert names to confidence values
        """
        if not self.trail:
            return {}

        return {
            name: self.trail.get_expert_confidence(name)
            for name in self.trail.expert_trails.keys()
        }

    # =========================================================================
    # Locking Integration
    # =========================================================================

    def get_optimal_depth(
        self,
        expert: str,
        task_type: str,
        fallback: str,
        safety_cap: str
    ) -> str:
        """
        Get trail-optimized thinking depth.

        For use in parameter locker (within safety bounds).

        Args:
            expert: Expert name
            task_type: Task type
            fallback: Default depth
            safety_cap: Maximum allowed depth from safety gating

        Returns:
            Recommended depth (never exceeds safety_cap)
        """
        if not self.trail:
            # No trail - use fallback respecting safety
            depth_order = ["minimal", "standard", "deep", "ultradeep"]
            fallback_idx = depth_order.index(fallback) if fallback in depth_order else 1
            cap_idx = depth_order.index(safety_cap) if safety_cap in depth_order else 3
            return depth_order[min(fallback_idx, cap_idx)]

        return self.trail.get_optimal_depth(expert, task_type, fallback, safety_cap)

    def has_depth_history(self, expert: str) -> bool:
        """Check if trail has depth optimization data for expert."""
        if not self.trail:
            return False
        return self.trail.has_depth_data(expert)

    # =========================================================================
    # Signal Integration
    # =========================================================================

    def get_signal_reliability(self, category: str, signal_name: str) -> float:
        """
        Get learned signal reliability.

        For adjusting signal confidence in PRISM detector.

        Args:
            category: Signal category
            signal_name: Signal name

        Returns:
            Reliability value in [0.0, 1.0]
        """
        if not self.trail:
            return 1.0
        return self.trail.get_signal_reliability(category, signal_name)

    # =========================================================================
    # Convergence Integration
    # =========================================================================

    def get_attractor_preferences(self) -> Dict[str, float]:
        """
        Get attractor basin preferences for convergence tracking.

        Returns:
            Dict mapping attractor names to success rates
        """
        if not self.trail:
            return {}
        return self.trail.get_attractor_preferences()

    # =========================================================================
    # Outcome Recording (Queued)
    # =========================================================================

    def record_expert_outcome(
        self,
        expert: str,
        success: bool,
        latency_ms: float = 0.0,
        task_type: str = "",
        depth: str = ""
    ) -> None:
        """
        Queue expert outcome for batch update.

        Args:
            expert: Expert name
            success: Whether routing was successful
            latency_ms: Response latency
            task_type: Task type
            depth: Thinking depth used
        """
        if self.trail:
            self.trail.record_expert_outcome(
                expert, success, latency_ms, task_type, depth
            )

    def record_signal_outcome(
        self,
        category: str,
        signal_name: str,
        correct: bool
    ) -> None:
        """
        Queue signal detection outcome for batch update.

        Args:
            category: Signal category
            signal_name: Signal name
            correct: Whether detection was correct
        """
        if self.trail:
            self.trail.record_signal_outcome(category, signal_name, correct)

    def record_attractor_outcome(
        self,
        attractor: str,
        converged: bool
    ) -> None:
        """
        Queue attractor convergence outcome for batch update.

        Args:
            attractor: Attractor basin name
            converged: Whether convergence was successful
        """
        if self.trail:
            self.trail.record_attractor_outcome(attractor, converged)

    # =========================================================================
    # Plasticity
    # =========================================================================

    def open_plasticity_window(self, trigger: str, divergence: float = 0.5) -> None:
        """Open plasticity window (e.g., after crash)."""
        if self.trail:
            self.trail.open_plasticity_window(trigger, divergence)

    def close_plasticity_window(self) -> None:
        """Close plasticity window."""
        if self.trail:
            self.trail.close_plasticity_window()

    def is_plasticity_active(self) -> bool:
        """Check if plasticity window is active."""
        if not self.trail:
            return False
        return self.trail.plasticity.window_active

    # =========================================================================
    # Batch Operations
    # =========================================================================

    def flush_updates(self) -> int:
        """
        Apply all queued updates to trail.

        Call at session end or explicit checkpoint.

        Returns:
            Number of updates applied
        """
        if not self.trail:
            return 0
        return self.trail.flush_updates()

    def save(self) -> bool:
        """
        Persist trail to disk.

        Returns:
            True if successful
        """
        if not self.trail:
            return True  # Nothing to save
        return save_trail(self.trail, self.session_id)

    def flush_and_save(self) -> Tuple[int, bool]:
        """
        Flush updates and save trail.

        Convenience method for session end.

        Returns:
            Tuple of (updates_applied, save_successful)
        """
        updates = self.flush_updates()
        saved = self.save()
        return updates, saved


# Import Tuple for type hint
from typing import Tuple


# =============================================================================
# Convenience Functions
# =============================================================================

def create_adapter(session_id: str = "default", load: bool = True) -> BCMPipelineAdapter:
    """
    Create and optionally load a BCM pipeline adapter.

    Args:
        session_id: Session identifier
        load: Whether to load trail immediately

    Returns:
        BCMPipelineAdapter instance
    """
    adapter = BCMPipelineAdapter(session_id)
    if load:
        adapter.ensure_loaded()
    return adapter


def integrate_with_state(
    adapter: BCMPipelineAdapter,
    state_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Integrate BCM data into cognitive state dict.

    Adds BCM fields to state for persistence.

    Args:
        adapter: BCM adapter
        state_dict: Cognitive state dictionary

    Returns:
        Updated state dictionary with BCM fields
    """
    trail = adapter.get_trail()

    state_dict["bcm_trail_version"] = trail.version if trail else ""
    state_dict["bcm_expert_confidence"] = adapter.get_all_expert_confidences()
    state_dict["bcm_plasticity_active"] = adapter.is_plasticity_active()
    state_dict["bcm_last_update"] = trail.last_update if trail else 0.0

    return state_dict


__all__ = [
    'BCMPipelineAdapter',
    'load_trail',
    'save_trail',
    'get_trail_path',
    'trail_exists',
    'create_adapter',
    'integrate_with_state',
    'BCM_STATE_DIR',
]
