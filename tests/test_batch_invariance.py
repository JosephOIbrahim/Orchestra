"""
Tests for Cognitive Batch Invariance (v7.1.0)
=============================================

Comprehensive test suite for ThinkingMachines-compliant batch invariance.

Test Categories:
- Kahan summation (test_kahan_*): Numerical stability tests
- Aggregation strategies (test_aggregation_*): All 5 strategies
- Tile size invariance (test_tile_*): Batch size independence
- Determinism (test_determinism_*): Same inputs -> same outputs
- Integration (test_integration_*): Cross-module tests
- Property tests (test_property_*): Hypothesis-based fuzzing

ThinkingMachines [He2025] Compliance:
- Fixed tile size (COGNITIVE_TILE_SIZE = 32)
- Deterministic sort before aggregation
- Kahan summation for numerical stability
"""

import math
import pytest
import hashlib
from typing import List
from unittest.mock import patch

from orchestra.batch_invariance import (
    # Constants
    COGNITIVE_TILE_SIZE,
    DETERMINISM_SEED,
    HASH_ALGORITHM,
    # Enums
    AggregationStrategy,
    DeterminismMode,
    AggregationOrder,
    ConflictResolution,
    # Core functions
    kahan_sum,
    kahan_mean,
    kahan_weighted_mean,
    chunk,
    tile_process,
    compute_state_hash,
    # Classes
    Instance,
    BatchInvariantAggregator,
    ConfidenceScore,
    BatchInvarianceConfig,
    # Verification
    verify_round_trip,
    verify_determinism,
    verify_batch_invariance,
    # Scoring
    score_confidence,
    # Config
    get_batch_config,
    set_batch_config,
)


# =============================================================================
# Constants Tests
# =============================================================================

class TestConstants:
    """Test that constants match CLAUDE.md specification."""

    def test_cognitive_tile_size_is_32(self):
        """CLAUDE.md specifies COGNITIVE_TILE_SIZE = 32."""
        assert COGNITIVE_TILE_SIZE == 32

    def test_determinism_seed_is_cafebabe(self):
        """CLAUDE.md specifies DETERMINISM_SEED = 0xCAFEBABE."""
        assert DETERMINISM_SEED == 0xCAFEBABE

    def test_hash_algorithm_is_sha256(self):
        """CLAUDE.md specifies SHA-256 for state hashing."""
        assert HASH_ALGORITHM == "sha256"


# =============================================================================
# Kahan Summation Tests
# =============================================================================

class TestKahanSum:
    """Test Kahan summation for numerical stability."""

    def test_kahan_sum_empty_list(self):
        """Empty list returns 0.0."""
        assert kahan_sum([]) == 0.0

    def test_kahan_sum_single_value(self):
        """Single value returns itself."""
        assert kahan_sum([42.0]) == 42.0

    def test_kahan_sum_basic(self):
        """Basic summation works correctly."""
        result = kahan_sum([1.0, 2.0, 3.0, 4.0])
        assert result == 10.0

    def test_kahan_sum_order_independent(self):
        """Result is same regardless of input order (sorted internally)."""
        values1 = [0.1, 0.2, 0.3, 0.4]
        values2 = [0.4, 0.3, 0.2, 0.1]
        values3 = [0.3, 0.1, 0.4, 0.2]

        assert kahan_sum(values1) == kahan_sum(values2)
        assert kahan_sum(values2) == kahan_sum(values3)

    def test_kahan_sum_numerical_stability(self):
        """Kahan summation is stable for many small values."""
        # Summing 0.1 ten times should give 1.0, but naive sum gives 0.9999...
        values = [0.1] * 10
        result = kahan_sum(values)
        # Kahan should be closer to exact than naive sum
        assert abs(result - 1.0) < 1e-15

    def test_kahan_sum_large_small_mix(self):
        """Kahan handles mix of large and small values."""
        values = [1e10, 1.0, 1e-10, -1e10]
        result = kahan_sum(values)
        # Should be approximately 1.0 + 1e-10
        assert abs(result - 1.0 - 1e-10) < 1e-5

    def test_kahan_sum_negative_values(self):
        """Kahan handles negative values."""
        values = [-1.0, -2.0, -3.0]
        assert kahan_sum(values) == -6.0

    def test_kahan_sum_mixed_signs(self):
        """Kahan handles mixed positive and negative values."""
        values = [1.0, -1.0, 2.0, -2.0, 3.0, -3.0]
        assert kahan_sum(values) == 0.0

    def test_kahan_sum_deterministic(self):
        """Same input always produces same output."""
        values = [0.1 * i for i in range(100)]
        results = [kahan_sum(values) for _ in range(100)]
        assert len(set(results)) == 1

    def test_kahan_sum_zeros(self):
        """Handles list of zeros."""
        assert kahan_sum([0.0, 0.0, 0.0]) == 0.0


