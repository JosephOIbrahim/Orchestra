"""
BCM Trail Module for Orchestra Integration
==========================================

Implements the BCM (Bienenstock-Cooper-Munro) inspired trail system
for stigmergic reinforcement learning in the cognitive engine.

This module wraps the validated BCM primitives from the SYNERGIES project
and provides Orchestra-specific functionality for:
- Expert success tracking (trails per expert)
- Signal reliability learning
- Depth optimization history
- Attractor preference learning

ThinkingMachines [He2025] Compliance:
- Trail data is metadata only (does not change routing ORDER)
- Deterministic lookups (same trail + same key = same value)
- Batch-invariant updates (queued, not in-band)

References:
- SPEC-001: Unifying Theory Integration
- SPEC-002: Agent Pheromone Paths
- RESEARCH-001: Reinforcement Scaling
- bcm_reinforcement.py: Core BCM implementation

Author: [User] + Claude
Date: 2026-01-31
Version: 0.1.0
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# BCM Core Primitives (inline to avoid external dependency during bootstrap)
# =============================================================================

@dataclass
class BCMConfig:
    """Configuration for BCM reinforcement dynamics.

    SPIKE-002 calibrated parameters for decay behavior.
    """
    base_threshold: float = 5.0
    reference_strength: float = 10.0
    scaling_exponent: float = 1.2
    decay_rate: float = 0.01  # SPIKE-002: 0.01 per 2-hour unit
    decay_time_unit_minutes: float = 120.0  # 2 hours
    min_strength: float = 0.01
    max_strength: float = 100.0
    plasticity_reduction_scale: float = 0.5
    plasticity_min_threshold_ratio: float = 0.1

    # Reinforcement amounts by type
    reinforcement_amounts: Dict[str, float] = field(default_factory=lambda: {
        "success": 0.30,      # Expert succeeded
        "partial": 0.15,      # Partial success
        "reference": 0.10,    # Used as reference
        "failure": -0.05,     # Negative reinforcement (small)
    })


DEFAULT_CONFIG = BCMConfig()


@dataclass
class Trail:
    """A trail tracking expert/signal performance."""
    id: str
    domain: str
    strength: float = 1.0
    decay_rate: float = 0.01
    last_update: datetime = field(default_factory=datetime.now)
    update_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0  # Optimistic default
        return self.success_count / total


@dataclass
class PlasticityState:
    """Tracks plasticity window state for recovery."""
    window_active: bool = False
    sigma: float = 0.0
    window_trigger: str = ""
    window_opened: Optional[datetime] = None


# =============================================================================
# BCM Math Functions
# =============================================================================

def calculate_theta_m(total_strength: float, config: BCMConfig = DEFAULT_CONFIG) -> float:
    """Calculate sliding modification threshold.

    BCM homeostasis: theta DECREASES as activity increases.
    """
    if total_strength <= 0:
        return config.base_threshold

    ratio = total_strength / config.reference_strength
    theta_m = config.base_threshold / (1 + ratio ** config.scaling_exponent)
    min_theta = config.base_threshold * config.plasticity_min_threshold_ratio
    return max(theta_m, min_theta)


def calculate_saturation_factor(trail_strength: float, theta_m: float) -> float:
    """Calculate saturation factor for reinforcement."""
    if theta_m <= 0:
        return 0.01
    return 1.0 / (1.0 + trail_strength / theta_m)


def apply_decay(trail: Trail, elapsed_minutes: float, config: BCMConfig = DEFAULT_CONFIG) -> None:
    """Apply time-based decay to trail strength."""
    if elapsed_minutes <= 0:
        return

    time_units = elapsed_minutes / config.decay_time_unit_minutes
    decay_factor = (1 - trail.decay_rate) ** time_units
    trail.strength = max(config.min_strength, trail.strength * decay_factor)


def reinforce_trail(
    trail: Trail,
    total_strength: float,
    reinforcement_type: str = "success",
    plasticity_sigma: float = 0.0,
    config: BCMConfig = DEFAULT_CONFIG
) -> float:
    """Reinforce a trail with BCM saturation.

    Returns:
        Effective reinforcement amount applied.
    """
    base_amount = config.reinforcement_amounts.get(reinforcement_type, 0.1)

    # Calculate theta with plasticity boost
    theta_m = calculate_theta_m(total_strength, config)
    if plasticity_sigma > 0:
        boost = plasticity_sigma * config.plasticity_reduction_scale
        theta_m = theta_m * (1 + boost)

    # Apply saturation
    saturation = calculate_saturation_factor(trail.strength, theta_m)
    effective = base_amount * saturation

    # Update trail
    old_strength = trail.strength
    trail.strength = max(config.min_strength,
                         min(config.max_strength, trail.strength + effective))
    trail.update_count += 1
    trail.last_update = datetime.now()

    return trail.strength - old_strength


# =============================================================================
# OrchestraTrail - Main Integration Class
# =============================================================================

@dataclass
class OrchestraTrail:
    """
    Trail context for Orchestra integration.

    Wraps BCM primitives with Orchestra-specific functionality:
    - Expert success tracking
    - Signal reliability learning
    - Depth optimization history
    - Attractor preference learning

    ThinkingMachines Compliance:
    - All lookups are deterministic (dict-based, sorted keys)
    - Updates are queued and applied in batch
    - No runtime learning during message processing
    """

    # BCM configuration
    config: BCMConfig = field(default_factory=BCMConfig)

    # Plasticity state
    plasticity: PlasticityState = field(default_factory=PlasticityState)

    # Expert-specific trails (keyed by expert name)
    expert_trails: Dict[str, Trail] = field(default_factory=dict)

    # Signal reliability tracking (keyed by "category:signal_name")
    signal_history: Dict[str, List[bool]] = field(default_factory=dict)

    # Depth optimization history (keyed by "expert:task_type")
    depth_history: Dict[str, List[Tuple[str, bool]]] = field(default_factory=dict)

    # Attractor success tracking (keyed by attractor name)
    attractor_history: Dict[str, List[bool]] = field(default_factory=dict)

    # Version and timestamps
    version: str = "0.1.0"
    created: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)

    # Pending updates (batch queue)
    _pending_updates: List[Dict[str, Any]] = field(default_factory=list, repr=False)

    # ==========================================================================
    # Expert Confidence
    # ==========================================================================

    def get_expert_trail(self, expert_name: str) -> Trail:
        """Get or create trail for expert."""
        if expert_name not in self.expert_trails:
            self.expert_trails[expert_name] = Trail(
                id=f"expert_{expert_name}",
                domain="orchestra",
                strength=1.0
            )
        return self.expert_trails[expert_name]

    def get_expert_confidence(self, expert_name: str) -> float:
        """
        Get BCM-adjusted confidence for expert.

        Returns value in [0.0, 1.0] based on trail strength and success rate.
        Higher strength + higher success rate = higher confidence.
        """
        if expert_name not in self.expert_trails:
            return 1.0  # Default: full confidence (no history)

        trail = self.expert_trails[expert_name]

        # Combine strength-based and success-rate-based confidence
        # Strength contribution (normalized to 0-1, saturates at strength=5)
        strength_confidence = min(1.0, trail.strength / 5.0)

        # Success rate contribution
        success_confidence = trail.success_rate()

        # Weighted combination: 60% success rate, 40% strength
        return 0.6 * success_confidence + 0.4 * strength_confidence

    def get_total_expert_strength(self) -> float:
        """Get total strength across all expert trails."""
        return sum(t.strength for t in self.expert_trails.values())

    # ==========================================================================
    # Signal Reliability
    # ==========================================================================

    def get_signal_reliability(self, category: str, signal_name: str) -> float:
        """
        Get learned reliability for signal detection.

        Based on historical accuracy of signal detection.
        """
        key = f"{category}:{signal_name}"
        if key not in self.signal_history:
            return 1.0  # Default: trust pattern matching

        history = self.signal_history[key]
        if len(history) < 10:
            return 1.0  # Not enough data

        # Use recent 50 instances
        recent = history[-50:]
        return sum(recent) / len(recent)

    # ==========================================================================
    # Depth Optimization
    # ==========================================================================

    def get_optimal_depth(
        self,
        expert: str,
        task_type: str,
        fallback: str,
        safety_cap: str = "ultradeep"
    ) -> str:
        """
        Get trail-recommended thinking depth.

        Args:
            expert: Expert name
            task_type: Task type (implement, debug, etc.)
            fallback: Fallback depth if no history
            safety_cap: Maximum allowed depth (from safety gating)

        Returns:
            Recommended depth (never exceeds safety_cap)
        """
        depth_order = ["minimal", "standard", "deep", "ultradeep"]
        key = f"{expert}:{task_type}"

        if key not in self.depth_history:
            # No history - use fallback, respecting safety cap
            fallback_idx = depth_order.index(fallback) if fallback in depth_order else 1
            cap_idx = depth_order.index(safety_cap) if safety_cap in depth_order else 3
            return depth_order[min(fallback_idx, cap_idx)]

        history = self.depth_history[key]
        if len(history) < 5:
            # Not enough history
            fallback_idx = depth_order.index(fallback) if fallback in depth_order else 1
            cap_idx = depth_order.index(safety_cap) if safety_cap in depth_order else 3
            return depth_order[min(fallback_idx, cap_idx)]

        # Find depth with best success rate
        depth_success = {}
        for depth, success in history[-20:]:  # Recent 20
            if depth not in depth_success:
                depth_success[depth] = []
            depth_success[depth].append(success)

        best_depth = fallback
        best_rate = 0.0
        for depth, successes in depth_success.items():
            rate = sum(successes) / len(successes)
            if rate > best_rate:
                best_rate = rate
                best_depth = depth

        # Respect safety cap
        best_idx = depth_order.index(best_depth) if best_depth in depth_order else 1
        cap_idx = depth_order.index(safety_cap) if safety_cap in depth_order else 3
        return depth_order[min(best_idx, cap_idx)]

    def has_depth_data(self, expert: str, task_type: str = None) -> bool:
        """Check if we have depth optimization data for expert."""
        if task_type:
            key = f"{expert}:{task_type}"
            return key in self.depth_history and len(self.depth_history[key]) >= 5

        # Check any task type
        for key in self.depth_history:
            if key.startswith(f"{expert}:"):
                if len(self.depth_history[key]) >= 5:
                    return True
        return False

    # ==========================================================================
    # Attractor Preferences
    # ==========================================================================

    def get_attractor_success_rate(self, attractor_name: str) -> float:
        """Get success rate for attractor basin."""
        if attractor_name not in self.attractor_history:
            return 1.0  # Default: optimistic

        history = self.attractor_history[attractor_name]
        if len(history) < 5:
            return 1.0  # Not enough data

        recent = history[-30:]
        return sum(recent) / len(recent)

    def get_attractor_preferences(self) -> Dict[str, float]:
        """Get all attractor preferences as dict."""
        default_attractors = ["focused", "exploring", "recovery", "teaching"]
        return {
            attractor: self.get_attractor_success_rate(attractor)
            for attractor in default_attractors
        }

    # ==========================================================================
    # Recording Outcomes (Queued Updates)
    # ==========================================================================

    def record_expert_outcome(
        self,
        expert: str,
        success: bool,
        latency_ms: float = 0.0,
        task_type: str = "",
        depth: str = ""
    ) -> None:
        """
        Queue expert usage outcome for batch update.

        Does NOT apply immediately - must call flush_updates().
        """
        self._pending_updates.append({
            "type": "expert",
            "expert": expert,
            "success": success,
            "latency_ms": latency_ms,
            "task_type": task_type,
            "depth": depth,
            "timestamp": time.time()
        })

    def record_signal_outcome(
        self,
        category: str,
        signal_name: str,
        correct: bool
    ) -> None:
        """
        Queue signal detection outcome for batch update.
        """
        self._pending_updates.append({
            "type": "signal",
            "category": category,
            "signal_name": signal_name,
            "correct": correct,
            "timestamp": time.time()
        })

    def record_attractor_outcome(
        self,
        attractor: str,
        converged: bool
    ) -> None:
        """
        Queue attractor convergence outcome for batch update.
        """
        self._pending_updates.append({
            "type": "attractor",
            "attractor": attractor,
            "converged": converged,
            "timestamp": time.time()
        })

    def flush_updates(self) -> int:
        """
        Apply all pending updates.

        Called at session end or explicit flush.

        Returns:
            Number of updates applied.
        """
        if not self._pending_updates:
            return 0

        count = 0
        total_strength = self.get_total_expert_strength()

        for update in self._pending_updates:
            update_type = update.get("type")

            if update_type == "expert":
                self._apply_expert_update(update, total_strength)
                count += 1

            elif update_type == "signal":
                self._apply_signal_update(update)
                count += 1

            elif update_type == "attractor":
                self._apply_attractor_update(update)
                count += 1

        self._pending_updates = []
        self.last_update = time.time()

        logger.info(f"Flushed {count} BCM trail updates")
        return count

    def _apply_expert_update(self, update: Dict, total_strength: float) -> None:
        """Apply expert outcome update."""
        expert = update["expert"]
        success = update["success"]
        task_type = update.get("task_type", "")
        depth = update.get("depth", "")

        trail = self.get_expert_trail(expert)

        # Reinforce based on outcome
        reinforcement_type = "success" if success else "failure"
        reinforce_trail(
            trail,
            total_strength,
            reinforcement_type,
            self.plasticity.sigma if self.plasticity.window_active else 0.0,
            self.config
        )

        # Update success/failure counts
        if success:
            trail.success_count += 1
        else:
            trail.failure_count += 1

        # Record depth outcome if provided
        if task_type and depth:
            key = f"{expert}:{task_type}"
            if key not in self.depth_history:
                self.depth_history[key] = []
            self.depth_history[key].append((depth, success))

            # Limit history size
            if len(self.depth_history[key]) > 100:
                self.depth_history[key] = self.depth_history[key][-50:]

    def _apply_signal_update(self, update: Dict) -> None:
        """Apply signal reliability update."""
        key = f"{update['category']}:{update['signal_name']}"
        if key not in self.signal_history:
            self.signal_history[key] = []

        self.signal_history[key].append(update["correct"])

        # Limit history size
        if len(self.signal_history[key]) > 1000:
            self.signal_history[key] = self.signal_history[key][-500:]

    def _apply_attractor_update(self, update: Dict) -> None:
        """Apply attractor outcome update."""
        attractor = update["attractor"]
        if attractor not in self.attractor_history:
            self.attractor_history[attractor] = []

        self.attractor_history[attractor].append(update["converged"])

        # Limit history size
        if len(self.attractor_history[attractor]) > 200:
            self.attractor_history[attractor] = self.attractor_history[attractor][-100:]

    # ==========================================================================
    # Plasticity Window
    # ==========================================================================

    def open_plasticity_window(self, trigger: str, divergence: float = 0.5) -> None:
        """Open plasticity window (e.g., after crash)."""
        self.plasticity.window_active = True
        self.plasticity.window_trigger = trigger
        self.plasticity.sigma = min(1.0, divergence)
        self.plasticity.window_opened = datetime.now()
        logger.info(f"Opened plasticity window: {trigger}, sigma={self.plasticity.sigma:.2f}")

    def close_plasticity_window(self) -> None:
        """Close plasticity window."""
        self.plasticity.window_active = False
        self.plasticity.window_trigger = ""
        self.plasticity.sigma = 0.0
        self.plasticity.window_opened = None
        logger.info("Closed plasticity window")

    # ==========================================================================
    # Decay
    # ==========================================================================

    def apply_session_decay(self, elapsed_minutes: float) -> None:
        """Apply time-based decay to all trails."""
        for trail in self.expert_trails.values():
            apply_decay(trail, elapsed_minutes, self.config)

    # ==========================================================================
    # Serialization
    # ==========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """Serialize trail to dictionary."""
        return {
            "version": self.version,
            "created": self.created,
            "last_update": self.last_update,
            "config": {
                "base_threshold": self.config.base_threshold,
                "reference_strength": self.config.reference_strength,
                "scaling_exponent": self.config.scaling_exponent,
                "decay_rate": self.config.decay_rate,
                "decay_time_unit_minutes": self.config.decay_time_unit_minutes,
            },
            "plasticity": {
                "window_active": self.plasticity.window_active,
                "sigma": self.plasticity.sigma,
                "window_trigger": self.plasticity.window_trigger,
            },
            "expert_trails": {
                name: {
                    "id": t.id,
                    "domain": t.domain,
                    "strength": t.strength,
                    "decay_rate": t.decay_rate,
                    "update_count": t.update_count,
                    "success_count": t.success_count,
                    "failure_count": t.failure_count,
                }
                for name, t in self.expert_trails.items()
            },
            "signal_history": self.signal_history,
            "depth_history": self.depth_history,
            "attractor_history": self.attractor_history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrchestraTrail':
        """Deserialize trail from dictionary."""
        trail = cls()

        trail.version = data.get("version", "0.1.0")
        trail.created = data.get("created", time.time())
        trail.last_update = data.get("last_update", time.time())

        # Config
        config_data = data.get("config", {})
        trail.config = BCMConfig(
            base_threshold=config_data.get("base_threshold", 5.0),
            reference_strength=config_data.get("reference_strength", 10.0),
            scaling_exponent=config_data.get("scaling_exponent", 1.2),
            decay_rate=config_data.get("decay_rate", 0.01),
            decay_time_unit_minutes=config_data.get("decay_time_unit_minutes", 120.0),
        )

        # Plasticity
        plast_data = data.get("plasticity", {})
        trail.plasticity = PlasticityState(
            window_active=plast_data.get("window_active", False),
            sigma=plast_data.get("sigma", 0.0),
            window_trigger=plast_data.get("window_trigger", ""),
        )

        # Expert trails
        for name, t_data in data.get("expert_trails", {}).items():
            trail.expert_trails[name] = Trail(
                id=t_data.get("id", f"expert_{name}"),
                domain=t_data.get("domain", "orchestra"),
                strength=t_data.get("strength", 1.0),
                decay_rate=t_data.get("decay_rate", 0.01),
                update_count=t_data.get("update_count", 0),
                success_count=t_data.get("success_count", 0),
                failure_count=t_data.get("failure_count", 0),
            )

        # Histories
        trail.signal_history = data.get("signal_history", {})
        trail.depth_history = data.get("depth_history", {})
        trail.attractor_history = data.get("attractor_history", {})

        return trail

    def checksum(self) -> str:
        """Generate deterministic checksum of trail state."""
        state_str = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()[:16]


__all__ = [
    'BCMConfig',
    'Trail',
    'PlasticityState',
    'OrchestraTrail',
    'calculate_theta_m',
    'calculate_saturation_factor',
    'apply_decay',
    'reinforce_trail',
]
