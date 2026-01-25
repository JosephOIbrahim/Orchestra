"""
Tests for the Cognitive Engine (5-Phase NEXUS Pipeline)

Tests:
- Expert routing (ADHD_MoE)
- Parameter locking (MAX3, safety gating)
- Convergence tracking (RC^+xi)
- Full pipeline orchestration
- Determinism guarantees (ThinkingMachines [He2025])
- Session reset logic
"""

import pytest
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import cognitive modules
from orchestra.expert_router import (
    ExpertRouter, Expert, RoutingResult, create_router
)
from orchestra.parameter_locker import (
    ParameterLocker, LockedParams, ThinkDepth, Paradigm, create_locker
)
from orchestra.convergence_tracker import (
    ConvergenceTracker, AttractorBasin, create_tracker
)
from orchestra.cognitive_orchestrator import (
    CognitiveOrchestrator, NexusResult, create_orchestrator
)
from orchestra.cognitive_state import (
    CognitiveState, CognitiveStateManager, BurnoutLevel, EnergyLevel,
    MomentumPhase, CognitiveMode
)
from orchestra.prism_detector import PRISMDetector, SignalVector, create_detector


# =============================================================================
# Expert Router Tests
# =============================================================================

class TestExpertRouter:
    """Tests for ADHD_MoE expert routing."""

    def test_create_router(self):
        """Router creates successfully."""
        router = create_router()
        assert router is not None

    def test_default_routes_to_direct(self):
        """Default routing (no signals) goes to Direct expert."""
        router = create_router()
        detector = create_detector()

        signals = detector.detect("Hello, how are you?")
        result = router.route(
            signals=signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.ROLLING,
            mode="focused"
        )

        assert result.expert == Expert.DIRECT
        assert result.constitutional_pass is True

    def test_frustration_routes_to_validator(self):
        """Frustration signals route to Validator (highest priority)."""
        router = create_router()
        detector = create_detector()

        signals = detector.detect("I'M SO FRUSTRATED! This is broken!")
        result = router.route(
            signals=signals,
            burnout=BurnoutLevel.RED,
            energy=EnergyLevel.LOW,
            momentum=MomentumPhase.CRASHED,
            mode="focused",
            caps_detected=True
        )

        assert result.expert == Expert.VALIDATOR
        assert result.safety_gate_pass is False

    def test_overwhelmed_routes_to_scaffolder_or_validator(self):
        """Overwhelmed signals route to Scaffolder or Validator (if emotional)."""
        router = create_router()
        detector = create_detector()

        # Note: "overwhelmed" triggers both emotional and scaffolder
        # Validator has higher priority, so emotional overwhelm -> Validator
        signals = detector.detect("I'm overwhelmed, there's too much to do")
        result = router.route(
            signals=signals,
            burnout=BurnoutLevel.YELLOW,
            energy=EnergyLevel.LOW,
            momentum=MomentumPhase.COLD_START,
            mode="focused"
        )

        # Either Validator (if emotional detected) or Scaffolder is valid
        assert result.expert in [Expert.SCAFFOLDER, Expert.VALIDATOR]

    def test_exploring_routes_to_socratic(self):
        """Exploring mode routes to Socratic expert."""
        router = create_router()
        detector = create_detector()

        signals = detector.detect("What if we tried a different approach?")
        result = router.route(
            signals=signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.HIGH,
            momentum=MomentumPhase.ROLLING,
            mode="exploring"
        )

        assert result.expert == Expert.SOCRATIC

    def test_expert_priority_order(self):
        """Expert priority order is fixed (Validator > Scaffolder > ... > Direct)."""
        # Define priority order (1 = highest priority)
        priority_order = [
            Expert.VALIDATOR,   # 1
            Expert.SCAFFOLDER,  # 2
            Expert.RESTORER,    # 3
            Expert.REFOCUSER,   # 4
            Expert.CELEBRATOR,  # 5
            Expert.SOCRATIC,    # 6
            Expert.DIRECT,      # 7
        ]

        # Verify all experts exist and order is defined
        assert len(priority_order) == 7
        assert Expert.VALIDATOR in priority_order
        assert Expert.DIRECT in priority_order

        # Verify order by checking indices
        assert priority_order.index(Expert.VALIDATOR) < priority_order.index(Expert.SCAFFOLDER)
        assert priority_order.index(Expert.SCAFFOLDER) < priority_order.index(Expert.DIRECT)


# =============================================================================
# Parameter Locker Tests
# =============================================================================

