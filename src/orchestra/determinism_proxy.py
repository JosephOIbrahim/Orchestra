"""
Determinism Proxy (L1 Boundary Layer)
======================================

Absorbs token-level nondeterminism at the application boundary.

Three mitigation strategies inspired by ThinkingMachines [He2025]:
1. Canonicalization — Normalize prompt bytes (fixed input tile boundaries)
2. Response Cache — Bypass nondeterministic layer for repeated queries
3. Structured Output — Constrain output token space (reduce argmax flips)

Wraps any API call with: Canonicalize → Cache check → API call → Cache store.

Usage:
    proxy = DeterminismProxy()

    # Sync usage
    response = proxy.call_sync(prompt, task_type="routing")

    # Async usage
    response = await proxy.call(prompt, task_type="routing")

Performance:
    - Cache hit: ~5ms (bypass API entirely)
    - Cache miss: ~50ms overhead (canonicalization + hash + cache store)
    - Net: cache hits make system FASTER than uncached
"""

import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .file_ops import atomic_write_json, safe_read_json, ensure_directory

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_CACHE_DIR = Path.home() / ".orchestra" / "cache" / "responses"
DEFAULT_TTL_SECONDS = 3600  # 1 hour


# =============================================================================
# Prompt Canonicalization
# =============================================================================

class PromptCanonicalizer:
    """
    Normalize prompts to canonical byte representation.

    He2025 analog: Fixing the input tile boundaries ensures the same
    logical query always has the same physical representation.

    Canonicalization steps (FIXED order):
    1. Unicode NFC normalization
    2. Strip trailing whitespace per line
    3. Collapse multiple blank lines to single
    4. Collapse multiple spaces to single (outside code blocks)
    5. Sort tool definitions alphabetically by name
    6. Deterministic JSON serialization for structured content
    """

    def canonicalize(self, prompt: str) -> str:
        """
        Normalize a prompt to canonical form.

        Args:
            prompt: Raw prompt string

        Returns:
            Canonical prompt string
        """
        if not prompt:
            return ""

        result = prompt

        # 1. Unicode NFC normalization
        result = unicodedata.normalize("NFC", result)

        # 2-4: Process outside code blocks only
        # Split on code block markers first to preserve code block content
        parts = re.split(r"(```[\s\S]*?```)", result)
        processed_parts = []
        for part in parts:
            if part.startswith("```"):
                # Code block — preserve exactly
                processed_parts.append(part)
            else:
                # Non-code: strip trailing whitespace, collapse blank lines, normalize spaces
                lines = part.split("\n")
                lines = [line.rstrip() for line in lines]

                # Collapse multiple blank lines to single
                collapsed = []
                prev_blank = False
                for line in lines:
                    is_blank = line.strip() == ""
                    if is_blank and prev_blank:
                        continue
                    collapsed.append(line)
                    prev_blank = is_blank

                # Collapse multiple spaces to single
                collapsed = [re.sub(r"  +", " ", line) for line in collapsed]
                processed_parts.append("\n".join(collapsed))

        result = "".join(processed_parts)

        # 5. Sort tool definitions if present
        result = self._sort_tool_definitions(result)

        return result.rstrip("\n")

    def canonical_hash(self, prompt: str) -> str:
        """
        SHA-256 hash of canonical form — used as cache key.

        Args:
            prompt: Raw or canonical prompt string

        Returns:
            Hex string of first 32 chars of SHA-256 hash
        """
        canonical = self.canonicalize(prompt)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    def _normalize_whitespace(self, text: str) -> str:
        """Collapse multiple spaces to single outside code blocks."""
        # Split on code block markers
        parts = re.split(r"(```[\s\S]*?```)", text)
        normalized = []
        for i, part in enumerate(parts):
            if part.startswith("```"):
                # Code block — preserve exactly
                normalized.append(part)
            else:
                # Non-code — collapse spaces (but preserve newlines)
                lines = part.split("\n")
                lines = [re.sub(r"  +", " ", line) for line in lines]
                normalized.append("\n".join(lines))
        return "".join(normalized)

    def _sort_tool_definitions(self, text: str) -> str:
        """Sort tool definition blocks alphabetically by name."""
        # Match JSON tool arrays: "tools": [...]
        tool_pattern = r'"tools"\s*:\s*\[([^\]]*)\]'
        match = re.search(tool_pattern, text, re.DOTALL)
        if not match:
            return text

        try:
            # Extract, parse, sort, and replace
            tools_str = "[" + match.group(1) + "]"
            tools = json.loads(tools_str)
            tools.sort(key=lambda t: t.get("name", ""))
            sorted_str = json.dumps(tools, sort_keys=True, separators=(",", ":"))
            return text[:match.start()] + '"tools":' + sorted_str + text[match.end():]
        except (json.JSONDecodeError, TypeError):
            return text


