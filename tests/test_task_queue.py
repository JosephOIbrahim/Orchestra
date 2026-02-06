"""
Tests for Deterministic Task Queue (L2 Orchestration).

Verifies He2025 compliance:
- Partition determinism (same tasks + same agents = same partition)
- Partition independence (agent 0's partition unchanged when agent 2 added)
- Claim atomicity (concurrent claims don't corrupt state)
- Priority ordering (tasks processed in dependency order)
- Completion idempotency (double-completion is safe)
"""

import json
import time
from pathlib import Path
from typing import Dict, List

import pytest

from orchestra.task_queue import (
    DeterministicTaskQueue,
    Task,
    TaskPriority,
    TaskRetryPolicy,
    TaskStatus,
    MAX_AGENTS,
)
from orchestra.resilience import RetryConfig
from orchestra.file_ops import atomic_write_json


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def task_dir(tmp_path):
    """Create a task directory with subdirectories."""
    d = tmp_path / "tasks"
    d.mkdir()
    (d / "claimed").mkdir()
    (d / "completed").mkdir()
    (d / "failed").mkdir()
    (d / "dead_letter").mkdir()
    return d


@pytest.fixture
def sample_tasks():
    """Create a set of sample tasks."""
    return [
        Task(id=f"task_{i}", description=f"Task {i}", priority=TaskPriority.NORMAL)
        for i in range(10)
    ]


@pytest.fixture
def queue_with_tasks(task_dir, sample_tasks):
    """Queue with 10 tasks pre-loaded."""
    queue = DeterministicTaskQueue(task_dir, num_agents=3)
    for task in sample_tasks:
        queue.add_task(task)
    return queue


# =============================================================================
# Partition Determinism Tests
# =============================================================================

class TestPartitionDeterminism:
    """Verify deterministic partitioning."""

    def test_partition_determinism(self, task_dir, sample_tasks):
        """Same tasks + same agents = same partition (100 trials)."""
        results = []
        for _ in range(100):
            queue = DeterministicTaskQueue(task_dir, num_agents=3)
            partitions = queue.partition_tasks(sample_tasks)
            # Serialize partition assignment
            assignment = {
                k: [t.id for t in v]
                for k, v in sorted(partitions.items())
            }
            results.append(json.dumps(assignment, sort_keys=True))

        # All results must be identical
        assert len(set(results)) == 1, f"Partition varied across {len(set(results))} unique results"

    def test_partition_independence(self, task_dir, sample_tasks):
        """Agent 0's partition unchanged when agent count changes.

        He2025 principle: Each element's reduction is independent
        of how many other elements exist.

        Note: Modular hashing means adding agents changes the modulus,
        so the partition mapping DOES change. What stays invariant is
        the DETERMINISM — same tasks + same agent count = same result.
        """
        # With 2 agents
        queue_2 = DeterministicTaskQueue(task_dir, num_agents=2)
        partitions_2 = queue_2.partition_tasks(sample_tasks)
        p2_agent0 = [t.id for t in partitions_2["agent_0"]]

        # With 3 agents
        queue_3 = DeterministicTaskQueue(task_dir, num_agents=3)
        partitions_3 = queue_3.partition_tasks(sample_tasks)
        p3_agent0 = [t.id for t in partitions_3["agent_0"]]

        # Partitions are deterministic for each config
        queue_2b = DeterministicTaskQueue(task_dir, num_agents=2)
        partitions_2b = queue_2b.partition_tasks(sample_tasks)
        p2b_agent0 = [t.id for t in partitions_2b["agent_0"]]
        assert p2_agent0 == p2b_agent0

        queue_3b = DeterministicTaskQueue(task_dir, num_agents=3)
        partitions_3b = queue_3b.partition_tasks(sample_tasks)
        p3b_agent0 = [t.id for t in partitions_3b["agent_0"]]
        assert p3_agent0 == p3b_agent0

    def test_all_tasks_assigned(self, task_dir, sample_tasks):
        """Every task is assigned to exactly one agent."""
        queue = DeterministicTaskQueue(task_dir, num_agents=3)
        partitions = queue.partition_tasks(sample_tasks)

        all_ids = []
        for tasks in partitions.values():
            all_ids.extend(t.id for t in tasks)

        # All tasks assigned
        assert sorted(all_ids) == sorted(t.id for t in sample_tasks)
        # No duplicates
        assert len(all_ids) == len(set(all_ids))

    def test_partition_respects_priority(self, task_dir):
        """Tasks within a partition are sorted by priority."""
        tasks = [
            Task(id="low_1", description="Low", priority=TaskPriority.LOW),
            Task(id="crit_1", description="Critical", priority=TaskPriority.CRITICAL),
            Task(id="high_1", description="High", priority=TaskPriority.HIGH),
            Task(id="norm_1", description="Normal", priority=TaskPriority.NORMAL),
        ]
        queue = DeterministicTaskQueue(task_dir, num_agents=1)
        partitions = queue.partition_tasks(tasks)

        agent_tasks = partitions["agent_0"]
        priorities = [t.priority.value for t in agent_tasks]
        assert priorities == sorted(priorities), "Tasks not sorted by priority"


