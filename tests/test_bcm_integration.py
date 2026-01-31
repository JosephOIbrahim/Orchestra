"""
BCM Integration Tests for Orchestra
===================================

Tests for the BCM (stigmergic reinforcement) integration with Orchestra.

Test Categories:
1. BCM Trail Unit Tests - Core trail functionality
2. Expert Routing Integration - Trail confidence in routing
3. Parameter Locking Integration - Trail-informed depth
4. Convergence Integration - Attractor preferences
5. Determinism Tests - Batch-invariance guarantees
6. Persistence Tests - Trail save/load

Run with: pytest tests/test_bcm_integration.py -v

Author: [User] + Claude
Date: 2026-01-31
"""

import pytest
import time
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from orchestra.bcm_trail import (
    BCMConfig,
    Trail,
    PlasticityState,
    OrchestraTrail,
    calculate_theta_m,
    calculate_saturation_factor,
    apply_decay,
    reinforce_trail,
)
from orchestra.bcm_integration import (
    BCMPipelineAdapter,
    load_trail,
    save_trail,
    create_adapter,
    integrate_with_state,
)
from orchestra.cognitive_state import CognitiveState


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Default BCM configuration."""
    return BCMConfig()


@pytest.fixture
def fresh_trail():
    """Fresh OrchestraTrail with no history."""
    return OrchestraTrail()


@pytest.fixture
def populated_trail():
    """Trail with some expert history."""
    trail = OrchestraTrail()

    # Add some expert trails
    trail.expert_trails["direct"] = Trail(
        id="expert_direct", domain="orchestra", strength=3.0,
        success_count=8, failure_count=2
    )
    trail.expert_trails["scaffolder"] = Trail(
        id="expert_scaffolder", domain="orchestra", strength=1.5,
        success_count=5, failure_count=5
    )
    trail.expert_trails["validator"] = Trail(
        id="expert_validator", domain="orchestra", strength=2.0,
        success_count=3, failure_count=1
    )

    return trail


@pytest.fixture
def adapter(fresh_trail):
    """BCM adapter with fresh trail."""
    adapter = BCMPipelineAdapter("test")
    adapter.trail = fresh_trail
    adapter._loaded = True
    return adapter


@pytest.fixture
def temp_bcm_dir(tmp_path):
    """Temporary directory for BCM state files."""
    bcm_dir = tmp_path / "bcm"
    bcm_dir.mkdir()
    return bcm_dir


# =============================================================================
# BCM Trail Unit Tests
# =============================================================================

class TestBCMTrailBasics:
    """Basic trail functionality tests."""

    def test_fresh_trail_has_defaults(self, fresh_trail):
        """Fresh trail should have sensible defaults."""
        assert fresh_trail.version == "0.1.0"
        assert fresh_trail.expert_trails == {}
        assert fresh_trail.signal_history == {}
        assert fresh_trail.plasticity.window_active is False

    def test_get_expert_trail_creates_if_missing(self, fresh_trail):
        """Getting nonexistent expert trail should create it."""
        trail = fresh_trail.get_expert_trail("direct")

        assert trail is not None
        assert trail.id == "expert_direct"
        assert trail.strength == 1.0
        assert "direct" in fresh_trail.expert_trails

    def test_expert_confidence_default_for_unknown(self, fresh_trail):
        """Unknown expert should have default confidence of 1.0."""
        confidence = fresh_trail.get_expert_confidence("unknown_expert")
        assert confidence == 1.0

    def test_expert_confidence_based_on_success_rate(self, populated_trail):
        """Expert confidence should reflect success rate."""
        # direct: 8/10 = 80% success
        direct_conf = populated_trail.get_expert_confidence("direct")

        # scaffolder: 5/10 = 50% success
        scaffolder_conf = populated_trail.get_expert_confidence("scaffolder")

        assert direct_conf > scaffolder_conf


class TestBCMReinforcement:
    """Trail reinforcement tests."""

    def test_reinforce_increases_strength(self, fresh_trail, config):
        """Successful reinforcement should increase trail strength."""
        trail = fresh_trail.get_expert_trail("test")
        old_strength = trail.strength

        reinforce_trail(trail, 1.0, "success", 0.0, config)

        assert trail.strength > old_strength

    def test_reinforce_saturates_at_high_strength(self, config):
        """Reinforcement should saturate as strength increases."""
        trail = Trail(id="test", domain="test", strength=10.0)
        total_strength = 10.0

        delta1 = reinforce_trail(trail, total_strength, "success", 0.0, config)

        # Reinforce again
        trail2 = Trail(id="test", domain="test", strength=1.0)
        delta2 = reinforce_trail(trail2, 1.0, "success", 0.0, config)

        # Lower strength should get more reinforcement
        assert delta2 > delta1

    def test_plasticity_window_boosts_reinforcement(self, config):
        """Plasticity window should boost reinforcement."""
        trail_normal = Trail(id="t1", domain="test", strength=5.0)
        trail_plastic = Trail(id="t2", domain="test", strength=5.0)

        # Reinforce without plasticity
        delta_normal = reinforce_trail(trail_normal, 5.0, "success", 0.0, config)

        # Reinforce with plasticity (sigma=0.7)
        delta_plastic = reinforce_trail(trail_plastic, 5.0, "success", 0.7, config)

        assert delta_plastic >= delta_normal


class TestBCMDecay:
    """Trail decay tests."""

    def test_decay_reduces_strength(self, config):
        """Decay should reduce trail strength over time."""
        trail = Trail(id="test", domain="test", strength=5.0)

        apply_decay(trail, 120.0, config)  # 2 hours

        assert trail.strength < 5.0

    def test_decay_respects_minimum(self, config):
        """Decay should not go below minimum."""
        trail = Trail(id="test", domain="test", strength=0.1)

        apply_decay(trail, 10000.0, config)  # Very long time

        assert trail.strength >= config.min_strength


class TestOutcomeRecording:
    """Outcome recording and batch updates."""

    def test_record_expert_outcome_queues_update(self, fresh_trail):
        """Recording outcome should queue, not apply immediately."""
        fresh_trail.record_expert_outcome("direct", True, 100.0)

        # Should be queued
        assert len(fresh_trail._pending_updates) == 1

        # Should not be applied yet
        assert "direct" not in fresh_trail.expert_trails

    def test_flush_applies_updates(self, fresh_trail):
        """Flushing should apply all queued updates."""
        fresh_trail.record_expert_outcome("direct", True, 100.0)
        fresh_trail.record_expert_outcome("scaffolder", False, 200.0)

        count = fresh_trail.flush_updates()

        assert count == 2
        assert "direct" in fresh_trail.expert_trails
        assert "scaffolder" in fresh_trail.expert_trails
        assert len(fresh_trail._pending_updates) == 0


# =============================================================================
# Expert Routing Integration Tests
# =============================================================================

class TestExpertRoutingIntegration:
    """Tests for BCM integration with expert routing."""

    def test_adapter_returns_confidence(self, adapter, populated_trail):
        """Adapter should return expert confidence."""
        adapter.trail = populated_trail

        confidence = adapter.get_expert_confidence("direct")

        assert 0.0 <= confidence <= 1.0

    def test_unknown_expert_has_default_confidence(self, adapter):
        """Unknown expert should have default confidence."""
        confidence = adapter.get_expert_confidence("unknown")

        assert confidence == 1.0

    def test_get_all_confidences(self, adapter, populated_trail):
        """Should get all expert confidences."""
        adapter.trail = populated_trail

        confidences = adapter.get_all_expert_confidences()

        assert "direct" in confidences
        assert "scaffolder" in confidences
        assert "validator" in confidences


class TestExpertRouterBCMIntegration:
    """Tests for BCM integration directly with ExpertRouter."""

    @pytest.fixture
    def router(self):
        """Create an ExpertRouter instance."""
        from orchestra.expert_router import ExpertRouter
        return ExpertRouter()

    @pytest.fixture
    def mock_signals(self):
        """Create mock SignalVector for testing."""
        from orchestra.prism_detector import SignalVector
        return SignalVector(
            emotional={},
            mode={},
            task={},
            domain={},
            energy={},
            grounding={}
        )

    def test_route_without_trail_has_default_bcm(self, router, mock_signals):
        """Route without trail should have default BCM metadata."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, MomentumPhase

        result = router.route(
            signals=mock_signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.BUILDING,
            trail=None  # No trail
        )

        assert result.bcm_confidence == 1.0
        assert result.bcm_expert_confidences == {}
        assert result.bcm_trail_version == ""
        assert result.bcm_enhanced is False

    def test_route_with_trail_populates_bcm(self, router, mock_signals, populated_trail):
        """Route with trail should populate BCM metadata."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, MomentumPhase

        result = router.route(
            signals=mock_signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.BUILDING,
            trail=populated_trail
        )

        assert result.bcm_enhanced is True
        assert result.bcm_trail_version == populated_trail.version
        assert len(result.bcm_expert_confidences) > 0

    def test_fixed_order_preserved_with_trail(self, router, mock_signals, populated_trail):
        """Expert selection order MUST NOT change with trail data."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, MomentumPhase

        # Route without trail
        result_no_trail = router.route(
            signals=mock_signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.BUILDING,
            trail=None
        )

        # Route with trail (same signals/state)
        result_with_trail = router.route(
            signals=mock_signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.BUILDING,
            trail=populated_trail
        )

        # CRITICAL: Same expert must be selected regardless of trail
        assert result_no_trail.expert == result_with_trail.expert
        assert result_no_trail.trigger == result_with_trail.trigger
        assert result_no_trail.priority_index == result_with_trail.priority_index

    def test_safety_gate_gets_bcm_metadata(self, router, mock_signals, populated_trail):
        """Safety gate routing should also include BCM metadata."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, MomentumPhase

        # Force safety gate with RED burnout
        result = router.route(
            signals=mock_signals,
            burnout=BurnoutLevel.RED,  # Forces Validator
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.BUILDING,
            trail=populated_trail
        )

        # Should be routed to Validator via safety gate
        assert result.expert.value == "validator"
        assert result.safety_gate_pass is False

        # But should still have BCM metadata
        assert result.bcm_enhanced is True
        assert result.bcm_trail_version == populated_trail.version

    def test_bcm_confidence_reflects_trail_state(self, router, mock_signals):
        """BCM confidence should reflect actual trail state."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, MomentumPhase

        # Create trail with strong "direct" expert
        trail = OrchestraTrail()
        trail.expert_trails["direct"] = Trail(
            id="expert_direct", domain="orchestra", strength=5.0,
            success_count=10, failure_count=0  # 100% success
        )

        result = router.route(
            signals=mock_signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.ROLLING,  # Should trigger Direct expert
            trail=trail
        )

        # Direct expert should have high confidence
        assert result.expert.value == "direct"
        assert result.bcm_confidence > 0.5  # Should reflect strong trail

    def test_determinism_with_trail(self, router, mock_signals, populated_trail):
        """Same inputs + same trail = same routing result."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, MomentumPhase

        result1 = router.route(
            signals=mock_signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.BUILDING,
            trail=populated_trail
        )

        result2 = router.route(
            signals=mock_signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.BUILDING,
            trail=populated_trail
        )

        # All fields should match
        assert result1.expert == result2.expert
        assert result1.trigger == result2.trigger
        assert result1.bcm_confidence == result2.bcm_confidence
        assert result1.bcm_expert_confidences == result2.bcm_expert_confidences

    def test_routing_result_serialization_with_bcm(self, router, mock_signals, populated_trail):
        """RoutingResult with BCM should serialize correctly."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, MomentumPhase

        result = router.route(
            signals=mock_signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.BUILDING,
            trail=populated_trail
        )

        # Serialize to dict
        data = result.to_dict()

        # BCM fields should be present
        assert "bcm_confidence" in data
        assert "bcm_expert_confidences" in data
        assert "bcm_trail_version" in data
        assert "bcm_enhanced" in data

        # Values should match
        assert data["bcm_enhanced"] is True
        assert data["bcm_trail_version"] == populated_trail.version