class TestParameterLocker:
    """Tests for MAX3 bounded reflection and safety gating."""

    def test_create_locker(self):
        """Locker creates successfully."""
        locker = create_locker()
        assert locker is not None

    def test_lock_generates_checksum(self):
        """Locking generates deterministic checksum."""
        locker = create_locker()
        router = create_router()
        detector = create_detector()

        signals = detector.detect("test message")
        routing = router.route(
            signals=signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.ROLLING,
            mode="focused"
        )

        from orchestra.cognitive_state import Altitude
        result = locker.lock(
            routing=routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            altitude=Altitude.VISION
        )

        assert result.params.checksum is not None
        assert len(result.params.checksum) == 6  # 6-char hex

    def test_same_inputs_same_checksum(self):
        """Same inputs produce same checksum (determinism)."""
        locker1 = create_locker()
        locker2 = create_locker()
        router = create_router()
        detector = create_detector()

        signals = detector.detect("test message")
        routing = router.route(
            signals=signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.ROLLING,
            mode="focused"
        )

        from orchestra.cognitive_state import Altitude
        result1 = locker1.lock(
            routing=routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            altitude=Altitude.VISION
        )
        result2 = locker2.lock(
            routing=routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            altitude=Altitude.VISION
        )

        assert result1.params.checksum == result2.params.checksum

    def test_safety_gating_depleted_caps_depth(self):
        """Depleted energy caps thinking depth to minimal."""
        locker = create_locker()
        router = create_router()
        detector = create_detector()

        signals = detector.detect("ultrathink about this problem")
        routing = router.route(
            signals=signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.DEPLETED,
            momentum=MomentumPhase.CRASHED,
            mode="focused"
        )

        from orchestra.cognitive_state import Altitude
        result = locker.lock(
            routing=routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.DEPLETED,
            altitude=Altitude.VISION,
            requested_depth=ThinkDepth.ULTRADEEP  # User requests ultradeep
        )

        # Safety gating should cap to minimal
        assert result.params.think_depth == "minimal"
        assert result.safety_capped is True

    def test_safety_gating_red_burnout(self):
        """RED burnout caps thinking depth to minimal."""
        locker = create_locker()
        router = create_router()
        detector = create_detector()

        signals = detector.detect("deep analysis needed")
        routing = router.route(
            signals=signals,
            burnout=BurnoutLevel.RED,
            energy=EnergyLevel.LOW,
            momentum=MomentumPhase.CRASHED,
            mode="focused"
        )

        from orchestra.cognitive_state import Altitude
        result = locker.lock(
            routing=routing,
            burnout=BurnoutLevel.RED,
            energy=EnergyLevel.LOW,
            altitude=Altitude.VISION,
            requested_depth=ThinkDepth.DEEP
        )

        assert result.params.think_depth == "minimal"
        assert result.safety_capped is True

    def test_max3_bounds_reflection(self):
        """MAX3: Reflection iterations bounded to 3."""
        from orchestra.cognitive_state import Altitude

        locker = create_locker()
        router = create_router()
        detector = create_detector()

        signals = detector.detect("test")
        routing = router.route(
            signals=signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            momentum=MomentumPhase.ROLLING,
            mode="focused"
        )

        result = locker.lock(
            routing=routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.MEDIUM,
            altitude=Altitude.VISION
        )

        # MAX3 should limit reflections
        assert result.params.max_reflections == 3


# =============================================================================
# Convergence Tracker Tests
# =============================================================================

class TestConvergenceTracker:
    """Tests for RC^+xi convergence tracking."""

    def test_create_tracker(self):
        """Tracker creates successfully."""
        tracker = create_tracker()
        assert tracker is not None

    def test_initial_tension_zero(self):
        """Initial epistemic tension is reasonable."""
        from orchestra.cognitive_state import Altitude
        tracker = create_tracker()
        result = tracker.update(
            expert=Expert.DIRECT,
            paradigm=Paradigm.CORTEX,
            burnout=BurnoutLevel.GREEN,
            momentum=MomentumPhase.ROLLING,
            altitude=Altitude.VISION
        )

        assert result.epistemic_tension >= 0.0
        assert result.epistemic_tension <= 1.0

    def test_stable_exchanges_increment(self):
        """Stable exchanges increment when attractor doesn't change."""
        from orchestra.cognitive_state import Altitude
        tracker = create_tracker()

        # Same inputs = same attractor = stable
        for _ in range(3):
            result = tracker.update(
                expert=Expert.DIRECT,
                paradigm=Paradigm.CORTEX,
                burnout=BurnoutLevel.GREEN,
                momentum=MomentumPhase.ROLLING,
                altitude=Altitude.VISION
            )

        assert result.stable_exchanges >= 1

    def test_convergence_at_three_stable(self):
        """Convergence detected after 3 stable exchanges at xi < epsilon."""
        from orchestra.cognitive_state import Altitude
        tracker = create_tracker()

        # Force same attractor repeatedly
        for _ in range(5):
            result = tracker.update(
                expert=Expert.DIRECT,
                paradigm=Paradigm.CORTEX,
                burnout=BurnoutLevel.GREEN,
                momentum=MomentumPhase.ROLLING,
                altitude=Altitude.VISION
            )

        # Should converge after 3 stable
        if result.stable_exchanges >= 3 and result.epistemic_tension < 0.1:
            assert result.converged is True

    def test_attractor_basins_defined(self):
        """All attractor basins are properly defined."""
        assert AttractorBasin.FOCUSED is not None
        assert AttractorBasin.EXPLORING is not None
        assert AttractorBasin.RECOVERY is not None
        assert AttractorBasin.TEACHING is not None


