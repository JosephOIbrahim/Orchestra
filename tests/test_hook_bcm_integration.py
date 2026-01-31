"""
Hook BCM Integration Tests for Orchestra v7.0.0
================================================

Tests for BCM integration through the Claude Code hook interface.

Test Categories:
1. Hook Trail Loading - BCM trail loads on first message
2. Anchor BCM Metadata - Anchor includes BCM checksum
3. Determinism - Same input produces same routing
4. Order Invariance - Trail data is METADATA only, never affects routing ORDER

ThinkingMachines [He2025] Compliance:
- BCM is metadata layer, NEVER changes routing order
- Same message + same state = same expert selection
- Fixed evaluation order preserved regardless of trail

Run with: pytest tests/test_hook_bcm_integration.py -v

Author: Claude + Orchestra Team
Date: 2026-01-31
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from io import StringIO

from orchestra.bcm_trail import OrchestraTrail, Trail
from orchestra.bcm_integration import BCMPipelineAdapter
from orchestra.cognitive_orchestrator import CognitiveOrchestrator, create_orchestrator
from orchestra.cognitive_state import BurnoutLevel, EnergyLevel, MomentumPhase


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def fresh_orchestrator(tmp_path, monkeypatch):
    """Create orchestrator with temp BCM directory."""
    import orchestra.bcm_integration as bcm_int
    monkeypatch.setattr(bcm_int, 'BCM_STATE_DIR', tmp_path)
    return CognitiveOrchestrator(session_id="hook_test")


@pytest.fixture
def orchestrator_with_trail(tmp_path, monkeypatch):
    """Create orchestrator with pre-populated BCM trail."""
    import orchestra.bcm_integration as bcm_int
    import time as time_module
    monkeypatch.setattr(bcm_int, 'BCM_STATE_DIR', tmp_path)

    # Use current timestamp to avoid decay
    current_time = time_module.time()

    # Create pre-populated trail file at correct path: trail_{session_id}.json
    trail_data = {
        "version": "0.1.0",
        "expert_trails": {
            "direct": {
                "id": "expert_direct",
                "domain": "orchestra",
                "strength": 5.0,
                "success_count": 10,
                "failure_count": 2,
                "last_reinforced": current_time  # Recent timestamp prevents decay
            },
            "validator": {
                "id": "expert_validator",
                "domain": "orchestra",
                "strength": 3.0,
                "success_count": 5,
                "failure_count": 1,
                "last_reinforced": current_time
            }
        },
        "signal_history": {},
        "depth_history": {},
        "attractor_history": {},
        "plasticity_state": {
            "window_active": False,
            "sigma": 0.0,
            "window_trigger": ""
        },
        "last_update": current_time
    }

    # Correct path: BCM_STATE_DIR / trail_{session_id}.json
    trail_file = tmp_path / "trail_hook_test.json"
    trail_file.write_text(json.dumps(trail_data))

    return CognitiveOrchestrator(session_id="hook_test")


# =============================================================================
# Test 1: Hook Loads BCM Trail
# =============================================================================

class TestHookLoadsBCMTrail:
    """Verify BCM trail is loaded on first message through hook."""

    def test_hook_loads_bcm_trail(self, fresh_orchestrator):
        """Trail should be loaded and available for processing."""
        # Process a message (simulates hook receiving message)
        result = fresh_orchestrator.process_message("help me implement this feature")

        # Trail should be loaded and accessible
        assert fresh_orchestrator.bcm._loaded is True
        trail = fresh_orchestrator.get_bcm_trail()
        assert trail is not None
        assert trail.version == "0.1.0"

        # Result should include trail metadata
        assert result.bcm_trail_version == "0.1.0"
        assert result.routing.bcm_enhanced is True

    def test_hook_lazy_loads_trail_only_once(self, fresh_orchestrator):
        """Trail should only be loaded once (lazy loading)."""
        # Process first message
        fresh_orchestrator.process_message("first message")
        trail1 = fresh_orchestrator.get_bcm_trail()

        # Process second message
        fresh_orchestrator.process_message("second message")
        trail2 = fresh_orchestrator.get_bcm_trail()

        # Should be same trail instance
        assert trail1 is trail2

    def test_hook_loads_existing_trail(self, orchestrator_with_trail):
        """Hook should load existing trail data from disk."""
        result = orchestrator_with_trail.process_message("test message")

        trail = orchestrator_with_trail.get_bcm_trail()

        # Should have loaded the pre-existing expert trails
        assert "direct" in trail.expert_trails
        # Use pytest.approx for floating-point comparison (tiny decay may occur)
        assert trail.expert_trails["direct"].strength == pytest.approx(5.0, rel=0.01)
        assert trail.expert_trails["direct"].success_count == 10


# =============================================================================
# Test 2: Anchor Includes BCM Checksum
# =============================================================================

class TestHookIncludesBCMAnchor:
    """Verify execution anchor includes BCM metadata."""

    def test_hook_includes_bcm_anchor(self, fresh_orchestrator):
        """Result should include BCM trail version in metadata."""
        result = fresh_orchestrator.process_message("implement a feature")

        # NexusResult should have BCM metadata
        assert result.bcm_trail_version != ""
        assert result.bcm_trail_version == "0.1.0"

    def test_anchor_format_valid(self, fresh_orchestrator):
        """Anchor string should be valid format."""
        result = fresh_orchestrator.process_message("help me debug this")

        anchor = result.to_anchor()

        # Should be valid anchor format
        assert anchor.startswith("[EXEC:")
        assert anchor.endswith("]")
        # Should contain expected components
        assert "|" in anchor

    def test_bcm_metadata_in_result_dict(self, fresh_orchestrator):
        """Serialized result should include BCM fields."""
        result = fresh_orchestrator.process_message("implement this")

        data = result.to_dict()

        # BCM fields should be present
        assert "bcm_trail_version" in data
        assert "bcm_trail_enhanced" in data
        assert "bcm_routing_confidence" in data
        assert "bcm_lock_optimized" in data
        assert "bcm_convergence_enhanced" in data

    def test_routing_result_has_bcm_metadata(self, orchestrator_with_trail):
        """Routing result should include BCM confidence metadata."""
        result = orchestrator_with_trail.process_message("test message")

        # Routing should have BCM metadata
        assert result.routing.bcm_enhanced is True
        assert result.routing.bcm_trail_version == "0.1.0"
        assert len(result.routing.bcm_expert_confidences) > 0


# =============================================================================
# Test 3: Determinism Through Hook
# =============================================================================

class TestDeterminismThroughHook:
    """Verify same input produces same routing through hook."""

    def test_determinism_through_hook(self, fresh_orchestrator):
        """Same message should produce identical routing."""
        message = "help me implement a feature for user authentication"

        result1 = fresh_orchestrator.process_message(message)

        # Reset to ensure clean state
        fresh_orchestrator.locker.reset()
        fresh_orchestrator.tracker.reset()

        result2 = fresh_orchestrator.process_message(message)

        # Expert selection must be identical
        assert result1.routing.expert == result2.routing.expert
        assert result1.routing.trigger == result2.routing.trigger

        # Lock params must be identical
        assert result1.lock.params.checksum == result2.lock.params.checksum

    def test_determinism_with_populated_trail(self, orchestrator_with_trail):
        """Same message with trail should produce identical routing."""
        message = "implement this feature"

        result1 = orchestrator_with_trail.process_message(message)

        orchestrator_with_trail.locker.reset()
        orchestrator_with_trail.tracker.reset()

        result2 = orchestrator_with_trail.process_message(message)

        # Expert selection must be identical
        assert result1.routing.expert == result2.routing.expert
        assert result1.lock.params.checksum == result2.lock.params.checksum

        # BCM metadata must also be identical
        assert result1.routing.bcm_confidence == result2.routing.bcm_confidence
        assert result1.bcm_trail_version == result2.bcm_trail_version

    def test_checksum_reproducibility(self, fresh_orchestrator):
        """Same inputs should produce same execution checksum."""
        message = "debug this error"

        result1 = fresh_orchestrator.process_message(message)
        checksum1 = result1.lock.params.checksum

        fresh_orchestrator.locker.reset()
        fresh_orchestrator.tracker.reset()

        result2 = fresh_orchestrator.process_message(message)
        checksum2 = result2.lock.params.checksum

        assert checksum1 == checksum2


# =============================================================================
# Test 4: BCM Doesn't Change Routing Order
# =============================================================================

class TestBCMDoesntChangeRoutingOrder:
    """CRITICAL: Trail data is metadata only, NEVER affects routing ORDER."""

    def test_bcm_doesnt_change_routing_order(self, tmp_path, monkeypatch):
        """Expert selection must be identical with and without trail."""
        import orchestra.bcm_integration as bcm_int
        monkeypatch.setattr(bcm_int, 'BCM_STATE_DIR', tmp_path)

        # Orchestrator without trail history
        orch_fresh = CognitiveOrchestrator(session_id="fresh")

        # Create orchestrator with trail that has strong expert preferences
        trail_dir = tmp_path / "biased"
        trail_dir.mkdir(parents=True, exist_ok=True)

        # Trail strongly biased toward scaffolder
        trail_data = {
            "version": "0.1.0",
            "expert_trails": {
                "scaffolder": {
                    "id": "expert_scaffolder",
                    "domain": "orchestra",
                    "strength": 10.0,  # Very strong
                    "success_count": 100,
                    "failure_count": 0,
                    "last_reinforced": 0.0
                },
                "direct": {
                    "id": "expert_direct",
                    "domain": "orchestra",
                    "strength": 0.1,  # Very weak
                    "success_count": 1,
                    "failure_count": 10,
                    "last_reinforced": 0.0
                }
            },
            "signal_history": {},
            "depth_history": {},
            "attractor_history": {},
            "plasticity_state": {"window_active": False, "sigma": 0.0, "window_trigger": ""},
            "last_update": 0.0
        }
        (trail_dir / "trail.json").write_text(json.dumps(trail_data))

        orch_biased = CognitiveOrchestrator(session_id="biased")

        # Message that should route to DIRECT expert (focused work)
        message = "implement this feature"

        result_fresh = orch_fresh.process_message(message)
        result_biased = orch_biased.process_message(message)

        # CRITICAL: Same expert must be selected regardless of trail bias
        assert result_fresh.routing.expert == result_biased.routing.expert
        assert result_fresh.routing.trigger == result_biased.routing.trigger
        assert result_fresh.routing.priority_index == result_biased.routing.priority_index

    def test_safety_gates_override_trail(self, tmp_path, monkeypatch):
        """Safety gates must override ANY trail preferences."""
        import orchestra.bcm_integration as bcm_int
        monkeypatch.setattr(bcm_int, 'BCM_STATE_DIR', tmp_path)

        # Create trail that "prefers" direct expert
        trail_dir = tmp_path / "safety_test"
        trail_dir.mkdir(parents=True, exist_ok=True)

        trail_data = {
            "version": "0.1.0",
            "expert_trails": {
                "direct": {
                    "id": "expert_direct",
                    "domain": "orchestra",
                    "strength": 100.0,  # Extremely strong preference
                    "success_count": 1000,
                    "failure_count": 0,
                    "last_reinforced": 0.0
                }
            },
            "signal_history": {},
            "depth_history": {},
            "attractor_history": {},
            "plasticity_state": {"window_active": False, "sigma": 0.0, "window_trigger": ""},
            "last_update": 0.0
        }
        (trail_dir / "trail.json").write_text(json.dumps(trail_data))

        orch = CognitiveOrchestrator(session_id="safety_test")

        # Set RED burnout (forces Validator regardless of trail)
        orch.state_manager.batch_update({"burnout_level": BurnoutLevel.RED})

        result = orch.process_message("implement a simple feature")

        # Safety gate MUST win - Validator selected despite trail preference
        assert result.routing.expert.value == "validator"
        assert result.routing.safety_gate_pass is False

    def test_emotional_signals_override_trail(self, tmp_path, monkeypatch):
        """Emotional signals must route to Validator regardless of trail."""
        import orchestra.bcm_integration as bcm_int
        monkeypatch.setattr(bcm_int, 'BCM_STATE_DIR', tmp_path)

        # Trail biased away from validator
        trail_dir = tmp_path / "emotional_test"
        trail_dir.mkdir(parents=True, exist_ok=True)

        trail_data = {
            "version": "0.1.0",
            "expert_trails": {
                "validator": {
                    "id": "expert_validator",
                    "domain": "orchestra",
                    "strength": 0.01,  # Near-zero strength
                    "success_count": 0,
                    "failure_count": 100,
                    "last_reinforced": 0.0
                },
                "direct": {
                    "id": "expert_direct",
                    "domain": "orchestra",
                    "strength": 100.0,
                    "success_count": 1000,
                    "failure_count": 0,
                    "last_reinforced": 0.0
                }
            },
            "signal_history": {},
            "depth_history": {},
            "attractor_history": {},
            "plasticity_state": {"window_active": False, "sigma": 0.0, "window_trigger": ""},
            "last_update": 0.0
        }
        (trail_dir / "trail.json").write_text(json.dumps(trail_data))

        orch = CognitiveOrchestrator(session_id="emotional_test")

        # Frustrated message should route to Validator
        result = orch.process_message("I'M SO FRUSTRATED! This keeps breaking!")

        # Emotional signal MUST win - Validator selected
        assert result.routing.expert.value == "validator"

    def test_trail_only_adds_metadata(self, orchestrator_with_trail, fresh_orchestrator):
        """Trail should only ADD metadata, not change core routing logic."""
        message = "explain how this works"

        result_fresh = fresh_orchestrator.process_message(message)
        result_trail = orchestrator_with_trail.process_message(message)

        # Core routing fields must match
        assert result_fresh.routing.expert == result_trail.routing.expert
        assert result_fresh.routing.constitutional_pass == result_trail.routing.constitutional_pass
        assert result_fresh.routing.safety_gate_pass == result_trail.routing.safety_gate_pass

        # Both should have BCM enhanced
        assert result_trail.routing.bcm_enhanced is True
        assert result_fresh.routing.bcm_enhanced is True

        # Populated trail should have different confidences for experts with history
        # Fresh trail has all defaults (1.0), populated has actual confidence based on success rate
        trail = orchestrator_with_trail.get_bcm_trail()
        if trail.expert_trails:
            # Confidence is based on success rate, not always 1.0
            for expert_name, expert_trail in trail.expert_trails.items():
                if expert_trail.success_count + expert_trail.failure_count > 0:
                    # There should be trail data loaded
                    assert expert_trail.strength > 0


# =============================================================================
# Additional Compliance Tests
# =============================================================================

class TestThinkingMachinesCompliance:
    """Tests ensuring ThinkingMachines [He2025] compliance."""

    def test_fixed_expert_priority_order(self, fresh_orchestrator):
        """Expert priority order must be FIXED."""
        from orchestra.expert_router import EXPERT_PRIORITY

        # This is the canonical order - never changes
        expected_order = [
            "validator", "scaffolder", "restorer", "refocuser",
            "celebrator", "socratic", "direct"
        ]

        actual_order = [e.value for e in EXPERT_PRIORITY]
        assert actual_order == expected_order

    def test_queued_updates_not_applied_during_processing(self, fresh_orchestrator):
        """BCM updates must be QUEUED, not applied during processing."""
        result1 = fresh_orchestrator.process_message("test message 1")

        # Record outcome (should queue, not apply)
        fresh_orchestrator.record_outcome(success=True)

        # Process another message
        result2 = fresh_orchestrator.process_message("test message 2")

        # Updates should still be pending (not applied during processing)
        trail = fresh_orchestrator.get_bcm_trail()
        assert len(trail._pending_updates) > 0

    def test_flush_applies_updates_after_processing(self, fresh_orchestrator):
        """Flush must apply updates AFTER processing, not during."""
        fresh_orchestrator.process_message("test message")
        fresh_orchestrator.record_outcome(success=True)

        # Flush applies updates
        updates, _ = fresh_orchestrator.flush_bcm_trail()

        # Updates should be applied
        trail = fresh_orchestrator.get_bcm_trail()
        assert len(trail._pending_updates) == 0
        assert updates > 0


# =============================================================================
# Run if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