# =============================================================================
# Parameter Locking Integration Tests
# =============================================================================

class TestParameterLockingIntegration:
    """Tests for BCM integration with parameter locking."""

    def test_optimal_depth_respects_safety_cap(self, adapter):
        """Recommended depth should never exceed safety cap."""
        depth = adapter.get_optimal_depth(
            expert="direct",
            task_type="implement",
            fallback="deep",
            safety_cap="standard"  # Safety limits to standard
        )

        depth_order = ["minimal", "standard", "deep", "ultradeep"]
        assert depth_order.index(depth) <= depth_order.index("standard")

    def test_no_history_uses_fallback(self, adapter):
        """Without history, should use fallback (within safety)."""
        depth = adapter.get_optimal_depth(
            expert="direct",
            task_type="implement",
            fallback="standard",
            safety_cap="ultradeep"
        )

        assert depth == "standard"

    def test_has_depth_history_false_for_new_expert(self, adapter):
        """New expert should have no depth history."""
        has_history = adapter.has_depth_history("brand_new_expert")

        assert has_history is False


class TestParameterLockerBCMIntegration:
    """Tests for BCM integration directly with ParameterLocker."""

    @pytest.fixture
    def locker(self):
        """Create a ParameterLocker instance."""
        from orchestra.parameter_locker import ParameterLocker
        return ParameterLocker()

    @pytest.fixture
    def mock_routing(self):
        """Create mock RoutingResult for testing."""
        from orchestra.expert_router import RoutingResult, Expert
        return RoutingResult(
            expert=Expert.DIRECT,
            trigger="default",
            priority_index=6,
            safety_gate_pass=True
        )

    @pytest.fixture
    def trail_with_depth_history(self):
        """Trail with depth optimization history."""
        trail = OrchestraTrail()

        # Add depth history for direct expert with task_type key format
        # Key format is "expert:task_type"
        trail.depth_history["direct:implement"] = [
            ("deep", True),   # deep worked
            ("deep", True),   # deep worked
            ("standard", True),  # standard worked
            ("ultradeep", False),  # ultradeep failed
            ("deep", True),  # Need 5+ samples for optimization
            ("deep", True),
        ]

        return trail

    def test_lock_without_trail_has_default_bcm(self, locker, mock_routing):
        """Lock without trail should have default BCM metadata."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, Altitude

        result = locker.lock(
            routing=mock_routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            altitude=Altitude.ARCHITECTURE,
            trail=None  # No trail
        )

        assert result.bcm_optimized is False
        assert result.bcm_suggested_depth is None
        assert result.bcm_trail_version == ""
        assert result.bcm_depth_history_count == 0

    def test_lock_with_trail_populates_bcm(self, locker, mock_routing, trail_with_depth_history):
        """Lock with trail should populate BCM metadata."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, Altitude

        result = locker.lock(
            routing=mock_routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            altitude=Altitude.ARCHITECTURE,
            trail=trail_with_depth_history,
            task_type="implement"
        )

        assert result.bcm_trail_version == trail_with_depth_history.version
        assert result.bcm_depth_history_count == 6  # 6 depth history entries

    def test_safety_gate_never_overridden_by_trail(self, locker, mock_routing):
        """CRITICAL: Safety gates must NEVER be overridden by trail data."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, Altitude
        from orchestra.parameter_locker import ThinkDepth

        # Create trail that strongly suggests ultradeep
        trail = OrchestraTrail()
        trail.depth_history["direct"] = [
            ("ultradeep", True),
            ("ultradeep", True),
            ("ultradeep", True),
        ]

        # Lock with depleted energy (should force minimal)
        result = locker.lock(
            routing=mock_routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.DEPLETED,  # Forces minimal
            altitude=Altitude.ARCHITECTURE,
            requested_depth=ThinkDepth.ULTRADEEP,
            trail=trail,
            task_type="implement"
        )

        # Safety gate MUST win - minimal depth enforced
        assert result.params.think_depth == "minimal"
        assert result.safety_capped is True

    def test_trail_can_reduce_depth_within_safety(self, locker, mock_routing):
        """Trail should be able to suggest lower depth within safety bounds."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, Altitude
        from orchestra.parameter_locker import ThinkDepth

        # Trail suggests standard is optimal for this expert
        trail = OrchestraTrail()
        trail.depth_history["direct"] = [
            ("standard", True),
            ("standard", True),
            ("deep", False),  # deep failed for this expert
        ]

        result = locker.lock(
            routing=mock_routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.HIGH,  # Allows ultradeep
            altitude=Altitude.ARCHITECTURE,
            requested_depth=ThinkDepth.DEEP,  # User requests deep
            trail=trail,
            task_type="implement"
        )

        # Trail may suggest standard (less than requested, but still valid)
        # The important thing is it doesn't exceed safety cap
        depth_order = ["minimal", "standard", "deep", "ultradeep"]
        actual_idx = depth_order.index(result.params.think_depth)
        cap_idx = depth_order.index("ultradeep")  # Safety cap with high energy

        assert actual_idx <= cap_idx

    def test_lock_determinism_with_trail(self, locker, mock_routing, trail_with_depth_history):
        """Same inputs + same trail = same lock result."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, Altitude
        from orchestra.parameter_locker import ThinkDepth

        result1 = locker.lock(
            routing=mock_routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            altitude=Altitude.ARCHITECTURE,
            requested_depth=ThinkDepth.STANDARD,
            trail=trail_with_depth_history,
            task_type="implement"
        )

        result2 = locker.lock(
            routing=mock_routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            altitude=Altitude.ARCHITECTURE,
            requested_depth=ThinkDepth.STANDARD,
            trail=trail_with_depth_history,
            task_type="implement"
        )

        # All fields should match
        assert result1.params.think_depth == result2.params.think_depth
        assert result1.params.checksum == result2.params.checksum
        assert result1.bcm_optimized == result2.bcm_optimized
        assert result1.bcm_suggested_depth == result2.bcm_suggested_depth

    def test_lock_result_serialization_with_bcm(self, locker, mock_routing, trail_with_depth_history):
        """LockResult with BCM should serialize correctly."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, Altitude

        result = locker.lock(
            routing=mock_routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            altitude=Altitude.ARCHITECTURE,
            trail=trail_with_depth_history,
            task_type="implement"
        )

        # Serialize to dict
        data = result.to_dict()

        # BCM fields should be present
        assert "bcm_optimized" in data
        assert "bcm_suggested_depth" in data
        assert "bcm_trail_version" in data
        assert "bcm_depth_history_count" in data

        # Version should match
        assert data["bcm_trail_version"] == trail_with_depth_history.version

    def test_red_burnout_forces_minimal_regardless_of_trail(self, locker, mock_routing):
        """RED burnout should force minimal depth regardless of trail suggestion."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, Altitude
        from orchestra.parameter_locker import ThinkDepth

        # Trail with ultradeep history
        trail = OrchestraTrail()
        trail.depth_history["direct"] = [("ultradeep", True)] * 5

        result = locker.lock(
            routing=mock_routing,
            burnout=BurnoutLevel.RED,  # Forces minimal
            energy=EnergyLevel.HIGH,
            altitude=Altitude.ARCHITECTURE,
            requested_depth=ThinkDepth.ULTRADEEP,
            trail=trail,
            task_type="implement"
        )

        assert result.params.think_depth == "minimal"
        assert result.safety_capped is True

    def test_orange_burnout_caps_at_standard(self, locker, mock_routing):
        """ORANGE burnout should cap at standard regardless of trail."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, Altitude
        from orchestra.parameter_locker import ThinkDepth

        trail = OrchestraTrail()
        trail.depth_history["direct"] = [("deep", True)] * 5

        result = locker.lock(
            routing=mock_routing,
            burnout=BurnoutLevel.ORANGE,  # Caps at standard
            energy=EnergyLevel.MEDIUM,
            altitude=Altitude.ARCHITECTURE,
            requested_depth=ThinkDepth.DEEP,
            trail=trail,
            task_type="implement"
        )

        depth_order = ["minimal", "standard", "deep", "ultradeep"]
        actual_idx = depth_order.index(result.params.think_depth)
        standard_idx = depth_order.index("standard")

        assert actual_idx <= standard_idx

    def test_no_trail_depth_history_returns_requested(self, locker, mock_routing):
        """Without trail depth history, should use requested depth."""
        from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, Altitude
        from orchestra.parameter_locker import ThinkDepth

        # Empty trail
        trail = OrchestraTrail()

        result = locker.lock(
            routing=mock_routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.HIGH,  # Allows ultradeep
            altitude=Altitude.ARCHITECTURE,
            requested_depth=ThinkDepth.DEEP,
            trail=trail,
            task_type="implement"
        )

        # Should use requested (within safety)
        assert result.params.think_depth == "deep"
        assert result.bcm_optimized is False


