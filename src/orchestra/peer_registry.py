"""
Peer Registry
=============

Manages peer discovery and registration for the Mycelium Arc.

Peers are registered agents that can share cognitive state horizontally.
The registry maintains deterministic ordering for aggregation.

ThinkingMachines [He2025] Compliance:
- Fixed peer ordering: sorted by (registration_timestamp, peer_id)
- Deterministic iteration over peers
- Atomic registration/unregistration

Patent Claim 5 Support:
- Implements peer discovery for horizontal composition
- Enables selective state flow between peers
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
import hashlib
import json
import logging
import time
import uuid

from .file_ops import atomic_write_json, safe_read_json
from .mycelium_aggregator import MyceliumState

logger = logging.getLogger(__name__)


# =============================================================================
# Peer Status
# =============================================================================

class PeerStatus(Enum):
    """Status of a registered peer."""
    ACTIVE = "active"           # Peer is actively sharing state
    PAUSED = "paused"           # Peer has paused state sharing
    DISCONNECTED = "disconnected"  # Peer is no longer reachable
    EXPIRED = "expired"         # Peer registration has expired


# =============================================================================
# Flow Policy
# =============================================================================

class FlowPolicy(Enum):
    """
    Policy for state flow between peers.

    Determines which fields flow from a peer to others.
    """
    ALL = "all"             # All fields flow
    SAFETY_ONLY = "safety_only"  # Only safety-critical fields (burnout)
    NONE = "none"           # No state flows
    CUSTOM = "custom"       # Custom field selection


@dataclass
class FlowConfig:
    """Configuration for what state flows from a peer."""
    policy: FlowPolicy = FlowPolicy.ALL
    allowed_fields: Set[str] = field(default_factory=lambda: {
        "burnout_level",
        "momentum_phase",
        "attractor_basin",
        "epistemic_tension"
    })
    blocked_fields: Set[str] = field(default_factory=set)

    def should_flow(self, field_name: str) -> bool:
        """Check if a field should flow based on policy."""
        if self.policy == FlowPolicy.NONE:
            return False

        if self.policy == FlowPolicy.SAFETY_ONLY:
            return field_name == "burnout_level"

        if field_name in self.blocked_fields:
            return False

        if self.policy == FlowPolicy.CUSTOM:
            return field_name in self.allowed_fields

        # FlowPolicy.ALL
        return True


# =============================================================================
# Peer Info
# =============================================================================

@dataclass
class PeerInfo:
    """
    Information about a registered peer.

    Tracks peer identity, status, and last known state.
    """
    peer_id: str
    registration_timestamp: float
    status: PeerStatus = PeerStatus.ACTIVE
    last_heartbeat: float = 0.0
    last_state: Optional[MyceliumState] = None
    flow_config: FlowConfig = field(default_factory=FlowConfig)

    # Metadata
    agent_type: str = "unknown"
    parent_session_id: str = ""
    description: str = ""

    def __post_init__(self):
        if self.last_heartbeat == 0.0:
            self.last_heartbeat = self.registration_timestamp

    def is_active(self) -> bool:
        """Check if peer is active."""
        return self.status == PeerStatus.ACTIVE

    def is_expired(self, ttl_seconds: float = 300.0) -> bool:
        """Check if peer has expired (no heartbeat for TTL)."""
        return (time.time() - self.last_heartbeat) > ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "peer_id": self.peer_id,
            "registration_timestamp": self.registration_timestamp,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat,
            "last_state": self.last_state.to_dict() if self.last_state else None,
            "flow_config": {
                "policy": self.flow_config.policy.value,
                "allowed_fields": list(self.flow_config.allowed_fields),
                "blocked_fields": list(self.flow_config.blocked_fields)
            },
            "agent_type": self.agent_type,
            "parent_session_id": self.parent_session_id,
            "description": self.description
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PeerInfo':
        """Deserialize from dict."""
        flow_data = data.get("flow_config", {})
        flow_config = FlowConfig(
            policy=FlowPolicy(flow_data.get("policy", "all")),
            allowed_fields=set(flow_data.get("allowed_fields", [])),
            blocked_fields=set(flow_data.get("blocked_fields", []))
        )

        return cls(
            peer_id=data["peer_id"],
            registration_timestamp=data["registration_timestamp"],
            status=PeerStatus(data.get("status", "active")),
            last_heartbeat=data.get("last_heartbeat", data["registration_timestamp"]),
            last_state=MyceliumState.from_dict(data["last_state"]) if data.get("last_state") else None,
            flow_config=flow_config,
            agent_type=data.get("agent_type", "unknown"),
            parent_session_id=data.get("parent_session_id", ""),
            description=data.get("description", "")
        )

    def sort_key(self) -> tuple:
        """Return sort key for deterministic ordering."""
        return (self.registration_timestamp, self.peer_id)


# =============================================================================
# Peer Registry
# =============================================================================

class PeerRegistry:
    """
    Registry for tracking and managing peers in the Mycelium Arc.

    Maintains deterministic ordering of peers for aggregation.
    Persists registry state to disk for cross-session continuity.

    ThinkingMachines [He2025] Compliance:
    - Fixed ordering: peers sorted by (timestamp, id)
    - Atomic operations for registration/unregistration
    - Deterministic iteration
    """

    # Default TTL for peer expiration
    PEER_TTL_SECONDS = 300.0  # 5 minutes

    def __init__(self, state_dir: Path = None):
        """
        Initialize peer registry.

        Args:
            state_dir: Directory for state persistence
        """
        self.state_dir = state_dir or (Path.home() / ".orchestra" / "mycelium")
        self.registry_file = self.state_dir / "peer_registry.json"
        self._peers: Dict[str, PeerInfo] = {}

        # Ensure directory exists
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Load persisted registry
        self._load()

    def _load(self):
        """Load registry from disk."""
        if self.registry_file.exists():
            try:
                data = safe_read_json(self.registry_file)
                if data:
                    for peer_data in data.get("peers", []):
                        peer = PeerInfo.from_dict(peer_data)
                        self._peers[peer.peer_id] = peer
                    logger.info(f"Loaded {len(self._peers)} peers from registry")
            except Exception as e:
                logger.error(f"Failed to load peer registry: {e}")
                self._peers = {}

    def _save(self):
        """Save registry to disk."""
        try:
            data = {
                "peers": [p.to_dict() for p in self._peers.values()],
                "saved_at": time.time()
            }
            atomic_write_json(self.registry_file, data)
            logger.debug(f"Saved {len(self._peers)} peers to registry")
        except Exception as e:
            logger.error(f"Failed to save peer registry: {e}")

    def register(
        self,
        peer_id: str = None,
        agent_type: str = "unknown",
        parent_session_id: str = "",
        description: str = "",
        flow_config: FlowConfig = None
    ) -> PeerInfo:
        """
        Register a new peer.

        Args:
            peer_id: Unique peer ID (generated if not provided)
            agent_type: Type of the agent
            parent_session_id: Parent session for context
            description: Human-readable description
            flow_config: Configuration for state flow

        Returns:
            PeerInfo for the registered peer
        """
        if peer_id is None:
            peer_id = f"peer_{uuid.uuid4().hex[:8]}"

        timestamp = time.time()

        peer = PeerInfo(
            peer_id=peer_id,
            registration_timestamp=timestamp,
            status=PeerStatus.ACTIVE,
            flow_config=flow_config or FlowConfig(),
            agent_type=agent_type,
            parent_session_id=parent_session_id,
            description=description
        )

        self._peers[peer_id] = peer
        self._save()

        logger.info(f"Registered peer: {peer_id} (type={agent_type})")
        return peer

    def unregister(self, peer_id: str) -> bool:
        """
        Unregister a peer.

        Args:
            peer_id: ID of peer to unregister

        Returns:
            True if peer was found and unregistered
        """
        if peer_id in self._peers:
            del self._peers[peer_id]
            self._save()
            logger.info(f"Unregistered peer: {peer_id}")
            return True
        return False

    def get_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """Get peer info by ID."""
        return self._peers.get(peer_id)

    def update_state(self, peer_id: str, state: MyceliumState):
        """
        Update a peer's last known state.

        Also updates heartbeat timestamp.

        Args:
            peer_id: ID of the peer
            state: New state from the peer
        """
        if peer_id in self._peers:
            peer = self._peers[peer_id]
            peer.last_state = state
            peer.last_heartbeat = time.time()
            self._save()

    def heartbeat(self, peer_id: str):
        """
        Update peer heartbeat timestamp.

        Called periodically to indicate peer is still alive.

        Args:
            peer_id: ID of the peer
        """
        if peer_id in self._peers:
            self._peers[peer_id].last_heartbeat = time.time()
            self._save()

    def set_status(self, peer_id: str, status: PeerStatus):
        """
        Update peer status.

        Args:
            peer_id: ID of the peer
            status: New status
        """
        if peer_id in self._peers:
            self._peers[peer_id].status = status
            self._save()

    def get_active_peers(self) -> List[PeerInfo]:
        """
        Get all active peers in deterministic order.

        Returns peers sorted by (registration_timestamp, peer_id).

        Returns:
            List of active PeerInfo objects
        """
        active = [p for p in self._peers.values() if p.is_active()]
        return sorted(active, key=lambda p: p.sort_key())

    def get_peer_states(self) -> List[MyceliumState]:
        """
        Get states from all active peers.

        Returns states in deterministic order (by peer sort key).

        Returns:
            List of MyceliumState objects
        """
        states = []
        for peer in self.get_active_peers():
            if peer.last_state is not None:
                states.append(peer.last_state)
        return states

    def cleanup_expired(self, ttl_seconds: float = None) -> int:
        """
        Remove expired peers.

        Args:
            ttl_seconds: TTL for expiration (defaults to PEER_TTL_SECONDS)

        Returns:
            Number of peers removed
        """
        ttl = ttl_seconds or self.PEER_TTL_SECONDS
        expired = [
            peer_id for peer_id, peer in self._peers.items()
            if peer.is_expired(ttl)
        ]

        for peer_id in expired:
            del self._peers[peer_id]

        if expired:
            self._save()
            logger.info(f"Cleaned up {len(expired)} expired peers")

        return len(expired)

    def count_active(self) -> int:
        """Count active peers."""
        return len([p for p in self._peers.values() if p.is_active()])

    def count_total(self) -> int:
        """Count total registered peers."""
        return len(self._peers)

    def clear(self):
        """Clear all peers from registry."""
        self._peers.clear()
        self._save()

    def get_status(self) -> Dict[str, Any]:
        """Get registry status summary."""
        return {
            "total_peers": self.count_total(),
            "active_peers": self.count_active(),
            "peers": {
                peer_id: {
                    "status": peer.status.value,
                    "agent_type": peer.agent_type,
                    "has_state": peer.last_state is not None
                }
                for peer_id, peer in self._peers.items()
            }
        }

    def checksum(self) -> str:
        """Generate deterministic checksum of registry state."""
        # Get active peers in deterministic order
        peers = self.get_active_peers()
        peer_data = [p.peer_id for p in peers]
        state_str = json.dumps(peer_data, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()[:16]


__all__ = [
    'PeerStatus',
    'FlowPolicy',
    'FlowConfig',
    'PeerInfo',
    'PeerRegistry',
]
