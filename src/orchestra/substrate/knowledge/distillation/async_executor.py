"""
Async Batch Executor

Parallel execution with rate limiting and progress tracking.
Enables concurrent LLM calls while respecting API limits.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
ThinkingMachines [He2025] Production Hardening.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Generic, TypeVar

from .errors import DistillationError, ErrorContext, ErrorSeverity

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Input type
R = TypeVar("R")  # Result type


@dataclass
class BatchExecutorConfig:
    """Configuration for async batch execution.

    Attributes:
        max_concurrent: Maximum concurrent operations
        rate_limit_per_second: Max operations per second (0 = unlimited)
        retry_count: Number of retries on failure
        retry_delay_seconds: Base delay between retries
        timeout_seconds: Timeout per operation (0 = no timeout)
        continue_on_error: Continue processing if some items fail
    """

    max_concurrent: int = 5
    rate_limit_per_second: float = 5.0
    retry_count: int = 3
    retry_delay_seconds: float = 1.0
    timeout_seconds: float = 60.0
    continue_on_error: bool = True


@dataclass
class BatchItemResult(Generic[T, R]):
    """Result for a single batch item.

    Attributes:
        item: Original input item
        result: Successful result (if success)
        error: Error (if failed)
        success: Whether the operation succeeded
        retries: Number of retries before success/failure
        duration_ms: Time taken in milliseconds
    """

    item: T
    result: R | None = None
    error: Exception | None = None
    success: bool = False
    retries: int = 0
    duration_ms: float = 0.0


@dataclass
class BatchResult(Generic[T, R]):
    """Result of batch execution.

    Attributes:
        items: List of item results
        successful: Count of successful items
        failed: Count of failed items
        total_duration_ms: Total execution time
        rate_limited_count: Number of times rate limiting was applied
    """

    items: list[BatchItemResult[T, R]] = field(default_factory=list)
    successful: int = 0
    failed: int = 0
    total_duration_ms: float = 0.0
    rate_limited_count: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.successful + self.failed
        return self.successful / total if total > 0 else 0.0

    def get_successful_results(self) -> list[R]:
        """Get list of successful results."""
        return [item.result for item in self.items if item.success and item.result is not None]

    def get_failed_items(self) -> list[T]:
        """Get list of failed items."""
        return [item.item for item in self.items if not item.success]


class AsyncBatchExecutor(Generic[T, R]):
    """Executes async operations in parallel with rate limiting.

    Provides controlled concurrency, rate limiting, retries, and
    progress tracking for batch LLM operations.

    Attributes:
        config: Executor configuration
    """

    def __init__(self, config: BatchExecutorConfig | None = None) -> None:
        self.config = config or BatchExecutorConfig()
        self._semaphore: asyncio.Semaphore | None = None
        self._last_request_time: float = 0.0
        self._rate_limit_lock = asyncio.Lock()
        self._rate_limited_count = 0

    async def execute_batch(
        self,
        items: list[T],
        func: Callable[[T], Coroutine[Any, Any, R]],
        desc: str = "Processing",
        *,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> BatchResult[T, R]:
        """Execute async function on all items in parallel.

        Args:
            items: List of input items
            func: Async function to apply to each item
            desc: Description for logging
            progress_callback: Optional callback(completed, total) for progress

        Returns:
            BatchResult with all item results
        """
        if not items:
            return BatchResult()

        start_time = time.perf_counter()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        self._rate_limited_count = 0

        logger.info(f"{desc}: Starting batch of {len(items)} items")

        # Create tasks for all items
        tasks = [
            self._execute_item(item, func, i, len(items), progress_callback)
            for i, item in enumerate(items)
        ]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build batch result
        batch_result = BatchResult[T, R]()
        batch_result.total_duration_ms = (time.perf_counter() - start_time) * 1000
        batch_result.rate_limited_count = self._rate_limited_count

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Task raised exception
                batch_result.items.append(
                    BatchItemResult(
                        item=items[i],
                        error=result,
                        success=False,
                    )
                )
                batch_result.failed += 1
            else:
                batch_result.items.append(result)
                if result.success:
                    batch_result.successful += 1
                else:
                    batch_result.failed += 1

        logger.info(
            f"{desc}: Completed {batch_result.successful}/{len(items)} "
            f"({batch_result.success_rate:.1%}) in {batch_result.total_duration_ms:.0f}ms"
        )

        return batch_result

    async def _execute_item(
        self,
        item: T,
        func: Callable[[T], Coroutine[Any, Any, R]],
        index: int,
        total: int,
        progress_callback: Callable[[int, int], None] | None,
    ) -> BatchItemResult[T, R]:
        """Execute function on a single item with retries.

        Args:
            item: Input item
            func: Async function to apply
            index: Item index (for logging)
            total: Total items (for logging)
            progress_callback: Progress callback

        Returns:
            BatchItemResult for this item
        """
        result = BatchItemResult[T, R](item=item)
        start_time = time.perf_counter()

        for attempt in range(self.config.retry_count + 1):
            try:
                # Acquire semaphore for concurrency control
                async with self._semaphore:  # type: ignore
                    # Apply rate limiting
                    await self._apply_rate_limit()

                    # Execute with optional timeout
                    if self.config.timeout_seconds > 0:
                        result.result = await asyncio.wait_for(
                            func(item),
                            timeout=self.config.timeout_seconds,
                        )
                    else:
                        result.result = await func(item)

                result.success = True
                result.retries = attempt
                break

            except asyncio.TimeoutError as e:
                result.error = e
                logger.warning(f"Item {index + 1}/{total}: Timeout (attempt {attempt + 1})")

            except Exception as e:
                result.error = e
                logger.debug(f"Item {index + 1}/{total}: Error (attempt {attempt + 1}): {e}")

                # Check if error is recoverable
                if isinstance(e, DistillationError) and not e.recoverable:
                    break

            if attempt < self.config.retry_count:
                # Wait before retry with exponential backoff
                delay = self.config.retry_delay_seconds * (2**attempt)
                await asyncio.sleep(delay)

        result.duration_ms = (time.perf_counter() - start_time) * 1000

        # Report progress
        if progress_callback:
            try:
                progress_callback(index + 1, total)
            except Exception:
                pass

        return result

    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        if self.config.rate_limit_per_second <= 0:
            return

        async with self._rate_limit_lock:
            min_interval = 1.0 / self.config.rate_limit_per_second
            current_time = time.perf_counter()
            elapsed = current_time - self._last_request_time

            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                self._rate_limited_count += 1
                await asyncio.sleep(wait_time)

            self._last_request_time = time.perf_counter()


async def execute_with_progress(
    items: list[T],
    func: Callable[[T], Coroutine[Any, Any, R]],
    desc: str = "Processing",
    *,
    max_concurrent: int = 5,
    rate_limit: float = 5.0,
    log_interval: int = 10,
) -> list[R]:
    """Convenience function for batch execution with logging.

    Args:
        items: List of input items
        func: Async function to apply
        desc: Description for logging
        max_concurrent: Max concurrent operations
        rate_limit: Max operations per second
        log_interval: Log progress every N items

    Returns:
        List of successful results (failed items excluded)
    """
    config = BatchExecutorConfig(
        max_concurrent=max_concurrent,
        rate_limit_per_second=rate_limit,
    )

    def progress_callback(completed: int, total: int) -> None:
        if completed % log_interval == 0 or completed == total:
            logger.info(f"{desc}: {completed}/{total} ({100 * completed / total:.1f}%)")

    executor = AsyncBatchExecutor[T, R](config)
    result = await executor.execute_batch(
        items, func, desc, progress_callback=progress_callback
    )

    return result.get_successful_results()