# =============================================================================
# Response Cache
# =============================================================================

@dataclass
class CachedResponse:
    """A cached API response with metadata."""
    response: Any
    canonical_hash: str
    cached_at: float
    ttl_seconds: int
    hit_count: int = 0

    @property
    def age_seconds(self) -> float:
        return time.time() - self.cached_at

    @property
    def is_expired(self) -> bool:
        return self.age_seconds > self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response": self.response,
            "canonical_hash": self.canonical_hash,
            "cached_at": self.cached_at,
            "ttl_seconds": self.ttl_seconds,
            "hit_count": self.hit_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CachedResponse":
        return cls(
            response=data["response"],
            canonical_hash=data["canonical_hash"],
            cached_at=data["cached_at"],
            ttl_seconds=data["ttl_seconds"],
            hit_count=data.get("hit_count", 0),
        )


class ResponseCache:
    """
    Hash(canonical_prompt) -> cached response.

    Filesystem-backed for persistence across sessions.
    TTL-based expiry (configurable, default 1 hour).

    Reuses patterns from:
    - idempotency.py's ExecutionRecord (cache structure)
    - file_ops.py's atomic_write_json (safe persistence)
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = 1000,
    ):
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._memory_cache: Dict[str, CachedResponse] = {}

        # Stats
        self._hits = 0
        self._misses = 0

        ensure_directory(self.cache_dir)

    def get(self, canonical_hash: str) -> Optional[CachedResponse]:
        """
        Get cached response by canonical hash.

        Checks memory cache first, then filesystem.

        Args:
            canonical_hash: SHA-256 hash of canonical prompt

        Returns:
            CachedResponse if found and not expired, None otherwise
        """
        # Memory cache (fast path)
        if canonical_hash in self._memory_cache:
            cached = self._memory_cache[canonical_hash]
            if not cached.is_expired:
                cached.hit_count += 1
                self._hits += 1
                logger.debug(f"Cache hit (memory): {canonical_hash[:8]}")
                return cached
            else:
                del self._memory_cache[canonical_hash]

        # Filesystem cache
        cache_file = self.cache_dir / f"{canonical_hash}.json"
        data = safe_read_json(cache_file)
        if data is not None:
            try:
                cached = CachedResponse.from_dict(data)
                if not cached.is_expired:
                    cached.hit_count += 1
                    self._memory_cache[canonical_hash] = cached
                    self._hits += 1
                    logger.debug(f"Cache hit (disk): {canonical_hash[:8]}")
                    return cached
                else:
                    # Expired — clean up
                    cache_file.unlink(missing_ok=True)
            except (KeyError, TypeError):
                pass

        self._misses += 1
        return None

    def put(self, canonical_hash: str, response: Any) -> None:
        """
        Store response in cache.

        Uses atomic write to prevent corruption.

        Args:
            canonical_hash: SHA-256 hash of canonical prompt
            response: API response to cache
        """
        cached = CachedResponse(
            response=response,
            canonical_hash=canonical_hash,
            cached_at=time.time(),
            ttl_seconds=self.ttl_seconds,
        )

        # Memory cache
        self._memory_cache[canonical_hash] = cached

        # Filesystem cache (atomic write)
        cache_file = self.cache_dir / f"{canonical_hash}.json"
        try:
            atomic_write_json(cache_file, cached.to_dict())
        except Exception as e:
            logger.warning(f"Failed to persist cache entry: {e}")

        self._cleanup_if_needed()

    def invalidate(self, canonical_hash: str) -> bool:
        """Remove a cache entry."""
        removed = canonical_hash in self._memory_cache
        self._memory_cache.pop(canonical_hash, None)
        cache_file = self.cache_dir / f"{canonical_hash}.json"
        if cache_file.exists():
            cache_file.unlink()
            removed = True
        return removed

    def clear(self) -> int:
        """Clear all cache entries. Returns count removed."""
        count = len(self._memory_cache)
        self._memory_cache.clear()
        if self.cache_dir.exists():
            for f in self.cache_dir.glob("*.json"):
                f.unlink()
                count += 1
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "memory_entries": len(self._memory_cache),
            "ttl_seconds": self.ttl_seconds,
        }

    def _cleanup_if_needed(self) -> None:
        """Remove expired and excess entries."""
        # Remove expired from memory
        expired = [
            k for k, v in self._memory_cache.items() if v.is_expired
        ]
        for k in expired:
            del self._memory_cache[k]

        # Trim to max_entries (remove oldest)
        if len(self._memory_cache) > self.max_entries:
            sorted_entries = sorted(
                self._memory_cache.items(),
                key=lambda x: x[1].cached_at,
            )
            to_remove = len(self._memory_cache) - self.max_entries
            for k, _ in sorted_entries[:to_remove]:
                del self._memory_cache[k]


# =============================================================================
# Structured Output Enforcement
# =============================================================================

class StructuredOutputEnforcer:
    """
    Enforce structured output formats to constrain token space.

    He2025 analog: Constraining the output token space is like reducing
    the matmul output dimensions. Smaller space = batch variance less
    likely to flip the argmax.

    When the agent needs a routing decision, force JSON schema.
    When the agent needs code, use tool_use with file_path + content.
    Free-form text only when explicitly needed.
    """

    # Task types that benefit from structured output
    STRUCTURED_TASKS = {
        "routing": {
            "type": "json_schema",
            "description": "Expert routing decision",
            "schema": {
                "type": "object",
                "properties": {
                    "expert": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                },
                "required": ["expert", "confidence"],
            },
        },
        "classification": {
            "type": "json_schema",
            "description": "Signal classification",
            "schema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "signals": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": ["category", "confidence"],
            },
        },
        "decision": {
            "type": "json_schema",
            "description": "Binary or multi-choice decision",
            "schema": {
                "type": "object",
                "properties": {
                    "choice": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["choice"],
            },
        },
    }

    def enforce(self, task_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get API parameters to enforce structured output.

        Args:
            task_type: Type of task (routing, classification, decision, etc.)

        Returns:
            Dict of additional API parameters to include
        """
        if task_type and task_type in self.STRUCTURED_TASKS:
            task_config = self.STRUCTURED_TASKS[task_type]
            return {
                "response_format": {
                    "type": "json_object",
                    "schema": task_config["schema"],
                }
            }
        return {}

    def get_supported_types(self) -> List[str]:
        """Get list of supported structured task types."""
        return list(self.STRUCTURED_TASKS.keys())