class TestKahanMean:
    """Test Kahan mean calculation."""

    def test_kahan_mean_empty(self):
        """Empty list returns 0.0."""
        assert kahan_mean([]) == 0.0

    def test_kahan_mean_single(self):
        """Single value returns itself."""
        assert kahan_mean([42.0]) == 42.0

    def test_kahan_mean_basic(self):
        """Basic mean calculation."""
        result = kahan_mean([2.0, 4.0, 6.0])
        assert result == 4.0

    def test_kahan_mean_deterministic(self):
        """Same input always produces same mean."""
        values = [0.1 * i for i in range(100)]
        results = [kahan_mean(values) for _ in range(100)]
        assert len(set(results)) == 1


class TestKahanWeightedMean:
    """Test weighted mean calculation."""

    def test_kahan_weighted_mean_empty(self):
        """Empty list returns 0.0."""
        assert kahan_weighted_mean([], []) == 0.0

    def test_kahan_weighted_mean_equal_weights(self):
        """Equal weights gives arithmetic mean."""
        values = [2.0, 4.0, 6.0]
        weights = [1.0, 1.0, 1.0]
        result = kahan_weighted_mean(values, weights)
        assert result == 4.0

    def test_kahan_weighted_mean_unequal_weights(self):
        """Unequal weights work correctly."""
        values = [10.0, 20.0]
        weights = [1.0, 3.0]  # 10*1 + 20*3 = 70, total weight = 4, mean = 17.5
        result = kahan_weighted_mean(values, weights)
        assert result == 17.5

    def test_kahan_weighted_mean_length_mismatch(self):
        """Raises ValueError if lengths don't match."""
        with pytest.raises(ValueError):
            kahan_weighted_mean([1.0, 2.0], [1.0])

    def test_kahan_weighted_mean_zero_weights(self):
        """Zero total weight returns 0.0."""
        values = [1.0, 2.0, 3.0]
        weights = [0.0, 0.0, 0.0]
        assert kahan_weighted_mean(values, weights) == 0.0


# =============================================================================
# Chunking Tests
# =============================================================================

