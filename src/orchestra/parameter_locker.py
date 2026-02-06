"""
Parameter Locker
================

Locks cognitive parameters before generation for deterministic behavior.

Features:
- MAX3 bounded reflection (max 3 iterations)
- Cognitive safety gating (state overrides user requests)
- Deterministic checksum computation
- Parameter freezing for batch-invariance
- v7.0.0: BCM trail-informed depth optimization

ThinkingMachines [He2025] Compliance:
- Parameters LOCKED before generation
- Same inputs = same locked params = same checksum
- No mid-generation parameter changes

Cognitive Safety Gating (from CLAUDE.md):
- depleted → minimal thinking
- low energy → standard thinking
- RED/ORANGE burnout → standard thinking
- high energy → ultradeep allowed (if requested)

v7.0.0 BCM Integration:
- Trail can suggest optimal depth based on historical performance
- Safety gates ALWAYS take precedence over trail suggestions
- Trail optimization = within_safety_bounds(trail_suggestion)
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum
import logging

from .expert_router import Expert, RoutingResult
from .cognitive_state import BurnoutLevel, EnergyLevel, Altitude

if TYPE_CHECKING:
    from .bcm_trail import OrchestraTrail

logger = logging.getLogger(__name__)


# =============================================================================
# Thinking Depths
# =============================================================================

class ThinkDepth(Enum):
    """Thinking depth levels with token budgets."""
    MINIMAL = "minimal"      # 1K tokens
    STANDARD = "standard"    # 8K tokens
    DEEP = "deep"            # 32K tokens
    ULTRADEEP = "ultradeep"  # 128K tokens (Opus only)


# Depth budgets
DEPTH_BUDGETS = {
    ThinkDepth.MINIMAL: 1_000,
    ThinkDepth.STANDARD: 8_000,
    ThinkDepth.DEEP: 32_000,
    ThinkDepth.ULTRADEEP: 128_000
}


# =============================================================================
# Paradigms
# =============================================================================

class Paradigm(Enum):
    """Cognitive paradigms."""
    CORTEX = "Cortex"      # Hierarchical, explicit, controlled
    MYCELIUM = "Mycelium"  # Distributed, associative, emergent


# =============================================================================
# Lock Status
# =============================================================================

class LockStatus(Enum):
    """Lock status states."""
    UNLOCKED = "unlocked"
    LOCKING = "locking"
    LOCKED = "locked"


# =============================================================================
# Locked Parameters
# =============================================================================

@dataclass
class LockedParams:
    """
    Immutable locked parameters for generation.

    Once locked, these CANNOT change during generation.

    ThinkingMachines [He2025] Batch-Invariance:
    - `checksum`: Routing-only checksum (excludes reflection_iteration)
    - `session_checksum`: Full checksum including iteration (for debugging)
    - Same routing params → same checksum regardless of reflection count

    v6.0.0: Added source_mode for grounding layer integration.
    """
    expert: str
    paradigm: str
    altitude: str
    think_depth: str
    source_mode: str = "learn"  # v6.0.0: learn | access | hybrid
    checksum: str = ""
    session_checksum: str = ""  # Includes reflection_iteration for debugging
    reflection_iteration: int = 0
    max_reflections: int = 3  # MAX3

    def __post_init__(self):
        """Compute deterministic checksums."""
        if not self.checksum:
            self.checksum = self._compute_checksum()
        if not self.session_checksum:
            self.session_checksum = self._compute_session_checksum()

    def _compute_checksum(self) -> str:
        """
        Compute deterministic checksum of ROUTING params only.

        Excludes reflection_iteration to ensure batch-invariance:
        Same routing decision → same checksum regardless of iteration.

        ThinkingMachines [He2025]: Same inputs → same outputs → same checksums
        v6.0.0: Includes source_mode in checksum
        """
        data = json.dumps({
            "expert": self.expert,
            "paradigm": self.paradigm,
            "altitude": self.altitude,
            "think_depth": self.think_depth,
            "source_mode": self.source_mode,  # v6.0.0
            # NOTE: reflection_iteration intentionally excluded for batch-invariance
        }, sort_keys=True)
        return hashlib.md5(data.encode()).hexdigest()[:6]

    def _compute_session_checksum(self) -> str:
        """
        Compute session-aware checksum including iteration.

        Used for debugging/tracing, not for batch-invariance verification.
        """
        data = json.dumps({
            "expert": self.expert,
            "paradigm": self.paradigm,
            "altitude": self.altitude,
            "think_depth": self.think_depth,
            "source_mode": self.source_mode,  # v6.0.0
            "reflection_iteration": self.reflection_iteration
        }, sort_keys=True)
        return hashlib.md5(data.encode()).hexdigest()[:6]

    def to_anchor(self) -> str:
        """
        Format as anchor string for embedding in responses.

        v6.0.0 Format: [EXEC:{checksum}|{expert}|{paradigm}|{altitude}|{think_depth}|{source_mode}]
        """
        return f"[EXEC:{self.checksum}|{self.expert}|{self.paradigm}|{self.altitude}|{self.think_depth}|{self.source_mode}]"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for WebSocket."""
        return {
            "expert": self.expert,
            "paradigm": self.paradigm,
            "altitude": self.altitude,
            "think_depth": self.think_depth,
            "source_mode": self.source_mode,  # v6.0.0
            "checksum": self.checksum,
            "session_checksum": self.session_checksum,
            "reflection_iteration": self.reflection_iteration,
            "max_reflections": self.max_reflections
        }

    def can_reflect(self) -> bool:
        """Check if another reflection iteration is allowed (MAX3)."""
        return self.reflection_iteration < self.max_reflections