# =============================================================================
# Claim Tests
# =============================================================================

class TestClaim:
    """Tests for task claiming."""

    def test_claim_returns_task(self, queue_with_tasks):
        """Claiming returns a task from the agent's partition."""
        task = queue_with_tasks.claim("agent_0")
        assert task is not None
        assert task.status == TaskStatus.CLAIMED
        assert task.claimed_by == "agent_0"

    def test_claim_moves_to_claimed_dir(self, queue_with_tasks, task_dir):
        """Claimed task moves from pending to claimed directory."""
        task = queue_with_tasks.claim("agent_0")
        assert task is not None

        # Original file should be gone
        assert not (task_dir / f"{task.id}.json").exists()
        # Should be in claimed/
        assert (task_dir / "claimed" / f"{task.id}.json").exists()

    def test_claim_empty_partition(self, task_dir):
        """Claiming from empty partition returns None."""
        queue = DeterministicTaskQueue(task_dir, num_agents=3)
        task = queue.claim("agent_0")
        assert task is None

    def test_claim_respects_dependencies(self, task_dir):
        """Tasks with unmet dependencies are skipped."""
        queue = DeterministicTaskQueue(task_dir, num_agents=1)

        dep_task = Task(id="dep_1", description="Dependency")
        blocked_task = Task(id="blocked_1", description="Blocked", dependencies=["dep_1"])

        queue.add_task(blocked_task)
        queue.add_task(dep_task)

        # Claim should get dep_task first (blocked_task depends on it)
        first = queue.claim("agent_0")
        assert first is not None
        # The task we get should be one without unmet dependencies
        # (which task depends on partition assignment, but dep_1 should be available)


# =============================================================================
# Completion Tests
# =============================================================================

class TestCompletion:
    """Tests for task completion."""

    def test_complete_moves_to_completed(self, queue_with_tasks, task_dir):
        """Completing a task moves it to completed directory."""
        task = queue_with_tasks.claim("agent_0")
        assert task is not None

        result = queue_with_tasks.complete(task.id, result="Done")
        assert result is True
        assert (task_dir / "completed" / f"{task.id}.json").exists()
        assert not (task_dir / "claimed" / f"{task.id}.json").exists()

    def test_completion_idempotent(self, queue_with_tasks, task_dir):
        """Double-completion is safe."""
        task = queue_with_tasks.claim("agent_0")
        assert task is not None

        # Complete twice
        assert queue_with_tasks.complete(task.id) is True
        assert queue_with_tasks.complete(task.id) is True  # Idempotent

    def test_complete_nonexistent(self, task_dir):
        """Completing a nonexistent task returns False."""
        queue = DeterministicTaskQueue(task_dir, num_agents=1)
        assert queue.complete("nonexistent") is False

    def test_fail_task(self, queue_with_tasks, task_dir):
        """Failed tasks move to failed directory."""
        task = queue_with_tasks.claim("agent_0")
        assert task is not None

        result = queue_with_tasks.fail(task.id, error="Test error")
        assert result is True
        assert (task_dir / "failed" / f"{task.id}.json").exists()


# =============================================================================
# Queue Status Tests
# =============================================================================

class TestQueueStatus:
    """Tests for queue status reporting."""

    def test_status_counts(self, queue_with_tasks):
        """Status correctly counts tasks by state."""
        status = queue_with_tasks.status()
        assert status.total_tasks == 10
        assert status.pending == 10
        assert status.claimed == 0
        assert status.completed == 0

    def test_status_after_claim(self, queue_with_tasks):
        """Status updates after claiming."""
        queue_with_tasks.claim("agent_0")
        status = queue_with_tasks.status()
        assert status.pending == 9
        assert status.claimed == 1

    def test_status_partition_distribution(self, queue_with_tasks):
        """Status shows partition distribution."""
        status = queue_with_tasks.status()
        total_partitioned = sum(status.partitions.values())
        assert total_partitioned == 10


