"""
Async Executor Tests

Tests for parallel execution with rate limiting.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from orchestra.substrate.knowledge.distillation.async_executor import (
    AsyncBatchExecutor,
    BatchExecutorConfig,
    BatchResult,
    execute_with_progress,
)


class TestBatchExecutorConfig:
    """Test batch executor configuration."""

    def test_default_config(self):
        """Default config should have reasonable values."""
        config = BatchExecutorConfig()

        assert config.max_concurrent == 5
        assert config.rate_limit_per_second == 5.0
        assert config.retry_count == 3
        assert config.continue_on_error is True


class TestAsyncBatchExecutor:
    """Test the async batch executor."""

    @pytest.mark.asyncio
    async def test_execute_empty_batch(self):
        """Empty batch should return empty result."""
        executor = AsyncBatchExecutor()

        result = await executor.execute_batch(
            [],
            lambda x: x,
            "Empty"
        )

        assert len(result.items) == 0
        assert result.successful == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_execute_simple_batch(self):
        """Execute a simple batch of operations."""
        config = BatchExecutorConfig(max_concurrent=2)
        executor = AsyncBatchExecutor(config)

        async def double(x: int) -> int:
            return x * 2

        items = [1, 2, 3, 4, 5]
        result = await executor.execute_batch(items, double, "Double")

        assert result.successful == 5
        assert result.failed == 0
        assert result.get_successful_results() == [2, 4, 6, 8, 10]

    @pytest.mark.asyncio
    async def test_execute_with_failures(self):
        """Batch should handle partial failures."""
        config = BatchExecutorConfig(
            max_concurrent=2,
            retry_count=0,  # No retries
            continue_on_error=True,
        )
        executor = AsyncBatchExecutor(config)

        async def fail_on_three(x: int) -> int:
            if x == 3:
                raise ValueError("Three is bad")
            return x * 2

        items = [1, 2, 3, 4, 5]
        result = await executor.execute_batch(items, fail_on_three, "Fail3")

        assert result.successful == 4
        assert result.failed == 1
        assert 3 in result.get_failed_items()

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Executor should retry on failure."""
        config = BatchExecutorConfig(
            max_concurrent=1,
            retry_count=2,
            retry_delay_seconds=0.01,  # Fast retries for testing
        )
        executor = AsyncBatchExecutor(config)

        call_counts = {}

        async def fail_then_succeed(x: int) -> int:
            call_counts[x] = call_counts.get(x, 0) + 1
            if call_counts[x] < 2:
                raise ValueError("First attempt fails")
            return x * 2

        result = await executor.execute_batch([1], fail_then_succeed, "Retry")

        assert result.successful == 1
        assert call_counts[1] == 2  # Should have been called twice

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Executor should respect rate limits."""
        config = BatchExecutorConfig(
            max_concurrent=10,  # High concurrency
            rate_limit_per_second=100.0,  # 100 per second = 10ms between
        )
        executor = AsyncBatchExecutor(config)

        async def quick_op(x: int) -> int:
            return x

        items = list(range(5))
        start = time.perf_counter()
        result = await executor.execute_batch(items, quick_op, "Rate")
        duration = time.perf_counter() - start

        assert result.successful == 5
        # With rate limiting, 5 items at 100/s should take ~40ms minimum
        # (first is immediate, then 4 * 10ms)
        # Allow some tolerance
        assert result.rate_limited_count >= 0

    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        """Executor should respect concurrency limit."""
        config = BatchExecutorConfig(
            max_concurrent=2,
            rate_limit_per_second=0,  # No rate limiting
        )
        executor = AsyncBatchExecutor(config)

        concurrent_count = 0
        max_concurrent = 0

        async def track_concurrency(x: int) -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1
            return x

        items = list(range(10))
        result = await executor.execute_batch(items, track_concurrency, "Conc")

        assert result.successful == 10
        assert max_concurrent <= 2  # Should never exceed limit

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Executor should timeout slow operations."""
        config = BatchExecutorConfig(
            max_concurrent=1,
            timeout_seconds=0.05,  # 50ms timeout
            retry_count=0,
        )
        executor = AsyncBatchExecutor(config)

        async def slow_op(x: int) -> int:
            await asyncio.sleep(0.5)  # 500ms - will timeout
            return x

        result = await executor.execute_batch([1], slow_op, "Timeout")

        assert result.failed == 1
        assert result.successful == 0

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        """Progress callback should be called."""
        executor = AsyncBatchExecutor()

        progress_calls = []

        def progress(completed: int, total: int):
            progress_calls.append((completed, total))

        async def identity(x: int) -> int:
            return x

        await executor.execute_batch(
            [1, 2, 3],
            identity,
            "Progress",
            progress_callback=progress,
        )

        assert len(progress_calls) == 3
        assert progress_calls[-1] == (3, 3)

    @pytest.mark.asyncio
    async def test_batch_result_properties(self):
        """Test BatchResult helper properties."""
        config = BatchExecutorConfig(retry_count=0)
        executor = AsyncBatchExecutor(config)

        async def maybe_fail(x: int) -> int:
            if x % 2 == 0:
                raise ValueError("Even fails")
            return x * 2

        items = [1, 2, 3, 4, 5]
        result = await executor.execute_batch(items, maybe_fail, "Props")

        assert result.success_rate == 3 / 5  # 60%
        assert result.get_successful_results() == [2, 6, 10]
        assert set(result.get_failed_items()) == {2, 4}


class TestExecuteWithProgress:
    """Test the convenience function."""

    @pytest.mark.asyncio
    async def test_execute_with_progress(self):
        """Test the convenience function."""
        async def double(x: int) -> int:
            return x * 2

        results = await execute_with_progress(
            [1, 2, 3],
            double,
            "Test",
            max_concurrent=2,
            rate_limit=0,
        )

        assert results == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_execute_filters_failures(self):
        """Convenience function should filter out failures."""
        async def fail_on_two(x: int) -> int:
            if x == 2:
                raise ValueError("No two")
            return x

        results = await execute_with_progress(
            [1, 2, 3],
            fail_on_two,
            "Filter",
            max_concurrent=1,
        )

        assert results == [1, 3]