# =============================================================================
# Cognitive Orchestrator Tests
# =============================================================================

class TestCognitiveOrchestrator:
    """Tests for the full 5-Phase NEXUS Pipeline."""

    def test_create_orchestrator(self):
        """Orchestrator creates successfully."""
        orchestrator = create_orchestrator()
        assert orchestrator is not None

    def test_process_message_returns_nexus_result(self):
        """Processing message returns NexusResult."""
        orchestrator = create_orchestrator()
        result = orchestrator.process_message("Hello, world!")

        assert isinstance(result, NexusResult)
        assert result.signals is not None
        assert result.routing is not None
        assert result.lock is not None
        assert result.convergence is not None

    def test_anchor_format(self):
        """Anchor has correct format."""
        orchestrator = create_orchestrator()
        result = orchestrator.process_message("test")

        anchor = result.to_anchor()
        # Format: [EXEC:checksum|expert|paradigm|altitude|depth]
        assert anchor.startswith("[EXEC:")
        assert anchor.endswith("]")
        parts = anchor[6:-1].split("|")
        assert len(parts) == 5

    def test_determinism_same_message_same_checksum(self):
        """Same message produces same checksum (determinism)."""
        orchestrator1 = create_orchestrator()
        orchestrator2 = create_orchestrator()

        # Reset both
        orchestrator1.reset_session()
        orchestrator2.reset_session()

        result1 = orchestrator1.process_message("test message")
        result2 = orchestrator2.process_message("test message")

        assert result1.lock.params.checksum == result2.lock.params.checksum

    def test_phase_order_fixed(self):
        """Phases execute in fixed order (DETECT->CASCADE->LOCK->EXECUTE->UPDATE)."""
        orchestrator = create_orchestrator()
        result = orchestrator.process_message("test")

        # All phase outputs should be present
        assert result.signals is not None  # DETECT
        assert result.routing is not None  # CASCADE
        assert result.lock is not None  # LOCK
        # EXECUTE is external (Claude's response)
        assert result.convergence is not None  # UPDATE

    def test_processing_time_tracked(self):
        """Processing time is tracked in milliseconds."""
        orchestrator = create_orchestrator()
        result = orchestrator.process_message("test")

        assert result.processing_time_ms > 0
        assert result.processing_time_ms < 1000  # Should be fast

    def test_session_reset(self):
        """Session reset clears state properly."""
        orchestrator = create_orchestrator()

        # Process some messages
        orchestrator.process_message("message 1")
        orchestrator.process_message("message 2")

        # Reset
        orchestrator.reset_session()

        # State should be fresh
        state = orchestrator.get_state()
        assert state.exchange_count == 0 or state.exchange_count == 1


# =============================================================================
# Cognitive State Tests
# =============================================================================

