"""
Tests for Determinism Proxy (L1 Boundary Layer).

Verifies:
- Prompt canonicalization stability
- Response cache hit/miss behavior
- Structured output enforcement
- Cache TTL expiry
- Integration patterns
"""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestra.determinism_proxy import (
    CachedResponse,
    DeterminismProxy,
    PromptCanonicalizer,
    ResponseCache,
    StructuredOutputEnforcer,
)


# =============================================================================
# PromptCanonicalizer Tests
# =============================================================================

class TestPromptCanonicalizer:
    """Tests for prompt canonicalization."""

    def setup_method(self):
        self.canon = PromptCanonicalizer()

    def test_canonicalization_stable(self):
        """Same prompt with different whitespace -> same hash."""
        prompt1 = "Hello   world,   how  are   you?"
        prompt2 = "Hello world, how are you?"
        prompt3 = "Hello  world,  how  are  you?"

        hash1 = self.canon.canonical_hash(prompt1)
        hash2 = self.canon.canonical_hash(prompt2)
        hash3 = self.canon.canonical_hash(prompt3)

        assert hash1 == hash2 == hash3

    def test_canonicalization_trailing_whitespace(self):
        """Trailing whitespace is stripped."""
        prompt1 = "Hello world   \nLine 2   \n"
        prompt2 = "Hello world\nLine 2\n"

        assert self.canon.canonical_hash(prompt1) == self.canon.canonical_hash(prompt2)

    def test_canonicalization_multiple_blank_lines(self):
        """Multiple blank lines collapsed to single."""
        prompt1 = "Line 1\n\n\n\nLine 2"
        prompt2 = "Line 1\n\nLine 2"

        assert self.canon.canonical_hash(prompt1) == self.canon.canonical_hash(prompt2)

    def test_canonicalization_unicode_nfc(self):
        """Unicode is NFC-normalized."""
        # e-acute composed vs decomposed
        prompt1 = "caf\u00e9"  # NFC: single codepoint
        prompt2 = "cafe\u0301"  # NFD: e + combining accent

        assert self.canon.canonical_hash(prompt1) == self.canon.canonical_hash(prompt2)

    def test_canonicalization_preserves_code_blocks(self):
        """Code block whitespace is preserved."""
        prompt = "Text before\n```\n  indented  code  \n```\nText after"
        canonical = self.canon.canonicalize(prompt)

        assert "  indented  code  " in canonical

    def test_canonicalization_empty_prompt(self):
        """Empty prompt returns empty string."""
        assert self.canon.canonicalize("") == ""

    def test_canonical_hash_format(self):
        """Hash is 32-char hex string."""
        h = self.canon.canonical_hash("test")
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_content_different_hash(self):
        """Different content produces different hashes."""
        h1 = self.canon.canonical_hash("Hello world")
        h2 = self.canon.canonical_hash("Goodbye world")
        assert h1 != h2

    def test_canonicalization_deterministic(self):
        """Same prompt always produces same canonical form."""
        prompt = "  Test   prompt   with   extra   spaces  "
        results = set()
        for _ in range(100):
            results.add(self.canon.canonical_hash(prompt))
        assert len(results) == 1

    def test_sort_tool_definitions(self):
        """Tool definitions in JSON are sorted alphabetically."""
        prompt = '{"tools": [{"name": "zebra"}, {"name": "apple"}]}'
        canonical = self.canon.canonicalize(prompt)
        # After canonicalization, apple should come before zebra
        apple_pos = canonical.find("apple")
        zebra_pos = canonical.find("zebra")
        assert apple_pos < zebra_pos


# =============================================================================
# ResponseCache Tests
# =============================================================================

