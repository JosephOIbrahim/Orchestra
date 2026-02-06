"""
Three-Layer Deterministic Integration Tests
=============================================

Verifies all three layers work in harmony:
- L1 (Determinism Proxy): Canonicalization + Cache + Structured Output
- L2 (Orchestration Shell): Deterministic task queue partitioning
- L3 (Substrate Foundation): Batch-invariant aggregation

He2025 compliance:
- Same canonical input → same cached output → same routing → same behavior
- Adding/removing agents doesn't change existing partitions (for same agent count)
- Cache miss → fresh call → substrate routing still deterministic
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestra.determinism_proxy import (
    DeterminismProxy,
    PromptCanonicalizer,
    ResponseCache,
)
from orchestra.task_queue import (
    DeterministicTaskQueue,
    Task,
    TaskPriority,
)
from orchestra.batch_invariance import (
    COGNITIVE_TILE_SIZE,
    AggregationStrategy,
    BatchInvariantAggregator,
    Instance,
    kahan_sum,
    verify_determinism,
)


# =============================================================================
# L1 ↔ L3: Canonicalization → Routing Determinism
# =============================================================================

class TestL1L3CanonicalRouting:
    """Verify canonical prompt form leads to deterministic routing."""

    def test_canonical_routing_whitespace(self, tmp_path):
        """Same prompt, different whitespace → same expert selection."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")
        canon = PromptCanonicalizer()

        # Three whitespace variants of same prompt
        prompts = [
            "I'm frustrated   with  this  code",
            "I'm frustrated with this code",
            "I'm  frustrated  with  this  code",
        ]

        hashes = [canon.canonical_hash(p) for p in prompts]
        # All should produce same canonical hash
        assert len(set(hashes)) == 1, f"Different hashes: {hashes}"

    def test_canonical_routing_newlines(self, tmp_path):
        """Same prompt, different newlines → same hash."""
        canon = PromptCanonicalizer()

        prompt1 = "Line 1\n\n\nLine 2"
        prompt2 = "Line 1\n\nLine 2"

        assert canon.canonical_hash(prompt1) == canon.canonical_hash(prompt2)

    def test_cache_hit_bypasses_pipeline(self, tmp_path):
        """Cache hit skips the entire nondeterministic layer."""
        proxy = DeterminismProxy(cache_dir=tmp_path / "cache")
        api_calls = []

        def mock_api(prompt, **kwargs):
            api_calls.append(prompt)
            return {"expert": "direct", "confidence": 0.9}

        # First call — cache miss, calls API
        result1 = proxy.call_sync("test routing", api_func=mock_api, task_type="routing")
        assert len(api_calls) == 1

        # Second call — cache hit, skips API entirely
        result2 = proxy.call_sync("test routing", api_func=mock_api, task_type="routing")
        assert len(api_calls) == 1  # Still 1 — API not called

        # Same result
        assert result1 == result2


# =============================================================================
# L2: Partition Independence
# =============================================================================

class TestL2PartitionIndependence:
    """Verify task partition determinism."""

    def test_partition_determinism_100_trials(self, tmp_path):
        """Same tasks + same agents = same partition across 100 trials."""
        tasks = [
            Task(id=f"task_{i}", description=f"Task {i}")
            for i in range(20)
        ]

        results = []
        for _ in range(100):
            queue = DeterministicTaskQueue(tmp_path / "tasks", num_agents=3)
            partitions = queue.partition_tasks(tasks)
            assignment = json.dumps(
                {k: sorted(t.id for t in v) for k, v in sorted(partitions.items())},
                sort_keys=True,
            )
            results.append(assignment)

        assert len(set(results)) == 1

    def test_partition_stable_per_agent_count(self, tmp_path):
        """Partitions are deterministic for a given agent count."""
        tasks = [Task(id=f"t_{i}", description=f"T{i}") for i in range(15)]

        # 2-agent config: run twice, same result
        q2a = DeterministicTaskQueue(tmp_path / "t1", num_agents=2)
        q2b = DeterministicTaskQueue(tmp_path / "t2", num_agents=2)
        p2a = {k: sorted(t.id for t in v) for k, v in q2a.partition_tasks(tasks).items()}
        p2b = {k: sorted(t.id for t in v) for k, v in q2b.partition_tasks(tasks).items()}
        assert p2a == p2b

        # 3-agent config: run twice, same result
        q3a = DeterministicTaskQueue(tmp_path / "t3", num_agents=3)
        q3b = DeterministicTaskQueue(tmp_path / "t4", num_agents=3)
        p3a = {k: sorted(t.id for t in v) for k, v in q3a.partition_tasks(tasks).items()}
        p3b = {k: sorted(t.id for t in v) for k, v in q3b.partition_tasks(tasks).items()}
        assert p3a == p3b


# =============================================================================
# L3: Batch Invariance Verification
# =============================================================================

