"""
Tests for Mycelium Aggregator
=============================

Tests the aggregation strategies for peer-to-peer state sharing.

Key focus:
- SAFETY-MAX for burnout levels
- Determinism (same inputs -> same outputs)
- Kahan summation for additive aggregation
"""

import pytest
import time

from orchestra.mycelium_aggregator import (
    MyceliumAggregator,
    MyceliumState,
    AggregationStrategy,
    FIELD_STRATEGIES,
    burnout_max,
    kahan_sum,
    aggregate_burnout_levels,
    aggregate_tensions,
)


class TestBurnoutMax:
    """Tests for SAFETY-MAX burnout aggregation."""

    def test_green_green_is_green(self):
        """Two green levels result in green."""
        assert burnout_max("green", "green") == "green"

    def test_green_yellow_is_yellow(self):
        """Yellow is higher than green."""
        assert burnout_max("green", "yellow") == "yellow"

    def test_yellow_green_is_yellow(self):
        """Order doesn't matter."""
        assert burnout_max("yellow", "green") == "yellow"

    def test_any_red_is_red(self):
        """Red always wins (SAFETY-MAX)."""
        assert burnout_max("green", "red") == "red"
        assert burnout_max("yellow", "red") == "red"
        assert burnout_max("orange", "red") == "red"
        assert burnout_max("red", "green") == "red"

    def test_orange_yellow_is_orange(self):
        """Orange beats yellow."""
        assert burnout_max("orange", "yellow") == "orange"

    def test_case_insensitive(self):
        """Should handle case variations."""
        assert burnout_max("GREEN", "YELLOW") == "yellow"
        assert burnout_max("Green", "Yellow") == "yellow"

    def test_none_handling(self):
        """Should handle None as green."""
        assert burnout_max(None, "yellow") == "yellow"
        assert burnout_max("yellow", None) == "yellow"


class TestKahanSummation:
    """Tests for batch-invariant Kahan summation."""

    def test_empty_list(self):
        """Empty list returns 0."""
        assert kahan_sum([]) == 0.0

    def test_single_value(self):
        """Single value returns itself."""
        assert kahan_sum([3.14]) == 3.14

    def test_simple_sum(self):
        """Basic sum works correctly."""
        assert kahan_sum([1.0, 2.0, 3.0]) == 6.0

    def test_order_independence(self):
        """Result is independent of input order (sorted internally)."""
        values1 = [1.5, 2.3, 0.7, 4.1]
        values2 = [4.1, 0.7, 2.3, 1.5]  # Shuffled
        assert kahan_sum(values1) == kahan_sum(values2)

    def test_numerical_stability(self):
        """Handles large/small value combinations."""
        # This would lose precision with naive sum
        values = [1e10, 1.0, -1e10]
        result = kahan_sum(values)
        assert abs(result - 1.0) < 1e-6

    @pytest.mark.parametrize("trial", range(100))
    def test_determinism_100_trials(self, trial):
        """Same inputs produce same output across 100 trials."""
        values = [0.1, 0.2, 0.3, 0.4, 0.5]
        expected = kahan_sum(values)
        assert kahan_sum(values) == expected


class TestMyceliumState:
    """Tests for MyceliumState dataclass."""

    def test_default_values(self):
        """Default state has expected values."""
        state = MyceliumState()
        assert state.burnout_level is None
        assert state.momentum_phase is None
        assert state.epistemic_tension is None
        assert state.peer_id == ""

    def test_serialization_roundtrip(self):
        """to_dict/from_dict preserves all fields."""
        original = MyceliumState(
            burnout_level="yellow",
            momentum_phase="building",
            epistemic_tension=0.5,
            peer_id="peer_123"
        )
        serialized = original.to_dict()
        restored = MyceliumState.from_dict(serialized)

        assert restored.burnout_level == "yellow"
        assert restored.momentum_phase == "building"
        assert restored.epistemic_tension == 0.5
        assert restored.peer_id == "peer_123"

    def test_checksum_determinism(self):
        """Same state produces same checksum."""
        state = MyceliumState(burnout_level="orange", peer_id="test")
        checksums = [state.checksum() for _ in range(100)]
        assert len(set(checksums)) == 1