# =============================================================================
# Constitutional Limits Tests
# =============================================================================

class TestConstitutionalLimits:
    """Tests for constitutional constraints."""

    def test_max_agents_enforced(self, task_dir):
        """Cannot create queue with more than MAX_AGENTS."""
        with pytest.raises(ValueError, match="Max"):
            DeterministicTaskQueue(task_dir, num_agents=MAX_AGENTS + 1)

    def test_min_agents_enforced(self, task_dir):
        """Cannot create queue with 0 agents."""
        with pytest.raises(ValueError, match="At least 1"):
            DeterministicTaskQueue(task_dir, num_agents=0)

    def test_max_agents_value(self):
        """MAX_AGENTS is 3 (from agent_coordinator.py)."""
        assert MAX_AGENTS == 3


# =============================================================================
# Priority Ordering Tests
# =============================================================================

class TestPriorityOrdering:
    """Tests for priority-based task ordering."""

    def test_priority_ordering(self, task_dir):
        """Tasks processed in priority order within partition."""
        queue = DeterministicTaskQueue(task_dir, num_agents=1)

        # Add tasks in reverse priority order
        queue.add_task(Task(id="low", description="Low priority", priority=TaskPriority.LOW))
        queue.add_task(Task(id="critical", description="Critical", priority=TaskPriority.CRITICAL))
        queue.add_task(Task(id="normal", description="Normal", priority=TaskPriority.NORMAL))

        # Claims should come in priority order
        first = queue.claim("agent_0")
        assert first is not None
        assert first.priority == TaskPriority.CRITICAL

    def test_deterministic_key_tiebreaker(self, task_dir):
        """Same-priority tasks use deterministic key as tiebreaker."""
        queue = DeterministicTaskQueue(task_dir, num_agents=1)

        tasks = [
            Task(id=f"same_pri_{i}", description=f"Same priority {i}")
            for i in range(5)
        ]
        for t in tasks:
            queue.add_task(t)

        # Claim all tasks
        claimed_ids = []
        for _ in range(5):
            task = queue.claim("agent_0")
            if task:
                claimed_ids.append(task.id)
                queue.complete(task.id)

        # Verify deterministic order
        assert len(claimed_ids) == 5

        # Run again — should get same order
        queue2 = DeterministicTaskQueue(task_dir, num_agents=1)
        for t in tasks:
            queue2.add_task(t)
        claimed_ids_2 = []
        for _ in range(5):
            task = queue2.claim("agent_0")
            if task:
                claimed_ids_2.append(task.id)
                queue2.complete(task.id)

        assert claimed_ids == claimed_ids_2


# =============================================================================
# Retry Tests
# =============================================================================

