"""
Framework Orchestrator - Production-Ready 7-Agent System (v3.0)

A production-hardened async orchestration system with:

v2.0 Production Hardening:
- Circuit breaker for cascading failure prevention
- Configurable timeouts and retries
- Atomic file writes for state integrity
- Input validation and sanitization
- Structured logging (text/JSON)
- Health check support
- Graceful shutdown handling

v3.0 Production Excellence:
- Prometheus-compatible metrics for observability
- Distributed tracing (Jaeger/Zipkin compatible)
- Bulkhead pattern for agent isolation
- Crash recovery checkpointing
- Graceful degradation with fallbacks
- Token-bucket rate limiting
- Idempotent execution for safe retries

Usage:
    from framework_orchestrator import FrameworkOrchestrator, OrchestratorConfig

    config = OrchestratorConfig()
    orchestrator = FrameworkOrchestrator(config=config)

    result = await orchestrator.orchestrate("Analyze this task")

CLI Usage:
    python -m framework_orchestrator --task "Your task here"
    python -m framework_orchestrator --health
    python -m framework_orchestrator --show-config
    python -m framework_orchestrator --metrics
    python -m framework_orchestrator --status
    python -m framework_orchestrator --show-interrupted

Environment Variables:
    FO_WORKSPACE - Workspace directory
    FO_AGENT_TIMEOUT - Per-agent timeout (seconds)
    FO_ORCHESTRATION_TIMEOUT - Total timeout (seconds)
    FO_MAX_RETRIES - Retry count
    FO_LOG_FORMAT - 'text' or 'json'
    FO_LOG_LEVEL - DEBUG, INFO, WARNING, ERROR

    # v3.0 Production Excellence
    FO_MAX_CONCURRENT_AGENTS - Bulkhead concurrency limit
    FO_CHECKPOINT_ENABLED - Enable crash recovery
    FO_METRICS_ENABLED - Enable Prometheus metrics
    FO_TRACING_ENABLED - Enable distributed tracing
    FO_ENABLE_BULKHEAD - Enable agent isolation
    FO_ENABLE_FALLBACK - Enable graceful degradation
    FO_ENABLE_RATE_LIMIT - Enable rate limiting
    FO_ENABLE_IDEMPOTENCY - Enable safe retries
"""

__version__ = "3.0.0"
__author__ = "Framework Ecosystem Integration"

# Core orchestrator
from .framework_orchestrator import (
    FrameworkOrchestrator,
    AgentResult,
    AgentStatus,
    OrchestratorState,
    BaseAgent,
    # Agent implementations (for testing)
    ECHOCuratorAgent,
    DomainIntelligenceAgent,
    MoERouterAgent,
    WorldModelerAgent,
    CodeGeneratorAgent,
    DeterminismGuardAgent,
    SelfReflectorAgent,
    Mycelium,
)

# Configuration
from .config import (
    OrchestratorConfig,
    get_config,
    set_config,
)

# Resilience patterns
from .resilience import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    ResilientExecutor,
    TimeoutError,
    with_timeout,
    with_retry,
    RetryConfig,
)

# File operations
from .file_ops import (
    atomic_write_json,
    atomic_write_text,
    safe_read_json,
    AtomicWriteError,
)

# Validation
from .validation import (
    validate_task,
    validate_context,
    validate_agent_name,
    validate_domain_config,
    sanitize_path_for_logging,
    sanitize_error_message,
    truncate_for_logging,
    ValidationResult,
    ValidationError,
)

# Logging
from .logging_setup import (
    setup_logging,
    get_logger,
    JSONFormatter,
    TextFormatter,
    log_execution,
    log_orchestration_start,
    log_orchestration_complete,
)

# Health checks
from .health import (
    HealthChecker,
    HealthStatus,
    HealthReport,
    ComponentHealth,
    format_health_report,
)

# Lifecycle management
from .lifecycle import (
    LifecycleManager,
    LifecycleState,
    ShutdownContext,
    run_with_lifecycle,
)

# Schema validation
from .schemas import (
    validate_json_schema,
    validate_domain_config as validate_domain_schema,
    validate_principles,
    validate_state_file,
    validate_agent_result,
    DOMAIN_CONFIG_SCHEMA,
    PRINCIPLES_SCHEMA,
    STATE_FILE_SCHEMA,
    AGENT_RESULT_SCHEMA,
)