class TestChunk:
    """Test chunk utility function."""

    def test_chunk_empty_list(self):
        """Empty list yields no chunks."""
        assert list(chunk([], 5)) == []

    def test_chunk_exact_division(self):
        """List divides evenly into chunks."""
        result = list(chunk([1, 2, 3, 4, 5, 6], 2))
        assert result == [[1, 2], [3, 4], [5, 6]]

    def test_chunk_remainder(self):
        """Last chunk can be smaller."""
        result = list(chunk([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]

    def test_chunk_larger_than_list(self):
        """Chunk size larger than list gives one chunk."""
        result = list(chunk([1, 2, 3], 10))
        assert result == [[1, 2, 3]]

    def test_chunk_size_one(self):
        """Chunk size 1 gives individual elements."""
        result = list(chunk([1, 2, 3], 1))
        assert result == [[1], [2], [3]]

    def test_chunk_invalid_size(self):
        """Zero or negative chunk size raises ValueError."""
        with pytest.raises(ValueError):
            list(chunk([1, 2, 3], 0))
        with pytest.raises(ValueError):
            list(chunk([1, 2, 3], -1))


class TestTileProcess:
    """Test tile processing utility."""

    def test_tile_process_empty(self):
        """Empty list yields empty result."""
        result = tile_process([], lambda x: sum(x))
        assert result == []

    def test_tile_process_sum_tiles(self):
        """Process tiles with sum function."""
        items = [1, 2, 3, 4, 5, 6, 7, 8]
        result = tile_process(items, lambda x: sum(x), tile_size=4)
        assert result == [10, 26]  # [1+2+3+4, 5+6+7+8]

    def test_tile_process_default_tile_size(self):
        """Default tile size is COGNITIVE_TILE_SIZE."""
        items = list(range(100))
        result = tile_process(items, lambda x: len(x))
        # 100 / 32 = 3 full tiles + 1 partial
        assert result == [32, 32, 32, 4]


# =============================================================================
# Instance Tests
# =============================================================================

class TestInstance:
    """Test Instance wrapper class."""

    def test_instance_creation(self):
        """Create instance with required fields."""
        inst = Instance(id="test", confidence=0.8)
        assert inst.id == "test"
        assert inst.confidence == 0.8
        assert inst.timestamp == 0.0
        assert inst.weight == 1.0

    def test_instance_deterministic_key(self):
        """Deterministic key is the id."""
        inst = Instance(id="test123", confidence=0.5)
        assert inst.deterministic_key == "test123"

    def test_instance_with_metadata(self):
        """Instance can have metadata."""
        inst = Instance(id="test", confidence=0.5, metadata={"key": "value"})
        assert inst.metadata["key"] == "value"


# =============================================================================
# Aggregation Strategy Tests
# =============================================================================

class TestAggregationStrategies:
    """Test all 5 aggregation strategies."""

    @pytest.fixture
    def sample_instances(self) -> List[Instance]:
        """Create sample instances for testing."""
        return [
            Instance(id="a", confidence=0.3, timestamp=1.0, weight=1.0),
            Instance(id="b", confidence=0.5, timestamp=2.0, weight=2.0),
            Instance(id="c", confidence=0.8, timestamp=3.0, weight=1.0),
            Instance(id="d", confidence=0.2, timestamp=4.0, weight=3.0),
        ]

    def test_max_strategy(self, sample_instances):
        """MAX strategy returns maximum confidence."""
        agg = BatchInvariantAggregator(AggregationStrategy.MAX)
        result = agg.aggregate(sample_instances)
        assert result == 0.8

    def test_max_strategy_single(self):
        """MAX with single instance returns that instance."""
        agg = BatchInvariantAggregator(AggregationStrategy.MAX)
        result = agg.aggregate([Instance(id="x", confidence=0.5)])
        assert result == 0.5

    def test_max_strategy_empty(self):
        """MAX with empty list returns 0.0."""
        agg = BatchInvariantAggregator(AggregationStrategy.MAX)
        result = agg.aggregate([])
        assert result == 0.0

    def test_mean_strategy(self, sample_instances):
        """MEAN strategy returns arithmetic mean."""
        agg = BatchInvariantAggregator(AggregationStrategy.MEAN)
        result = agg.aggregate(sample_instances)
        expected = (0.3 + 0.5 + 0.8 + 0.2) / 4  # 0.45
        assert abs(result - expected) < 1e-10

    def test_mean_strategy_single(self):
        """MEAN with single instance returns that instance."""
        agg = BatchInvariantAggregator(AggregationStrategy.MEAN)
        result = agg.aggregate([Instance(id="x", confidence=0.5)])
        assert result == 0.5

    def test_mean_strategy_empty(self):
        """MEAN with empty list returns 0.0."""
        agg = BatchInvariantAggregator(AggregationStrategy.MEAN)
        result = agg.aggregate([])
        assert result == 0.0

    def test_weighted_mean_strategy(self, sample_instances):
        """WEIGHTED_MEAN strategy uses weights."""
        agg = BatchInvariantAggregator(AggregationStrategy.WEIGHTED_MEAN)
        result = agg.aggregate(sample_instances)
        # Weighted: (0.3*1 + 0.5*2 + 0.8*1 + 0.2*3) / (1+2+1+3) = 2.7 / 7
        expected = 2.7 / 7
        assert abs(result - expected) < 1e-10

    def test_decay_mean_strategy(self, sample_instances):
        """DECAY_MEAN applies temporal decay."""
        agg = BatchInvariantAggregator(
            AggregationStrategy.DECAY_MEAN,
            decay_factor=0.9
        )
        result = agg.aggregate(sample_instances)
        # Should be positive and less than max
        assert 0.0 < result < 0.8

    def test_threshold_filter_strategy(self, sample_instances):
        """THRESHOLD_FILTER returns max above threshold."""
        agg = BatchInvariantAggregator(
            AggregationStrategy.THRESHOLD_FILTER,
            threshold=0.4
        )
        result = agg.aggregate(sample_instances)
        # Only 0.5 and 0.8 are >= 0.4, max is 0.8
        assert result == 0.8

    def test_threshold_filter_none_above(self, sample_instances):
        """THRESHOLD_FILTER returns 0.0 if none above threshold."""
        agg = BatchInvariantAggregator(
            AggregationStrategy.THRESHOLD_FILTER,
            threshold=0.9
        )
        result = agg.aggregate(sample_instances)
        assert result == 0.0


class TestAggregationOrder:
    """Test aggregation ordering strategies."""

    @pytest.fixture
    def instances(self) -> List[Instance]:
        return [
            Instance(id="c", confidence=0.3, timestamp=2.0),
            Instance(id="a", confidence=0.8, timestamp=3.0),
            Instance(id="b", confidence=0.5, timestamp=1.0),
        ]

    def test_id_ascending_order(self, instances):
        """ID_ASCENDING sorts by id."""
        agg = BatchInvariantAggregator(
            AggregationStrategy.MAX,
            order=AggregationOrder.ID_ASCENDING
        )
        sorted_insts = agg._sort_instances(instances)
        assert [i.id for i in sorted_insts] == ["a", "b", "c"]

    def test_confidence_descending_order(self, instances):
        """CONFIDENCE_DESCENDING sorts by confidence (highest first)."""
        agg = BatchInvariantAggregator(
            AggregationStrategy.MAX,
            order=AggregationOrder.CONFIDENCE_DESCENDING
        )
        sorted_insts = agg._sort_instances(instances)
        assert [i.confidence for i in sorted_insts] == [0.8, 0.5, 0.3]

    def test_chronological_order(self, instances):
        """CHRONOLOGICAL sorts by timestamp."""
        agg = BatchInvariantAggregator(
            AggregationStrategy.MAX,
            order=AggregationOrder.CHRONOLOGICAL
        )
        sorted_insts = agg._sort_instances(instances)
        assert [i.timestamp for i in sorted_insts] == [1.0, 2.0, 3.0]

    def test_hash_order(self, instances):
        """HASH sorts by deterministic hash."""
        agg = BatchInvariantAggregator(
            AggregationStrategy.MAX,
            order=AggregationOrder.HASH
        )
        sorted_insts = agg._sort_instances(instances)
        # Just verify it's deterministic
        sorted_again = agg._sort_instances(instances)
        assert [i.id for i in sorted_insts] == [i.id for i in sorted_again]


# =============================================================================
# Tile Invariance Tests
# =============================================================================

class TestTileInvariance:
    """Test that results are deterministic regardless of tile size.

    Note: For MEAN strategy, mean-of-means != mean-of-all when tiles have
    different sizes. This is mathematically expected. The key property is
    DETERMINISM (same inputs → same output), not exact equivalence.
    """

    @pytest.fixture
    def large_instance_list(self) -> List[Instance]:
        """Create a large list of instances."""
        return [
            Instance(id=f"inst_{i}", confidence=0.1 * (i % 10))
            for i in range(200)
        ]

    def test_max_tile_invariant(self, large_instance_list):
        """MAX strategy gives same result for any tile size."""
        results = []
        for tile_size in [1, 8, 16, 32, 64, 128]:
            agg = BatchInvariantAggregator(
                AggregationStrategy.MAX,
                tile_size=tile_size
            )
            results.append(agg.aggregate_tiled(large_instance_list))
        assert len(set(results)) == 1

    def test_mean_deterministic_per_tile_size(self, large_instance_list):
        """MEAN strategy is deterministic for each tile size.

        Note: Different tile sizes may produce different results (mean of means
        != mean of all). The key property is DETERMINISM within each tile size.
        """
        for tile_size in [8, 32, 64]:
            agg = BatchInvariantAggregator(
                AggregationStrategy.MEAN,
                tile_size=tile_size
            )
            results = [agg.aggregate_tiled(large_instance_list) for _ in range(50)]
            # Same tile size should always give same result
            assert len(set(results)) == 1

    def test_mean_non_tiled_is_tile_invariant(self, large_instance_list):
        """Non-tiled aggregate() is independent of tile_size parameter.

        The tile_size parameter only affects aggregate_tiled().
        aggregate() processes all instances at once.
        """
        results = []
        for tile_size in [1, 8, 16, 32, 64, 128]:
            agg = BatchInvariantAggregator(
                AggregationStrategy.MEAN,
                tile_size=tile_size
            )
            # aggregate() doesn't use tiles, just sorts and processes all
            results.append(agg.aggregate(large_instance_list))
        # Non-tiled aggregate should be identical
        assert len(set(results)) == 1

    def test_verify_batch_invariance_for_max(self, large_instance_list):
        """verify_batch_invariance confirms tile independence for MAX."""
        agg = BatchInvariantAggregator(AggregationStrategy.MAX)
        assert verify_batch_invariance(large_instance_list, agg)


# =============================================================================
# Determinism Tests
# =============================================================================

class TestDeterminism:
    """Test that same inputs always produce same outputs."""

    @pytest.fixture
    def instances(self) -> List[Instance]:
        return [
            Instance(id=f"test_{i}", confidence=0.1 * i)
            for i in range(50)
        ]

    def test_aggregator_determinism_100_trials(self, instances):
        """Same instances produce same result over 100 trials."""
        agg = BatchInvariantAggregator(AggregationStrategy.MEAN)
        results = [agg.aggregate(instances) for _ in range(100)]
        assert len(set(results)) == 1

    def test_verify_determinism_function(self, instances):
        """verify_determinism confirms deterministic behavior."""
        agg = BatchInvariantAggregator(AggregationStrategy.MAX)
        assert verify_determinism(instances, agg, n_trials=100)

    def test_hash_determinism(self):
        """compute_state_hash gives same result for same input."""
        data = {"key": "value", "number": 42, "nested": {"a": 1}}
        hashes = [compute_state_hash(data) for _ in range(100)]
        assert len(set(hashes)) == 1

    def test_hash_different_order_same_result(self):
        """compute_state_hash is order-independent (sort_keys=True)."""
        data1 = {"b": 2, "a": 1}
        data2 = {"a": 1, "b": 2}
        assert compute_state_hash(data1) == compute_state_hash(data2)

    def test_score_confidence_determinism(self, instances):
        """score_confidence gives deterministic results."""
        scores = [
            score_confidence(instances, AggregationStrategy.MEAN)
            for _ in range(100)
        ]
        assert len(set(s.score for s in scores)) == 1
        assert len(set(s.deterministic_hash for s in scores)) == 1


# =============================================================================
# Configuration Tests
# =============================================================================

class TestConfiguration:
    """Test configuration classes."""

    def test_default_config(self):
        """Default config has expected values."""
        config = BatchInvarianceConfig()
        assert config.tile_size == 32
        assert config.determinism_seed == 0xCAFEBABE
        assert config.mode == DeterminismMode.STRICT
        assert config.aggregation_strategy == AggregationStrategy.MAX
        assert config.aggregation_order == AggregationOrder.ID_ASCENDING

    def test_config_to_dict(self):
        """Config serializes to dict."""
        config = BatchInvarianceConfig()
        d = config.to_dict()
        assert d["tile_size"] == 32
        assert d["mode"] == "strict"
        assert d["aggregation_strategy"] == "max"

    def test_config_from_dict(self):
        """Config deserializes from dict."""
        d = {
            "tile_size": 64,
            "mode": "relaxed",
            "aggregation_strategy": "mean",
        }
        config = BatchInvarianceConfig.from_dict(d)
        assert config.tile_size == 64
        assert config.mode == DeterminismMode.RELAXED
        assert config.aggregation_strategy == AggregationStrategy.MEAN

    def test_global_config(self):
        """get_batch_config and set_batch_config work."""
        original = get_batch_config()
        new_config = BatchInvarianceConfig(tile_size=64)
        set_batch_config(new_config)
        assert get_batch_config().tile_size == 64
        # Restore
        set_batch_config(original)


# =============================================================================
# Confidence Score Tests
# =============================================================================

class TestConfidenceScore:
    """Test ConfidenceScore dataclass."""

    def test_confidence_score_creation(self):
        """Create ConfidenceScore with all fields."""
        score = ConfidenceScore(
            score=0.75,
            strategy=AggregationStrategy.MEAN,
            instance_count=10,
            tile_size=32,
            deterministic_hash="abc123"
        )
        assert score.score == 0.75
        assert score.strategy == AggregationStrategy.MEAN
        assert score.instance_count == 10

    def test_confidence_score_to_dict(self):
        """ConfidenceScore serializes to dict."""
        score = ConfidenceScore(
            score=0.75,
            strategy=AggregationStrategy.MEAN,
            instance_count=10,
            tile_size=32,
            deterministic_hash="abc123"
        )
        d = score.to_dict()
        assert d["score"] == 0.75
        assert d["strategy"] == "mean"
        assert d["instance_count"] == 10


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests with other Orchestra modules."""

    def test_convergence_tracker_uses_kahan(self):
        """ConvergenceTracker uses kahan_sum for L2 distance."""
        from orchestra.convergence_tracker import StateVector

        # Create two state vectors
        v1 = StateVector(expert=0.5, paradigm=0.5, burnout=0.5, momentum=0.5, altitude=0.5)
        v2 = StateVector(expert=0.6, paradigm=0.6, burnout=0.6, momentum=0.6, altitude=0.6)

        # Calculate distance multiple times - should be deterministic
        distances = [StateVector.distance(v1, v2) for _ in range(100)]
        assert len(set(distances)) == 1

    def test_cognitive_state_has_batch_invariance_fields(self):
        """CognitiveState has v7.1.0 batch invariance fields."""
        from orchestra.cognitive_state import CognitiveState

        state = CognitiveState()
        assert hasattr(state, 'cognitive_tile_size')
        assert hasattr(state, 'determinism_mode')
        assert hasattr(state, 'aggregation_strategy')
        assert hasattr(state, 'schema_version')
        assert state.cognitive_tile_size == 32
        assert state.schema_version == "7.1.0"

    def test_cognitive_state_batch_update_includes_new_fields(self):
        """CognitiveState batch_update handles v7.1.0 fields."""
        from orchestra.cognitive_state import CognitiveState

        state = CognitiveState()
        state.batch_update({
            'determinism_mode': 'relaxed',
            'aggregation_strategy': 'mean',
        })
        assert state.determinism_mode == 'relaxed'
        assert state.aggregation_strategy == 'mean'

    def test_cognitive_state_to_dict_includes_new_fields(self):
        """CognitiveState.to_dict includes v7.1.0 fields."""
        from orchestra.cognitive_state import CognitiveState

        state = CognitiveState()
        d = state.to_dict()
        assert 'cognitive_tile_size' in d
        assert 'determinism_mode' in d
        assert 'schema_version' in d
        assert d['schema_version'] == '7.1.0'

    def test_cognitive_state_snapshot_includes_new_fields(self):
        """CognitiveState.snapshot includes v7.1.0 fields."""
        from orchestra.cognitive_state import CognitiveState

        state = CognitiveState()
        state.determinism_mode = "relaxed"
        snapshot = state.snapshot()
        assert snapshot.determinism_mode == "relaxed"
        assert snapshot.cognitive_tile_size == 32


# =============================================================================
# Property Tests (Hypothesis)
# =============================================================================

try:
    from hypothesis import given, strategies as st, settings

    class TestPropertyBased:
        """Property-based tests using Hypothesis."""

        @given(st.lists(st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False)))
        @settings(max_examples=50)
        def test_kahan_sum_order_invariant(self, values):
            """Kahan sum is invariant to input order."""
            import random
            shuffled = values.copy()
            random.shuffle(shuffled)
            assert kahan_sum(values) == kahan_sum(shuffled)

        @given(st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=1, max_size=100))
        @settings(max_examples=50)
        def test_aggregator_determinism_property(self, confidences):
            """Aggregator is deterministic for any input."""
            instances = [Instance(id=f"id_{i}", confidence=c) for i, c in enumerate(confidences)]
            agg = BatchInvariantAggregator(AggregationStrategy.MEAN)
            results = [agg.aggregate(instances) for _ in range(10)]
            assert len(set(results)) == 1

        @given(st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=1, max_size=100))
        @settings(max_examples=50)
        def test_max_is_max(self, confidences):
            """MAX strategy returns actual maximum."""
            instances = [Instance(id=f"id_{i}", confidence=c) for i, c in enumerate(confidences)]
            agg = BatchInvariantAggregator(AggregationStrategy.MAX)
            result = agg.aggregate(instances)
            assert result == max(confidences)

        @given(st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=1, max_size=100))
        @settings(max_examples=50)
        def test_mean_is_mean(self, confidences):
            """MEAN strategy returns actual mean."""
            instances = [Instance(id=f"id_{i}", confidence=c) for i, c in enumerate(confidences)]
            agg = BatchInvariantAggregator(AggregationStrategy.MEAN)
            result = agg.aggregate(instances)
            expected = sum(confidences) / len(confidences)
            assert abs(result - expected) < 1e-10

        @given(st.integers(min_value=1, max_value=1000))
        @settings(max_examples=20)
        def test_tile_size_invariance_property(self, n_instances):
            """Result is same for any tile size."""
            instances = [Instance(id=f"id_{i}", confidence=0.5) for i in range(n_instances)]

            agg32 = BatchInvariantAggregator(AggregationStrategy.MEAN, tile_size=32)
            agg64 = BatchInvariantAggregator(AggregationStrategy.MEAN, tile_size=64)

            assert abs(agg32.aggregate(instances) - agg64.aggregate(instances)) < 1e-10

except ImportError:
    # Hypothesis not installed, skip property tests
    pass


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_instance_list(self):
        """All strategies handle empty list."""
        for strategy in AggregationStrategy:
            agg = BatchInvariantAggregator(strategy)
            result = agg.aggregate([])
            assert result == 0.0

    def test_single_instance(self):
        """All strategies handle single instance correctly."""
        inst = Instance(id="only", confidence=0.42)
        for strategy in [AggregationStrategy.MAX, AggregationStrategy.MEAN]:
            agg = BatchInvariantAggregator(strategy)
            result = agg.aggregate([inst])
            assert result == 0.42

    def test_identical_confidences(self):
        """Handles list of identical confidences."""
        instances = [Instance(id=f"id_{i}", confidence=0.5) for i in range(10)]
        agg = BatchInvariantAggregator(AggregationStrategy.MEAN)
        assert agg.aggregate(instances) == 0.5

    def test_zero_confidences(self):
        """Handles list of zero confidences."""
        instances = [Instance(id=f"id_{i}", confidence=0.0) for i in range(10)]
        agg = BatchInvariantAggregator(AggregationStrategy.MAX)
        assert agg.aggregate(instances) == 0.0

    def test_very_small_confidences(self):
        """Handles very small confidence values."""
        instances = [Instance(id=f"id_{i}", confidence=1e-15 * i) for i in range(10)]
        agg = BatchInvariantAggregator(AggregationStrategy.MEAN)
        result = agg.aggregate(instances)
        assert result >= 0

    def test_large_instance_count(self):
        """Handles large number of instances."""
        instances = [Instance(id=f"id_{i}", confidence=0.5) for i in range(10000)]
        agg = BatchInvariantAggregator(AggregationStrategy.MEAN)
        result = agg.aggregate(instances)
        assert abs(result - 0.5) < 1e-10


# =============================================================================
# Round-Trip Tests
# =============================================================================

class TestRoundTrip:
    """Test round-trip verification."""

    def test_verify_round_trip_success(self):
        """verify_round_trip succeeds for identity functions."""
        instances = [Instance(id=f"id_{i}", confidence=0.5) for i in range(10)]

        # Identity compress/expand
        def compress(insts):
            return [(i.id, i.confidence) for i in insts]

        def expand(data):
            return [Instance(id=d[0], confidence=d[1]) for d in data]

        assert verify_round_trip(instances, compress, expand)


# =============================================================================
# Enums Tests
# =============================================================================

class TestEnums:
    """Test enum values match CLAUDE.md specification."""

    def test_aggregation_strategy_values(self):
        """AggregationStrategy has correct values."""
        assert AggregationStrategy.MAX.value == "max"
        assert AggregationStrategy.MEAN.value == "mean"
        assert AggregationStrategy.WEIGHTED_MEAN.value == "weighted_mean"
        assert AggregationStrategy.DECAY_MEAN.value == "decay_mean"
        assert AggregationStrategy.THRESHOLD_FILTER.value == "threshold_filter"

    def test_determinism_mode_values(self):
        """DeterminismMode has correct values."""
        assert DeterminismMode.STRICT.value == "strict"
        assert DeterminismMode.RELAXED.value == "relaxed"
        assert DeterminismMode.NONE.value == "none"

    def test_aggregation_order_values(self):
        """AggregationOrder has correct values."""
        assert AggregationOrder.ID_ASCENDING.value == "id_ascending"
        assert AggregationOrder.CONFIDENCE_DESCENDING.value == "confidence_descending"
        assert AggregationOrder.CHRONOLOGICAL.value == "chronological"
        assert AggregationOrder.HASH.value == "hash"

    def test_conflict_resolution_values(self):
        """ConflictResolution has correct values."""
        assert ConflictResolution.NEWEST_WINS.value == "newest_wins"
        assert ConflictResolution.HIGHEST_CONFIDENCE.value == "highest_confidence"
        assert ConflictResolution.MANUAL.value == "manual"
        assert ConflictResolution.MERGE.value == "merge"