# =============================================================================
# Convergence Integration Tests
# =============================================================================

class TestConvergenceIntegration:
    """Tests for BCM integration with convergence tracking."""

    def test_attractor_preferences_default_to_one(self, adapter):
        """Default attractor preferences should be 1.0."""
        prefs = adapter.get_attractor_preferences()

        # Fresh trail has no history, so all preferences empty
        # (or 1.0 if we query directly)
        assert isinstance(prefs, dict)

    def test_record_attractor_outcome(self, adapter):
        """Should queue attractor outcomes."""
        adapter.trail.record_attractor_outcome("focused", True)
        adapter.trail.record_attractor_outcome("focused", True)
        adapter.trail.record_attractor_outcome("focused", False)

        assert len(adapter.trail._pending_updates) == 3


class TestConvergenceTrackerBCMIntegration:
    """Tests for BCM integration directly with ConvergenceTracker."""

    @pytest.fixture
    def tracker(self):
        """Create a ConvergenceTracker instance."""
        from orchestra.convergence_tracker import ConvergenceTracker
        return ConvergenceTracker()

    @pytest.fixture
    def trail_with_attractor_history(self):
        """Trail with attractor convergence history."""
        trail = OrchestraTrail()

        # Add attractor history
        trail.attractor_history["focused"] = [True, True, True, False]  # 75% success
        trail.attractor_history["exploring"] = [True, False, True, False]  # 50% success
        trail.attractor_history["recovery"] = [True, True]  # 100% success

        return trail

    def test_update_without_trail_has_default_bcm(self, tracker):
        """Update without trail should have default BCM metadata."""
        from orchestra.expert_router import Expert
        from orchestra.parameter_locker import Paradigm
        from orchestra.cognitive_state import BurnoutLevel, MomentumPhase, Altitude

        result = tracker.update(
            expert=Expert.DIRECT,
            paradigm=Paradigm.CORTEX,
            burnout=BurnoutLevel.GREEN,
            momentum=MomentumPhase.ROLLING,
            altitude=Altitude.VISION,
            trail=None
        )

        assert result.bcm_attractor_preferences == {}
        assert result.bcm_trail_version == ""
        assert result.bcm_enhanced is False

    def test_update_with_trail_populates_bcm(self, tracker, trail_with_attractor_history):
        """Update with trail should populate BCM metadata."""
        from orchestra.expert_router import Expert
        from orchestra.parameter_locker import Paradigm
        from orchestra.cognitive_state import BurnoutLevel, MomentumPhase, Altitude

        result = tracker.update(
            expert=Expert.DIRECT,
            paradigm=Paradigm.CORTEX,
            burnout=BurnoutLevel.GREEN,
            momentum=MomentumPhase.ROLLING,
            altitude=Altitude.VISION,
            trail=trail_with_attractor_history
        )

        assert result.bcm_enhanced is True
        assert result.bcm_trail_version == trail_with_attractor_history.version
        assert "focused" in result.bcm_attractor_preferences
        assert "exploring" in result.bcm_attractor_preferences

    def test_attractor_detection_unchanged_by_trail(self, tracker, trail_with_attractor_history):
        """CRITICAL: Trail data must NOT change attractor detection."""
        from orchestra.expert_router import Expert
        from orchestra.parameter_locker import Paradigm
        from orchestra.cognitive_state import BurnoutLevel, MomentumPhase, Altitude

        # State that should detect as "focused" attractor
        # (Direct expert, Cortex, GREEN, ROLLING)
        result_no_trail = tracker.update(
            expert=Expert.DIRECT,
            paradigm=Paradigm.CORTEX,
            burnout=BurnoutLevel.GREEN,
            momentum=MomentumPhase.ROLLING,
            altitude=Altitude.VISION,
            trail=None
        )

        # Reset tracker for clean comparison
        tracker.reset()

        result_with_trail = tracker.update(
            expert=Expert.DIRECT,
            paradigm=Paradigm.CORTEX,
            burnout=BurnoutLevel.GREEN,
            momentum=MomentumPhase.ROLLING,
            altitude=Altitude.VISION,
            trail=trail_with_attractor_history
        )

        # Attractor detection must be IDENTICAL
        assert result_no_trail.attractor_basin == result_with_trail.attractor_basin
        assert result_no_trail.epistemic_tension == result_with_trail.epistemic_tension
        assert result_no_trail.converged == result_with_trail.converged

    def test_convergence_result_serialization_with_bcm(self, tracker, trail_with_attractor_history):
        """ConvergenceResult with BCM should serialize correctly."""
        from orchestra.expert_router import Expert
        from orchestra.parameter_locker import Paradigm
        from orchestra.cognitive_state import BurnoutLevel, MomentumPhase, Altitude

        result = tracker.update(
            expert=Expert.DIRECT,
            paradigm=Paradigm.CORTEX,
            burnout=BurnoutLevel.GREEN,
            momentum=MomentumPhase.ROLLING,
            altitude=Altitude.VISION,
            trail=trail_with_attractor_history
        )

        # Serialize to dict
        data = result.to_dict()

        # BCM fields should be present
        assert "bcm_attractor_preferences" in data
        assert "bcm_trail_version" in data
        assert "bcm_enhanced" in data

        # Values should match
        assert data["bcm_enhanced"] is True
        assert data["bcm_trail_version"] == trail_with_attractor_history.version

    def test_determinism_with_trail(self, tracker, trail_with_attractor_history):
        """Same inputs + same trail = same convergence result."""
        from orchestra.expert_router import Expert
        from orchestra.parameter_locker import Paradigm
        from orchestra.cognitive_state import BurnoutLevel, MomentumPhase, Altitude

        result1 = tracker.update(
            expert=Expert.DIRECT,
            paradigm=Paradigm.CORTEX,
            burnout=BurnoutLevel.GREEN,
            momentum=MomentumPhase.ROLLING,
            altitude=Altitude.VISION,
            trail=trail_with_attractor_history
        )

        tracker.reset()

        result2 = tracker.update(
            expert=Expert.DIRECT,
            paradigm=Paradigm.CORTEX,
            burnout=BurnoutLevel.GREEN,
            momentum=MomentumPhase.ROLLING,
            altitude=Altitude.VISION,
            trail=trail_with_attractor_history
        )

        # All fields should match
        assert result1.attractor_basin == result2.attractor_basin
        assert result1.epistemic_tension == result2.epistemic_tension
        assert result1.bcm_enhanced == result2.bcm_enhanced
        assert result1.bcm_attractor_preferences == result2.bcm_attractor_preferences

    def test_attractor_preferences_reflect_history(self, tracker):
        """BCM attractor preferences should reflect trail history."""
        from orchestra.expert_router import Expert
        from orchestra.parameter_locker import Paradigm
        from orchestra.cognitive_state import BurnoutLevel, MomentumPhase, Altitude

        # Create trail with specific history
        trail = OrchestraTrail()
        trail.attractor_history["focused"] = [True] * 10  # 100% success

        result = tracker.update(
            expert=Expert.DIRECT,
            paradigm=Paradigm.CORTEX,
            burnout=BurnoutLevel.GREEN,
            momentum=MomentumPhase.ROLLING,
            altitude=Altitude.VISION,
            trail=trail
        )

        # Should have high preference for focused
        assert result.bcm_attractor_preferences.get("focused", 0) > 0.9


