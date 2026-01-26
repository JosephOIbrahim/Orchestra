"""
Distillation Errors

Structured exception hierarchy for the distillation pipeline.
Provides granular error handling with context preservation.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
ThinkingMachines [He2025] Production Hardening.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorSeverity(Enum):
    """Severity levels for distillation errors."""

    WARNING = "warning"  # Non-blocking, operation can continue
    ERROR = "error"  # Operation failed but pipeline can continue
    CRITICAL = "critical"  # Pipeline must stop


class ErrorCategory(Enum):
    """Categories of distillation errors."""

    LLM = "llm"  # LLM API errors
    VALIDATION = "validation"  # Content validation errors
    IO = "io"  # File I/O errors
    PARSING = "parsing"  # Response parsing errors
    CONFIGURATION = "configuration"  # Config errors
    CHECKPOINT = "checkpoint"  # Checkpoint/resumption errors


@dataclass
class ErrorContext:
    """Context information for debugging errors."""

    stage: str = ""  # Pipeline stage (ingest, query, answer, etc.)
    document_id: str = ""  # Affected document
    chunk_id: str = ""  # Affected chunk
    prim_path: str = ""  # Affected prim
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "stage": self.stage,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "prim_path": self.prim_path,
            **self.extra,
        }


class DistillationError(Exception):
    """Base exception for all distillation pipeline errors.

    Attributes:
        message: Human-readable error message
        severity: Error severity level
        category: Error category
        context: Additional context for debugging
        recoverable: Whether the operation can be retried
    """

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        category: ErrorCategory = ErrorCategory.LLM,
        context: ErrorContext | None = None,
        recoverable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.category = category
        self.context = context or ErrorContext()
        self.recoverable = recoverable
        self.__cause__ = cause

    def __str__(self) -> str:
        parts = [f"[{self.severity.value}] {self.message}"]
        if self.context.stage:
            parts.append(f"Stage: {self.context.stage}")
        if self.__cause__:
            parts.append(f"Caused by: {self.__cause__}")
        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for logging."""
        return {
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "context": self.context.to_dict(),
            "recoverable": self.recoverable,
            "cause": str(self.__cause__) if self.__cause__ else None,
        }


class LLMResponseError(DistillationError):
    """Error from LLM API call."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
        context: ErrorContext | None = None,
        cause: Exception | None = None,
    ) -> None:
        # Rate limits and timeouts are recoverable
        recoverable = status_code in {429, 500, 502, 503, 504} if status_code else False

        super().__init__(
            message,
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.LLM,
            context=context,
            recoverable=recoverable,
            cause=cause,
        )
        self.status_code = status_code
        self.response_body = response_body


class LLMParsingError(DistillationError):
    """Error parsing LLM response."""

    def __init__(
        self,
        message: str,
        *,
        response_content: str | None = None,
        expected_schema: str | None = None,
        context: ErrorContext | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.WARNING,  # Parsing errors are recoverable
            category=ErrorCategory.PARSING,
            context=context,
            recoverable=True,
            cause=cause,
        )
        self.response_content = response_content
        self.expected_schema = expected_schema


class ValidationError(DistillationError):
    """Error during content validation."""

    def __init__(
        self,
        message: str,
        *,
        validation_scores: dict[str, float] | None = None,
        failure_reasons: list[str] | None = None,
        context: ErrorContext | None = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.VALIDATION,
            context=context,
            recoverable=False,  # Validation failures are final
        )
        self.validation_scores = validation_scores or {}
        self.failure_reasons = failure_reasons or []


class IOError(DistillationError):
    """File I/O error."""

    def __init__(
        self,
        message: str,
        *,
        file_path: str | None = None,
        operation: str = "read",
        context: ErrorContext | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.IO,
            context=context,
            recoverable=operation == "read",  # Read errors might be retryable
            cause=cause,
        )
        self.file_path = file_path
        self.operation = operation


class ConfigurationError(DistillationError):
    """Configuration error."""

    def __init__(
        self,
        message: str,
        *,
        config_field: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.CONFIGURATION,
            recoverable=False,
        )
        self.config_field = config_field
        self.expected = expected
        self.actual = actual


class CheckpointError(DistillationError):
    """Checkpoint save/load error."""

    def __init__(
        self,
        message: str,
        *,
        checkpoint_path: str | None = None,
        stage: str | None = None,
        context: ErrorContext | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.CHECKPOINT,
            context=context,
            recoverable=True,
            cause=cause,
        )
        self.checkpoint_path = checkpoint_path
        if stage and context:
            context.stage = stage


class PipelineStageError(DistillationError):
    """Error in a specific pipeline stage."""

    def __init__(
        self,
        message: str,
        stage: str,
        *,
        items_processed: int = 0,
        items_failed: int = 0,
        context: ErrorContext | None = None,
        cause: Exception | None = None,
    ) -> None:
        context = context or ErrorContext()
        context.stage = stage

        super().__init__(
            message,
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.LLM,
            context=context,
            recoverable=True,
            cause=cause,
        )
        self.stage = stage
        self.items_processed = items_processed
        self.items_failed = items_failed


def wrap_error(
    e: Exception,
    message: str,
    *,
    context: ErrorContext | None = None,
) -> DistillationError:
    """Wrap a generic exception in a DistillationError.

    Args:
        e: Original exception
        message: Additional context message
        context: Error context

    Returns:
        Wrapped DistillationError
    """
    if isinstance(e, DistillationError):
        # Already wrapped, just update context if provided
        if context:
            e.context = context
        return e

    return DistillationError(
        f"{message}: {e}",
        severity=ErrorSeverity.ERROR,
        context=context,
        cause=e,
    )
