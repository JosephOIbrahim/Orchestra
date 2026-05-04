"""Tests for StateStore — single owner of cognitive_state.json persistence."""

import json
import threading
from pathlib import Path

import pytest

from orchestra.state_store import (
    DEFAULT_STATE_PATH,
    StateStore,
    get_default_store,
    reset_default_store,
)


@pytest.fixture
def tmp_store(tmp_path: Path) -> StateStore:
    return StateStore(path=tmp_path / "state.json")


class TestStateStoreBasics:
    def test_load_returns_empty_dict_when_missing(self, tmp_store: StateStore):
        assert tmp_store.load() == {}

    def test_save_and_load_roundtrip(self, tmp_store: StateStore):
        payload = {"burnout_level": "YELLOW", "tasks_completed": 7}
        tmp_store.save(payload)
        assert tmp_store.load() == payload

    def test_save_writes_atomically_to_disk(self, tmp_store: StateStore):
        tmp_store.save({"a": 1})
        # The on-disk content must be valid JSON immediately after save.
        on_disk = json.loads(tmp_store.path.read_text())
        assert on_disk == {"a": 1}

    def test_reload_picks_up_external_changes(self, tmp_store: StateStore):
        tmp_store.save({"v": 1})
        # Simulate another process mutating the file.
        tmp_store.path.write_text(json.dumps({"v": 2}))
        # Cached load returns the stale value...
        assert tmp_store.load() == {"v": 1}
        # ...but reload() invalidates the cache.
        assert tmp_store.reload() == {"v": 2}

    def test_load_returns_copy_not_internal_state(self, tmp_store: StateStore):
        tmp_store.save({"k": [1, 2]})
        snapshot = tmp_store.load()
        snapshot["mutated"] = True
        # Mutations on the returned dict must not pollute the cache.
        assert "mutated" not in tmp_store.load()


class TestStateStoreErrorHandling:
    def test_rejects_non_dict_save(self, tmp_store: StateStore):
        with pytest.raises(TypeError):
            tmp_store.save([1, 2, 3])  # type: ignore[arg-type]

    def test_rejects_non_object_json_on_load(self, tmp_path: Path):
        target = tmp_path / "bad.json"
        target.write_text("[1, 2, 3]")
        store = StateStore(path=target)
        with pytest.raises(ValueError):
            store.load()

    def test_invalid_json_returns_empty_via_safe_read(self, tmp_path: Path):
        target = tmp_path / "garbage.json"
        target.write_text("not json at all")
        store = StateStore(path=target)
        # safe_read_json returns None for invalid; StateStore treats as {}.
        assert store.load() == {}


class TestStateStoreConcurrency:
    def test_concurrent_saves_dont_corrupt(self, tmp_store: StateStore):
        # Two threads racing on save() must end with one consistent
        # parseable JSON file (atomic write + lock guarantees this).
        def writer(value: int):
            for _ in range(20):
                tmp_store.save({"value": value})

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        final = json.loads(tmp_store.path.read_text())
        assert "value" in final
        assert final["value"] in {0, 1, 2, 3}


class TestDefaultStore:
    def test_get_default_store_is_singleton(self):
        reset_default_store()
        a = get_default_store()
        b = get_default_store()
        assert a is b

    def test_default_path(self):
        reset_default_store()
        assert get_default_store().path == DEFAULT_STATE_PATH