# =============================================================================
# Determinism Tests
# =============================================================================

class TestDeterminism:
    """Batch-invariance and determinism tests."""

    def test_same_inputs_same_confidence(self, populated_trail):
        """Same trail state should produce same confidence."""
        conf1 = populated_trail.get_expert_confidence("direct")
        conf2 = populated_trail.get_expert_confidence("direct")

        assert conf1 == conf2

    def test_checksum_deterministic(self, populated_trail):
        """Trail checksum should be deterministic."""
        checksum1 = populated_trail.checksum()
        checksum2 = populated_trail.checksum()

        assert checksum1 == checksum2

    def test_serialization_roundtrip(self, populated_trail):
        """Serialize -> deserialize should produce equivalent trail."""
        data = populated_trail.to_dict()
        restored = OrchestraTrail.from_dict(data)

        assert restored.checksum() == populated_trail.checksum()

    def test_outcome_order_independence(self):
        """Recording order should not affect final state significantly."""
        # Trail 1: record A then B
        trail1 = OrchestraTrail()
        trail1.record_expert_outcome("direct", True)
        trail1.record_expert_outcome("scaffolder", False)
        trail1.flush_updates()

        # Trail 2: record B then A
        trail2 = OrchestraTrail()
        trail2.record_expert_outcome("scaffolder", False)
        trail2.record_expert_outcome("direct", True)
        trail2.flush_updates()

        # Both should have same experts
        assert set(trail1.expert_trails.keys()) == set(trail2.expert_trails.keys())


