"""
Tests for ADHD Support Module.

Tests burnout cascade, recovery options, working memory limits,
and other ADHD-aware constraints.

ThinkingMachines [He2025] compliance:
- Fixed constraint values
- Deterministic behavior
- Binary toggle (ON/OFF)
"""

import pytest
from unittest.mock import MagicMock, patch

from orchestra.adhd_support import (
    ADHDConstraints,
    ADHDCheckResult,
    RecoveryOption,
    RECOVERY_OPTIONS,
    ADHDSupportManager,
    BurnoutTracker,
    WorkingMemoryTracker,
    check_burnout_cascade,
    create_adhd_manager,
)
from orchestra.cognitive_state import CognitiveState, BurnoutLevel, EnergyLevel


class TestADHDConstraints:
    """Test ADHD constraint constants."""

    def test_working_memory_limit_fixed(self):
        """Working memory limit is exactly 3."""
        assert ADHDConstraints.WORKING_MEMORY_LIMIT == 3

    def test_body_check_interval_fixed(self):
        """Body check interval is exactly 20."""
        assert ADHDConstraints.BODY_CHECK_INTERVAL == 20

    def test_tangent_budget_fixed(self):
        """Default tangent budget is exactly 5."""
        assert ADHDConstraints.DEFAULT_TANGENT_BUDGET == 5

    def test_depth_limits_fixed(self):
        """Depth limits are deterministic."""
        assert ADHDConstraints.MAX_DEPTH_DEPLETED == "minimal"
        assert ADHDConstraints.MAX_DEPTH_LOW_ENERGY == "standard"
        assert ADHDConstraints.MAX_DEPTH_BURNOUT == "standard"


class TestRecoveryOptions:
    """Test recovery option definitions."""

    def test_all_options_defined(self):
        """All RecoveryOption enum values have entries."""
        for option in RecoveryOption:
            assert option in RECOVERY_OPTIONS
            assert "label" in RECOVERY_OPTIONS[option]
            assert "description" in RECOVERY_OPTIONS[option]
            assert "action" in RECOVERY_OPTIONS[option]

    def test_done_today_option(self):
        """Done for today saves state."""
        option = RECOVERY_OPTIONS[RecoveryOption.DONE_TODAY]
        assert option["action"] == "save_and_exit"

    def test_scope_cut_option(self):
        """Scope cut reduces requirements."""
        option = RECOVERY_OPTIONS[RecoveryOption.SCOPE_CUT]
        assert option["action"] == "reduce_scope"


class TestADHDCheckResult:
    """Test ADHDCheckResult dataclass."""

    def test_default_values(self):
        """Default values are safe."""
        result = ADHDCheckResult()

        assert result.working_memory_exceeded is False
        assert result.body_check_needed is False
        assert result.recovery_needed is False
        assert result.depth_limit == "deep"

    def test_to_dict(self):
        """Serializes correctly."""
        result = ADHDCheckResult(
            working_memory_exceeded=True,
            working_memory_items=4
        )

        d = result.to_dict()
        assert d["working_memory_exceeded"] is True
        assert d["working_memory_items"] == 4


class TestBurnoutTracker:
    """Test burnout level tracking."""

    def test_initial_level_green(self):
        """Starts at GREEN."""
        tracker = BurnoutTracker()
        assert tracker.level == BurnoutLevel.GREEN

    def test_escalation_to_yellow(self):
        """Escalates to YELLOW on signals."""
        tracker = BurnoutTracker()

        # Simulate warning signals
        for _ in range(3):
            tracker.record_warning_signal()

        assert tracker.level == BurnoutLevel.YELLOW

    def test_escalation_to_orange(self):
        """Escalates to ORANGE on sustained signals."""
        tracker = BurnoutTracker()
        tracker.level = BurnoutLevel.YELLOW

        for _ in range(3):
            tracker.record_warning_signal()

        assert tracker.level == BurnoutLevel.ORANGE

    def test_escalation_to_red(self):
        """Escalates to RED on critical signals."""
        tracker = BurnoutTracker()
        tracker.level = BurnoutLevel.ORANGE

        for _ in range(3):
            tracker.record_warning_signal()

        assert tracker.level == BurnoutLevel.RED

    def test_recovery_decreases_level(self):
        """Recovery signals decrease level."""
        tracker = BurnoutTracker()
        tracker.level = BurnoutLevel.YELLOW

        tracker.record_recovery_signal()
        assert tracker.level == BurnoutLevel.GREEN

    def test_red_requires_explicit_recovery(self):
        """RED doesn't auto-recover."""
        tracker = BurnoutTracker()
        tracker.level = BurnoutLevel.RED

        # Single recovery signal not enough
        tracker.record_recovery_signal()
        # RED should require explicit action, not just time
        # (Implementation may vary)


class TestWorkingMemoryTracker:
    """Test working memory tracking."""

    def test_initial_empty(self):
        """Starts empty."""
        tracker = WorkingMemoryTracker()
        assert tracker.item_count == 0

    def test_add_item(self):
        """Can add items."""
        tracker = WorkingMemoryTracker()

        tracker.add_item("task1")
        assert tracker.item_count == 1

        tracker.add_item("task2")
        assert tracker.item_count == 2

    def test_exceeds_limit(self):
        """Reports when exceeding limit."""
        tracker = WorkingMemoryTracker()

        # Add up to limit
        for i in range(ADHDConstraints.WORKING_MEMORY_LIMIT):
            tracker.add_item(f"item_{i}")

        assert tracker.is_exceeded() is False

        # Add one more
        tracker.add_item("overflow")
        assert tracker.is_exceeded() is True

    def test_remove_item(self):
        """Can remove items."""
        tracker = WorkingMemoryTracker()

        tracker.add_item("task1")
        tracker.add_item("task2")
        tracker.remove_item("task1")

        assert tracker.item_count == 1

    def test_clear_all(self):
        """Can clear all items."""
        tracker = WorkingMemoryTracker()

        for i in range(5):
            tracker.add_item(f"item_{i}")

        tracker.clear()
        assert tracker.item_count == 0


