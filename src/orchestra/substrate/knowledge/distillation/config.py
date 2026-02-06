"""
Distillation Pipeline Configuration

Configuration dataclass for the knowledge distillation pipeline.
Controls LLM behavior, validation thresholds, and output settings.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class LLMProvider(Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class ValidationStrictness(Enum):
    """Validation strictness levels."""
    LENIENT = "lenient"      # Lower thresholds, more prims pass
    STANDARD = "standard"    # Default thresholds
    STRICT = "strict"        # Higher thresholds, fewer but higher quality


@dataclass
class DistillationConfig:
    """Configuration for the knowledge distillation pipeline.

    Attributes:
        llm_provider: Which LLM provider to use
        model_name: Model identifier (e.g., 'claude-sonnet-4-20250514')
        temperature: LLM temperature (0.0 for determinism)
        max_tokens: Max tokens per LLM response
        distilled_confidence: Default confidence for distilled prims
        validation_threshold: Min score to pass validation
        hallucination_threshold: Max hallucination score allowed
        queries_per_document: Questions to generate per doc chunk
        chunk_size: Max characters per document chunk
        chunk_overlap: Overlap between chunks for context
        output_dir: Directory for output USDA files
        corpus_dir: Directory containing source documents
        validation_strictness: How strict validation should be
        retry_count: Number of retries on LLM failures
        retry_delay_seconds: Base delay between retries
        batch_size: Documents to process before writing output
        enable_caching: Cache LLM responses for resumability

    Example:
        >>> config = DistillationConfig()
        >>> config.model_name
        'claude-sonnet-4-20250514'
    """
    # LLM Settings
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    model_name: str = "claude-sonnet-4-20250514"
    temperature: float = 0.0  # Determinism (ThinkingMachines [He2025])
    max_tokens: int = 4096

    # Confidence & Validation Thresholds
    distilled_confidence: float = 0.70  # Lower than curated (0.95)
    validation_threshold: float = 0.85  # Required to pass validation
    hallucination_threshold: float = 0.10  # Max 10% hallucinated content
    consistency_threshold: float = 0.80  # Min consistency score

    # Generation Settings
    queries_per_document: int = 5
    chunk_size: int = 4000  # Characters
    chunk_overlap: int = 200  # Overlap for context continuity

    # File Paths
    output_dir: Path = field(default_factory=lambda: Path.home() / ".orchestra" / "knowledge" / "distilled")
    corpus_dir: Path = field(default_factory=lambda: Path.cwd() / "docs")

    # Validation Settings
    validation_strictness: ValidationStrictness = ValidationStrictness.STANDARD

    # Retry & Performance
    retry_count: int = 3
    retry_delay_seconds: float = 1.0
    batch_size: int = 10
    enable_caching: bool = True

    # Benchmark Settings
    hypothesis_speedup_target: float = 10.0  # >10x speedup required
    benchmark_iterations: int = 100  # Iterations for timing accuracy

    # Async Batching Settings (Production Hardening)
    max_concurrent_llm_calls: int = 5  # Concurrent LLM requests
    llm_rate_limit_per_second: float = 5.0  # Rate limit for LLM API

    # Checkpointing Settings (Production Hardening)
    enable_checkpointing: bool = True  # Enable pipeline checkpoints
    checkpoint_dir: Path | None = None  # Custom checkpoint dir (default: output_dir/.checkpoints)

    # Frontier AI Settings (Optional)
    enable_self_consistency: bool = False  # Multi-sample voting for hallucination
    consistency_samples: int = 3  # Number of samples for consistency check
    consistency_temperatures: list[float] = field(
        default_factory=lambda: [0.3, 0.5, 0.7]
    )
    enable_entailment_grounding: bool = False  # NLI-based claim verification
    neutral_counts_as_hallucination: bool = False  # Treat NLI neutral as hallucination

    def __post_init__(self) -> None:
        """Ensure paths are Path objects and directories exist."""
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.corpus_dir, str):
            self.corpus_dir = Path(self.corpus_dir)
        if isinstance(self.llm_provider, str):
            self.llm_provider = LLMProvider(self.llm_provider)
        if isinstance(self.validation_strictness, str):
            self.validation_strictness = ValidationStrictness(self.validation_strictness)

    def ensure_directories(self) -> None:
        """Create output directories if they don't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def effective_thresholds(self) -> dict[str, float]:
        """Get thresholds adjusted for strictness level."""
        multipliers = {
            ValidationStrictness.LENIENT: 0.85,
            ValidationStrictness.STANDARD: 1.0,
            ValidationStrictness.STRICT: 1.15,
        }
        mult = multipliers[self.validation_strictness]
        return {
            "validation": min(1.0, self.validation_threshold * mult),
            "consistency": min(1.0, self.consistency_threshold * mult),
            "hallucination": max(0.0, self.hallucination_threshold / mult),
        }

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "llm_provider": self.llm_provider.value,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "distilled_confidence": self.distilled_confidence,
            "validation_threshold": self.validation_threshold,
            "hallucination_threshold": self.hallucination_threshold,
            "consistency_threshold": self.consistency_threshold,
            "queries_per_document": self.queries_per_document,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "output_dir": str(self.output_dir),
            "corpus_dir": str(self.corpus_dir),
            "validation_strictness": self.validation_strictness.value,
            "retry_count": self.retry_count,
            "retry_delay_seconds": self.retry_delay_seconds,
            "batch_size": self.batch_size,
            "enable_caching": self.enable_caching,
            "hypothesis_speedup_target": self.hypothesis_speedup_target,
            "benchmark_iterations": self.benchmark_iterations,
            # Production Hardening
            "max_concurrent_llm_calls": self.max_concurrent_llm_calls,
            "llm_rate_limit_per_second": self.llm_rate_limit_per_second,
            "enable_checkpointing": self.enable_checkpointing,
            "checkpoint_dir": str(self.checkpoint_dir) if self.checkpoint_dir else None,
            # Frontier AI
            "enable_self_consistency": self.enable_self_consistency,
            "consistency_samples": self.consistency_samples,
            "consistency_temperatures": self.consistency_temperatures,
            "enable_entailment_grounding": self.enable_entailment_grounding,
            "neutral_counts_as_hallucination": self.neutral_counts_as_hallucination,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DistillationConfig:
        """Create from dictionary."""
        checkpoint_dir = data.get("checkpoint_dir")
        return cls(
            llm_provider=LLMProvider(data.get("llm_provider", "anthropic")),
            model_name=data.get("model_name", "claude-sonnet-4-20250514"),
            temperature=data.get("temperature", 0.0),
            max_tokens=data.get("max_tokens", 4096),
            distilled_confidence=data.get("distilled_confidence", 0.70),
            validation_threshold=data.get("validation_threshold", 0.85),
            hallucination_threshold=data.get("hallucination_threshold", 0.10),
            consistency_threshold=data.get("consistency_threshold", 0.80),
            queries_per_document=data.get("queries_per_document", 5),
            chunk_size=data.get("chunk_size", 4000),
            chunk_overlap=data.get("chunk_overlap", 200),
            output_dir=Path(data.get("output_dir", str(Path.home() / ".orchestra" / "knowledge" / "distilled"))),
            corpus_dir=Path(data.get("corpus_dir", str(Path.cwd() / "docs"))),
            validation_strictness=ValidationStrictness(data.get("validation_strictness", "standard")),
            retry_count=data.get("retry_count", 3),
            retry_delay_seconds=data.get("retry_delay_seconds", 1.0),
            batch_size=data.get("batch_size", 10),
            enable_caching=data.get("enable_caching", True),
            hypothesis_speedup_target=data.get("hypothesis_speedup_target", 10.0),
            benchmark_iterations=data.get("benchmark_iterations", 100),
            # Production Hardening
            max_concurrent_llm_calls=data.get("max_concurrent_llm_calls", 5),
            llm_rate_limit_per_second=data.get("llm_rate_limit_per_second", 5.0),
            enable_checkpointing=data.get("enable_checkpointing", True),
            checkpoint_dir=Path(checkpoint_dir) if checkpoint_dir else None,
            # Frontier AI
            enable_self_consistency=data.get("enable_self_consistency", False),
            consistency_samples=data.get("consistency_samples", 3),
            consistency_temperatures=data.get("consistency_temperatures", [0.3, 0.5, 0.7]),
            enable_entailment_grounding=data.get("enable_entailment_grounding", False),
            neutral_counts_as_hallucination=data.get("neutral_counts_as_hallucination", False),
        )