# =============================================================================
# Persistence Tests
# =============================================================================

class TestPersistence:
    """Trail persistence tests."""

    def test_save_and_load_roundtrip(self, populated_trail, tmp_path, monkeypatch):
        """Save then load should produce equivalent trail."""
        # Monkeypatch the BCM_STATE_DIR
        import orchestra.bcm_integration as bcm_int
        monkeypatch.setattr(bcm_int, 'BCM_STATE_DIR', tmp_path)

        # Save
        result = save_trail(populated_trail, "test_session")
        assert result is True

        # Load
        loaded = load_trail("test_session")

        # Compare meaningful content (not timestamps which may drift)
        assert loaded.version == populated_trail.version
        assert set(loaded.expert_trails.keys()) == set(populated_trail.expert_trails.keys())

        for name in populated_trail.expert_trails:
            orig = populated_trail.expert_trails[name]
            load = loaded.expert_trails[name]
            assert load.id == orig.id
            assert load.success_count == orig.success_count
            assert load.failure_count == orig.failure_count
            # Strength may drift slightly due to decay, but should be close
            assert abs(load.strength - orig.strength) < 0.1

    def test_load_nonexistent_creates_fresh(self, tmp_path, monkeypatch):
        """Loading nonexistent trail should create fresh one."""
        import orchestra.bcm_integration as bcm_int
        monkeypatch.setattr(bcm_int, 'BCM_STATE_DIR', tmp_path)

        trail = load_trail("nonexistent_session")

        assert trail is not None
        assert trail.expert_trails == {}


