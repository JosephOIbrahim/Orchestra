"""
WebSocket server for real-time dashboard state updates.

Provides:
- /ws/state - Real-time cognitive state broadcast
- Heartbeat/keepalive for connection monitoring
- Graceful reconnection support

ThinkingMachines [He2025] compliant:
- Deterministic state serialization
- Fixed update intervals
- Pre-computed state mappings

Usage:
    from websocket_server import WebSocketServer

    server = WebSocketServer(port=8081)
    await server.start()
"""

import asyncio
import hmac
import json
import hashlib
import os
import struct
import base64
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Set

from pydantic import Field, TypeAdapter, ValidationError

from .state_store import StateStore, get_default_store

logger = logging.getLogger(__name__)


# Strict per-field validators for the `override` command.
#
# Each entry is a Pydantic TypeAdapter compiled once at import time; the
# override handler consults this table and rejects anything not in it.
# This replaces the previous `validate_field` which fell through to
# `hasattr(self, field)` for any field not in VALID_VALUES — that
# fallback meant unbounded strings, lists, and floats could be injected
# via `setattr`. See websocket_server.py change in claude/expert-codebase-
# review-21b7B for the full rationale.
_BoundedStr64 = Annotated[str, Field(max_length=64)]
_BoundedStr256 = Annotated[str, Field(max_length=256)]
_DomainList = Annotated[List[Annotated[str, Field(max_length=64)]], Field(max_length=16)]

_OVERRIDE_FIELD_TYPES: Dict[str, Any] = {
    # Enums
    "burnout_level": Literal["GREEN", "YELLOW", "ORANGE", "RED"],
    "decision_mode": Literal["work", "delegate", "protect"],
    "momentum_phase": Literal["cold_start", "building", "rolling", "peak", "crashed"],
    "energy_level": Literal["high", "medium", "low", "depleted"],
    "altitude": Literal["30000ft", "15000ft", "5000ft", "Ground"],
    "paradigm": Literal["Cortex", "Mycelium"],
    "current_phase": Literal["detect", "cascade", "lock", "execute", "update"],
    "selected_expert": Literal[
        "validator", "scaffolder", "restorer", "refocuser",
        "celebrator", "socratic", "direct",
    ],
    "lock_status": Literal["unlocked", "locking", "locked"],
    "locked_think_depth": Literal["minimal", "standard", "deep", "ultradeep"],
    "attractor_basin": Literal["focused", "exploring", "recovery", "teaching"],
    # Bounded ints
    "working_memory_used": Annotated[int, Field(ge=0, le=16)],
    "tangent_budget": Annotated[int, Field(ge=0, le=32)],
    "tasks_completed": Annotated[int, Field(ge=0, le=1_000_000)],
    "session_minutes": Annotated[int, Field(ge=0, le=24 * 60)],
    "reflection_iteration": Annotated[int, Field(ge=0, le=3)],
    "stable_exchanges": Annotated[int, Field(ge=0, le=100)],
    # Bounded floats
    "epistemic_tension": Annotated[float, Field(ge=0.0, le=1.0)],
    "epsilon": Annotated[float, Field(ge=0.0, le=1.0)],
    # Bounded strings (Optional where field defaults to None)
    "current_task": Optional[_BoundedStr256],
    "signals_emotional": Optional[_BoundedStr64],
    "signals_mode": Optional[_BoundedStr64],
    "signals_task": Optional[_BoundedStr256],
    "safety_redirect": Optional[_BoundedStr64],
    "expert_trigger": Optional[_BoundedStr256],
    "locked_expert": _BoundedStr64,
    "locked_paradigm": _BoundedStr64,
    "locked_altitude": Annotated[str, Field(max_length=32)],
    "lock_checksum": Optional[Annotated[str, Field(max_length=16)]],
    # Bounded list
    "signals_domain": Optional[_DomainList],
    # Bools
    "body_check_needed": bool,
    "constitutional_pass": bool,
    "safety_gate_pass": bool,
    "converged": bool,
    "feedback_active": bool,
}