# ============================================================================
# v3.0 Production Excellence Modules
# ============================================================================

# Metrics (Prometheus-compatible)
from .metrics import (
    OrchestratorMetrics,
    get_metrics,
    reset_metrics,
    Counter,
    Histogram,
    Gauge,
)

# Distributed Tracing
from .tracing import (
    DistributedTracer,
    get_tracer,
    configure_tracer,
    trace,
    TraceContext,
    Span,
    SpanStatus,
)

# Bulkhead (Agent Isolation)
from .bulkhead import (
    BulkheadExecutor,
    AdaptiveBulkhead,
    BulkheadRejected,
    BulkheadTimeout,
)

# Checkpointing (Crash Recovery)
from .checkpoint import (
    OrchestrationCheckpoint,
    CheckpointData,
    CheckpointStatus,
    recover_from_crash,
)

# Fallback (Graceful Degradation)
from .fallback import (
    FallbackRegistry,
    FallbackResult,
    GracefulDegradation,
    CachedResult,
)

# Rate Limiting
from .rate_limit import (
    RateLimiter,
    SlidingWindowLimiter,
    CompositeRateLimiter,
    RateLimitExceeded,
)

# Idempotency
from .idempotency import (
    IdempotencyManager,
    ExecutionStatus,
    ExecutionRecord,
    IdempotencyConflict,
    generate_idempotency_key,
)

__all__ = [
    # Version
    "__version__",

    # Core
    "FrameworkOrchestrator",
    "AgentResult",
    "AgentStatus",
    "OrchestratorState",
    "BaseAgent",
    # Agent implementations
    "ECHOCuratorAgent",
    "DomainIntelligenceAgent",
    "MoERouterAgent",
    "WorldModelerAgent",
    "CodeGeneratorAgent",
    "DeterminismGuardAgent",
    "SelfReflectorAgent",
    "Mycelium",

    # Configuration
    "OrchestratorConfig",
    "get_config",
    "set_config",

    # Resilience
    "CircuitBreaker",
    "CircuitBreakerOpen",
    "CircuitState",
    "ResilientExecutor",
    "TimeoutError",
    "with_timeout",
    "with_retry",
    "RetryConfig",

    # File operations
    "atomic_write_json",
    "atomic_write_text",
    "safe_read_json",
    "AtomicWriteError",

    # Validation
    "validate_task",
    "validate_context",
    "validate_agent_name",
    "validate_domain_config",
    "sanitize_path_for_logging",
    "sanitize_error_message",
    "truncate_for_logging",
    "ValidationResult",
    "ValidationError",

    # Logging
    "setup_logging",
    "get_logger",
    "JSONFormatter",
    "TextFormatter",

    # Health
    "HealthChecker",
    "HealthStatus",
    "HealthReport",
    "ComponentHealth",
    "format_health_report",

    # Lifecycle
    "LifecycleManager",
    "LifecycleState",
    "ShutdownContext",
    "run_with_lifecycle",

    # Schemas
    "validate_json_schema",
    "validate_domain_schema",
    "validate_principles",
    "validate_state_file",
    "validate_agent_result",

    # ========================================
    # v3.0 Production Excellence
    # ========================================

    # Metrics
    "OrchestratorMetrics",
    "get_metrics",
    "reset_metrics",
    "Counter",
    "Histogram",
    "Gauge",

    # Tracing
    "DistributedTracer",
    "get_tracer",
    "configure_tracer",
    "trace",
    "TraceContext",
    "Span",
    "SpanStatus",

    # Bulkhead
    "BulkheadExecutor",
    "AdaptiveBulkhead",
    "BulkheadRejected",
    "BulkheadTimeout",

    # Checkpoint
    "OrchestrationCheckpoint",
    "CheckpointData",
    "CheckpointStatus",
    "recover_from_crash",

    # Fallback
    "FallbackRegistry",
    "FallbackResult",
    "GracefulDegradation",
    "CachedResult",

    # Rate Limiting
    "RateLimiter",
    "SlidingWindowLimiter",
    "CompositeRateLimiter",
    "RateLimitExceeded",

    # Idempotency
    "IdempotencyManager",
    "ExecutionStatus",
    "ExecutionRecord",
    "IdempotencyConflict",
    "generate_idempotency_key",
]
