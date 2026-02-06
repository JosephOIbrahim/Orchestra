"""
Benchmark

Tests the Persistent State Hypothesis: retrieval is >10x faster than inference.
Measures retrieval latency, inference latency, and calculates speedup ratios.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

from ..schemas import KnowledgePrim
from ..retriever import KnowledgeRetriever
from .config import DistillationConfig
from .llm_client import BaseLLMClient

logger = logging.getLogger(__name__)


@dataclass
class TimingResult:
    """Result of a single timing measurement.

    Attributes:
        query: The query used
        method: 'retrieval' or 'inference'
        latency_ms: Time taken in milliseconds
        success: Whether the operation succeeded
        result_summary: Brief summary of the result
    """
    query: str
    method: str
    latency_ms: float
    success: bool = True
    result_summary: str = ""


@dataclass
class BenchmarkResult:
    """Complete benchmark result for hypothesis testing.

    Attributes:
        retrieval_mean_ms: Mean retrieval latency
        retrieval_median_ms: Median retrieval latency
        retrieval_p95_ms: 95th percentile retrieval latency
        inference_mean_ms: Mean inference latency
        inference_median_ms: Median inference latency
        inference_p95_ms: 95th percentile inference latency
        speedup_ratio: inference_mean / retrieval_mean
        hypothesis_met: Whether speedup >= target (10x)
        knowledge_hit_rate: Fraction of queries with knowledge hits
        sample_size: Number of queries tested
        detailed_timings: All individual timing results
    """
    retrieval_mean_ms: float = 0.0
    retrieval_median_ms: float = 0.0
    retrieval_p95_ms: float = 0.0
    inference_mean_ms: float = 0.0
    inference_median_ms: float = 0.0
    inference_p95_ms: float = 0.0
    speedup_ratio: float = 0.0
    hypothesis_met: bool = False
    knowledge_hit_rate: float = 0.0
    sample_size: int = 0
    detailed_timings: list[TimingResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "retrieval_mean_ms": self.retrieval_mean_ms,
            "retrieval_median_ms": self.retrieval_median_ms,
            "retrieval_p95_ms": self.retrieval_p95_ms,
            "inference_mean_ms": self.inference_mean_ms,
            "inference_median_ms": self.inference_median_ms,
            "inference_p95_ms": self.inference_p95_ms,
            "speedup_ratio": self.speedup_ratio,
            "hypothesis_met": self.hypothesis_met,
            "knowledge_hit_rate": self.knowledge_hit_rate,
            "sample_size": self.sample_size,
            "timing_count": len(self.detailed_timings),
        }

    def summary(self) -> str:
        """Generate human-readable summary."""
        status = "CONFIRMED" if self.hypothesis_met else "NOT MET"
        return f"""
Persistent State Hypothesis: {status}
{'=' * 50}
Target: >= {10.0}x speedup

Retrieval Latency:
  Mean:   {self.retrieval_mean_ms:.3f} ms
  Median: {self.retrieval_median_ms:.3f} ms
  P95:    {self.retrieval_p95_ms:.3f} ms

Inference Latency:
  Mean:   {self.inference_mean_ms:.1f} ms
  Median: {self.inference_median_ms:.1f} ms
  P95:    {self.inference_p95_ms:.1f} ms