@dataclass
class LockResult:
    """Result of parameter locking."""
    status: LockStatus
    params: LockedParams
    safety_capped: bool = False  # True if safety gating reduced depth
    original_depth: Optional[str] = None  # Depth before safety cap
    converged: bool = False  # True if early convergence detected (xi < epsilon)

    # v7.0.0: BCM Trail optimization metadata
    bcm_optimized: bool = False  # True if trail influenced depth selection
    bcm_suggested_depth: Optional[str] = None  # Trail's suggested depth
    bcm_trail_version: str = ""  # Trail version used
    bcm_depth_history_count: int = 0  # Number of depth samples in trail

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "status": self.status.value,
            "params": self.params.to_dict(),
            "safety_capped": self.safety_capped,
            "original_depth": self.original_depth,
            "converged": self.converged,
            # v7.0.0: BCM metadata
            "bcm_optimized": self.bcm_optimized,
            "bcm_suggested_depth": self.bcm_suggested_depth,
            "bcm_trail_version": self.bcm_trail_version,
            "bcm_depth_history_count": self.bcm_depth_history_count
        }


# =============================================================================
# Parameter Locker
# =============================================================================

class ParameterLocker:
    """
    Locks cognitive parameters for deterministic generation.

    Implements:
    - MAX3 bounded reflection
    - Cognitive safety gating
    - Deterministic checksums
    - Paradigm selection based on mode
    """

    def __init__(self, max_reflections: int = 3, epsilon: float = 0.1):
        """
        Initialize locker.

        Args:
            max_reflections: Maximum reflection iterations (MAX3)
            epsilon: Convergence threshold for stopping early

        Note: reflection_count is now tracked in CognitiveState for batch-invariance.
        """
        self.max_reflections = max_reflections
        self.epsilon = epsilon
        self._current_lock: Optional[LockResult] = None

    def lock(
        self,
        routing: RoutingResult,
        burnout: BurnoutLevel,
        energy: EnergyLevel,
        altitude: Altitude,
        requested_depth: ThinkDepth = ThinkDepth.STANDARD,
        mode: str = "focused",
        epistemic_tension: float = 0.0,
        reflection_count: int = 0,
        source_mode: str = "learn",  # v6.0.0
        trail: Optional['OrchestraTrail'] = None,  # v7.0.0
        task_type: str = ""  # v7.0.0
    ) -> LockResult:
        """
        Lock parameters for generation.

        ThinkingMachines [He2025]: Parameters locked BEFORE generation.
        Batch-invariance: reflection_count passed from state snapshot,
        not stored as instance state.
        [GWM2026]: source_mode locks grounding decision.

        v7.0.0: Trail-informed depth optimization within safety bounds.
        IMPORTANT: Safety gates ALWAYS take precedence over trail suggestions.

        Args:
            routing: Result from expert router
            burnout: Current burnout level
            energy: Current energy level
            altitude: Current altitude
            requested_depth: User-requested thinking depth
            mode: Current cognitive mode (for paradigm selection)
            epistemic_tension: Current epistemic tension (for early stop)
            reflection_count: Current reflection count (from CognitiveState snapshot)
            source_mode: v6.0.0 - Grounding source mode (learn|access|hybrid)
            trail: v7.0.0 - BCM trail for depth optimization (optional)
            task_type: v7.0.0 - Task type for trail-based depth lookup

        Returns:
            LockResult with locked parameters
        """
        # =================================================================
        # STEP 1: Determine paradigm based on mode
        # =================================================================
        paradigm = self._select_paradigm(routing.expert, mode)

        # =================================================================
        # STEP 2: Apply cognitive safety gating to thinking depth
        # =================================================================
        actual_depth, safety_capped = self._apply_safety_gating(
            requested_depth, burnout, energy
        )

        # =================================================================
        # STEP 2b (v7.0.0): Apply BCM trail optimization WITHIN safety bounds
        # =================================================================
        bcm_metadata = self._apply_bcm_depth_optimization(
            actual_depth=actual_depth,
            safety_cap=self._get_max_depth(burnout, energy),
            expert=routing.expert.value,
            task_type=task_type,
            trail=trail
        )

        # If trail provided a better depth within safety bounds, use it
        if bcm_metadata["optimized"] and bcm_metadata["suggested_depth"]:
            suggested = bcm_metadata["suggested_depth"]
            depth_order = [ThinkDepth.MINIMAL, ThinkDepth.STANDARD, ThinkDepth.DEEP, ThinkDepth.ULTRADEEP]
            depth_map = {d.value: d for d in depth_order}

            if suggested in depth_map:
                suggested_depth = depth_map[suggested]
                suggested_idx = depth_order.index(suggested_depth)
                cap_idx = depth_order.index(self._get_max_depth(burnout, energy))

                # Trail can adjust within safety bounds (never exceed cap)
                if suggested_idx <= cap_idx:
                    # Use trail suggestion (within safety bounds)
                    actual_depth = suggested_depth
                    logger.info(f"BCM trail adjusted depth: {suggested} (within safety cap)")

        # =================================================================
        # STEP 3: Check MAX3 and epsilon stopping
        # =================================================================
        converged = False
        if epistemic_tension < self.epsilon and reflection_count > 0:
            # Early convergence - signal to caller
            logger.info(f"Early convergence at xi={epistemic_tension:.2f} < epsilon={self.epsilon}")
            converged = True

        if reflection_count >= self.max_reflections:
            # MAX3 reached - force minimal depth
            actual_depth = ThinkDepth.MINIMAL
            safety_capped = True
            logger.info(f"MAX3 reached ({reflection_count}/{self.max_reflections})")

        # =================================================================
        # STEP 4: Create locked params
        # =================================================================
        params = LockedParams(
            expert=routing.expert.value,
            paradigm=paradigm.value,
            altitude=self._format_altitude(altitude),
            think_depth=actual_depth.value,
            source_mode=source_mode,  # v6.0.0
            reflection_iteration=reflection_count
        )

        result = LockResult(
            status=LockStatus.LOCKED,
            params=params,
            safety_capped=safety_capped,
            original_depth=requested_depth.value if safety_capped else None,
            converged=converged,
            # v7.0.0: BCM metadata
            bcm_optimized=bcm_metadata["optimized"],
            bcm_suggested_depth=bcm_metadata["suggested_depth"],
            bcm_trail_version=bcm_metadata["trail_version"],
            bcm_depth_history_count=bcm_metadata["depth_history_count"]
        )

        self._current_lock = result
        # NOTE: Counter increment now handled by caller (CognitiveOrchestrator)
        # after batch_update() for batch-invariance

        logger.info(f"Locked params: {params.to_anchor()}")
        return result

    def _select_paradigm(self, expert: Expert, mode: str) -> Paradigm:
        """
        Select paradigm based on expert and mode.

        Per CLAUDE.md:
        - Default: Cortex (hierarchical, explicit)
        - Switch to Mycelium on "what if", exploring signals
        """
        # Socratic expert + exploring mode → Mycelium
        if expert == Expert.SOCRATIC and mode in ("exploring", "teaching"):
            return Paradigm.MYCELIUM

        # Explicit mode signals
        if mode == "exploring":
            return Paradigm.MYCELIUM

        # Default to Cortex
        return Paradigm.CORTEX

    def _apply_safety_gating(
        self,
        requested: ThinkDepth,
        burnout: BurnoutLevel,
        energy: EnergyLevel
    ) -> tuple[ThinkDepth, bool]:
        """
        Apply cognitive safety gating to thinking depth.

        Per CLAUDE.md:
        - depleted → minimal
        - low energy → standard
        - RED/ORANGE burnout → standard
        - high energy → ultradeep OK (if requested)

        Safety state ALWAYS overrides user request. Can REDUCE, never increase.

        Returns:
            (actual_depth, was_capped)
        """
        max_allowed = self._get_max_depth(burnout, energy)

        # Get depth order for comparison
        depth_order = [ThinkDepth.MINIMAL, ThinkDepth.STANDARD, ThinkDepth.DEEP, ThinkDepth.ULTRADEEP]

        requested_idx = depth_order.index(requested)
        max_idx = depth_order.index(max_allowed)

        if requested_idx > max_idx:
            # Safety cap - reduce to max allowed
            logger.info(f"Safety gating: {requested.value} → {max_allowed.value}")
            return (max_allowed, True)

        return (requested, False)

    def _apply_bcm_depth_optimization(
        self,
        actual_depth: ThinkDepth,
        safety_cap: ThinkDepth,
        expert: str,
        task_type: str,
        trail: Optional['OrchestraTrail']
    ) -> Dict[str, Any]:
        """
        v7.0.0: Apply BCM trail-informed depth optimization.

        CRITICAL: Safety cap is NEVER exceeded. Trail can only suggest
        depths within the already-determined safety bounds.

        ThinkingMachines [He2025] Compliance:
        - Trail data is read-only during this phase
        - Decision is deterministic given same inputs
        - No side effects on trail during locking

        Args:
            actual_depth: Current depth after safety gating
            safety_cap: Maximum allowed depth from safety gating
            expert: Expert name
            task_type: Task type for depth lookup
            trail: BCM trail (optional)

        Returns:
            Dict with BCM metadata:
            - optimized: bool - Whether trail influenced decision
            - suggested_depth: str or None - Trail's suggestion
            - trail_version: str - Trail version
            - depth_history_count: int - Number of depth samples
        """
        # Default: no trail or no optimization
        result = {
            "optimized": False,
            "suggested_depth": None,
            "trail_version": "",
            "depth_history_count": 0
        }

        if trail is None:
            return result

        # Set version from trail
        result["trail_version"] = trail.version

        # Build the key for depth history lookup (format: "expert:task_type")
        depth_key = f"{expert}:{task_type}" if task_type else expert

        # Check if trail has depth history for this expert
        if not trail.has_depth_data(expert, task_type or None):
            return result

        # Get depth history count
        if depth_key in trail.depth_history:
            result["depth_history_count"] = len(trail.depth_history[depth_key])

        # Get trail's optimal depth suggestion
        # Pass safety_cap.value as string (trail expects string depths)
        suggested = trail.get_optimal_depth(
            expert=expert,
            task_type=task_type,
            fallback=actual_depth.value,
            safety_cap=safety_cap.value
        )

        if suggested:
            result["suggested_depth"] = suggested

            # Only mark as optimized if suggestion differs from current
            # and is within safety bounds
            depth_order = ["minimal", "standard", "deep", "ultradeep"]
            if suggested in depth_order:
                suggested_idx = depth_order.index(suggested)
                cap_idx = depth_order.index(safety_cap.value)

                if suggested_idx <= cap_idx:
                    result["optimized"] = True
                    logger.debug(
                        f"BCM trail suggests {suggested} for {expert}/{task_type} "
                        f"(within cap {safety_cap.value})"
                    )

        return result

    def _get_max_depth(self, burnout: BurnoutLevel, energy: EnergyLevel) -> ThinkDepth:
        """
        Get maximum allowed thinking depth based on state.

        Cognitive Safety Gating (from CLAUDE.md):
        - depleted → minimal
        - low energy → standard
        - RED burnout → minimal
        - ORANGE burnout → standard
        - high energy → ultradeep OK
        """
        # Energy depleted → minimal
        if energy == EnergyLevel.DEPLETED:
            return ThinkDepth.MINIMAL

        # RED burnout → minimal
        if burnout == BurnoutLevel.RED:
            return ThinkDepth.MINIMAL

        # Low energy OR ORANGE burnout → standard
        if energy == EnergyLevel.LOW or burnout == BurnoutLevel.ORANGE:
            return ThinkDepth.STANDARD

        # High energy → ultradeep allowed
        if energy == EnergyLevel.HIGH:
            return ThinkDepth.ULTRADEEP

        # Default → deep
        return ThinkDepth.DEEP

    def _format_altitude(self, altitude: Altitude) -> str:
        """Format altitude for display."""
        altitude_map = {
            Altitude.VISION: "30000ft",
            Altitude.ARCHITECTURE: "15000ft",
            Altitude.COMPONENTS: "5000ft",
            Altitude.GROUND: "Ground"
        }
        return altitude_map.get(altitude, "30000ft")

    def reset(self) -> None:
        """Reset locker state (for new task).

        Note: reflection_count is now reset in CognitiveState for batch-invariance.
        """
        self._current_lock = None

    def get_current_lock(self) -> Optional[LockResult]:
        """Get current lock result."""
        return self._current_lock


# =============================================================================
# Factory Function
# =============================================================================

def create_locker(max_reflections: int = 3, epsilon: float = 0.1) -> ParameterLocker:
    """Create a ParameterLocker instance."""
    return ParameterLocker(max_reflections=max_reflections, epsilon=epsilon)


__all__ = [
    'ThinkDepth', 'Paradigm', 'LockStatus',
    'LockedParams', 'LockResult', 'ParameterLocker',
    'DEPTH_BUDGETS', 'create_locker'
]