class TestL3BatchInvariance:
    """Verify batch-invariant aggregation."""

    def test_kahan_sum_determinism(self):
        """Kahan summation is deterministic over 100 trials."""
        values = [0.1] * 100 + [0.3] * 50 + [0.7] * 30
        results = set()
        for _ in range(100):
            results.add(kahan_sum(values))
        assert len(results) == 1

    def test_tile_size_constant(self):
        """COGNITIVE_TILE_SIZE is always 32."""
        assert COGNITIVE_TILE_SIZE == 32

    def test_aggregator_determinism(self):
        """BatchInvariantAggregator produces identical results."""
        instances = [
            Instance(id=f"inst_{i}", confidence=i * 0.1, timestamp=float(i))
            for i in range(50)
        ]
        aggregator = BatchInvariantAggregator(strategy=AggregationStrategy.MEAN)
        assert verify_determinism(instances, aggregator, n_trials=100)


# =============================================================================
# Full Stack: L1 + L2 + L3
# =============================================================================

class TestFullStackDeterminism:
    """End-to-end determinism across all three layers."""

    def test_full_stack_determinism(self, tmp_path):
        """
        Mock API, verify:
        same canonical input → same cached output → same routing → same behavior
        """
        cache_dir = tmp_path / "cache"
        proxy = DeterminismProxy(cache_dir=cache_dir)

        # Mock API that returns structured routing decision
        def mock_api(prompt, **kwargs):
            # Simulate routing based on prompt content
            if "frustrated" in prompt.lower():
                return {"expert": "validator", "confidence": 1.0}
            return {"expert": "direct", "confidence": 0.5}

        results = []
        for _ in range(50):
            result = proxy.call_sync(
                "I'm  frustrated   with   this",  # Varied whitespace
                api_func=mock_api,
                task_type="routing",
            )
            results.append(json.dumps(result, sort_keys=True))

        # All 50 results must be identical
        assert len(set(results)) == 1
        # API should have been called exactly once (49 cache hits)
        stats = proxy.get_stats()
        assert stats["cache_bypasses"] == 1

    def test_cache_bypass_still_deterministic(self, tmp_path):
        """Cache miss → fresh API call → routing still deterministic."""
        proxy = DeterminismProxy(
            cache_dir=tmp_path / "cache",
            enable_cache=False,  # Force all calls through API
        )

        api_calls = []

        def deterministic_api(prompt, **kwargs):
            api_calls.append(prompt)
            # Deterministic response based on canonical prompt
            return {"expert": "direct", "confidence": 0.8}

        results = []
        for _ in range(10):
            result = proxy.call_sync(
                "test deterministic routing",
                api_func=deterministic_api,
            )
            results.append(json.dumps(result, sort_keys=True))

        # All results identical (API is deterministic)
        assert len(set(results)) == 1
        # All 10 calls went to API (no cache)
        assert len(api_calls) == 10

    def test_l1_l2_l3_pipeline(self, tmp_path):
        """
        Full pipeline:
        1. L1: Canonicalize prompt → cache check
        2. L2: Partition task to agent
        3. L3: Aggregate confidence with Kahan
        """
        # L1: Canonicalize
        canon = PromptCanonicalizer()
        prompt = "  implement   the   feature  "
        canonical_hash = canon.canonical_hash(prompt)
        assert len(canonical_hash) == 32

        # L2: Create task and partition
        task = Task(
            id=f"task_{canonical_hash[:8]}",
            description=prompt.strip(),
            priority=TaskPriority.NORMAL,
        )
        queue = DeterministicTaskQueue(tmp_path / "tasks", num_agents=3)
        queue.add_task(task)
        partitions = queue.partition_tasks()

        # Task is assigned to exactly one agent
        assigned_agents = [
            agent for agent, tasks in partitions.items()
            if any(t.id == task.id for t in tasks)
        ]
        assert len(assigned_agents) == 1

        # L3: Aggregate confidence scores
        scores = [0.7, 0.8, 0.9, 0.6, 0.85]
        aggregator = BatchInvariantAggregator(strategy=AggregationStrategy.MEAN)
        instances = [Instance(id=str(i), confidence=s) for i, s in enumerate(scores)]
        confidence = aggregator.aggregate(instances)

        # Verify determinism
        assert verify_determinism(instances, aggregator, n_trials=100)
        assert 0.0 <= confidence <= 1.0

    def test_agent_mode_hook_integration(self):
        """Verify agent mode detection flag exists."""
        from orchestra.hooks.cognitive_hook import AGENT_MODE
        # In test environment, should be False (no env var set)
        assert isinstance(AGENT_MODE, bool)

    def test_orchestrator_has_proxy_support(self):
        """Verify CognitiveOrchestrator accepts determinism_proxy parameter."""
        from orchestra.cognitive_orchestrator import CognitiveOrchestrator
        import inspect
        sig = inspect.signature(CognitiveOrchestrator.__init__)
        assert "determinism_proxy" in sig.parameters
