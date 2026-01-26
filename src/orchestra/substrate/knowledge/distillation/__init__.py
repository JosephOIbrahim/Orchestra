"""
Knowledge Distillation Pipeline

Automated pipeline for extracting KnowledgePrims from documentation corpora.
Tests the Persistent State Hypothesis: retrieval is >10x faster than inference.

Part of USD Cognitive Substrate - Orchestra v5.0.2

Example:
    >>> from orchestra.substrate.knowledge.distillation import (
    ...     DistillationConfig,
    ...     DistillationPipeline,
    ... )
    >>> config = DistillationConfig(corpus_dir=Path("docs/"))
    >>> pipeline = DistillationPipeline(config)
    >>> stats = await pipeline.run()

CLI Usage:
    python -m orchestra.substrate.knowledge.distillation.pipeline \\
        --corpus docs/ --output ~/.orchestra/knowledge/distilled/
"""

from __future__ import annotations

from .answer_generator import AnswerGenerator, GeneratedAnswer
from .benchmark import Benchmark, BenchmarkResult, TimingResult
from .confidence_scorer import ConfidenceBreakdown, ConfidenceScorer
from .config import DistillationConfig, LLMProvider, ValidationStrictness
from .corpus_ingester import CorpusIngester, DocumentChunk
from .llm_client import (
    AnthropicClient,
    BaseLLMClient,
    LLMResponse,
    OpenAIClient,
    create_llm_client,
)
from .pipeline import DistillationPipeline, PipelineStats
from .prim_extractor import ExtractionResult, PrimExtractor
from .query_generator import GeneratedQuery, QueryGenerator, QuestionType
from .trigger_generator import TriggerGenerator, TriggerSet
from .usda_writer import USDAWriter
from .validator import ValidationResult, Validator

# Production Hardening (ThinkingMachines [He2025])
from .async_executor import (
    AsyncBatchExecutor,
    BatchExecutorConfig,
    BatchItemResult,
    BatchResult,
    execute_with_progress,
)
from .checkpoint import (
    CheckpointManager,
    PipelineCheckpoint,
    PipelineStage,
    StageData,
    create_checkpoint_manager,
)
from .errors import (
    CheckpointError,
    ConfigurationError,
    DistillationError,
    ErrorCategory,
    ErrorContext,
    ErrorSeverity,
    IOError,
    LLMParsingError,
    LLMResponseError,
    PipelineStageError,
    ValidationError,
    wrap_error,
)
from .response_schemas import (
    AnswerGenerationResponse,
    GeneratedQuestionSchema,
    HallucinationCheckResponse,
    QueryGenerationResponse,
    TriggerGenerationResponse,
    extract_json_from_response,
    parse_answer_response,
    parse_hallucination_response,
    parse_llm_json,
    parse_query_response,
    parse_trigger_response,
)

# Frontier AI Enhancements (Optional)
from .entailment_grounder import (
    ClaimGrounding,
    EntailmentGrounder,
    EntailmentVerdict,
    GroundingResult,
    ground_content,
)
from .self_consistency import (
    ClaimVerification,
    ConsistencyResult,
    SelfConsistencyVerifier,
)

__all__ = [
    # Config
    "DistillationConfig",
    "LLMProvider",
    "ValidationStrictness",
    # Pipeline
    "DistillationPipeline",
    "PipelineStats",
    # LLM Client
    "BaseLLMClient",
    "AnthropicClient",
    "OpenAIClient",
    "LLMResponse",
    "create_llm_client",
    # Ingestion
    "CorpusIngester",
    "DocumentChunk",
    # Query Generation
    "QueryGenerator",
    "GeneratedQuery",
    "QuestionType",
    # Answer Generation
    "AnswerGenerator",
    "GeneratedAnswer",
    # Prim Extraction
    "PrimExtractor",
    "ExtractionResult",
    # Trigger Generation
    "TriggerGenerator",
    "TriggerSet",
    # Checking
    "Validator",
    "ValidationResult",
    # Confidence Scoring
    "ConfidenceScorer",
    "ConfidenceBreakdown",
    # USDA Output
    "USDAWriter",
    # Benchmarking
    "Benchmark",
    "BenchmarkResult",
    "TimingResult",
    # Production Hardening - Async Executor
    "AsyncBatchExecutor",
    "BatchExecutorConfig",
    "BatchItemResult",
    "BatchResult",
    "execute_with_progress",
    # Production Hardening - Checkpointing
    "CheckpointManager",
    "PipelineCheckpoint",
    "PipelineStage",
    "StageData",
    "create_checkpoint_manager",
    # Production Hardening - Errors
    "DistillationError",
    "LLMResponseError",
    "LLMParsingError",
    "ValidationError",
    "IOError",
    "ConfigurationError",
    "CheckpointError",
    "PipelineStageError",
    "ErrorSeverity",
    "ErrorCategory",
    "ErrorContext",
    "wrap_error",
    # Production Hardening - Response Schemas
    "QueryGenerationResponse",
    "GeneratedQuestionSchema",
    "AnswerGenerationResponse",
    "HallucinationCheckResponse",
    "TriggerGenerationResponse",
    "parse_llm_json",
    "parse_query_response",
    "parse_answer_response",
    "parse_hallucination_response",
    "parse_trigger_response",
    "extract_json_from_response",
    # Frontier AI - Self Consistency
    "SelfConsistencyVerifier",
    "ConsistencyResult",
    "ClaimVerification",
    # Frontier AI - Entailment Grounding
    "EntailmentGrounder",
    "GroundingResult",
    "ClaimGrounding",
    "EntailmentVerdict",
    "ground_content",
]
