"""
Mycelium Aggregator
===================

Implements aggregation strategies for peer-to-peer state sharing in the Mycelium Arc.

Key insight: Different cognitive fields require different aggregation strategies:
- SAFETY-MAX: For burnout levels - takes the maximum (most conservative)
- INHERIT: For mode/paradigm - first non-None wins (LIVRPS-like)
- ADDITIVE: For tensions - sum across peers (compound effect)

ThinkingMachines [He2025] Compliance:
- Fixed aggregation order (sorted by peer_id for determinism)
- Kahan summation for numerical stability
- No runtime algorithm switching

Patent Claim 5 Support:
- Implements horizontal (peer-to-peer) state composition
- Complements vertical (parent-child) LIVRPS composition
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List
import hashlib
import logging
import time

logger = logging.getLogger(__name__)


# =============================================================================
# Aggregation Strategy Enum
# =============================================================================

class AggregationStrategy(Enum):
    """
    Strategies for aggregating peer state values.

    Each strategy has specific semantics for how multiple peer values
    are combined into a single resolved value.
    """
    SAFETY_MAX = "safety_max"    # Max value (most conservative for safety)
    INHERIT = "inherit"          # First non-None wins (like LIVRPS)
    ADDITIVE = "additive"        # Sum across peers (tensions compound)
    MIN = "min"                  # Minimum value
    AVERAGE = "average"          # Mean of all values (Kahan summation)


# =============================================================================
# Burnout Level Ordering (for SAFETY-MAX)
# =============================================================================

BURNOUT_ORDER = {
    "green": 0,
    "yellow": 1,
    "orange": 2,
    "red": 3
}

BURNOUT_REVERSE = {v: k for k, v in BURNOUT_ORDER.items()}


def burnout_max(a: str, b: str) -> str:
    """
    Return the higher (more severe) burnout level.

    SAFETY-MAX: If any peer is in RED, the aggregated result is RED.
    This protects the cognitive safety of the entire peer group.
    """
    a_order = BURNOUT_ORDER.get(a.lower() if a else "green", 0)
    b_order = BURNOUT_ORDER.get(b.lower() if b else "green", 0)
    return BURNOUT_REVERSE[max(a_order, b_order)]


# =============================================================================
# Kahan Summation (batch-invariant)
# =============================================================================

def kahan_sum(values: List[float]) -> float:
    """
    Kahan summation for batch-invariant floating-point accumulation.

    Sorts values before summing to ensure deterministic order.
    This is critical for ThinkingMachines [He2025] compliance.

    Args:
        values: List of float values to sum

    Returns:
        Sum with reduced numerical error
    """
    if not values:
        return 0.0

    # Sort for deterministic order
    sorted_values = sorted(values)

    total = 0.0
    compensation = 0.0

    for v in sorted_values:
        y = v - compensation
        t = total + y
        compensation = (t - total) - y
        total = t

    return total


# =============================================================================
# Mycelium State (what flows between peers)
# =============================================================================

@dataclass
class MyceliumState:
    """
    State that flows between peers in the Mycelium Arc.

    Fields are categorized by aggregation strategy:
    - SAFETY-MAX: burnout_level (never lower, always conservative)
    - INHERIT: momentum_phase, attractor_basin (first non-None)
    - ADDITIVE: epistemic_tension (tensions compound across peers)

    This is the horizontal composition complement to LIVRPS vertical composition.
    """
    # SAFETY-MAX fields (conservative maximum)
    burnout_level: Optional[str] = None

    # INHERIT fields (first non-None wins)
    momentum_phase: Optional[str] = None
    attractor_basin: Optional[str] = None

    # ADDITIVE fields (tensions compound)
    epistemic_tension: Optional[float] = None

    # Metadata
    peer_id: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for persistence/transmission."""
        return {
            "burnout_level": self.burnout_level,
            "momentum_phase": self.momentum_phase,
            "attractor_basin": self.attractor_basin,
            "epistemic_tension": self.epistemic_tension,
            "peer_id": self.peer_id,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MyceliumState':
        """Deserialize from dict."""
        return cls(
            burnout_level=data.get("burnout_level"),
            momentum_phase=data.get("momentum_phase"),
            attractor_basin=data.get("attractor_basin"),
            epistemic_tension=data.get("epistemic_tension"),
            peer_id=data.get("peer_id", ""),
            timestamp=data.get("timestamp", time.time())
        )

    def checksum(self) -> str:
        """Generate deterministic checksum."""
        import json
        data = {k: v for k, v in self.to_dict().items() if k != "timestamp"}
        state_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()[:16]


# =============================================================================
# Field Aggregation Configuration
# =============================================================================

# Maps field names to their aggregation strategies
FIELD_STRATEGIES: Dict[str, AggregationStrategy] = {
    # SAFETY-MAX: conservative maximum for safety-critical fields
    "burnout_level": AggregationStrategy.SAFETY_MAX,

    # INHERIT: first non-None value (ordered by timestamp, then peer_id)
    "momentum_phase": AggregationStrategy.INHERIT,
    "attractor_basin": AggregationStrategy.INHERIT,

    # ADDITIVE: tensions compound across peers
    "epistemic_tension": AggregationStrategy.ADDITIVE,
}


# =============================================================================
# Aggregator Class
# =============================================================================

class MyceliumAggregator:
    """
    Aggregates peer states according to field-specific strategies.

    This is the core of the Mycelium Arc: horizontal state composition
    that complements the vertical LIVRPS composition.

    ThinkingMachines [He2025] Compliance:
    - Fixed aggregation order (peers sorted by timestamp, then id)
    - Fixed field evaluation order (alphabetical)
    - Kahan summation for additive aggregation
    - Deterministic checksums for reproducibility
    """

    def __init__(self, field_strategies: Dict[str, AggregationStrategy] = None):
        """
        Initialize aggregator.

        Args:
            field_strategies: Optional override for field aggregation strategies
        """
        self.field_strategies = field_strategies or FIELD_STRATEGIES.copy()

    def aggregate(self, peer_states: List[MyceliumState]) -> MyceliumState:
        """
        Aggregate multiple peer states into a single resolved state.

        The aggregation process:
        1. Sort peers by (timestamp, peer_id) for deterministic order
        2. For each field (in alphabetical order):
           - Apply the field's aggregation strategy
           - Collect the aggregated value
        3. Return the combined state

        Args:
            peer_states: List of peer states to aggregate

        Returns:
            Aggregated MyceliumState
        """
        if not peer_states:
            return MyceliumState()

        if len(peer_states) == 1:
            return peer_states[0]

        # Sort peers by (timestamp, peer_id) for deterministic order
        sorted_peers = sorted(
            peer_states,
            key=lambda p: (p.timestamp, p.peer_id)
        )

        # Aggregate each field in alphabetical order for determinism
        result = MyceliumState()

        # Process fields in fixed alphabetical order
        for field_name in sorted(self.field_strategies.keys()):
            strategy = self.field_strategies[field_name]
            values = [
                getattr(p, field_name)
                for p in sorted_peers
                if getattr(p, field_name, None) is not None
            ]

            if values:
                aggregated = self._apply_strategy(strategy, values, field_name)
                setattr(result, field_name, aggregated)

        # Set metadata
        result.peer_id = "aggregated"
        result.timestamp = time.time()

        return result

    def _apply_strategy(
        self,
        strategy: AggregationStrategy,
        values: List[Any],
        field_name: str
    ) -> Any:
        """
        Apply an aggregation strategy to a list of values.

        Args:
            strategy: The aggregation strategy to use
            values: List of values to aggregate
            field_name: Name of the field (for special handling)

        Returns:
            Aggregated value
        """
        if not values:
            return None

        if strategy == AggregationStrategy.SAFETY_MAX:
            # For burnout: max severity
            if field_name == "burnout_level":
                result = values[0]
                for v in values[1:]:
                    result = burnout_max(result, v)
                return result
            # For numeric: simple max
            return max(values)

        elif strategy == AggregationStrategy.INHERIT:
            # First value wins (peers already sorted)
            return values[0]

        elif strategy == AggregationStrategy.ADDITIVE:
            # Sum with Kahan summation for numerical stability
            float_values = [float(v) for v in values if v is not None]
            return kahan_sum(float_values)

        elif strategy == AggregationStrategy.MIN:
            return min(values)

        elif strategy == AggregationStrategy.AVERAGE:
            float_values = [float(v) for v in values if v is not None]
            if float_values:
                return kahan_sum(float_values) / len(float_values)
            return None

        # Unknown strategy - fall back to inherit
        logger.warning(f"Unknown strategy {strategy}, using INHERIT")
        return values[0]

    def aggregate_single_field(
        self,
        field_name: str,
        values: List[Any]
    ) -> Any:
        """
        Aggregate a single field from multiple values.

        Convenience method for aggregating one field at a time.

        Args:
            field_name: Name of the field
            values: List of values to aggregate

        Returns:
            Aggregated value
        """
        strategy = self.field_strategies.get(field_name, AggregationStrategy.INHERIT)
        return self._apply_strategy(strategy, values, field_name)

    def verify_determinism(
        self,
        peer_states: List[MyceliumState],
        n_trials: int = 100
    ) -> bool:
        """
        Verify that aggregation is deterministic (same inputs -> same outputs).

        ThinkingMachines [He2025] compliance verification.

        Args:
            peer_states: Peer states to test
            n_trials: Number of trials to run

        Returns:
            True if all trials produce identical checksums
        """
        checksums = set()

        for _ in range(n_trials):
            result = self.aggregate(peer_states)
            checksums.add(result.checksum())

        deterministic = len(checksums) == 1

        if not deterministic:
            logger.error(f"Non-deterministic aggregation! {len(checksums)} unique checksums")

        return deterministic


# =============================================================================
# Convenience Functions
# =============================================================================

def aggregate_burnout_levels(levels: List[str]) -> str:
    """
    Aggregate burnout levels using SAFETY-MAX.

    The result is the maximum (most severe) level.
    This ensures that if ANY peer is in RED, the group is RED.

    Args:
        levels: List of burnout level strings

    Returns:
        Maximum burnout level
    """
    if not levels:
        return "green"

    result = levels[0]
    for level in levels[1:]:
        result = burnout_max(result, level)
    return result


def aggregate_tensions(tensions: List[float]) -> float:
    """
    Aggregate epistemic tensions using ADDITIVE strategy.

    Tensions compound: if multiple peers have high tension,
    the group tension is the sum.

    Args:
        tensions: List of tension values

    Returns:
        Summed tension (capped at 1.0)
    """
    if not tensions:
        return 0.0

    # Cap at 1.0 to maintain valid range
    return min(1.0, kahan_sum(tensions))


__all__ = [
    'AggregationStrategy',
    'MyceliumState',
    'MyceliumAggregator',
    'FIELD_STRATEGIES',
    'burnout_max',
    'kahan_sum',
    'aggregate_burnout_levels',
    'aggregate_tensions',
]