Speedup Ratio: {self.speedup_ratio:.1f}x
Knowledge Hit Rate: {self.knowledge_hit_rate * 100:.1f}%
Sample Size: {self.sample_size} queries
"""


class Benchmark:
    """Benchmarks retrieval vs inference performance.

    Tests the Persistent State Hypothesis by measuring:
    - O(1) knowledge retrieval latency
    - LLM inference latency for the same queries
    - Speedup ratio (should be >= 10x)

    Attributes:
        config: Distillation configuration
        llm_client: LLM client for inference benchmarks
        retriever: Knowledge retriever for retrieval benchmarks
    """

    def __init__(
        self,
        config: DistillationConfig,
        llm_client: BaseLLMClient | None = None,
        retriever: KnowledgeRetriever | None = None,
    ) -> None:
        self.config = config
        self.llm_client = llm_client
        self.retriever = retriever

    def _generate_test_queries(
        self, prims: list[KnowledgePrim], count: int
    ) -> list[str]:
        """Generate test queries from prims.

        Args:
            prims: Available prims
            count: Number of queries to generate

        Returns:
            List of test queries
        """
        queries = []

        for prim in prims[:count]:
            # Use triggers as queries
            for trigger in prim.triggers[:2]:
                queries.append(f"What is {trigger}?")

            # Use key concepts
            for concept in prim.key_concepts[:1]:
                queries.append(f"Explain {concept}")

        return queries[:count]

    def _time_retrieval(self, query: str) -> TimingResult:
        """Time a single retrieval operation.

        Args:
            query: Query string

        Returns:
            TimingResult with latency
        """
        if not self.retriever:
            return TimingResult(
                query=query,
                method="retrieval",
                latency_ms=0.0,
                success=False,
                result_summary="No retriever available",
            )

        start = time.perf_counter()
        result = self.retriever.search(query)
        elapsed_ms = (time.perf_counter() - start) * 1000

        return TimingResult(
            query=query,
            method="retrieval",
            latency_ms=elapsed_ms,
            success=result.found,
            result_summary=f"Found {len(result.prims)} prims" if result.found else "No match",
        )

    async def _time_inference(self, query: str) -> TimingResult:
        """Time a single inference operation.

        Args:
            query: Query string

        Returns:
            TimingResult with latency
        """
        if not self.llm_client:
            return TimingResult(
                query=query,
                method="inference",
                latency_ms=0.0,
                success=False,
                result_summary="No LLM client available",
            )

        start = time.perf_counter()
        try:
            response = await self.llm_client.generate(
                prompt=query,
                max_tokens=500,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

            return TimingResult(
                query=query,
                method="inference",
                latency_ms=elapsed_ms,
                success=True,
                result_summary=f"{len(response.content)} chars",
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TimingResult(
                query=query,
                method="inference",
                latency_ms=elapsed_ms,
                success=False,
                result_summary=str(e),
            )

    async def run(
        self,
        prims: list[KnowledgePrim] | None = None,
        queries: list[str] | None = None,
        iterations: int | None = None,
    ) -> BenchmarkResult:
        """Run the benchmark.

        Args:
            prims: Prims to generate queries from (if queries not provided)
            queries: Explicit test queries
            iterations: Number of timing iterations

        Returns:
            BenchmarkResult with all metrics
        """
        iters = iterations or self.config.benchmark_iterations

        # Generate or use provided queries
        if queries:
            test_queries = queries
        elif prims:
            test_queries = self._generate_test_queries(prims, iters)
        else:
            logger.warning("No prims or queries provided for benchmark")
            return BenchmarkResult()

        # Limit to configured iterations
        test_queries = test_queries[:iters]

        logger.info(f"Running benchmark with {len(test_queries)} queries")

        # Collect timings
        retrieval_timings = []
        inference_timings = []
        hits = 0

        for i, query in enumerate(test_queries):
            # Time retrieval
            ret_result = self._time_retrieval(query)
            retrieval_timings.append(ret_result)
            if ret_result.success:
                hits += 1

            # Time inference (sample, not all - too expensive)
            if i < min(10, len(test_queries)):  # Only benchmark first 10 for inference
                inf_result = await self._time_inference(query)
                inference_timings.append(inf_result)

            if (i + 1) % 20 == 0:
                logger.info(f"Benchmark progress: {i + 1}/{len(test_queries)}")

        # Calculate statistics
        result = self._calculate_statistics(
            retrieval_timings,
            inference_timings,
            hits,
            len(test_queries),
        )

        logger.info(f"Benchmark complete: speedup={result.speedup_ratio:.1f}x")

        return result

    def _calculate_statistics(
        self,
        retrieval_timings: list[TimingResult],
        inference_timings: list[TimingResult],
        hits: int,
        total: int,
    ) -> BenchmarkResult:
        """Calculate statistics from timing results.

        Args:
            retrieval_timings: All retrieval timings
            inference_timings: All inference timings
            hits: Number of successful retrievals
            total: Total queries

        Returns:
            BenchmarkResult with calculated metrics
        """
        result = BenchmarkResult()
        result.sample_size = total
        result.knowledge_hit_rate = hits / total if total > 0 else 0.0

        # Retrieval statistics
        ret_latencies = [t.latency_ms for t in retrieval_timings if t.success]
        if ret_latencies:
            result.retrieval_mean_ms = statistics.mean(ret_latencies)
            result.retrieval_median_ms = statistics.median(ret_latencies)
            result.retrieval_p95_ms = self._percentile(ret_latencies, 95)

        # Inference statistics
        inf_latencies = [t.latency_ms for t in inference_timings if t.success]
        if inf_latencies:
            result.inference_mean_ms = statistics.mean(inf_latencies)
            result.inference_median_ms = statistics.median(inf_latencies)
            result.inference_p95_ms = self._percentile(inf_latencies, 95)

        # Calculate speedup
        if result.retrieval_mean_ms > 0 and result.inference_mean_ms > 0:
            result.speedup_ratio = result.inference_mean_ms / result.retrieval_mean_ms
        else:
            result.speedup_ratio = 0.0

        # Check hypothesis
        result.hypothesis_met = result.speedup_ratio >= self.config.hypothesis_speedup_target

        # Store detailed timings
        result.detailed_timings = retrieval_timings + inference_timings

        return result

    def _percentile(self, data: list[float], p: int) -> float:
        """Calculate percentile.

        Args:
            data: List of values
            p: Percentile (0-100)

        Returns:
            Percentile value
        """
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100)
        idx = min(idx, len(sorted_data) - 1)
        return sorted_data[idx]

    async def run_quick(
        self, prims: list[KnowledgePrim]
    ) -> dict[str, Any]:
        """Run a quick benchmark for immediate feedback.

        Args:
            prims: Prims to benchmark

        Returns:
            Quick summary dict
        """
        # Just time a few retrievals without inference
        queries = self._generate_test_queries(prims, 20)

        retrieval_times = []
        hits = 0

        for query in queries:
            result = self._time_retrieval(query)
            if result.success:
                retrieval_times.append(result.latency_ms)
                hits += 1

        if retrieval_times:
            return {
                "retrieval_mean_ms": statistics.mean(retrieval_times),
                "retrieval_p95_ms": self._percentile(retrieval_times, 95),
                "hit_rate": hits / len(queries),
                "samples": len(queries),
            }
        else:
            return {
                "retrieval_mean_ms": 0.0,
                "hit_rate": 0.0,
                "samples": len(queries),
                "error": "No successful retrievals",
            }