_OVERRIDE_VALIDATORS: Dict[str, TypeAdapter] = {
    name: TypeAdapter(typ) for name, typ in _OVERRIDE_FIELD_TYPES.items()
}


@dataclass
class CognitiveState:
    """
    Current cognitive state for dashboard display.

    ThinkingMachines [He2025]: Fixed structure, deterministic serialization.
    Full Orchestra substrate controls - 5-Phase NEXUS Pipeline.

    Phases:
    1. DETECT  - PRISM signal extraction
    2. CASCADE - Constitutional/safety gates + Cognitive Safety MoE expert routing
    3. LOCK    - Parameter locking with MAX3 bounds
    4. EXECUTE - Work/delegate/protect execution
    5. UPDATE  - RC^+xi convergence tracking
    """
    # === EXISTING FIELDS ===
    burnout_level: str = "GREEN"
    decision_mode: str = "work"
    momentum_phase: str = "rolling"
    energy_level: str = "high"
    working_memory_used: int = 2
    tangent_budget: int = 5
    altitude: str = "30000ft"
    paradigm: str = "Cortex"
    body_check_needed: bool = False
    current_task: Optional[str] = None
    tasks_completed: int = 0
    session_minutes: int = 0

    # === PHASE 1: DETECT - PRISM Signals ===
    signals_emotional: Optional[str] = None  # 'frustrated', 'overwhelmed', 'stuck'
    signals_mode: Optional[str] = None  # 'exploring', 'focused', 'teaching'
    signals_domain: Optional[List[str]] = None  # ['usd', 'houdini'], ['react', 'next']
    signals_task: Optional[str] = None  # 'implement', 'debug', 'plan', 'vision'
    current_phase: str = "detect"  # detect|cascade|lock|execute|update

    # === PHASE 2: CASCADE - Expert Routing ===
    constitutional_pass: bool = True
    safety_gate_pass: bool = True
    safety_redirect: Optional[str] = None  # 'validator', 'scaffolder', 'restorer'
    selected_expert: str = "direct"  # validator|scaffolder|restorer|refocuser|celebrator|socratic|direct
    expert_trigger: Optional[str] = None  # The signal that triggered expert selection

    # === PHASE 3: LOCK - Parameter Locking ===
    lock_status: str = "unlocked"  # unlocked|locking|locked
    reflection_iteration: int = 0  # MAX3: 0-3
    locked_expert: str = "direct"
    locked_paradigm: str = "Cortex"
    locked_altitude: str = "30000ft"
    locked_think_depth: str = "standard"  # minimal|standard|deep|ultradeep
    lock_checksum: Optional[str] = None  # 6-char deterministic checksum

    # === PHASE 5: UPDATE - RC^+xi Convergence ===
    epistemic_tension: float = 0.0  # xi_n: 0.0 - 1.0
    epsilon: float = 0.1  # Convergence threshold
    attractor_basin: str = "focused"  # focused|exploring|recovery|teaching
    stable_exchanges: int = 0  # 0-3 (converged at 3)
    converged: bool = False
    feedback_active: bool = True  # Loop indicator

    # Valid values for validation
    VALID_VALUES: Dict[str, list] = None

    def __post_init__(self):
        # Define valid values for each field
        self.VALID_VALUES = {
            'burnout_level': ['GREEN', 'YELLOW', 'ORANGE', 'RED'],
            'decision_mode': ['work', 'delegate', 'protect'],
            'momentum_phase': ['cold_start', 'building', 'rolling', 'peak', 'crashed'],
            'energy_level': ['high', 'medium', 'low', 'depleted'],
            'altitude': ['30000ft', '15000ft', '5000ft', 'Ground'],
            'paradigm': ['Cortex', 'Mycelium'],
            'current_phase': ['detect', 'cascade', 'lock', 'execute', 'update'],
            'selected_expert': ['validator', 'scaffolder', 'restorer', 'refocuser', 'celebrator', 'socratic', 'direct'],
            'lock_status': ['unlocked', 'locking', 'locked'],
            'locked_think_depth': ['minimal', 'standard', 'deep', 'ultradeep'],
            'attractor_basin': ['focused', 'exploring', 'recovery', 'teaching']
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop('VALID_VALUES', None)  # Don't serialize validation rules
        return d

    def checksum(self) -> str:
        """Deterministic checksum for state verification."""
        data = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.md5(data.encode()).hexdigest()[:8]

    def validate_field(self, field: str, value: Any) -> bool:
        """Validate a field value for an `override` command.

        Backed by a Pydantic TypeAdapter per field (see
        ``_OVERRIDE_VALIDATORS``). Fields not in the allowlist are
        rejected; values that fail the adapter's type/range/length
        check are rejected. This replaces the previous fallback
        ``hasattr(self, field)`` which permitted unbounded strings,
        lists, and floats to be injected via ``setattr``.
        """
        adapter = _OVERRIDE_VALIDATORS.get(field)
        if adapter is None:
            return False
        try:
            # strict=True prevents type coercion (e.g. "true" -> True,
            # "5" -> 5). The override path takes JSON-typed values; the
            # adapter must reject mistyped inputs rather than coerce them.
            adapter.validate_python(value, strict=True)
            return True
        except ValidationError:
            return False


class WebSocketServer:
    """
    Minimal WebSocket server for dashboard real-time updates.

    Implements RFC 6455 WebSocket protocol (basic handshake + text frames).
    No external dependencies - pure asyncio.
    """

    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8081,
        update_interval: float = 1.0,
        auth_token: Optional[str] = None,
        store: Optional[StateStore] = None,
    ):
        self.host = host
        self.port = port
        self.update_interval = update_interval
        # Auth token gates state-mutating commands ("override"). Read-only
        # broadcast is unauthenticated, but mutation requires the token.
        # Sourced from explicit arg or ORCHESTRA_TOKEN env var. If neither
        # is set, override is rejected — i.e. the dashboard cannot mutate
        # state without an explicit operator decision.
        self._auth_token = auth_token or os.environ.get("ORCHESTRA_TOKEN")
        # Single owner of the state file. Defaults to the process-wide
        # store so HTTP and WS servers in the same process share state.
        self._store = store or get_default_store()
        self._server: Optional[asyncio.Server] = None
        self._clients: Set[asyncio.StreamWriter] = set()
        self._running = False
        self._state = CognitiveState()
        # Hydrate from existing state file, if any.
        self._apply_state_dict(self._store.load())
        self._broadcast_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            self.host,
            self.port
        )
        self._running = True
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the WebSocket server gracefully."""
        self._running = False
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        # Close all client connections
        for writer in list(self._clients):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self._clients.clear()

        if self._server:
            self._server.close()
            await self._server.wait_closed()
        logger.info("WebSocket server stopped")

    async def serve_forever(self) -> None:
        """Run server until cancelled."""
        if self._server:
            async with self._server:
                await self._server.serve_forever()

    def update_state(self, **kwargs) -> None:
        """
        Update cognitive state.

        Args:
            **kwargs: State fields to update
        """
        for key, value in kwargs.items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)

    def get_state(self) -> CognitiveState:
        """Get current cognitive state."""
        return self._state

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        """Handle incoming WebSocket connection."""
        try:
            # Read HTTP upgrade request
            request_line = await reader.readline()
            if not request_line:
                return

            # Parse request
            parts = request_line.decode().strip().split(' ')
            if len(parts) < 2:
                return

            path = parts[1]

            # Read headers
            headers = {}
            while True:
                line = await reader.readline()
                if line == b'\r\n' or not line:
                    break
                if b':' in line:
                    key, value = line.decode().strip().split(':', 1)
                    headers[key.strip().lower()] = value.strip()

            # Verify WebSocket upgrade request
            if headers.get('upgrade', '').lower() != 'websocket':
                writer.write(b'HTTP/1.1 400 Bad Request\r\n\r\n')
                await writer.drain()
                return

            # Get WebSocket key
            ws_key = headers.get('sec-websocket-key', '')
            if not ws_key:
                writer.write(b'HTTP/1.1 400 Bad Request\r\n\r\n')
                await writer.drain()
                return

            # Calculate accept key
            accept_key = self._calculate_accept_key(ws_key)

            # Send upgrade response
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key}\r\n"
                "\r\n"
            )
            writer.write(response.encode())
            await writer.drain()

            # Add to clients
            self._clients.add(writer)
            logger.info(f"WebSocket client connected: {path}")

            # Send initial state
            await self._send_state(writer)

            # Keep connection alive, handle incoming frames
            while self._running:
                try:
                    # Read frame with timeout
                    data = await asyncio.wait_for(reader.read(2), timeout=30.0)
                    if not data:
                        break

                    # Parse frame header
                    opcode = data[0] & 0x0f
                    masked = (data[1] & 0x80) != 0
                    payload_len = data[1] & 0x7f

                    # Handle extended payload length
                    if payload_len == 126:
                        ext = await reader.read(2)
                        payload_len = struct.unpack('>H', ext)[0]
                    elif payload_len == 127:
                        ext = await reader.read(8)
                        payload_len = struct.unpack('>Q', ext)[0]

                    # Read mask key if present
                    mask_key = None
                    if masked:
                        mask_key = await reader.read(4)

                    # Read payload
                    payload = b''
                    if payload_len > 0:
                        payload = await reader.read(payload_len)
                        if masked and mask_key:
                            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

                    if opcode == 0x8:  # Close frame
                        break
                    elif opcode == 0x9:  # Ping
                        await self._send_frame(writer, 0x0a, b'')
                    elif opcode == 0x0a:  # Pong
                        pass
                    elif opcode == 0x1:  # Text frame - handle commands
                        await self._handle_command(payload.decode('utf-8'), writer)

                except asyncio.TimeoutError:
                    # Send ping to keep alive
                    try:
                        await self._send_frame(writer, 0x9, b'')
                    except Exception:
                        break
                except Exception as e:
                    logger.error(f"Frame handling error: {e}")
                    break

        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self._clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("WebSocket client disconnected")

    def _calculate_accept_key(self, key: str) -> str:
        """Calculate WebSocket accept key per RFC 6455."""
        import hashlib
        combined = key + self.GUID
        sha1 = hashlib.sha1(combined.encode()).digest()
        return base64.b64encode(sha1).decode()

    async def _send_frame(self, writer: asyncio.StreamWriter, opcode: int, data: bytes) -> None:
        """Send WebSocket frame."""
        length = len(data)

        # Build frame header
        frame = bytes([0x80 | opcode])  # FIN + opcode

        if length < 126:
            frame += bytes([length])
        elif length < 65536:
            frame += bytes([126]) + struct.pack('>H', length)
        else:
            frame += bytes([127]) + struct.pack('>Q', length)

        frame += data
        writer.write(frame)
        await writer.drain()

    async def _send_state(self, writer: asyncio.StreamWriter) -> None:
        """Send current state to a client."""
        try:
            data = json.dumps(self._state.to_dict(), sort_keys=True).encode()
            await self._send_frame(writer, 0x1, data)  # Text frame
        except Exception as e:
            logger.error(f"Error sending state: {e}")
            self._clients.discard(writer)

    async def _handle_command(self, message: str, writer: asyncio.StreamWriter) -> None:
        """
        Handle incoming command from dashboard.

        Command format:
        {
            "type": "override",
            "field": "decision_mode",
            "value": "protect"
        }
        """
        try:
            cmd = json.loads(message)
            cmd_type = cmd.get('type')

            if cmd_type == 'override':
                # Auth gate: require ORCHESTRA_TOKEN. Without a configured
                # token, no override is ever accepted — fail closed.
                token = cmd.get('token', '')
                if not self._auth_token or not isinstance(token, str) or \
                        not hmac.compare_digest(token, self._auth_token):
                    logger.warning(
                        "Override rejected: missing or invalid token "
                        "(client=%s)",
                        writer.get_extra_info("peername"),
                    )
                    return

                field = cmd.get('field')
                value = cmd.get('value')

                # Note: the prior `field and value` test rejected legitimate
                # falsy values like False / 0 / ""; tighten to "field is a
                # non-empty string AND value passes the typed allowlist."
                # validate_field now consults the Pydantic TypeAdapter
                # table — fields outside that allowlist are rejected.
                if (
                    isinstance(field, str)
                    and field
                    and self._state.validate_field(field, value)
                ):
                    setattr(self._state, field, value)
                    self._save_state_to_file()
                    logger.info(f"Override applied: {field} = {value}")

                    # Broadcast updated state to all clients immediately
                    for client in list(self._clients):
                        await self._send_state(client)
                else:
                    logger.warning(f"Invalid override: field=%r", field)

        except json.JSONDecodeError:
            logger.warning(f"Invalid command JSON: {message}")
        except Exception as e:
            logger.error(f"Command handling error: {e}")

    # Backwards-compat path attribute. The actual file is owned by
    # StateStore; reading these here keeps any external callers working.
    @property
    def STATE_FILE(self) -> Path:  # noqa: N802 (legacy shape preserved)
        return self._store.path

    @property
    def STATE_DIR(self) -> Path:  # noqa: N802
        return self._store.path.parent

    def _save_state_to_file(self) -> None:
        """Persist current cognitive state via the StateStore (atomic)."""
        try:
            self._store.save(self._state.to_dict())
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    async def _broadcast_loop(self) -> None:
        """Broadcast state updates to all connected clients."""
        while self._running:
            await asyncio.sleep(self.update_interval)

            # Refresh state from the store (in case another process or
            # the orchestrator wrote it).
            try:
                self._apply_state_dict(self._store.reload())
            except Exception as e:
                # Surface load failures rather than silently fall through
                # to the previous behavior. The store will retain the last
                # known good cache, so we proceed with what we have.
                logger.warning("State reload failed during broadcast: %s", e)

            # Broadcast to all clients
            for writer in list(self._clients):
                await self._send_state(writer)

    def _load_state_from_file(self) -> None:
        """Load cognitive state from the StateStore."""
        try:
            self._apply_state_dict(self._store.load())
        except Exception as e:
            logger.warning("State load failed: %s", e)

    def _apply_state_dict(self, data: Dict[str, Any]) -> None:
        """Apply a dict of fields to the in-memory state.

        Only known dataclass fields are applied; unknown keys in the
        on-disk payload are ignored (so future schema additions don't
        crash older readers, and stray keys can't inject attributes).
        """
        if not data:
            return
        # Build the allowlist from the dataclass field set, excluding the
        # validation-only VALID_VALUES marker. setattr is bounded to this
        # set of declared fields — no hasattr fallback.
        from dataclasses import fields as _fields
        allowed = {f.name for f in _fields(self._state)} - {"VALID_VALUES"}
        for key, value in data.items():
            if key in allowed:
                setattr(self._state, key, value)


async def start_websocket_server(
    port: int = 8081,
    host: str = "127.0.0.1",
    auth_token: Optional[str] = None,
) -> WebSocketServer:
    """
    Start the WebSocket server.

    Args:
        port: Port to listen on
        host: Host to bind to (default 127.0.0.1; bind to 0.0.0.0 only with
            an explicit ORCHESTRA_TOKEN set)
        auth_token: Optional shared-secret for state-mutating commands.
            Falls back to the ORCHESTRA_TOKEN env var.

    Returns:
        Running WebSocketServer instance
    """
    server = WebSocketServer(host=host, port=port, auth_token=auth_token)
    await server.start()
    return server


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Orchestra WebSocket Server')
    parser.add_argument('--port', type=int, default=8081, help='Port to listen on')
    parser.add_argument(
        '--host', type=str, default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1; use 0.0.0.0 only with '
             'ORCHESTRA_TOKEN set in env)',
    )
    args = parser.parse_args()

    async def main():
        server = await start_websocket_server(port=args.port, host=args.host)
        print(f"WebSocket server running on ws://{args.host}:{args.port}")
        print("Endpoints: /ws/state")
        print("Press Ctrl+C to stop")
        try:
            await server.serve_forever()
        except KeyboardInterrupt:
            await server.stop()

    asyncio.run(main())
