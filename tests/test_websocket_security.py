"""Tests for WebSocket server hardening: bind default, token auth, and
the Pydantic-backed override allowlist that replaces the dangerous
setattr-via-hasattr path.
"""

import asyncio
import json

import pytest

from orchestra.state_store import StateStore
from orchestra.websocket_server import (
    CognitiveState,
    WebSocketServer,
    _OVERRIDE_VALIDATORS,
)


class TestSecureDefaults:
    def test_default_bind_is_loopback(self):
        # Exposing on the network must be an explicit operator decision.
        s = WebSocketServer()
        assert s.host == "127.0.0.1"

    def test_no_token_means_overrides_rejected(self):
        # Without ORCHESTRA_TOKEN set and no auth_token argument, no
        # override can be accepted.
        s = WebSocketServer(auth_token=None)
        assert s._auth_token is None or s._auth_token == ""


class TestOverrideAllowlist:
    """The previous validate_field had a hasattr() fallback that allowed
    any unbounded attribute. The new path uses Pydantic TypeAdapters in
    strict mode against an explicit allowlist."""

    def setup_method(self):
        self.state = CognitiveState()

    def test_valid_enum_accepted(self):
        assert self.state.validate_field("burnout_level", "YELLOW")

    def test_invalid_enum_rejected(self):
        assert not self.state.validate_field("burnout_level", "PURPLE")

    def test_bounded_int_in_range_accepted(self):
        assert self.state.validate_field("working_memory_used", 5)

    def test_bounded_int_out_of_range_rejected(self):
        assert not self.state.validate_field("working_memory_used", 9999)
        assert not self.state.validate_field("working_memory_used", -1)

    def test_bounded_float_accepted(self):
        assert self.state.validate_field("epistemic_tension", 0.5)

    def test_bounded_float_out_of_range_rejected(self):
        assert not self.state.validate_field("epistemic_tension", 99.0)
        assert not self.state.validate_field("epistemic_tension", -0.1)

    def test_short_string_accepted(self):
        assert self.state.validate_field("signals_task", "implement feature x")

    def test_oversized_string_rejected_dos_vector(self):
        # The headline DoS vector: 10MB string injection via override.
        assert not self.state.validate_field("signals_task", "x" * 10_000_000)

    def test_oversized_list_rejected_dos_vector(self):
        assert not self.state.validate_field("signals_domain", ["x"] * 100)

    def test_strict_mode_rejects_type_coercion(self):
        # Pydantic's lax mode would coerce "true" -> True, "5" -> 5.
        # Strict mode prevents this — JSON-typed values must arrive
        # already-typed.
        assert not self.state.validate_field("feedback_active", "true")
        assert not self.state.validate_field("working_memory_used", "5")

    def test_unknown_field_rejected(self):
        # The previous hasattr(self, field) fallback allowed any
        # attribute. Now: only the explicit allowlist.
        assert not self.state.validate_field("arbitrary_new_field", 1)

    def test_private_attribute_rejected(self):
        # The hasattr fallback would have permitted setattr on _running,
        # _clients, _server etc. — operationally devastating.
        assert not self.state.validate_field("_running", False)
        assert not self.state.validate_field("VALID_VALUES", {})

    def test_allowlist_size(self):
        # Sanity check: the allowlist covers the actual dataclass fields
        # we expect to be operator-overridable.
        assert len(_OVERRIDE_VALIDATORS) >= 30


class TestWebSocketServerWithStateStore:
    def test_store_is_used_for_persistence(self, tmp_path):
        # Server should hydrate from the StateStore on construction and
        # delegate saves to it — no ad-hoc open() calls.
        store = StateStore(path=tmp_path / "state.json")
        store.save({"burnout_level": "RED"})

        server = WebSocketServer(store=store)
        assert server._state.burnout_level == "RED"
        # State_FILE / STATE_DIR properties point at the store path.
        assert server.STATE_FILE == store.path
        assert server.STATE_DIR == store.path.parent

    def test_save_persists_via_store(self, tmp_path):
        store = StateStore(path=tmp_path / "state.json")
        server = WebSocketServer(store=store)
        server._state.burnout_level = "ORANGE"
        server._save_state_to_file()
        # The store must now have the value (atomic write).
        assert store.reload()["burnout_level"] == "ORANGE"

    def test_load_ignores_unknown_keys_in_file(self, tmp_path):
        # A malicious or stale state file with extra keys must not be
        # able to inject attributes onto the dataclass.
        store = StateStore(path=tmp_path / "state.json")
        store.save({"burnout_level": "GREEN", "_running": True, "evil": 1})
        server = WebSocketServer(store=store)
        # _running stayed as initialized (False); 'evil' isn't an attr.
        assert server._running is False
        assert not hasattr(server._state, "evil")


@pytest.mark.asyncio
async def test_handle_command_rejects_override_without_token(tmp_path):
    """Override commands must be rejected when no token is configured."""
    store = StateStore(path=tmp_path / "state.json")
    server = WebSocketServer(auth_token=None, store=store)

    # Construct a fake writer with the methods _handle_command touches.
    class FakeWriter:
        def get_extra_info(self, _):
            return ("test", 0)

        def write(self, _):
            pass

        async def drain(self):
            pass

    writer = FakeWriter()

    cmd = json.dumps({
        "type": "override",
        "field": "burnout_level",
        "value": "RED",
        # No token provided.
    })
    await server._handle_command(cmd, writer)
    # State must not have been mutated.
    assert server._state.burnout_level == "GREEN"


@pytest.mark.asyncio
async def test_handle_command_accepts_override_with_token(tmp_path):
    store = StateStore(path=tmp_path / "state.json")
    server = WebSocketServer(auth_token="s3cr3t", store=store)

    class FakeWriter:
        def get_extra_info(self, _):
            return ("test", 0)

        def write(self, _):
            pass

        async def drain(self):
            pass

    writer = FakeWriter()
    cmd = json.dumps({
        "type": "override",
        "field": "burnout_level",
        "value": "ORANGE",
        "token": "s3cr3t",
    })
    await server._handle_command(cmd, writer)
    assert server._state.burnout_level == "ORANGE"


@pytest.mark.asyncio
async def test_handle_command_rejects_override_with_wrong_token(tmp_path):
    store = StateStore(path=tmp_path / "state.json")
    server = WebSocketServer(auth_token="s3cr3t", store=store)

    class FakeWriter:
        def get_extra_info(self, _):
            return ("test", 0)

        def write(self, _):
            pass

        async def drain(self):
            pass

    writer = FakeWriter()
    cmd = json.dumps({
        "type": "override",
        "field": "burnout_level",
        "value": "ORANGE",
        "token": "wrong",
    })
    await server._handle_command(cmd, writer)
    assert server._state.burnout_level == "GREEN"
