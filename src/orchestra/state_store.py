"""
StateStore - single owner of cognitive-state persistence.

Replaces ad-hoc file I/O previously embedded in websocket_server.py and
http_server.py. Wraps file_ops.atomic_write_json so writes are crash-safe
(write-to-tmp + atomic rename) and adds a threading.Lock so concurrent
loads/saves from a single process are serialized.

This module exists because the cognitive-state file at
~/.orchestra/state/cognitive_state.json was previously written by the
WebSocket server, read by the HTTP server, and managed by
cognitive_state.py — three writers, no central coordinator, no atomic
write in two of them. Collapsing those paths to one StateStore closes
the TOCTOU window, the partial-write window, and the silent-failure
fallback at websocket_server.py:478-479.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional

from .file_ops import atomic_write_json, safe_read_json

DEFAULT_STATE_PATH = Path.home() / ".orchestra" / "state" / "cognitive_state.json"


class StateStore:
    """Atomic, thread-safe JSON persistence for cognitive state.

    The store deals in plain dicts; transports and domain code keep their
    own typed coercion (CognitiveState.to_dict()/from_dict()). Keeping
    this layer schema-agnostic means a single StateStore serves both the
    WebSocket DTO and the canonical CognitiveStateManager without
    importing either.
    """

    def __init__(self, path: Optional[Path] = None):
        self._path = Path(path) if path else DEFAULT_STATE_PATH
        self._lock = threading.Lock()
        self._cached: Optional[Dict[str, Any]] = None

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Dict[str, Any]:
        """Return the current state as a dict.

        Returns {} if the file does not exist. Returns the cached value
        on subsequent calls until save()/reload() invalidates it.

        Raises:
            ValueError: if the file exists but parses to a non-object
                JSON value (refusing to silently coerce).
        """
        with self._lock:
            if self._cached is not None:
                return dict(self._cached)
            data = safe_read_json(self._path, default=None)
            if data is None:
                self._cached = {}
            elif isinstance(data, dict):
                self._cached = dict(data)
            else:
                raise ValueError(
                    f"State file {self._path} contains non-object JSON "
                    f"({type(data).__name__}); refusing to load."
                )
            return dict(self._cached)

    def save(self, state: Dict[str, Any]) -> None:
        """Atomically persist state and refresh the cache."""
        if not isinstance(state, dict):
            raise TypeError(
                f"State must be a dict, got {type(state).__name__}"
            )
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self._path, state)
            self._cached = dict(state)

    def reload(self) -> Dict[str, Any]:
        """Drop the cache and re-read from disk."""
        with self._lock:
            self._cached = None
        return self.load()


_default_store: Optional[StateStore] = None
_default_store_lock = threading.Lock()


def get_default_store() -> StateStore:
    """Return the process-wide default StateStore (lazy)."""
    global _default_store
    with _default_store_lock:
        if _default_store is None:
            _default_store = StateStore()
    return _default_store


def reset_default_store() -> None:
    """Reset the default store (intended for tests only)."""
    global _default_store
    with _default_store_lock:
        _default_store = None