# =============================================================================
# Unified Determinism Proxy
# =============================================================================

class DeterminismProxy:
    """
    L1 boundary: Canonicalize -> Cache check -> API call -> Cache store.

    Wraps any API call with He2025-aligned mitigations:
    1. Canonicalize prompt bytes (fix input tile boundaries)
    2. Check response cache (bypass nondeterministic layer)
    3. Enforce structured output (constrain output space)
    4. Store response in cache (deduplicate future calls)
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        enable_cache: bool = True,
        enable_structured_output: bool = True,
    ):
        self.canonicalizer = PromptCanonicalizer()
        self.cache = ResponseCache(
            cache_dir=cache_dir or DEFAULT_CACHE_DIR,
            ttl_seconds=ttl_seconds,
        ) if enable_cache else None
        self.enforcer = StructuredOutputEnforcer() if enable_structured_output else None

        # Stats
        self._calls = 0
        self._cache_bypasses = 0

    async def call(
        self,
        prompt: str,
        api_func=None,
        task_type: Optional[str] = None,
        bypass_cache: bool = False,
        **kwargs,
    ) -> Any:
        """
        Process prompt through determinism proxy (async).

        Args:
            prompt: Raw prompt string
            api_func: Async callable for API call (receives canonical prompt + kwargs)
            task_type: Task type for structured output enforcement
            bypass_cache: Skip cache lookup (still stores result)
            **kwargs: Additional parameters passed to api_func

        Returns:
            API response (cached or fresh)
        """
        self._calls += 1

        # Step 1: Canonicalize
        canonical = self.canonicalizer.canonicalize(prompt)
        cache_key = self.canonicalizer.canonical_hash(canonical)

        # Step 2: Cache check
        if self.cache and not bypass_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached.response

        self._cache_bypasses += 1

        # Step 3: Structured output enforcement
        output_params = {}
        if self.enforcer and task_type:
            output_params = self.enforcer.enforce(task_type)

        # Step 4: API call
        if api_func is None:
            raise ValueError("api_func is required for cache miss")

        merged_kwargs = {**output_params, **kwargs}
        response = await api_func(canonical, **merged_kwargs)

        # Step 5: Cache store
        if self.cache:
            self.cache.put(cache_key, response)

        return response

    def call_sync(
        self,
        prompt: str,
        api_func=None,
        task_type: Optional[str] = None,
        bypass_cache: bool = False,
        **kwargs,
    ) -> Any:
        """
        Process prompt through determinism proxy (sync).

        Same as call() but synchronous.
        """
        self._calls += 1

        # Step 1: Canonicalize
        canonical = self.canonicalizer.canonicalize(prompt)
        cache_key = self.canonicalizer.canonical_hash(canonical)

        # Step 2: Cache check
        if self.cache and not bypass_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached.response

        self._cache_bypasses += 1

        # Step 3: Structured output enforcement
        output_params = {}
        if self.enforcer and task_type:
            output_params = self.enforcer.enforce(task_type)

        # Step 4: API call
        if api_func is None:
            raise ValueError("api_func is required for cache miss")

        merged_kwargs = {**output_params, **kwargs}
        response = api_func(canonical, **merged_kwargs)

        # Step 5: Cache store
        if self.cache:
            self.cache.put(cache_key, response)

        return response

    def get_stats(self) -> Dict[str, Any]:
        """Get proxy statistics."""
        stats = {
            "total_calls": self._calls,
            "cache_bypasses": self._cache_bypasses,
        }
        if self.cache:
            stats["cache"] = self.cache.get_stats()
        return stats

    def invalidate_cache(self, prompt: str) -> bool:
        """Invalidate cached response for a prompt."""
        if not self.cache:
            return False
        cache_key = self.canonicalizer.canonical_hash(prompt)
        return self.cache.invalidate(cache_key)

    def clear_cache(self) -> int:
        """Clear all cached responses."""
        if not self.cache:
            return 0
        return self.cache.clear()


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "PromptCanonicalizer",
    "ResponseCache",
    "CachedResponse",
    "StructuredOutputEnforcer",
    "DeterminismProxy",
    "DEFAULT_CACHE_DIR",
    "DEFAULT_TTL_SECONDS",
]
