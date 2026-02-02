"""
Mycelium Arc
============

Core peer-to-peer state composition engine for Orchestra.

The Mycelium Arc implements horizontal (peer-to-peer) state sharing,
complementing the vertical (parent-child) LIVRPS composition.

Key Innovation:
- SAFETY-MAX aggregation: Burnout takes the maximum across connected peers
- INHERIT aggregation: First non-None wins for mode/paradigm
- ADDITIVE aggregation: Tensions compound across peers

This enables multiple agents to share cognitive safety state,
ensuring that if ANY peer is in RED burnout, all connected peers
respect that safety boundary.

ThinkingMachines [He2025] Compliance:
- Fixed peer ordering for deterministic aggregation
- Queued updates applied in FLUSH phase
- Batch-invariant aggregation via Kahan summation

Patent Claim 5 Support:
- Implements horizontal state composition between peers
- Complements LIVRPS vertical composition
- Enables multi-agent cognitive safety coordination
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import hashlib
import json
import logging
import time

from .mycelium_aggregator import (
    MyceliumState,
    MyceliumAggregator,
    AggregationStrategy,
    FIELD_STRATEGIES,
)
from .peer_registry import (
    PeerRegistry,
    PeerInfo,
    PeerStatus,
    FlowConfig,
    FlowPolicy,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Queued Update (for ThinkingMachines compliance)
# =============================================================================

@dataclass
class QueuedMyceliumUpdate:
    """
    A queued state update to be applied in FLUSH phase.

    ThinkingMachines [He2025] compliance: Updates are queued during
    processing and applied AFTER response generation, just like BCM trails.
    """
    peer_id: str
    state: MyceliumState
    timestamp: float = field(default_factory=time.time)
    applied: bool = False


# =============================================================================
# Mycelium Arc Configuration
# =============================================================================

@dataclass
class MyceliumArcConfig:
    """Configuration for the Mycelium Arc."""
    # Enable/disable mycelium composition
    enabled: bool = True

    # Peer TTL before expiration
    peer_ttl_seconds: float = 300.0

    # Maximum peers to aggregate (for performance)
    max_peers: int = 10

    # Auto-cleanup interval
    cleanup_interval_seconds: float = 60.0

    # Default flow policy for new peers
    default_flow_policy: FlowPolicy = FlowPolicy.ALL


# =============================================================================
# Mycelium Arc
# =============================================================================

class MyceliumArc:
    """
    Peer-to-peer state composition engine.

    The Mycelium Arc sits alongside the LIVRPS vertical composition stack
    and provides horizontal state sharing between peer agents.

    LIVRPS Priority Integration:
    - MYCELIUM layer sits between INHERITS (2) and VARIANTS (3)
    - Priority value: 2.5
    - Horizontal composition complements vertical

    Aggregation Flow:
    1. Collect states from active peers
    2. Filter fields by flow policy
    3. Aggregate using field-specific strategies
    4. Return aggregated MyceliumState

    Safety Guarantee:
    - SAFETY-MAX ensures burnout is never lowered by peer aggregation
    - If ANY peer is RED, aggregated result is RED
    - Constitutional safety floors are preserved
    """

    def __init__(
        self,
        state_dir: Path = None,
        config: MyceliumArcConfig = None
    ):
        """
        Initialize Mycelium Arc.

        Args:
            state_dir: Directory for state persistence
            config: Configuration options
        """
        self.state_dir = state_dir or (Path.home() / ".orchestra" / "mycelium")
        self.config = config or MyceliumArcConfig()

        # Core components
        self.registry = PeerRegistry(self.state_dir)
        self.aggregator = MyceliumAggregator()

        # Queued updates (for FLUSH phase)
        self._queued_updates: List[QueuedMyceliumUpdate] = []

        # Local peer state
        self._local_peer_id: Optional[str] = None
        self._local_state: Optional[MyceliumState] = None

        # Last cleanup timestamp
        self._last_cleanup = time.time()

        logger.info("Mycelium Arc initialized")

    # =========================================================================
    # Local Peer Management
    # =========================================================================

    def register_local(
        self,
        peer_id: str = None,
        agent_type: str = "local",
        parent_session_id: str = "",
        description: str = "Local agent"
    ) -> PeerInfo:
        """
        Register the local agent as a peer.

        Args:
            peer_id: Optional peer ID
            agent_type: Type of this agent
            parent_session_id: Parent session ID
            description: Description of this agent

        Returns:
            PeerInfo for the local peer
        """
        peer = self.registry.register(
            peer_id=peer_id,
            agent_type=agent_type,
            parent_session_id=parent_session_id,
            description=description
        )
        self._local_peer_id = peer.peer_id
        return peer

    def update_local_state(self, state: MyceliumState):
        """
        Update the local peer's state.

        This queues the update for FLUSH phase per ThinkingMachines compliance.

        Args:
            state: New local state
        """
        if self._local_peer_id is None:
            logger.warning("No local peer registered, cannot update state")
            return

        # Queue the update
        state.peer_id = self._local_peer_id
        self._queued_updates.append(QueuedMyceliumUpdate(
            peer_id=self._local_peer_id,
            state=state
        ))

        # Store locally for immediate access
        self._local_state = state

    def get_local_state(self) -> Optional[MyceliumState]:
        """Get the local peer's current state."""
        return self._local_state

    # =========================================================================
    # Peer State Aggregation
    # =========================================================================

    def aggregate_peer_states(self) -> MyceliumState:
        """
        Aggregate states from all active peers.

        This is the core of horizontal composition:
        1. Get states from all active peers
        2. Filter by flow policies
        3. Aggregate using field-specific strategies
        4. Return the combined state

        Returns:
            Aggregated MyceliumState
        """
        if not self.config.enabled:
            return MyceliumState()

        # Get peer states (already in deterministic order)
        peer_states = self._get_filtered_states()

        if not peer_states:
            return MyceliumState()

        # Aggregate using configured strategies
        return self.aggregator.aggregate(peer_states)

    def _get_filtered_states(self) -> List[MyceliumState]:
        """
        Get peer states filtered by flow policies.

        Returns states in deterministic order.
        """
        result = []
        peers = self.registry.get_active_peers()

        # Limit to max peers
        peers = peers[:self.config.max_peers]

        for peer in peers:
            if peer.last_state is None:
                continue

            # Create filtered state based on flow policy
            filtered = self._filter_state_by_policy(
                peer.last_state,
                peer.flow_config
            )
            if filtered:
                result.append(filtered)

        return result

    def _filter_state_by_policy(
        self,
        state: MyceliumState,
        flow_config: FlowConfig
    ) -> Optional[MyceliumState]:
        """
        Filter a state according to flow policy.

        Args:
            state: Original state
            flow_config: Flow configuration

        Returns:
            Filtered state or None if all fields blocked
        """
        filtered = MyceliumState(
            peer_id=state.peer_id,
            timestamp=state.timestamp
        )

        has_values = False

        # Check each field against policy
        for field_name in FIELD_STRATEGIES.keys():
            if flow_config.should_flow(field_name):
                value = getattr(state, field_name, None)
                if value is not None:
                    setattr(filtered, field_name, value)
                    has_values = True

        return filtered if has_values else None

    def get_resolved_field(self, field_name: str) -> Any:
        """
        Get a single field resolved through peer aggregation.

        Convenience method for querying specific fields.

        Args:
            field_name: Name of the field

        Returns:
            Aggregated value for the field
        """
        aggregated = self.aggregate_peer_states()
        return getattr(aggregated, field_name, None)

    def get_max_burnout(self) -> str:
        """
        Get the maximum burnout level across all peers.

        SAFETY-MAX: Returns the most severe burnout level.

        Returns:
            Maximum burnout level string
        """
        return self.get_resolved_field("burnout_level") or "green"

    def get_combined_tension(self) -> float:
        """
        Get the combined epistemic tension across all peers.

        ADDITIVE: Tensions compound.

        Returns:
            Combined tension value
        """
        return self.get_resolved_field("epistemic_tension") or 0.0

    # =========================================================================
    # FLUSH Phase (ThinkingMachines Compliance)
    # =========================================================================

    def flush_updates(self):
        """
        Apply queued updates.

        Called in the FLUSH phase AFTER response generation.
        This ensures updates don't affect the current processing cycle.
        """
        for update in self._queued_updates:
            if not update.applied:
                self.registry.update_state(update.peer_id, update.state)
                update.applied = True
                logger.debug(f"Flushed update for peer {update.peer_id}")

        self._queued_updates.clear()

        # Periodic cleanup
        self._maybe_cleanup()

    def _maybe_cleanup(self):
        """Run cleanup if interval has elapsed."""
        now = time.time()
        if (now - self._last_cleanup) > self.config.cleanup_interval_seconds:
            self.registry.cleanup_expired(self.config.peer_ttl_seconds)
            self._last_cleanup = now

    # =========================================================================
    # Peer Management
    # =========================================================================

    def add_peer(
        self,
        peer_id: str = None,
        agent_type: str = "remote",
        flow_policy: FlowPolicy = None
    ) -> PeerInfo:
        """
        Add a new peer to the arc.

        Args:
            peer_id: Optional peer ID
            agent_type: Type of the peer agent
            flow_policy: Flow policy for the peer

        Returns:
            PeerInfo for the new peer
        """
        policy = flow_policy or self.config.default_flow_policy
        return self.registry.register(
            peer_id=peer_id,
            agent_type=agent_type,
            flow_config=FlowConfig(policy=policy)
        )

    def remove_peer(self, peer_id: str) -> bool:
        """
        Remove a peer from the arc.

        Args:
            peer_id: ID of peer to remove

        Returns:
            True if peer was removed
        """
        return self.registry.unregister(peer_id)

    def update_peer_state(self, peer_id: str, state: MyceliumState):
        """
        Update a peer's state.

        Queues the update for FLUSH phase.

        Args:
            peer_id: ID of the peer
            state: New state
        """
        state.peer_id = peer_id
        self._queued_updates.append(QueuedMyceliumUpdate(
            peer_id=peer_id,
            state=state
        ))

    def get_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """Get peer info by ID."""
        return self.registry.get_peer(peer_id)

    def list_peers(self) -> List[PeerInfo]:
        """Get all active peers."""
        return self.registry.get_active_peers()

    # =========================================================================
    # Integration with Cognitive Stage
    # =========================================================================

    def compose_with_livrps(
        self,
        local_value: Any,
        field_name: str
    ) -> Any:
        """
        Compose a value with LIVRPS + Mycelium.

        LIVRPS Priority: LOCAL > INHERITS > MYCELIUM > VARIANTS > ...

        The Mycelium layer (2.5) sits between INHERITS (2) and VARIANTS (3).
        Local session values always win.

        Args:
            local_value: Value from LOCAL/INHERITS layers
            field_name: Name of the field

        Returns:
            Composed value
        """
        if local_value is not None:
            # LOCAL/INHERITS wins
            return local_value

        # Try MYCELIUM layer
        return self.get_resolved_field(field_name)

    def get_mycelium_layer_data(self) -> Dict[str, Any]:
        """
        Get all Mycelium layer data for LIVRPS composition.

        Returns a dict suitable for inserting into the LIVRPS stack.

        Returns:
            Dict of field_name -> aggregated_value
        """
        aggregated = self.aggregate_peer_states()
        return aggregated.to_dict()

    # =========================================================================
    # Status and Debugging
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get Mycelium Arc status."""
        return {
            "enabled": self.config.enabled,
            "local_peer_id": self._local_peer_id,
            "local_state": self._local_state.to_dict() if self._local_state else None,
            "registry": self.registry.get_status(),
            "pending_updates": len(self._queued_updates),
            "aggregated_burnout": self.get_max_burnout(),
            "aggregated_tension": self.get_combined_tension()
        }

    def checksum(self) -> str:
        """Generate deterministic checksum of arc state."""
        aggregated = self.aggregate_peer_states()
        data = {
            "enabled": self.config.enabled,
            "local_peer": self._local_peer_id,
            "registry_checksum": self.registry.checksum(),
            "aggregated_checksum": aggregated.checksum()
        }
        state_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()[:16]

    def verify_determinism(self, n_trials: int = 100) -> bool:
        """
        Verify that aggregation is deterministic.

        Args:
            n_trials: Number of trials

        Returns:
            True if all trials produce identical results
        """
        checksums = set()

        for _ in range(n_trials):
            result = self.aggregate_peer_states()
            checksums.add(result.checksum())

        return len(checksums) == 1


# =============================================================================
# Factory Function
# =============================================================================

def create_mycelium_arc(
    state_dir: Path = None,
    enabled: bool = True
) -> MyceliumArc:
    """
    Create and initialize a Mycelium Arc.

    Args:
        state_dir: Directory for state persistence
        enabled: Whether to enable mycelium composition

    Returns:
        Initialized MyceliumArc
    """
    config = MyceliumArcConfig(enabled=enabled)
    return MyceliumArc(state_dir=state_dir, config=config)


__all__ = [
    'MyceliumArc',
    'MyceliumArcConfig',
    'QueuedMyceliumUpdate',
    'create_mycelium_arc',
]