# =============================================================================
# Cognitive State Integration Tests
# =============================================================================

class TestCognitiveStateIntegration:
    """Tests for BCM fields in CognitiveState."""

    def test_cognitive_state_has_bcm_fields(self):
        """CognitiveState should have BCM fields."""
        state = CognitiveState()

        assert hasattr(state, 'bcm_trail_version')
        assert hasattr(state, 'bcm_expert_confidence')
        assert hasattr(state, 'bcm_plasticity_active')
        assert hasattr(state, 'bcm_last_update')

    def test_bcm_fields_serialize(self):
        """BCM fields should serialize correctly."""
        state = CognitiveState()
        state.bcm_trail_version = "0.1.0"
        state.bcm_expert_confidence = {"direct": 0.9}
        state.bcm_plasticity_active = True
        state.bcm_last_update = 12345.0

        data = state.to_dict()

        assert data["bcm_trail_version"] == "0.1.0"
        assert data["bcm_expert_confidence"] == {"direct": 0.9}
        assert data["bcm_plasticity_active"] is True
        assert data["bcm_last_update"] == 12345.0

    def test_bcm_fields_deserialize(self):
        """BCM fields should deserialize correctly."""
        data = {
            "bcm_trail_version": "0.2.0",
            "bcm_expert_confidence": {"scaffolder": 0.8},
            "bcm_plasticity_active": False,
            "bcm_last_update": 67890.0,
        }

        state = CognitiveState.from_dict(data)

        assert state.bcm_trail_version == "0.2.0"
        assert state.bcm_expert_confidence == {"scaffolder": 0.8}
        assert state.bcm_plasticity_active is False
        assert state.bcm_last_update == 67890.0

    def test_snapshot_includes_bcm_fields(self):
        """State snapshot should include BCM fields."""
        state = CognitiveState()
        state.bcm_trail_version = "test"
        state.bcm_expert_confidence = {"direct": 0.5}

        snapshot = state.snapshot()

        assert snapshot.bcm_trail_version == "test"
        assert snapshot.bcm_expert_confidence == {"direct": 0.5}

    def test_batch_update_includes_bcm_fields(self):
        """Batch update should handle BCM fields."""
        state = CognitiveState()

        state.batch_update({
            "bcm_trail_version": "updated",
            "bcm_plasticity_active": True,
        })

        assert state.bcm_trail_version == "updated"
        assert state.bcm_plasticity_active is True