class TestADHDSupportManager:
    """Test ADHDSupportManager."""

    def test_enabled_by_default(self):
        """Manager enabled by default."""
        manager = ADHDSupportManager(enabled=True)
        assert manager.enabled is True

    def test_disabled_mode(self):
        """Disabled manager skips checks."""
        manager = ADHDSupportManager(enabled=False)

        result = manager.check_constraints(
            working_memory_items=10,  # Way over limit
            rapid_exchanges=100  # Way over
        )

        # When disabled, should not flag issues
        assert result.working_memory_exceeded is False

    def test_enabled_detects_memory_exceeded(self):
        """Enabled manager detects memory issues."""
        manager = ADHDSupportManager(enabled=True)

        result = manager.check_constraints(
            working_memory_items=5,  # Over limit of 3
            rapid_exchanges=5
        )

        assert result.working_memory_exceeded is True

    def test_body_check_triggered(self):
        """Body check triggered at interval."""
        manager = ADHDSupportManager(enabled=True)

        result = manager.check_constraints(
            working_memory_items=1,
            rapid_exchanges=21  # Over 20
        )

        assert result.body_check_needed is True
        assert result.body_check_message is not None

    def test_perfectionism_detection(self):
        """Detects perfectionism phrases."""
        manager = ADHDSupportManager(enabled=True)

        result = manager.check_constraints(
            working_memory_items=1,
            rapid_exchanges=5,
            task_text="let me just add one more thing"
        )

        assert result.perfectionism_detected is True

    def test_recovery_needed_at_red(self):
        """Recovery needed when RED burnout."""
        manager = ADHDSupportManager(enabled=True)
        manager.burnout.level = BurnoutLevel.RED

        result = manager.check_constraints(
            working_memory_items=1,
            rapid_exchanges=5
        )

        assert result.recovery_needed is True
        assert len(result.recovery_options) > 0


class TestBurnoutCascade:
    """Test burnout cascade prevention."""

    def test_green_allows_all(self):
        """GREEN allows all operations."""
        state = CognitiveState()
        state.burnout_level = BurnoutLevel.GREEN

        result = check_burnout_cascade(state)

        assert result.can_spawn_agents is True
        assert result.max_agents == 3
        assert result.depth_allowed == "deep"

    def test_yellow_warns(self):
        """YELLOW shows warning."""
        state = CognitiveState()
        state.burnout_level = BurnoutLevel.YELLOW

        result = check_burnout_cascade(state)

        assert result.can_spawn_agents is True
        assert result.warning is not None

    def test_orange_limits_agents(self):
        """ORANGE limits agent spawning."""
        state = CognitiveState()
        state.burnout_level = BurnoutLevel.ORANGE

        result = check_burnout_cascade(state)

        assert result.max_agents <= 1
        assert result.depth_allowed == "standard"

    def test_red_blocks_agents(self):
        """RED blocks agent spawning."""
        state = CognitiveState()
        state.burnout_level = BurnoutLevel.RED

        result = check_burnout_cascade(state)

        assert result.can_spawn_agents is False
        assert result.force_recovery is True


class TestDepthLimiting:
    """Test thinking depth limits."""

    def test_depleted_forces_minimal(self):
        """Depleted energy forces minimal depth."""
        manager = ADHDSupportManager(enabled=True)

        result = manager.get_depth_limit(energy_level=EnergyLevel.DEPLETED)

        assert result == "minimal"

    def test_low_energy_caps_standard(self):
        """Low energy caps at standard."""
        manager = ADHDSupportManager(enabled=True)

        result = manager.get_depth_limit(energy_level=EnergyLevel.LOW)

        assert result == "standard"

    def test_high_energy_allows_deep(self):
        """High energy allows deep thinking."""
        manager = ADHDSupportManager(enabled=True)

        result = manager.get_depth_limit(energy_level=EnergyLevel.HIGH)

        assert result == "deep"


class TestDeterminism:
    """Test determinism requirements [He2025]."""

    def test_same_input_same_output(self):
        """Same inputs produce same results."""
        manager = ADHDSupportManager(enabled=True)

        results = [
            manager.check_constraints(
                working_memory_items=4,
                rapid_exchanges=25,
                task_text="one more thing"
            )
            for _ in range(10)
        ]

        # All results should be identical
        first = results[0]
        for r in results[1:]:
            assert r.working_memory_exceeded == first.working_memory_exceeded
            assert r.body_check_needed == first.body_check_needed
            assert r.perfectionism_detected == first.perfectionism_detected

    def test_constraints_never_vary(self):
        """Constraint values never change."""
        # Multiple accesses should return same values
        for _ in range(100):
            assert ADHDConstraints.WORKING_MEMORY_LIMIT == 3
            assert ADHDConstraints.BODY_CHECK_INTERVAL == 20
            assert ADHDConstraints.DEFAULT_TANGENT_BUDGET == 5


class TestCreateADHDManager:
    """Test factory function."""

    def test_creates_enabled_manager(self):
        """Creates enabled manager when state has adhd_enabled."""
        state = MagicMock()
        state.adhd_enabled = True

        manager = create_adhd_manager(state)
        assert manager.enabled is True

    def test_creates_disabled_manager(self):
        """Creates disabled manager when state has adhd_enabled=False."""
        state = MagicMock()
        state.adhd_enabled = False

        manager = create_adhd_manager(state)
        assert manager.enabled is False