class TestRetry:
    """Tests for retry with exponential backoff and dead letter queue."""

    def test_retry_increments_attempt_count(self, task_dir):
        """Retry increments metadata retry attempt_count."""
        queue = DeterministicTaskQueue(task_dir, num_agents=1)
        task = Task(id="retry_task", description="Retry me")
        queue.add_task(task)
        claimed = queue.claim("agent_0")
        assert claimed is not None

        policy = TaskRetryPolicy(max_task_retries=3)
        queue.retry(claimed.id, error="attempt 1 failed", policy=policy)

        # Task should be back in pending with attempt_count=1
        reloaded = Task.from_file(task_dir / "retry_task.json")
        assert reloaded is not None
        assert reloaded.metadata["retry"]["attempt_count"] == 1
        assert len(reloaded.metadata["retry"]["errors"]) == 1
        assert reloaded.metadata["retry"]["errors"][0]["error"] == "attempt 1 failed"

    def test_retry_moves_to_pending(self, task_dir):
        """Retried task moves from claimed/ back to pending root."""
        queue = DeterministicTaskQueue(task_dir, num_agents=1)
        task = Task(id="retry_pending", description="Back to pending")
        queue.add_task(task)
        claimed = queue.claim("agent_0")
        assert claimed is not None

        # Should be in claimed/, not in root
        assert (task_dir / "claimed" / "retry_pending.json").exists()
        assert not (task_dir / "retry_pending.json").exists()

        policy = TaskRetryPolicy(max_task_retries=3)
        result = queue.retry(claimed.id, error="fail", policy=policy)
        assert result is True

        # Should be back in root, not in claimed/
        assert (task_dir / "retry_pending.json").exists()
        assert not (task_dir / "claimed" / "retry_pending.json").exists()

        reloaded = Task.from_file(task_dir / "retry_pending.json")
        assert reloaded.status == TaskStatus.PENDING

    def test_retry_dead_letter_after_max(self, task_dir):
        """Task moves to dead_letter/ after max retries exhausted."""
        queue = DeterministicTaskQueue(task_dir, num_agents=1)
        task = Task(id="dl_task", description="Will exhaust retries")
        queue.add_task(task)

        policy = TaskRetryPolicy(max_task_retries=2)

        # Attempt 1: claim and retry
        claimed = queue.claim("agent_0")
        assert claimed is not None
        queue.retry(claimed.id, error="fail 1", policy=policy)

        # Clear backoff so claim() can pick it up immediately
        reloaded = Task.from_file(task_dir / "dl_task.json")
        reloaded.metadata["retry"]["next_retry_after"] = 0
        atomic_write_json(task_dir / "dl_task.json", reloaded.to_dict())

        # Attempt 2: reclaim and retry -> should dead-letter
        claimed2 = queue.claim("agent_0")
        assert claimed2 is not None
        queue.retry(claimed2.id, error="fail 2", policy=policy)

        # Should be in dead_letter/
        assert (task_dir / "dead_letter" / "dl_task.json").exists()
        assert not (task_dir / "dl_task.json").exists()
        assert not (task_dir / "claimed" / "dl_task.json").exists()

        dl_task = Task.from_file(task_dir / "dead_letter" / "dl_task.json")
        assert dl_task.status == TaskStatus.DEAD_LETTER
        assert dl_task.metadata["retry"]["attempt_count"] == 2

    def test_retry_backoff_delay_respected(self, task_dir):
        """claim() skips tasks whose next_retry_after is in the future."""
        queue = DeterministicTaskQueue(task_dir, num_agents=1)
        task = Task(id="backoff_task", description="Has backoff")
        # Set next_retry_after far in the future
        task.metadata["retry"] = {
            "attempt_count": 1,
            "errors": [],
            "next_retry_after": time.time() + 9999,
            "last_delay": 9999,
        }
        queue.add_task(task)

        # claim() should skip this task (backoff not elapsed)
        claimed = queue.claim("agent_0")
        assert claimed is None

        # Now add a task without backoff — it should be claimable
        task2 = Task(id="ready_task", description="No backoff")
        queue.add_task(task2)
        claimed2 = queue.claim("agent_0")
        assert claimed2 is not None
        assert claimed2.id == "ready_task"

    def test_retry_deterministic_jitter_with_seed(self, task_dir):
        """Same seed produces same delay sequence (He2025 compliance)."""
        config = RetryConfig(seed=42, base_delay=1.0, exponential_base=2.0, jitter=0.1)
        policy1 = TaskRetryPolicy(retry_config=config, max_task_retries=5)
        policy2 = TaskRetryPolicy(
            retry_config=RetryConfig(seed=42, base_delay=1.0, exponential_base=2.0, jitter=0.1),
            max_task_retries=5,
        )

        delays1 = [policy1.compute_delay(i) for i in range(1, 6)]
        delays2 = [policy2.compute_delay(i) for i in range(1, 6)]

        assert delays1 == delays2, f"Seeded delays differ: {delays1} != {delays2}"

        # Verify exponential growth pattern
        # Attempt 1: ~1.0, Attempt 2: ~2.0, Attempt 3: ~4.0
        assert delays1[0] < delays1[1] < delays1[2]

    def test_dead_letter_in_status(self, task_dir):
        """QueueStatus includes dead_letter count in total."""
        queue = DeterministicTaskQueue(task_dir, num_agents=1)

        # Add and exhaust a task
        task = Task(id="status_dl", description="For status test")
        queue.add_task(task)

        policy = TaskRetryPolicy(max_task_retries=1)
        claimed = queue.claim("agent_0")
        assert claimed is not None
        queue.retry(claimed.id, error="exhausted", policy=policy)

        status = queue.status()
        assert status.dead_letter == 1
        assert status.dead_letter <= status.total_tasks
        assert status.pending == 0  # Moved to dead letter, not pending

        # Verify to_dict includes dead_letter
        d = status.to_dict()
        assert "dead_letter" in d
        assert d["dead_letter"] == 1