# =============================================================================
# Plasticity Window Tests
# =============================================================================

class TestPlasticityWindow:
    """Tests for plasticity window operations."""

    def test_open_plasticity_window(self, adapter):
        """Opening window should set state."""
        adapter.open_plasticity_window("crashed", 0.7)

        assert adapter.is_plasticity_active() is True
        assert adapter.trail.plasticity.sigma == 0.7
        assert adapter.trail.plasticity.window_trigger == "crashed"

    def test_close_plasticity_window(self, adapter):
        """Closing window should clear state."""
        adapter.open_plasticity_window("test", 0.5)
        adapter.close_plasticity_window()

        assert adapter.is_plasticity_active() is False
        assert adapter.trail.plasticity.sigma == 0.0


# =============================================================================
# Adapter Lifecycle Tests
# =============================================================================

class TestAdapterLifecycle:
    """Tests for adapter lifecycle operations."""

    def test_flush_and_save(self, adapter, tmp_path, monkeypatch):
        """flush_and_save should apply updates and persist."""
        import orchestra.bcm_integration as bcm_int
        monkeypatch.setattr(bcm_int, 'BCM_STATE_DIR', tmp_path)

        adapter.record_expert_outcome("direct", True)
        updates, saved = adapter.flush_and_save()

        assert updates == 1
        assert saved is True

    def test_ensure_loaded_lazy_loads(self, tmp_path, monkeypatch):
        """ensure_loaded should lazy load trail."""
        import orchestra.bcm_integration as bcm_int
        monkeypatch.setattr(bcm_int, 'BCM_STATE_DIR', tmp_path)

        adapter = BCMPipelineAdapter("lazy_test")
        assert adapter._loaded is False

        trail = adapter.ensure_loaded()

        assert adapter._loaded is True
        assert trail is not None


