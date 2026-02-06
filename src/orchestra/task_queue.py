"""
Deterministic Task Queue (L2 Orchestration)
============================================

He2025-aligned task queue for multi-agent orchestration.

Core principle: Each agent's task selection is independent of how many
other agents are running. Pre-assigned partitions, not race conditions.

He2025 mapping:
- Fixed partition = Fixed reduction granule
- Agent independence = Element independence
- Priority-sorted = Deterministic ordering
- Filesystem rename = Stable arithmetic (atomic operations)

Usage:
    queue = DeterministicTaskQueue(task_dir=Path("/workspace/tasks"), num_agents=3)

    # Partition tasks
    partitions = queue.partition_tasks()

    # Claim next task for this agent
    task = queue.claim(agent_id="agent_0")

    # Complete task
    queue.complete(task.path)
"""

import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .file_ops import atomic_write_json, safe_read_json, ensure_directory
from .resilience import RetryConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

MAX_AGENTS = 3  # Constitutional limit from agent_coordinator.py


# =============================================================================
# Data Structures
# =============================================================================

class TaskStatus(Enum):
    """Task lifecycle states."""
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class TaskPriority(Enum):
    """Task priority levels."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class Task:
    """A task in the deterministic queue."""
    id: str
    description: str
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    claimed_by: Optional[str] = None
    claimed_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def deterministic_key(self) -> str:
        """Deterministic key for partitioning and sorting."""
        return hashlib.sha256(self.id.encode()).hexdigest()

    @property
    def partition_index(self) -> int:
        """Partition assignment based on deterministic hash."""
        return int(self.deterministic_key[:8], 16)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "created_at": self.created_at,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            id=data["id"],
            description=data["description"],
            priority=TaskPriority(data.get("priority", 2)),
            status=TaskStatus(data.get("status", "pending")),
            dependencies=data.get("dependencies", []),
            created_at=data.get("created_at", time.time()),
            claimed_by=data.get("claimed_by"),
            claimed_at=data.get("claimed_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_file(cls, path: Path) -> Optional["Task"]:
        """Load task from JSON file."""
        data = safe_read_json(path)
        if data is None:
            return None
        return cls.from_dict(data)


class TaskRetryPolicy:
    """Retry policy for task queue with exponential backoff.

    Wraps RetryConfig (resilience.py) with filesystem-level task semantics:
    dead letter queue, metadata timestamps, and deterministic jitter.

    He2025: Seeded RNG ensures same retry sequence across runs.
    """

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        max_task_retries: int = 3,
        dead_letter_after_exhaustion: bool = True,
    ):
        self.config = retry_config or RetryConfig()
        self.max_task_retries = max_task_retries
        self.dead_letter_after_exhaustion = dead_letter_after_exhaustion
        # He2025: seeded RNG for deterministic jitter
        self._rng = (
            random.Random(self.config.seed)
            if self.config.seed is not None
            else random.Random()
        )

    def compute_delay(self, attempt: int) -> float:
        """Compute backoff delay for a given attempt number.

        Same formula as resilience.with_retry() lines 378-388:
        base_calculated = min(base_delay * exponential_base^(attempt-1), max_delay)
        jitter_amount = base_calculated * jitter
        delay = base_calculated + uniform(-jitter_amount, jitter_amount)
        """
        cfg = self.config
        base_calculated = min(
            cfg.base_delay * (cfg.exponential_base ** (attempt - 1)),
            cfg.max_delay,
        )
        jitter_amount = base_calculated * cfg.jitter
        delay = base_calculated + self._rng.uniform(-jitter_amount, jitter_amount)
        return max(0.0, delay)

    def should_retry(self, task: "Task") -> bool:
        """Check if task has retries remaining."""
        return self.get_attempt_count(task) < self.max_task_retries

    def get_attempt_count(self, task: "Task") -> int:
        """Get current attempt count from task metadata."""
        return task.metadata.get("retry", {}).get("attempt_count", 0)


@dataclass
class QueueStatus:
    """Snapshot of queue state."""
    total_tasks: int = 0
    pending: int = 0
    claimed: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    dead_letter: int = 0
    partitions: Dict[str, int] = field(default_factory=dict)
    agents_active: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "pending": self.pending,
            "claimed": self.claimed,
            "running": self.running,
            "completed": self.completed,
            "failed": self.failed,
            "dead_letter": self.dead_letter,
            "partitions": self.partitions,
            "agents_active": self.agents_active,
        }


# =============================================================================
# Deterministic Task Queue
# =============================================================================

class DeterministicTaskQueue:
    """
    He2025-aligned task queue.

    Tasks are pre-sorted by priority and dependency graph.
    Each agent gets a fixed partition (not first-come-first-served).
    Agent X's available tasks never depend on Agent Y's state.

    Partition assignment: task_hash % num_agents == agent_index
    Same tasks + same agent count = same partition (always).
    """

    def __init__(
        self,
        task_dir: Path,
        num_agents: int = 1,
    ):
        """
        Initialize task queue.

        Args:
            task_dir: Directory containing task JSON files
            num_agents: Number of agents (max 3, constitutional limit)
        """
        if num_agents > MAX_AGENTS:
            raise ValueError(f"Max {MAX_AGENTS} agents allowed (constitutional limit)")
        if num_agents < 1:
            raise ValueError("At least 1 agent required")

        self.task_dir = Path(task_dir)
        self.num_agents = num_agents

        self.retry_policy: Optional[TaskRetryPolicy] = None

        # Ensure directories exist
        ensure_directory(self.task_dir)
        ensure_directory(self.task_dir / "claimed")
        ensure_directory(self.task_dir / "completed")
        ensure_directory(self.task_dir / "failed")
        ensure_directory(self.task_dir / "dead_letter")

    def _load_tasks(self, directory: Optional[Path] = None) -> List[Task]:
        """Load all tasks from a directory."""
        target = directory or self.task_dir
        tasks = []
        if not target.exists():
            return tasks
        for f in sorted(target.glob("*.json")):
            task = Task.from_file(f)
            if task:
                tasks.append(task)
        return tasks

    def _get_agent_index(self, agent_id: str) -> int:
        """
        Get agent index from ID.

        Supports both "agent_0" format and custom IDs.
        For custom IDs, uses deterministic hash.
        """
        # Try to extract numeric index
        if agent_id.startswith("agent_"):
            try:
                idx = int(agent_id.split("_")[1])
                if 0 <= idx < self.num_agents:
                    return idx
            except (ValueError, IndexError):
                pass

        # Fallback: hash-based assignment
        return int(hashlib.sha256(agent_id.encode()).hexdigest()[:8], 16) % self.num_agents

    def partition_tasks(self, tasks: Optional[List[Task]] = None) -> Dict[str, List[Task]]:
        """
        Assign tasks to agents via deterministic partitioning.

        Uses modular hashing: task_hash % num_agents == agent_index
        Same tasks + same agent count = same partition (always).

        Args:
            tasks: Tasks to partition (loads from disk if None)

        Returns:
            Dict mapping agent_id -> list of tasks
        """
        if tasks is None:
            tasks = self._load_tasks()

        # Sort by priority then deterministic key (FIXED order)
        sorted_tasks = sorted(
            tasks,
            key=lambda t: (t.priority.value, t.deterministic_key),
        )

        # Partition by modular hash
        partitions: Dict[str, List[Task]] = {
            f"agent_{i}": [] for i in range(self.num_agents)
        }

        for task in sorted_tasks:
            agent_index = task.partition_index % self.num_agents
            agent_id = f"agent_{agent_index}"
            partitions[agent_id].append(task)

        return partitions

    def claim(self, agent_id: str) -> Optional[Task]:
        """
        Claim next task from this agent's partition.

        Atomic via filesystem rename (not lock files).

        He2025: Agent's available tasks are independent of other agents.

        Args:
            agent_id: ID of the claiming agent

        Returns:
            Claimed Task, or None if no tasks available
        """
        agent_index = self._get_agent_index(agent_id)
        pending_tasks = self._load_tasks()

        # Filter to this agent's partition
        my_tasks = [
            t for t in pending_tasks
            if t.partition_index % self.num_agents == agent_index
            and t.status == TaskStatus.PENDING
        ]

        # Sort by priority then deterministic key
        my_tasks.sort(key=lambda t: (t.priority.value, t.deterministic_key))

        # Check dependencies
        completed_ids = {t.id for t in self._load_tasks(self.task_dir / "completed")}

        for task in my_tasks:
            # Skip if dependencies not met
            if task.dependencies and not all(
                dep in completed_ids for dep in task.dependencies
            ):
                continue

            # Skip if retry backoff not elapsed
            retry_meta = task.metadata.get("retry", {})
            next_retry_after = retry_meta.get("next_retry_after")
            if next_retry_after is not None and time.time() < next_retry_after:
                continue

            # Claim via atomic rename
            source = self.task_dir / f"{task.id}.json"
            if not source.exists():
                continue

            task.status = TaskStatus.CLAIMED
            task.claimed_by = agent_id
            task.claimed_at = time.time()

            dest = self.task_dir / "claimed" / f"{task.id}.json"
            try:
                atomic_write_json(dest, task.to_dict())
                source.unlink()
                logger.info(f"Task claimed: {task.id} by {agent_id}")
                return task
            except Exception as e:
                logger.warning(f"Failed to claim {task.id}: {e}")
                continue

        return None

    def complete(self, task_id: str, result: Optional[str] = None) -> bool:
        """
        Mark task as completed.

        Moves from claimed/ to completed/ via atomic rename.
        Idempotent — double completion is safe.

        Args:
            task_id: ID of the task to complete
            result: Optional result description

        Returns:
            True if task was completed
        """
        claimed_path = self.task_dir / "claimed" / f"{task_id}.json"
        if not claimed_path.exists():
            # Already completed or doesn't exist
            completed_path = self.task_dir / "completed" / f"{task_id}.json"
            if completed_path.exists():
                return True  # Idempotent
            return False

        data = safe_read_json(claimed_path)
        if data is None:
            return False

        task = Task.from_dict(data)
        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.result = result

        dest = self.task_dir / "completed" / f"{task_id}.json"
        try:
            atomic_write_json(dest, task.to_dict())
            claimed_path.unlink()
            logger.info(f"Task completed: {task_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to complete {task_id}: {e}")
            return False

    def fail(self, task_id: str, error: Optional[str] = None) -> bool:
        """Mark task as failed."""
        claimed_path = self.task_dir / "claimed" / f"{task_id}.json"
        if not claimed_path.exists():
            return False

        data = safe_read_json(claimed_path)
        if data is None:
            return False

        task = Task.from_dict(data)
        task.status = TaskStatus.FAILED
        task.completed_at = time.time()
        task.result = error

        dest = self.task_dir / "failed" / f"{task_id}.json"
        try:
            atomic_write_json(dest, task.to_dict())
            claimed_path.unlink()
            return True
        except Exception as e:
            logger.warning(f"Failed to mark {task_id} as failed: {e}")
            return False

    def retry(
        self,
        task_id: str,
        error: Optional[str] = None,
        policy: Optional["TaskRetryPolicy"] = None,
    ) -> bool:
        """
        Retry a failed/claimed task with exponential backoff.

        Increments retry metadata, computes next delay, and either:
        - Moves task back to pending (with next_retry_after set), or
        - Moves to dead_letter/ if retries exhausted

        Args:
            task_id: ID of the task to retry
            error: Error message from the failed attempt
            policy: Retry policy (uses self.retry_policy or default)

        Returns:
            True if task was requeued or dead-lettered
        """
        policy = policy or self.retry_policy or TaskRetryPolicy()

        # Load from claimed/
        claimed_path = self.task_dir / "claimed" / f"{task_id}.json"
        if not claimed_path.exists():
            logger.warning(f"Cannot retry {task_id}: not in claimed/")
            return False

        data = safe_read_json(claimed_path)
        if data is None:
            return False

        task = Task.from_dict(data)

        # Update retry metadata
        retry_meta = task.metadata.get("retry", {})
        attempt_count = retry_meta.get("attempt_count", 0) + 1
        errors = retry_meta.get("errors", [])
        if error:
            errors.append({"error": error, "timestamp": time.time()})

        # Check if retries exhausted
        if attempt_count >= policy.max_task_retries:
            if policy.dead_letter_after_exhaustion:
                # Move to dead_letter/
                task.status = TaskStatus.DEAD_LETTER
                task.metadata["retry"] = {
                    "attempt_count": attempt_count,
                    "errors": errors,
                    "exhausted_at": time.time(),
                }
                dest = self.task_dir / "dead_letter" / f"{task_id}.json"
                try:
                    atomic_write_json(dest, task.to_dict())
                    claimed_path.unlink()
                    logger.info(f"Task {task_id} moved to dead letter after {attempt_count} attempts")
                    return True
                except Exception as e:
                    logger.warning(f"Failed to dead-letter {task_id}: {e}")
                    return False
            else:
                # Fall back to regular fail
                return self.fail(task_id, error=error)

        # Compute backoff delay and requeue
        delay = policy.compute_delay(attempt_count)
        now = time.time()

        task.status = TaskStatus.PENDING
        task.claimed_by = None
        task.claimed_at = None
        task.metadata["retry"] = {
            "attempt_count": attempt_count,
            "errors": errors,
            "next_retry_after": now + delay,
            "last_delay": delay,
        }

        # Move back to pending (root task_dir)
        dest = self.task_dir / f"{task_id}.json"
        try:
            atomic_write_json(dest, task.to_dict())
            claimed_path.unlink()
            logger.info(f"Task {task_id} requeued (attempt {attempt_count}, delay {delay:.2f}s)")
            return True
        except Exception as e:
            logger.warning(f"Failed to requeue {task_id}: {e}")
            return False

    def get_retry_delay(self, task_id: str) -> Optional[float]:
        """
        Get remaining delay before a task can be reclaimed.

        Returns seconds remaining, 0.0 if ready, or None if task not found/not pending.
        """
        path = self.task_dir / f"{task_id}.json"
        if not path.exists():
            return None

        data = safe_read_json(path)
        if data is None:
            return None

        task = Task.from_dict(data)
        retry_meta = task.metadata.get("retry", {})
        next_retry_after = retry_meta.get("next_retry_after")
        if next_retry_after is None:
            return 0.0

        remaining = next_retry_after - time.time()
        return max(0.0, remaining)

    def is_dead_lettered(self, task_id: str) -> bool:
        """Check if a task is in the dead letter queue."""
        return (self.task_dir / "dead_letter" / f"{task_id}.json").exists()

    def add_task(self, task: Task) -> bool:
        """
        Add a task to the queue.

        Args:
            task: Task to add

        Returns:
            True if task was added
        """
        path = self.task_dir / f"{task.id}.json"
        try:
            atomic_write_json(path, task.to_dict())
            logger.info(f"Task added: {task.id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to add task {task.id}: {e}")
            return False

    def status(self) -> QueueStatus:
        """
        Get deterministic queue status.

        Sorted by priority, grouped by state.
        """
        qs = QueueStatus()

        pending = self._load_tasks()
        claimed = self._load_tasks(self.task_dir / "claimed")
        completed = self._load_tasks(self.task_dir / "completed")
        failed = self._load_tasks(self.task_dir / "failed")
        dead_letter = self._load_tasks(self.task_dir / "dead_letter")

        qs.pending = len(pending)
        qs.claimed = len(claimed)
        qs.completed = len(completed)
        qs.failed = len(failed)
        qs.dead_letter = len(dead_letter)
        qs.total_tasks = qs.pending + qs.claimed + qs.completed + qs.failed + qs.dead_letter

        # Partition sizes
        partitions = self.partition_tasks(pending)
        qs.partitions = {k: len(v) for k, v in partitions.items()}

        # Active agents
        qs.agents_active = list({t.claimed_by for t in claimed if t.claimed_by})

        return qs


# =============================================================================
# CLI Entry Point (for bash script integration)
# =============================================================================

def main():
    """CLI entry point for task queue operations."""
    import argparse

    parser = argparse.ArgumentParser(description="Deterministic Task Queue")
    subparsers = parser.add_subparsers(dest="command")

    # claim
    claim_parser = subparsers.add_parser("claim", help="Claim next task")
    claim_parser.add_argument("--agent-id", required=True)
    claim_parser.add_argument("--task-dir", required=True, type=Path)
    claim_parser.add_argument("--num-agents", type=int, default=3)

    # status
    status_parser = subparsers.add_parser("status", help="Queue status")
    status_parser.add_argument("--task-dir", required=True, type=Path)
    status_parser.add_argument("--num-agents", type=int, default=3)

    # complete
    complete_parser = subparsers.add_parser("complete", help="Complete task")
    complete_parser.add_argument("--task-id", required=True)
    complete_parser.add_argument("--task-dir", required=True, type=Path)

    # retry
    retry_parser = subparsers.add_parser("retry", help="Retry a claimed task with backoff")
    retry_parser.add_argument("--task-id", required=True)
    retry_parser.add_argument("--task-dir", required=True, type=Path)
    retry_parser.add_argument("--error", default=None, help="Error message from failed attempt")
    retry_parser.add_argument("--max-retries", type=int, default=3)
    retry_parser.add_argument("--seed", type=int, default=None, help="RNG seed for deterministic jitter")

    # dead-letter
    dl_parser = subparsers.add_parser("dead-letter", help="List dead-lettered tasks")
    dl_parser.add_argument("--task-dir", required=True, type=Path)

    # retry-delay
    rd_parser = subparsers.add_parser("retry-delay", help="Get remaining backoff delay for a task")
    rd_parser.add_argument("--task-id", required=True)
    rd_parser.add_argument("--task-dir", required=True, type=Path)

    args = parser.parse_args()

    if args.command == "claim":
        queue = DeterministicTaskQueue(args.task_dir, args.num_agents)
        task = queue.claim(args.agent_id)
        if task:
            print(json.dumps(task.to_dict()))
        else:
            print("")  # Empty = no tasks
    elif args.command == "status":
        queue = DeterministicTaskQueue(args.task_dir, args.num_agents)
        print(json.dumps(queue.status().to_dict(), indent=2))
    elif args.command == "complete":
        queue = DeterministicTaskQueue(args.task_dir, num_agents=1)
        queue.complete(args.task_id)
    elif args.command == "retry":
        queue = DeterministicTaskQueue(args.task_dir, num_agents=1)
        config = RetryConfig(seed=args.seed) if args.seed is not None else RetryConfig()
        policy = TaskRetryPolicy(
            retry_config=config,
            max_task_retries=args.max_retries,
        )
        result = queue.retry(args.task_id, error=args.error, policy=policy)
        if queue.is_dead_lettered(args.task_id):
            print("DEAD_LETTER")
        elif result:
            print("REQUEUED")
        else:
            print("FAILED")
    elif args.command == "dead-letter":
        queue = DeterministicTaskQueue(args.task_dir, num_agents=1)
        tasks = queue._load_tasks(queue.task_dir / "dead_letter")
        print(json.dumps([t.to_dict() for t in tasks], indent=2))
    elif args.command == "retry-delay":
        queue = DeterministicTaskQueue(args.task_dir, num_agents=1)
        delay = queue.get_retry_delay(args.task_id)
        if delay is not None:
            print(f"{delay:.2f}")
        else:
            print("0.00")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "Task",
    "TaskStatus",
    "TaskPriority",
    "TaskRetryPolicy",
    "QueueStatus",
    "DeterministicTaskQueue",
    "MAX_AGENTS",
]