class TestResponseCache:
    """Tests for response caching."""

    def test_cache_miss(self, tmp_path):
        """New hash returns None."""
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        result = cache.get("nonexistent_hash")
        assert result is None

    def test_cache_hit(self, tmp_path):
        """Stored response is retrievable."""
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        cache.put("test_hash", {"result": "hello"})

        cached = cache.get("test_hash")
        assert cached is not None
        assert cached.response == {"result": "hello"}

    def test_cache_hit_no_api_call(self, tmp_path):
        """Second call returns cached response without API call."""
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        cache.put("test_hash", {"result": "cached"})

        # First get - cache hit
        result1 = cache.get("test_hash")
        # Second get - still cache hit
        result2 = cache.get("test_hash")

        assert result1.response == result2.response
        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 0

    def test_cache_ttl_expiry(self, tmp_path):
        """Expired entries return None."""
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl_seconds=1)
        cache.put("test_hash", {"result": "will expire"})

        # Immediately available
        assert cache.get("test_hash") is not None

        # Wait for expiry
        time.sleep(1.1)

        # Now expired
        assert cache.get("test_hash") is None

    def test_cache_filesystem_persistence(self, tmp_path):
        """Cache entries persist to filesystem."""
        cache_dir = tmp_path / "cache"
        cache1 = ResponseCache(cache_dir=cache_dir, ttl_seconds=3600)
        cache1.put("persist_hash", {"result": "persistent"})

        # Create new cache instance (simulates restart)
        cache2 = ResponseCache(cache_dir=cache_dir, ttl_seconds=3600)
        cached = cache2.get("persist_hash")
        assert cached is not None
        assert cached.response == {"result": "persistent"}

    def test_cache_invalidation(self, tmp_path):
        """Invalidated entries are removed."""
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        cache.put("to_remove", {"result": "temporary"})
        assert cache.get("to_remove") is not None

        cache.invalidate("to_remove")
        assert cache.get("to_remove") is None

    def test_cache_clear(self, tmp_path):
        """Clear removes all entries."""
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        cache.put("hash1", {"result": 1})
        cache.put("hash2", {"result": 2})

        count = cache.clear()
        assert count >= 2
        assert cache.get("hash1") is None
        assert cache.get("hash2") is None

    def test_cache_stats(self, tmp_path):
        """Stats track hits and misses."""
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)

        cache.get("miss1")  # miss
        cache.get("miss2")  # miss
        cache.put("hit1", {"result": 1})
        cache.get("hit1")  # hit

        stats = cache.get_stats()
        assert stats["misses"] == 2
        assert stats["hits"] == 1


# =============================================================================
# StructuredOutputEnforcer Tests
# =============================================================================

class TestStructuredOutputEnforcer:
    """Tests for structured output enforcement."""

    def setup_method(self):
        self.enforcer = StructuredOutputEnforcer()

    def test_routing_task_gets_schema(self):
        """Routing tasks get JSON schema enforcement."""
        params = self.enforcer.enforce("routing")
        assert "response_format" in params
        schema = params["response_format"]["schema"]
        assert "expert" in schema["properties"]
        assert "confidence" in schema["properties"]

    def test_unknown_task_returns_empty(self):
        """Unknown task types return empty params."""
        params = self.enforcer.enforce("unknown_type")
        assert params == {}

    def test_none_task_returns_empty(self):
        """None task type returns empty params."""
        params = self.enforcer.enforce(None)
        assert params == {}

    def test_supported_types(self):
        """All declared types are supported."""
        types = self.enforcer.get_supported_types()
        assert "routing" in types
        assert "classification" in types
        assert "decision" in types


# =============================================================================
# DeterminismProxy Tests
# =============================================================================

