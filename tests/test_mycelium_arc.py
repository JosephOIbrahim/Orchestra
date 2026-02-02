"""
Tests for Mycelium Arc
======================

Tests the core peer-to-peer state composition engine.

Key focus:
- Peer registration and lifecycle
- State aggregation through the arc
- LIVRPS integration at layer 2.5
- Determinism guarantees
"""

import pytest
import time
import tempfile
from pathlib import Path

from orchestra.mycelium_arc import (
    MyceliumArc,
    MyceliumArcConfig,
    QueuedMyceliumUpdate,
    create_mycelium_arc,
)
from orchestra.mycelium_aggregator import MyceliumState
from orchestra.peer_registry import (
    PeerRegistry,
    PeerInfo,
    PeerStatus,
    FlowConfig,
    FlowPolicy,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for state files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def arc(temp_dir):
    """Create a Mycelium Arc with temp directory."""
    return create_mycelium_arc(state_dir=temp_dir)


class TestMyceliumArcConfig:
    """Tests for arc configuration."""

    def test_default_config(self):
        """Default config has expected values."""
        config = MyceliumArcConfig()
        assert config.enabled is True
        assert config.peer_ttl_seconds == 300.0
        assert config.max_peers == 10
        assert config.default_flow_policy == FlowPolicy.ALL

    def test_disabled_config(self):
        """Can disable mycelium composition."""
        config = MyceliumArcConfig(enabled=False)
        assert config.enabled is False


class TestPeerRegistry:
    """Tests for peer registry."""

    def test_register_peer(self, temp_dir):
        """Can register a new peer."""
        registry = PeerRegistry(temp_dir)
        peer = registry.register(
            peer_id="test_peer",
            agent_type="test",
            description="Test peer"
        )

        assert peer.peer_id == "test_peer"
        assert peer.agent_type == "test"
        assert peer.status == PeerStatus.ACTIVE

    def test_auto_generate_peer_id(self, temp_dir):
        """Peer ID is auto-generated if not provided."""
        registry = PeerRegistry(temp_dir)
        peer = registry.register(agent_type="test")

        assert peer.peer_id.startswith("peer_")
        assert len(peer.peer_id) > 5

    def test_get_active_peers_deterministic_order(self, temp_dir):
        """Active peers are returned in deterministic order."""
        registry = PeerRegistry(temp_dir)

        # Register with explicit timestamps
        registry.register(peer_id="c", agent_type="test")
        time.sleep(0.01)
        registry.register(peer_id="a", agent_type="test")
        time.sleep(0.01)
        registry.register(peer_id="b", agent_type="test")

        # Get active peers multiple times
        orders = []
        for _ in range(10):
            peers = registry.get_active_peers()
            orders.append([p.peer_id for p in peers])

        # All orders should be identical
        assert len(set(tuple(o) for o in orders)) == 1

    def test_unregister_peer(self, temp_dir):
        """Can unregister a peer."""
        registry = PeerRegistry(temp_dir)
        registry.register(peer_id="test_peer")

        assert registry.count_total() == 1
        registry.unregister("test_peer")
        assert registry.count_total() == 0

    def test_update_state(self, temp_dir):
        """Can update peer state."""
        registry = PeerRegistry(temp_dir)
        registry.register(peer_id="test_peer")

        state = MyceliumState(burnout_level="yellow", peer_id="test_peer")
        registry.update_state("test_peer", state)

        peer = registry.get_peer("test_peer")
        assert peer.last_state.burnout_level == "yellow"


class TestMyceliumArc:
    """Tests for the main arc class."""

    def test_create_arc(self, temp_dir):
        """Can create a mycelium arc."""
        arc = create_mycelium_arc(state_dir=temp_dir)
        assert arc.config.enabled is True

    def test_register_local_peer(self, arc):
        """Can register local agent as peer."""
        peer = arc.register_local(peer_id="local_agent")

        assert peer.peer_id == "local_agent"
        assert arc._local_peer_id == "local_agent"

    def test_update_local_state(self, arc):
        """Can update local state."""
        arc.register_local(peer_id="local")

        state = MyceliumState(burnout_level="orange")
        arc.update_local_state(state)

        assert arc._local_state.burnout_level == "orange"

    def test_add_remote_peer(self, arc):
        """Can add a remote peer."""
        peer = arc.add_peer(peer_id="remote_1", agent_type="worker")

        assert peer.peer_id == "remote_1"
        assert peer.agent_type == "worker"

    def test_aggregate_empty_returns_empty_state(self, arc):
        """Empty arc returns empty state."""
        result = arc.aggregate_peer_states()
        assert result.burnout_level is None

    def test_aggregate_single_peer(self, arc):
        """Single peer's state is returned."""
        arc.register_local(peer_id="local")
        state = MyceliumState(burnout_level="yellow", epistemic_tension=0.3)
        arc.update_local_state(state)
        arc.flush_updates()  # Apply updates

        result = arc.aggregate_peer_states()
        assert result.burnout_level == "yellow"

    def test_safety_max_burnout_aggregation(self, arc):
        """Burnout uses SAFETY-MAX across peers."""
        # Add multiple peers with different burnout levels
        arc.add_peer(peer_id="peer_a")
        arc.add_peer(peer_id="peer_b")
        arc.add_peer(peer_id="peer_c")

        # Update their states
        arc.update_peer_state("peer_a", MyceliumState(burnout_level="green"))
        arc.update_peer_state("peer_b", MyceliumState(burnout_level="red"))
        arc.update_peer_state("peer_c", MyceliumState(burnout_level="yellow"))
        arc.flush_updates()

        # Aggregate should return RED (highest severity)
        assert arc.get_max_burnout() == "red"

    def test_additive_tension_aggregation(self, arc):
        """Tensions are summed across peers."""
        arc.add_peer(peer_id="peer_a")
        arc.add_peer(peer_id="peer_b")

        arc.update_peer_state("peer_a", MyceliumState(epistemic_tension=0.2))
        arc.update_peer_state("peer_b", MyceliumState(epistemic_tension=0.3))
        arc.flush_updates()

        result = arc.get_combined_tension()
        assert abs(result - 0.5) < 0.001

    def test_queued_updates_applied_on_flush(self, arc):
        """Updates are queued and applied on flush."""
        arc.add_peer(peer_id="peer_a")

        # Update without flush
        arc.update_peer_state("peer_a", MyceliumState(burnout_level="orange"))

        # Update should be queued
        assert len(arc._queued_updates) == 1

        # Flush applies updates
        arc.flush_updates()
        assert len(arc._queued_updates) == 0

        # State should now be available
        peer = arc.get_peer("peer_a")
        assert peer.last_state.burnout_level == "orange"

    def test_flow_policy_filtering(self, arc):
        """Flow policy filters state fields."""
        # Add peer with SAFETY_ONLY policy
        arc.registry.register(
            peer_id="restricted",
            flow_config=FlowConfig(policy=FlowPolicy.SAFETY_ONLY)
        )

        # Update with multiple fields
        arc.update_peer_state("restricted", MyceliumState(
            burnout_level="orange",
            momentum_phase="peak",  # Should be filtered out
            epistemic_tension=0.5   # Should be filtered out
        ))
        arc.flush_updates()

        # Get filtered states
        states = arc._get_filtered_states()

        # Should only have burnout
        for state in states:
            if state.peer_id == "restricted":
                assert state.burnout_level == "orange"
                assert state.momentum_phase is None

    def test_compose_with_livrps_local_wins(self, arc):
        """Local value overrides mycelium layer."""
        arc.add_peer(peer_id="peer_a")
        arc.update_peer_state("peer_a", MyceliumState(burnout_level="red"))
        arc.flush_updates()

        # Local value should win
        result = arc.compose_with_livrps("yellow", "burnout_level")
        assert result == "yellow"

    def test_compose_with_livrps_mycelium_fallback(self, arc):
        """Mycelium provides value when local is None."""
        arc.add_peer(peer_id="peer_a")
        arc.update_peer_state("peer_a", MyceliumState(burnout_level="orange"))
        arc.flush_updates()

        # No local value - should get mycelium value
        result = arc.compose_with_livrps(None, "burnout_level")
        assert result == "orange"

    def test_get_status(self, arc):
        """Can get arc status."""
        arc.register_local(peer_id="local")
        arc.add_peer(peer_id="remote_1")

        status = arc.get_status()

        assert status["enabled"] is True
        assert status["local_peer_id"] == "local"
        assert status["registry"]["total_peers"] == 2

    @pytest.mark.parametrize("trial", range(100))
    def test_determinism_100_trials(self, arc, trial):
        """Aggregation is deterministic across 100 trials."""
        # Add peers with known state
        arc.add_peer(peer_id="a")
        arc.add_peer(peer_id="b")
        arc.add_peer(peer_id="c")

        arc.update_peer_state("a", MyceliumState(burnout_level="yellow", epistemic_tension=0.1))
        arc.update_peer_state("b", MyceliumState(burnout_level="orange", epistemic_tension=0.2))
        arc.update_peer_state("c", MyceliumState(burnout_level="green", epistemic_tension=0.3))
        arc.flush_updates()

        # Get checksum
        checksum = arc.checksum()

        # Re-aggregate and check
        result = arc.aggregate_peer_states()
        assert arc.checksum() == checksum

    def test_verify_determinism_method(self, arc):
        """verify_determinism correctly validates."""
        arc.add_peer(peer_id="a")
        arc.add_peer(peer_id="b")

        arc.update_peer_state("a", MyceliumState(burnout_level="orange"))
        arc.update_peer_state("b", MyceliumState(burnout_level="yellow"))
        arc.flush_updates()

        assert arc.verify_determinism(n_trials=50) is True


class TestLayerPriority:
    """Tests for LIVRPS layer integration."""

    def test_mycelium_layer_exists(self):
        """MYCELIUM layer should exist in LayerPriority."""
        from orchestra.cognitive_stage import LayerPriority

        assert hasattr(LayerPriority, 'MYCELIUM')
        assert LayerPriority.MYCELIUM.value == 2.5

    def test_mycelium_between_inherits_and_variants(self):
        """MYCELIUM should be between INHERITS (2) and VARIANTS (3)."""
        from orchestra.cognitive_stage import LayerPriority

        assert LayerPriority.INHERITS.value < LayerPriority.MYCELIUM.value
        assert LayerPriority.MYCELIUM.value < LayerPriority.VARIANTS.value


class TestAgentContextPeerAwareness:
    """Tests for AgentContext peer awareness."""

    def test_agent_context_has_mycelium_fields(self):
        """AgentContext should have mycelium fields."""
        from orchestra.agent_coordinator import AgentContext

        context = AgentContext(
            parent_session_id="test",
            burnout_level="green",
            energy_level="high",
            active_project="test",
            original_goal="test",
            depth=1
        )

        assert hasattr(context, 'mycelium_peer_id')
        assert hasattr(context, 'mycelium_enabled')
        assert hasattr(context, 'mycelium_aggregated_burnout')

    def test_get_effective_burnout_safety_max(self):
        """get_effective_burnout uses SAFETY-MAX."""
        from orchestra.agent_coordinator import AgentContext

        context = AgentContext(
            parent_session_id="test",
            burnout_level="yellow",
            energy_level="high",
            active_project="test",
            original_goal="test",
            depth=1,
            mycelium_aggregated_burnout="orange"
        )

        # Should return orange (higher severity)
        assert context.get_effective_burnout() == "orange"

    def test_get_effective_burnout_local_higher(self):
        """Returns local burnout when it's higher."""
        from orchestra.agent_coordinator import AgentContext

        context = AgentContext(
            parent_session_id="test",
            burnout_level="red",
            energy_level="high",
            active_project="test",
            original_goal="test",
            depth=1,
            mycelium_aggregated_burnout="yellow"
        )

        # Should return red (local is higher)
        assert context.get_effective_burnout() == "red"


class TestCognitiveStateMyceliumFields:
    """Tests for CognitiveState mycelium fields."""

    def test_cognitive_state_has_mycelium_fields(self):
        """CognitiveState should have mycelium fields."""
        from orchestra.cognitive_state import CognitiveState

        state = CognitiveState()

        assert hasattr(state, 'mycelium_enabled')
        assert hasattr(state, 'mycelium_peer_id')
        assert hasattr(state, 'mycelium_peer_count')
        assert hasattr(state, 'mycelium_aggregated_burnout')
        assert hasattr(state, 'mycelium_aggregated_tension')
        assert hasattr(state, 'mycelium_last_sync')

    def test_mycelium_fields_default_values(self):
        """Mycelium fields have expected defaults."""
        from orchestra.cognitive_state import CognitiveState

        state = CognitiveState()

        assert state.mycelium_enabled is True
        assert state.mycelium_peer_id == ""
        assert state.mycelium_peer_count == 0
        assert state.mycelium_aggregated_burnout == "green"
        assert state.mycelium_aggregated_tension == 0.0
        assert state.mycelium_last_sync == 0.0

    def test_mycelium_fields_serialization(self):
        """Mycelium fields survive serialization roundtrip."""
        from orchestra.cognitive_state import CognitiveState

        original = CognitiveState(
            mycelium_enabled=True,
            mycelium_peer_id="test_peer",
            mycelium_peer_count=3,
            mycelium_aggregated_burnout="orange",
            mycelium_aggregated_tension=0.5,
            mycelium_last_sync=1234567890.0
        )

        serialized = original.to_dict()
        restored = CognitiveState.from_dict(serialized)

        assert restored.mycelium_enabled == original.mycelium_enabled
        assert restored.mycelium_peer_id == original.mycelium_peer_id
        assert restored.mycelium_peer_count == original.mycelium_peer_count
        assert restored.mycelium_aggregated_burnout == original.mycelium_aggregated_burnout
        assert restored.mycelium_aggregated_tension == original.mycelium_aggregated_tension
        assert restored.mycelium_last_sync == original.mycelium_last_sync


class TestPatentClaim5:
    """Tests specifically validating Patent Claim 5 support."""

    def test_horizontal_composition_exists(self, arc):
        """Horizontal (peer-to-peer) composition is implemented."""
        # This is the key innovation for Patent Claim 5
        arc.add_peer(peer_id="peer_a")
        arc.add_peer(peer_id="peer_b")

        arc.update_peer_state("peer_a", MyceliumState(burnout_level="yellow"))
        arc.update_peer_state("peer_b", MyceliumState(burnout_level="orange"))
        arc.flush_updates()

        # Peers can share state horizontally
        result = arc.aggregate_peer_states()
        assert result.burnout_level is not None

    def test_complements_vertical_livrps(self, arc):
        """Mycelium complements vertical LIVRPS composition."""
        from orchestra.cognitive_stage import LayerPriority

        # MYCELIUM (2.5) sits between INHERITS (2) and VARIANTS (3)
        # This is horizontal composition complementing vertical LIVRPS
        assert LayerPriority.INHERITS.value < LayerPriority.MYCELIUM.value
        assert LayerPriority.MYCELIUM.value < LayerPriority.VARIANTS.value

    def test_safety_max_protects_all_peers(self, arc):
        """SAFETY-MAX ensures all peers respect safety boundaries."""
        # If ANY peer is RED, all connected peers should see RED
        arc.add_peer(peer_id="healthy")
        arc.add_peer(peer_id="struggling")

        arc.update_peer_state("healthy", MyceliumState(burnout_level="green"))
        arc.update_peer_state("struggling", MyceliumState(burnout_level="red"))
        arc.flush_updates()

        # The aggregated result protects all peers
        assert arc.get_max_burnout() == "red"