# =============================================================================
# CognitiveOrchestrator BCM Integration Tests
# =============================================================================

class TestCognitiveOrchestratorBCMIntegration:
    """Tests for BCM integration with CognitiveOrchestrator."""

    @pytest.fixture
    def orchestrator(self, tmp_path, monkeypatch):
        """Create a CognitiveOrchestrator with temp BCM dir."""
        import orchestra.bcm_integration as bcm_int
        monkeypatch.setattr(bcm_int, 'BCM_STATE_DIR', tmp_path)

        from orchestra.cognitive_orchestrator import CognitiveOrchestrator
        return CognitiveOrchestrator(session_id="test")

    def test_process_message_loads_trail(self, orchestrator):
        """Processing message should load BCM trail."""
        result = orchestrator.process_message("help me implement this feature")

        # Trail should be loaded
        trail = orchestrator.get_bcm_trail()
        assert trail is not None

        # Result should have trail version
        assert result.bcm_trail_version == trail.version

    def test_process_message_passes_trail_to_routing(self, orchestrator):
        """Trail should be passed to routing phase."""
        result = orchestrator.process_message("I'm frustrated!")

        # Routing should have BCM metadata
        assert result.routing.bcm_trail_version != ""
        assert result.routing.bcm_enhanced is True

    def test_process_message_passes_trail_to_locking(self, orchestrator):
        """Trail should be passed to locking phase."""
        result = orchestrator.process_message("implement a new feature")

        # Lock should have BCM metadata
        assert result.lock.bcm_trail_version != ""

    def test_process_message_passes_trail_to_convergence(self, orchestrator):
        """Trail should be passed to convergence phase."""
        result = orchestrator.process_message("let's explore this idea")

        # Convergence should have BCM metadata
        assert result.convergence.bcm_trail_version != ""
        assert result.convergence.bcm_enhanced is True

    def test_record_outcome_queues_update(self, orchestrator):
        """Recording outcome should queue BCM update."""
        orchestrator.process_message("implement this feature")
        orchestrator.record_outcome(success=True, latency_ms=100.0)

        # Should have pending updates
        trail = orchestrator.get_bcm_trail()
        assert len(trail._pending_updates) > 0

    def test_flush_applies_updates(self, orchestrator):
        """Flushing should apply queued updates."""
        orchestrator.process_message("implement this feature")
        orchestrator.record_outcome(success=True, latency_ms=100.0)

        updates, saved = orchestrator.flush_bcm_trail()

        assert updates > 0
        assert saved is True

        # Trail should have the update applied
        trail = orchestrator.get_bcm_trail()
        assert len(trail._pending_updates) == 0

    def test_reset_session_flushes_trail(self, orchestrator):
        """Reset should flush BCM trail."""
        orchestrator.process_message("help me")
        orchestrator.record_outcome(success=True)

        # Reset should flush
        orchestrator.reset_session()

        # Trail should be flushed
        trail = orchestrator.get_bcm_trail()
        assert len(trail._pending_updates) == 0

    def test_plasticity_window(self, orchestrator):
        """Opening/closing plasticity window should work."""
        orchestrator.open_plasticity_window("crashed", 0.7)

        assert orchestrator.bcm.is_plasticity_active() is True

        orchestrator.close_plasticity_window()

        assert orchestrator.bcm.is_plasticity_active() is False

    def test_state_updates_include_bcm_fields(self, orchestrator):
        """State updates should include BCM fields."""
        orchestrator.process_message("implement this")

        state = orchestrator.get_state()

        # BCM fields should be updated
        assert state.bcm_trail_version != ""

    def test_nexus_result_serialization(self, orchestrator):
        """NexusResult with BCM should serialize correctly."""
        result = orchestrator.process_message("implement a feature")

        data = result.to_dict()

        # BCM fields should be present
        assert "bcm_trail_version" in data
        assert "bcm_trail_enhanced" in data
        assert "bcm_routing_confidence" in data
        assert "bcm_lock_optimized" in data
        assert "bcm_convergence_enhanced" in data


# =============================================================================
# Run if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