class TestDeterminismProxy:
    """Tests for the unified proxy."""

    def test_sync_call_cache_hit(self, tmp_path):
        """Sync call returns cached response on second call."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")

        api_calls = []

        def mock_api(prompt, **kwargs):
            api_calls.append(prompt)
            return {"result": "from_api"}

        # First call - cache miss, calls API
        result1 = proxy.call_sync("test prompt", api_func=mock_api)
        assert result1 == {"result": "from_api"}
        assert len(api_calls) == 1

        # Second call - cache hit, skips API
        result2 = proxy.call_sync("test prompt", api_func=mock_api)
        assert result2 == {"result": "from_api"}
        assert len(api_calls) == 1  # Still 1 - API not called again

    def test_sync_call_cache_miss(self, tmp_path):
        """New prompt triggers API call."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")

        def mock_api(prompt, **kwargs):
            return {"result": prompt[:10]}

        result = proxy.call_sync("unique prompt", api_func=mock_api)
        assert result == {"result": "unique pro"}

    def test_whitespace_normalized_same_cache(self, tmp_path):
        """Same prompt with different whitespace hits same cache entry."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")

        api_calls = []

        def mock_api(prompt, **kwargs):
            api_calls.append(prompt)
            return {"result": "cached"}

        proxy.call_sync("hello   world", api_func=mock_api)
        proxy.call_sync("hello world", api_func=mock_api)

        assert len(api_calls) == 1  # Only one API call

    def test_structured_output_routing(self, tmp_path):
        """Routing tasks get JSON schema parameters."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")

        received_kwargs = {}

        def mock_api(prompt, **kwargs):
            received_kwargs.update(kwargs)
            return {"expert": "direct"}

        proxy.call_sync(
            "route this signal",
            api_func=mock_api,
            task_type="routing",
        )

        assert "response_format" in received_kwargs

    def test_bypass_cache(self, tmp_path):
        """bypass_cache=True forces fresh API call."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")

        api_calls = []

        def mock_api(prompt, **kwargs):
            api_calls.append(prompt)
            return {"result": len(api_calls)}

        proxy.call_sync("test", api_func=mock_api)
        proxy.call_sync("test", api_func=mock_api, bypass_cache=True)

        assert len(api_calls) == 2

    def test_no_api_func_raises(self, tmp_path):
        """Missing api_func raises ValueError on cache miss."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")
        with pytest.raises(ValueError, match="api_func is required"):
            proxy.call_sync("test")

    def test_cache_disabled(self, tmp_path):
        """Proxy works with cache disabled."""
        proxy = DeterminismProxy(
            cache_dir=tmp_path / "cache",
            enable_cache=False,
        )

        api_calls = []

        def mock_api(prompt, **kwargs):
            api_calls.append(prompt)
            return {"result": "no_cache"}

        proxy.call_sync("test", api_func=mock_api)
        proxy.call_sync("test", api_func=mock_api)

        assert len(api_calls) == 2  # Both trigger API

    def test_stats(self, tmp_path):
        """Proxy tracks call statistics."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")

        def mock_api(prompt, **kwargs):
            return {"result": "ok"}

        proxy.call_sync("test1", api_func=mock_api)
        proxy.call_sync("test1", api_func=mock_api)  # cache hit
        proxy.call_sync("test2", api_func=mock_api)

        stats = proxy.get_stats()
        assert stats["total_calls"] == 3
        assert stats["cache_bypasses"] == 2  # 2 unique prompts
        assert stats["cache"]["hits"] == 1
        assert stats["cache"]["misses"] == 2

    @pytest.mark.asyncio
    async def test_async_call(self, tmp_path):
        """Async call works correctly."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")

        async def mock_api(prompt, **kwargs):
            return {"result": "async_ok"}

        result = await proxy.call("test async", api_func=mock_api)
        assert result == {"result": "async_ok"}

    @pytest.mark.asyncio
    async def test_async_cache_hit(self, tmp_path):
        """Async call returns cached response."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")
        call_count = 0

        async def mock_api(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"result": "async_cached"}

        await proxy.call("test async", api_func=mock_api)
        await proxy.call("test async", api_func=mock_api)

        assert call_count == 1


# =============================================================================
# Idempotency Integration Tests
# =============================================================================

class TestIdempotencyIntegration:
    """Tests verifying compatibility with existing IdempotencyManager patterns."""

    def test_cache_key_matches_idempotency_pattern(self):
        """Canonical hash can serve as idempotency key."""
        from orchestra.idempotency import generate_idempotency_key

        canon = PromptCanonicalizer()
        prompt = "test prompt for idempotency"
        cache_key = canon.canonical_hash(prompt)

        # Both generate 32-char hex strings
        idem_key = generate_idempotency_key("agent", prompt, 1)
        assert len(cache_key) == 32
        assert len(idem_key) == 32

    def test_canonical_hash_deterministic_like_idempotency(self):
        """Canonical hash is deterministic (same as idempotency requirement)."""
        canon = PromptCanonicalizer()
        prompt = "deterministic test"

        hashes = set()
        for _ in range(100):
            hashes.add(canon.canonical_hash(prompt))

        assert len(hashes) == 1
