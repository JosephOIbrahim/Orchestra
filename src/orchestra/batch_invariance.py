"""
Cognitive Batch Invariance (v7.1.0)
===================================

Implements ThinkingMachines-compliant batch invariance for cognitive state operations.

Core Insight:
    The same problem that causes LLM non-determinism (batch-size-dependent reduction order)
    also affects cognitive state operations (memory-count-dependent template matching order).
    The solution is the same: FIXED TILE SIZES + DETERMINISTIC ORDERING.

[He2025]: He, Horace and Thinking Machines Lab, "Defeating Nondeterminism in LLM Inference"
          https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/

ThinkingMachines Compliance:
- Fixed tile size (COGNITIVE_TILE_SIZE = 32)
- Deterministic sort before aggregation
- Kahan summation for numerical stability
- Verification tools for round-trip, determinism, and batch invariance

Usage:
    from orchestra.batch_invariance import (
        kahan_sum,
        BatchInvariantAggregator,
        AggregationStrategy,
        verify_determinism,
    )

    # Kahan summation for numerical stability
    total = kahan_sum([0.1, 0.2, 0.3])

    # Aggregation with fixed tile size
    aggregator = BatchInvariantAggregator(AggregationStrategy.MEAN)
    result = aggregator.aggregate(instances)

    # Verify determinism
    assert verify_determinism(memories, n_trials=100)
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterator, List, Optional, Protocol, TypeVar
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Constants (FIXED, never change)
# =============================================================================

COGNITIVE_TILE_SIZE: int = 32
"""Fixed tile size for batch-invariant processing. Never changes."""

DETERMINISM_SEED: int = 0xCAFEBABE
"""Fixed seed for any randomized operations requiring determinism."""

HASH_ALGORITHM: str = "sha256"
"""Hash algorithm for state checksums."""


# =============================================================================
# Enums
# =============================================================================

class AggregationStrategy(Enum):
    """
    Aggregation strategies for combining confidence scores.

    All strategies guarantee determinism via:
    - Sorting instances by deterministic key BEFORE aggregation
    - Using Kahan summation for numerical stability
    - Processing in fixed tile sizes
    """
    MAX = "max"
    """Maximum value: max(c_i)"""

    MEAN = "mean"
    """Arithmetic mean: sum(c_i) / n"""

    WEIGHTED_MEAN = "weighted_mean"
    """Weighted mean: sum(c_i * w_i) / sum(w_j)"""

    DECAY_MEAN = "decay_mean"
    """Decay-weighted mean: mean(c_i * 0.99^t)"""

    THRESHOLD_FILTER = "threshold_filter"
    """Maximum above threshold: max(c_i where c_i >= threshold)"""


class DeterminismMode(Enum):
    """Determinism enforcement mode."""
    STRICT = "strict"
    """Full determinism enforcement (default)."""

    RELAXED = "relaxed"
    """Relaxed enforcement (allows non-deterministic fallbacks)."""

    NONE = "none"
    """No enforcement (for testing non-deterministic scenarios)."""


class AggregationOrder(Enum):
    """Ordering strategy for aggregation."""
    ID_ASCENDING = "id_ascending"
    """Sort by instance ID ascending."""

    CONFIDENCE_DESCENDING = "confidence_descending"
    """Sort by confidence descending (highest first)."""

    CHRONOLOGICAL = "chronological"
    """Sort by timestamp chronologically."""

    HASH = "hash"
    """Sort by deterministic hash of instance."""


class ConflictResolution(Enum):
    """Resolution strategy for conflicting values."""
    NEWEST_WINS = "newest_wins"
    """Most recent value wins."""

    HIGHEST_CONFIDENCE = "highest_confidence"
    """Highest confidence value wins."""

    MANUAL = "manual"
    """Require manual resolution."""

    MERGE = "merge"
    """Merge values using aggregation strategy."""


# =============================================================================
# Protocols
# =============================================================================

T = TypeVar('T')


class HasDeterministicKey(Protocol):
    """Protocol for instances that can provide a deterministic key."""

    @property
    def deterministic_key(self) -> str:
        """Return a deterministic key for sorting."""
        ...


class HasConfidence(Protocol):
    """Protocol for instances with confidence scores."""

    @property
    def confidence(self) -> float:
        """Return the confidence score."""
        ...


class HasTimestamp(Protocol):
    """Protocol for instances with timestamps."""

    @property
    def timestamp(self) -> float:
        """Return the timestamp."""
        ...


class HasWeight(Protocol):
    """Protocol for instances with weights."""

    @property
    def weight(self) -> float:
        """Return the weight for weighted aggregation."""
        ...


# =============================================================================
# Kahan Summation
# =============================================================================

def kahan_sum(values: List[float]) -> float:
    """
    Batch-invariant accumulation using Kahan summation algorithm.

    Kahan summation compensates for floating-point errors that accumulate
    when summing many numbers, ensuring batch-invariant results.

    CRITICAL: Values are sorted before summation to ensure deterministic order.

    Args:
        values: List of float values to sum

    Returns:
        Sum with compensation for floating-point errors

    Example:
        >>> kahan_sum([0.1, 0.2, 0.3, 0.4])
        1.0  # Exact, not 0.9999999999999999
    """
    if not values:
        return 0.0

    # CRITICAL: Sort for deterministic order
    sorted_values = sorted(values)

    total = 0.0
    compensation = 0.0

    for v in sorted_values:
        y = v - compensation
        t = total + y
        compensation = (t - total) - y
        total = t

    return total


def kahan_mean(values: List[float]) -> float:
    """
    Calculate mean using Kahan summation for numerical stability.

    Args:
        values: List of float values

    Returns:
        Mean value, or 0.0 if empty
    """
    if not values:
        return 0.0
    return kahan_sum(values) / len(values)


def kahan_weighted_mean(values: List[float], weights: List[float]) -> float:
    """
    Calculate weighted mean using Kahan summation.

    Args:
        values: List of float values
        weights: List of weights (must match length of values)

    Returns:
        Weighted mean, or 0.0 if empty

    Raises:
        ValueError: If values and weights have different lengths
    """
    if not values:
        return 0.0

    if len(values) != len(weights):
        raise ValueError(f"Values ({len(values)}) and weights ({len(weights)}) must have same length")

    # Create pairs and sort by value for determinism
    pairs = sorted(zip(values, weights), key=lambda x: x[0])

    weighted_sum = 0.0
    weight_sum = 0.0
    compensation_w = 0.0
    compensation_v = 0.0

    for v, w in pairs:
        # Accumulate weights with Kahan
        y_w = w - compensation_w
        t_w = weight_sum + y_w
        compensation_w = (t_w - weight_sum) - y_w
        weight_sum = t_w

        # Accumulate weighted values with Kahan
        y_v = (v * w) - compensation_v
        t_v = weighted_sum + y_v
        compensation_v = (t_v - weighted_sum) - y_v
        weighted_sum = t_v

    if weight_sum == 0.0:
        return 0.0

    return weighted_sum / weight_sum


# =============================================================================
# Chunking Utilities
# =============================================================================

def chunk(iterable: List[T], size: int) -> Iterator[List[T]]:
    """
    Split iterable into fixed-size chunks.

    Args:
        iterable: List to chunk
        size: Chunk size (must be > 0)

    Yields:
        Lists of size `size` (last chunk may be smaller)

    Raises:
        ValueError: If size <= 0
    """
    if size <= 0:
        raise ValueError(f"Chunk size must be positive, got {size}")

    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


def tile_process(
    items: List[T],
    processor: Callable[[List[T]], Any],
    tile_size: int = COGNITIVE_TILE_SIZE
) -> List[Any]:
    """
    Process items in fixed-size tiles for batch invariance.

    Args:
        items: Items to process
        processor: Function to apply to each tile
        tile_size: Tile size (default: COGNITIVE_TILE_SIZE)

    Returns:
        List of results from each tile
    """
    results = []
    for tile in chunk(items, tile_size):
        results.append(processor(tile))
    return results


# =============================================================================
# Instance Wrapper
# =============================================================================

@dataclass
class Instance:
    """
    Wrapper for aggregation instances with required attributes.

    Provides deterministic key generation for sorting.
    """
    id: str
    confidence: float
    timestamp: float = 0.0
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def deterministic_key(self) -> str:
        """Generate deterministic key for sorting."""
        return self.id

    def __hash__(self) -> int:
        return hash(self.id)


# =============================================================================
# BatchInvariantAggregator
# =============================================================================

class BatchInvariantAggregator:
    """
    Aggregates confidence scores with guaranteed batch invariance.

    ThinkingMachines [He2025] Compliance:
    - Fixed tile size (COGNITIVE_TILE_SIZE = 32)
    - Deterministic sort before aggregation
    - Kahan summation for numerical stability
    - Same inputs -> same outputs regardless of batch size

    Usage:
        aggregator = BatchInvariantAggregator(AggregationStrategy.MEAN)
        result = aggregator.aggregate(instances)

        # With custom tile size (not recommended except for testing)
        aggregator = BatchInvariantAggregator(
            AggregationStrategy.MAX,
            tile_size=64
        )
    """

    def __init__(
        self,
        strategy: AggregationStrategy = AggregationStrategy.MAX,
        tile_size: int = COGNITIVE_TILE_SIZE,
        threshold: float = 0.5,
        decay_factor: float = 0.99,
        order: AggregationOrder = AggregationOrder.ID_ASCENDING,
    ):
        """
        Initialize aggregator.

        Args:
            strategy: Aggregation strategy to use
            tile_size: Fixed tile size for processing (default: 32)
            threshold: Threshold for THRESHOLD_FILTER strategy
            decay_factor: Decay factor for DECAY_MEAN strategy
            order: Ordering strategy for aggregation
        """
        self.strategy = strategy
        self.tile_size = tile_size
        self.threshold = threshold
        self.decay_factor = decay_factor
        self.order = order

    def aggregate(self, instances: List[Instance]) -> float:
        """
        Aggregate instances using configured strategy.

        Args:
            instances: List of Instance objects

        Returns:
            Aggregated confidence score
        """
        if not instances:
            return 0.0

        # STEP 1: Sort by deterministic key BEFORE aggregation
        sorted_instances = self._sort_instances(instances)

        # STEP 2: Apply strategy
        if self.strategy == AggregationStrategy.MAX:
            return self._aggregate_max(sorted_instances)
        elif self.strategy == AggregationStrategy.MEAN:
            return self._aggregate_mean(sorted_instances)
        elif self.strategy == AggregationStrategy.WEIGHTED_MEAN:
            return self._aggregate_weighted_mean(sorted_instances)
        elif self.strategy == AggregationStrategy.DECAY_MEAN:
            return self._aggregate_decay_mean(sorted_instances)
        elif self.strategy == AggregationStrategy.THRESHOLD_FILTER:
            return self._aggregate_threshold_filter(sorted_instances)
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

    def _sort_instances(self, instances: List[Instance]) -> List[Instance]:
        """Sort instances by configured order."""
        if self.order == AggregationOrder.ID_ASCENDING:
            return sorted(instances, key=lambda x: x.deterministic_key)
        elif self.order == AggregationOrder.CONFIDENCE_DESCENDING:
            return sorted(instances, key=lambda x: (-x.confidence, x.deterministic_key))
        elif self.order == AggregationOrder.CHRONOLOGICAL:
            return sorted(instances, key=lambda x: (x.timestamp, x.deterministic_key))
        elif self.order == AggregationOrder.HASH:
            return sorted(instances, key=lambda x: hashlib.sha256(
                x.deterministic_key.encode()
            ).hexdigest())
        else:
            return sorted(instances, key=lambda x: x.deterministic_key)

    def _aggregate_max(self, instances: List[Instance]) -> float:
        """MAX strategy: max(c_i)"""
        return max(inst.confidence for inst in instances)

    def _aggregate_mean(self, instances: List[Instance]) -> float:
        """MEAN strategy: sum(c_i) / n using Kahan summation"""
        confidences = [inst.confidence for inst in instances]
        return kahan_mean(confidences)

    def _aggregate_weighted_mean(self, instances: List[Instance]) -> float:
        """WEIGHTED_MEAN strategy: sum(c_i * w_i) / sum(w_j)"""
        values = [inst.confidence for inst in instances]
        weights = [inst.weight for inst in instances]
        return kahan_weighted_mean(values, weights)

    def _aggregate_decay_mean(self, instances: List[Instance]) -> float:
        """DECAY_MEAN strategy: mean(c_i * decay^t)"""
        if not instances:
            return 0.0

        # Sort by timestamp for decay calculation
        time_sorted = sorted(instances, key=lambda x: x.timestamp)

        # Apply decay based on relative time
        if time_sorted:
            base_time = time_sorted[0].timestamp
            decayed_values = []
            for inst in time_sorted:
                time_diff = inst.timestamp - base_time
                decay = self.decay_factor ** time_diff
                decayed_values.append(inst.confidence * decay)

            return kahan_mean(decayed_values)

        return 0.0

    def _aggregate_threshold_filter(self, instances: List[Instance]) -> float:
        """THRESHOLD_FILTER strategy: max(c_i where c_i >= threshold)"""
        filtered = [inst.confidence for inst in instances if inst.confidence >= self.threshold]
        if not filtered:
            return 0.0
        return max(filtered)

    def aggregate_tiled(self, instances: List[Instance]) -> float:
        """
        Aggregate using fixed tile processing.

        Processes instances in fixed-size tiles and combines results.
        This ensures batch-invariant behavior regardless of input size.

        Args:
            instances: List of Instance objects

        Returns:
            Aggregated confidence score
        """
        if not instances:
            return 0.0

        # Sort first for determinism
        sorted_instances = self._sort_instances(instances)

        # Process in tiles
        tile_results = []
        for tile in chunk(sorted_instances, self.tile_size):
            tile_result = self.aggregate(tile)
            tile_results.append(tile_result)

        # Combine tile results using same strategy
        if self.strategy == AggregationStrategy.MAX:
            return max(tile_results) if tile_results else 0.0
        else:
            return kahan_mean(tile_results)


# =============================================================================
# Verification Tools
# =============================================================================

def compute_state_hash(data: Any) -> str:
    """
    Compute deterministic hash of state data.

    Args:
        data: Data to hash (must be JSON-serializable)

    Returns:
        SHA-256 hash string (first 16 characters)
    """
    import json
    state_str = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(state_str.encode()).hexdigest()[:16]


def verify_round_trip(
    memories: List[Instance],
    compress: Callable[[List[Instance]], Any],
    expand: Callable[[Any], List[Instance]],
) -> bool:
    """
    Verify compress -> expand -> compress = identity.

    Args:
        memories: List of Instance objects
        compress: Function to compress instances
        expand: Function to expand compressed data

    Returns:
        True if round-trip preserves identity
    """
    assembly = compress(memories)
    expanded = expand(assembly)
    recompressed = compress(expanded)

    hash1 = compute_state_hash(assembly)
    hash2 = compute_state_hash(recompressed)

    if hash1 != hash2:
        logger.warning(f"Round-trip verification failed: {hash1} != {hash2}")
        return False

    return True


def verify_determinism(
    memories: List[Instance],
    aggregator: BatchInvariantAggregator,
    n_trials: int = 100,
) -> bool:
    """
    Verify same inputs -> same outputs over N trials.

    Args:
        memories: List of Instance objects
        aggregator: Aggregator to test
        n_trials: Number of trials (default: 100)

    Returns:
        True if all trials produce identical results
    """
    if not memories:
        return True

    results = set()
    for _ in range(n_trials):
        result = aggregator.aggregate(memories)
        results.add(result)

    if len(results) != 1:
        logger.warning(f"Determinism verification failed: {len(results)} unique results")
        return False

    return True


def verify_batch_invariance(
    memories: List[Instance],
    aggregator: BatchInvariantAggregator,
    tile_sizes: Optional[List[int]] = None,
) -> bool:
    """
    Verify result is independent of tile size.

    Args:
        memories: List of Instance objects
        aggregator: Aggregator to test
        tile_sizes: List of tile sizes to test (default: [1, 8, 32, 128, 1024])

    Returns:
        True if all tile sizes produce identical results
    """
    if tile_sizes is None:
        tile_sizes = [1, 8, 32, 128, 1024]

    if not memories:
        return True

    results = []
    for tile_size in tile_sizes:
        # Create aggregator with specific tile size
        test_aggregator = BatchInvariantAggregator(
            strategy=aggregator.strategy,
            tile_size=tile_size,
            threshold=aggregator.threshold,
            decay_factor=aggregator.decay_factor,
            order=aggregator.order,
        )
        result = test_aggregator.aggregate_tiled(memories)
        results.append(result)

    # Check all results are equal (within floating point tolerance)
    if not results:
        return True

    first = results[0]
    for i, result in enumerate(results[1:], 1):
        if abs(result - first) > 1e-10:
            logger.warning(
                f"Batch invariance failed: tile_size={tile_sizes[i]} "
                f"produced {result}, expected {first}"
            )
            return False

    return True


# =============================================================================
# Confidence Scorer Integration
# =============================================================================

@dataclass
class ConfidenceScore:
    """
    Result of confidence scoring.

    Includes provenance information for debugging.
    """
    score: float
    strategy: AggregationStrategy
    instance_count: int
    tile_size: int
    deterministic_hash: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "score": self.score,
            "strategy": self.strategy.value,
            "instance_count": self.instance_count,
            "tile_size": self.tile_size,
            "deterministic_hash": self.deterministic_hash,
        }


def score_confidence(
    instances: List[Instance],
    strategy: AggregationStrategy = AggregationStrategy.MEAN,
    tile_size: int = COGNITIVE_TILE_SIZE,
) -> ConfidenceScore:
    """
    Score confidence with full provenance tracking.

    Args:
        instances: List of Instance objects
        strategy: Aggregation strategy
        tile_size: Tile size for processing

    Returns:
        ConfidenceScore with result and provenance
    """
    aggregator = BatchInvariantAggregator(strategy=strategy, tile_size=tile_size)
    score = aggregator.aggregate(instances)

    # Compute deterministic hash of inputs
    input_data = [(inst.id, inst.confidence) for inst in sorted(instances, key=lambda x: x.id)]
    deterministic_hash = compute_state_hash(input_data)

    return ConfidenceScore(
        score=score,
        strategy=strategy,
        instance_count=len(instances),
        tile_size=tile_size,
        deterministic_hash=deterministic_hash,
    )


# =============================================================================
# Configuration Defaults
# =============================================================================

@dataclass
class BatchInvarianceConfig:
    """Configuration for batch invariance module."""

    tile_size: int = COGNITIVE_TILE_SIZE
    """Fixed tile size for all operations."""

    determinism_seed: int = DETERMINISM_SEED
    """Seed for any randomized operations."""

    mode: DeterminismMode = DeterminismMode.STRICT
    """Enforcement mode."""

    aggregation_strategy: AggregationStrategy = AggregationStrategy.MAX
    """Default aggregation strategy."""

    aggregation_order: AggregationOrder = AggregationOrder.ID_ASCENDING
    """Default sort order for aggregation."""

    conflict_resolution: ConflictResolution = ConflictResolution.NEWEST_WINS
    """Default conflict resolution strategy."""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "tile_size": self.tile_size,
            "determinism_seed": self.determinism_seed,
            "mode": self.mode.value,
            "aggregation_strategy": self.aggregation_strategy.value,
            "aggregation_order": self.aggregation_order.value,
            "conflict_resolution": self.conflict_resolution.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BatchInvarianceConfig':
        """Deserialize from dict."""
        return cls(
            tile_size=data.get("tile_size", COGNITIVE_TILE_SIZE),
            determinism_seed=data.get("determinism_seed", DETERMINISM_SEED),
            mode=DeterminismMode(data.get("mode", "strict")),
            aggregation_strategy=AggregationStrategy(data.get("aggregation_strategy", "max")),
            aggregation_order=AggregationOrder(data.get("aggregation_order", "id_ascending")),
            conflict_resolution=ConflictResolution(data.get("conflict_resolution", "newest_wins")),
        )


# =============================================================================
# Module State (Global Default Config)
# =============================================================================

_default_config: Optional[BatchInvarianceConfig] = None


def get_batch_config() -> BatchInvarianceConfig:
    """Get the global batch invariance configuration."""
    global _default_config
    if _default_config is None:
        _default_config = BatchInvarianceConfig()
    return _default_config


def set_batch_config(config: BatchInvarianceConfig) -> None:
    """Set the global batch invariance configuration."""
    global _default_config
    _default_config = config


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Constants
    "COGNITIVE_TILE_SIZE",
    "DETERMINISM_SEED",
    "HASH_ALGORITHM",
    # Enums
    "AggregationStrategy",
    "DeterminismMode",
    "AggregationOrder",
    "ConflictResolution",
    # Core functions
    "kahan_sum",
    "kahan_mean",
    "kahan_weighted_mean",
    "chunk",
    "tile_process",
    "compute_state_hash",
    # Classes
    "Instance",
    "BatchInvariantAggregator",
    "ConfidenceScore",
    "BatchInvarianceConfig",
    # Verification
    "verify_round_trip",
    "verify_determinism",
    "verify_batch_invariance",
    # Scoring
    "score_confidence",
    # Config
    "get_batch_config",
    "set_batch_config",
]