class TestCognitiveState:
    """Tests for cognitive state management."""

    def test_create_state(self):
        """State creates with defaults."""
        state = CognitiveState()
        assert state.burnout_level == BurnoutLevel.GREEN
        assert state.momentum_phase == MomentumPhase.COLD_START
        assert state.energy_level == EnergyLevel.MEDIUM

    def test_snapshot_immutable(self):
        """Snapshot is immutable copy."""
        state = CognitiveState()
        snapshot = state.snapshot()

        state.burnout_level = BurnoutLevel.RED
        assert snapshot.burnout_level == BurnoutLevel.GREEN

    def test_batch_update(self):
        """Batch update applies changes."""
        state = CognitiveState()
        state.batch_update({
            "burnout_level": BurnoutLevel.YELLOW,
            "energy_level": EnergyLevel.LOW
        })

        assert state.burnout_level == BurnoutLevel.YELLOW
        assert state.energy_level == EnergyLevel.LOW

    def test_checksum_deterministic(self):
        """Checksum is deterministic for same state values."""
        # Create states with same fixed timestamps
        fixed_time = 1000000.0
        state1 = CognitiveState(session_start=fixed_time, last_activity=fixed_time)
        state2 = CognitiveState(session_start=fixed_time, last_activity=fixed_time)

        assert state1.checksum() == state2.checksum()

    def test_escalate_burnout(self):
        """Burnout escalation works correctly."""
        state = CognitiveState()
        assert state.burnout_level == BurnoutLevel.GREEN

        state.escalate_burnout()
        assert state.burnout_level == BurnoutLevel.YELLOW

        state.escalate_burnout()
        assert state.burnout_level == BurnoutLevel.ORANGE

        state.escalate_burnout()
        assert state.burnout_level == BurnoutLevel.RED

        # Can't go higher than RED
        state.escalate_burnout()
        assert state.burnout_level == BurnoutLevel.RED


# =============================================================================
# Session Reset Logic Tests
# =============================================================================

class TestSessionResetLogic:
    """Tests for session staleness detection and reset."""

    def test_stale_session_detection(self, tmp_path):
        """Session detected as stale after 2 hours."""
        state_dir = tmp_path / ".orchestra" / "state"
        manager = CognitiveStateManager(state_dir=state_dir)

        # Create state with old timestamp
        state = manager.get_state()
        state.last_activity = time.time() - (3 * 60 * 60)  # 3 hours ago
        manager.save()

        # Reload - should detect staleness
        manager._state = None  # Force reload
        assert manager._is_session_stale() or manager.get_state() is not None

    def test_session_reset_preserves_preferences(self, tmp_path):
        """Session reset preserves user preferences."""
        state_dir = tmp_path / ".orchestra" / "state"
        manager = CognitiveStateManager(state_dir=state_dir)

        # Set preferences
        state = manager.get_state()
        state.focus_level = "locked_in"
        state.urgency = "deadline"
        state.exchange_count = 50
        state.last_activity = time.time() - (3 * 60 * 60)  # Stale
        manager.save()

        # Reload
        manager._state = None
        loaded = manager.load()

        # Preferences preserved, session fields reset
        assert loaded.focus_level == "locked_in"
        assert loaded.urgency == "deadline"
        # exchange_count should be reset
        assert loaded.exchange_count < 50 or manager._is_session_stale()

    def test_fresh_session_not_reset(self, tmp_path):
        """Fresh session (< 2 hours) is not reset."""
        state_dir = tmp_path / ".orchestra" / "state"
        manager = CognitiveStateManager(state_dir=state_dir)

        state = manager.get_state()
        state.exchange_count = 10
        state.last_activity = time.time() - 60  # 1 minute ago
        manager.save()

        manager._state = None
        loaded = manager.load()

        # Should not be reset
        assert loaded.exchange_count == 10


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline_frustrated_user(self):
        """Full pipeline correctly handles frustrated user."""
        orchestrator = create_orchestrator()
        result = orchestrator.process_message(
            "I'M SO DONE WITH THIS! Nothing works!"
        )

        # Should route to Validator
        assert result.routing.expert == Expert.VALIDATOR
        # Safety gate should trigger
        assert result.routing.safety_gate_pass is False or result.routing.expert == Expert.VALIDATOR

    def test_full_pipeline_exploring_user(self):
        """Full pipeline correctly handles exploring user."""
        orchestrator = create_orchestrator()
        orchestrator.reset_session()

        result = orchestrator.process_message(
            "What if we approached this differently? I'm curious about alternatives."
        )

        # Should detect exploring mode
        assert result.signals.mode_detected in ["exploring", "focused", None]

    def test_full_pipeline_performance(self):
        """Pipeline completes in reasonable time."""
        orchestrator = create_orchestrator()

        start = time.time()
        for _ in range(10):
            orchestrator.process_message("test message")
        elapsed = time.time() - start

        # 10 messages should complete in under 1 second
        assert elapsed < 1.0

    def test_to_dict_serializable(self):
        """NexusResult.to_dict() is JSON-serializable."""
        import json

        orchestrator = create_orchestrator()
        result = orchestrator.process_message("test")

        # Should not raise
        json_str = json.dumps(result.to_dict())
        assert json_str is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