class TestMyceliumAggregator:
    """Tests for the aggregator class."""

    def test_empty_list_returns_empty_state(self):
        """Empty peer list returns empty state."""
        aggregator = MyceliumAggregator()
        result = aggregator.aggregate([])
        assert result.burnout_level is None

    def test_single_peer_passes_through(self):
        """Single peer's values pass through unchanged."""
        aggregator = MyceliumAggregator()
        peer = MyceliumState(
            burnout_level="yellow",
            momentum_phase="rolling",
            epistemic_tension=0.3,
            peer_id="solo"
        )
        result = aggregator.aggregate([peer])
        assert result.burnout_level == "yellow"
        assert result.momentum_phase == "rolling"
        assert result.epistemic_tension == 0.3

    def test_safety_max_burnout(self):
        """Burnout uses SAFETY-MAX (highest severity wins)."""
        aggregator = MyceliumAggregator()
        peers = [
            MyceliumState(burnout_level="green", peer_id="a"),
            MyceliumState(burnout_level="orange", peer_id="b"),
            MyceliumState(burnout_level="yellow", peer_id="c"),
        ]
        result = aggregator.aggregate(peers)
        assert result.burnout_level == "orange"

    def test_safety_max_red_always_wins(self):
        """If ANY peer is RED, result is RED."""
        aggregator = MyceliumAggregator()
        peers = [
            MyceliumState(burnout_level="green", peer_id="a"),
            MyceliumState(burnout_level="green", peer_id="b"),
            MyceliumState(burnout_level="red", peer_id="c"),
            MyceliumState(burnout_level="green", peer_id="d"),
        ]
        result = aggregator.aggregate(peers)
        assert result.burnout_level == "red"

    def test_inherit_first_non_none(self):
        """INHERIT strategy takes first non-None value."""
        aggregator = MyceliumAggregator()
        peers = [
            MyceliumState(momentum_phase=None, peer_id="a", timestamp=1.0),
            MyceliumState(momentum_phase="rolling", peer_id="b", timestamp=2.0),
            MyceliumState(momentum_phase="peak", peer_id="c", timestamp=3.0),
        ]
        result = aggregator.aggregate(peers)
        # First non-None in timestamp order is "rolling"
        assert result.momentum_phase == "rolling"

    def test_additive_tensions_sum(self):
        """ADDITIVE strategy sums tensions."""
        aggregator = MyceliumAggregator()
        peers = [
            MyceliumState(epistemic_tension=0.2, peer_id="a"),
            MyceliumState(epistemic_tension=0.3, peer_id="b"),
            MyceliumState(epistemic_tension=0.1, peer_id="c"),
        ]
        result = aggregator.aggregate(peers)
        assert abs(result.epistemic_tension - 0.6) < 0.001

    def test_deterministic_ordering(self):
        """Aggregation is deterministic regardless of input order."""
        aggregator = MyceliumAggregator()

        # Create peers with different timestamps
        peers1 = [
            MyceliumState(burnout_level="yellow", peer_id="b", timestamp=2.0),
            MyceliumState(burnout_level="green", peer_id="a", timestamp=1.0),
            MyceliumState(burnout_level="orange", peer_id="c", timestamp=3.0),
        ]

        # Same peers, different list order
        peers2 = [
            MyceliumState(burnout_level="green", peer_id="a", timestamp=1.0),
            MyceliumState(burnout_level="orange", peer_id="c", timestamp=3.0),
            MyceliumState(burnout_level="yellow", peer_id="b", timestamp=2.0),
        ]

        result1 = aggregator.aggregate(peers1)
        result2 = aggregator.aggregate(peers2)

        assert result1.burnout_level == result2.burnout_level
        assert result1.checksum() == result2.checksum()

    @pytest.mark.parametrize("trial", range(100))
    def test_determinism_100_trials(self, trial):
        """Aggregation produces identical results across 100 trials."""
        aggregator = MyceliumAggregator()
        peers = [
            MyceliumState(burnout_level="yellow", epistemic_tension=0.1, peer_id="a"),
            MyceliumState(burnout_level="orange", epistemic_tension=0.2, peer_id="b"),
            MyceliumState(burnout_level="green", epistemic_tension=0.3, peer_id="c"),
        ]

        result = aggregator.aggregate(peers)
        expected_checksum = result.checksum()

        # Re-run aggregation
        result2 = aggregator.aggregate(peers)
        assert result2.checksum() == expected_checksum

    def test_verify_determinism_method(self):
        """verify_determinism correctly validates determinism."""
        aggregator = MyceliumAggregator()
        peers = [
            MyceliumState(burnout_level="orange", peer_id="a"),
            MyceliumState(burnout_level="yellow", peer_id="b"),
        ]

        assert aggregator.verify_determinism(peers, n_trials=50) is True


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_aggregate_burnout_levels_empty(self):
        """Empty list returns green."""
        assert aggregate_burnout_levels([]) == "green"

    def test_aggregate_burnout_levels_max(self):
        """Returns maximum severity."""
        levels = ["green", "yellow", "orange", "yellow"]
        assert aggregate_burnout_levels(levels) == "orange"

    def test_aggregate_tensions_empty(self):
        """Empty list returns 0."""
        assert aggregate_tensions([]) == 0.0

    def test_aggregate_tensions_caps_at_one(self):
        """Tensions are capped at 1.0."""
        tensions = [0.5, 0.4, 0.3, 0.2]  # Sum = 1.4
        assert aggregate_tensions(tensions) == 1.0

    def test_aggregate_tensions_normal(self):
        """Normal tensions sum correctly."""
        tensions = [0.1, 0.2, 0.15]
        result = aggregate_tensions(tensions)
        assert abs(result - 0.45) < 0.001


class TestFieldStrategies:
    """Tests for field strategy configuration."""

    def test_burnout_is_safety_max(self):
        """Burnout uses SAFETY-MAX strategy."""
        assert FIELD_STRATEGIES["burnout_level"] == AggregationStrategy.SAFETY_MAX

    def test_momentum_is_inherit(self):
        """Momentum uses INHERIT strategy."""
        assert FIELD_STRATEGIES["momentum_phase"] == AggregationStrategy.INHERIT

    def test_tension_is_additive(self):
        """Tension uses ADDITIVE strategy."""
        assert FIELD_STRATEGIES["epistemic_tension"] == AggregationStrategy.ADDITIVE
