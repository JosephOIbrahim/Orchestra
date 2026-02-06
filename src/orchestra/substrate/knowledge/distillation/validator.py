"""
Validator

Validates distilled knowledge prims for accuracy and hallucination.
Uses multi-stage validation with LLM and heuristic checks.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from ..schemas import KnowledgePrim
from .answer_generator import GeneratedAnswer
from .config import DistillationConfig
from .llm_client import BaseLLMClient
from .response_schemas import parse_hallucination_response

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a knowledge prim.

    Attributes:
        prim_path: Path to the validated prim
        retrieval_accuracy: How accurately content matches source
        hallucination_score: Degree of unsupported claims (0.0 = none, 1.0 = all)
        consistency_score: Internal consistency of the content
        passed: Whether the prim passed validation
        failure_reasons: List of reasons for failure
        warnings: Non-blocking issues
        metadata: Additional validation metadata
    """
    prim_path: str
    retrieval_accuracy: float = 0.0
    hallucination_score: float = 1.0
    consistency_score: float = 0.0
    passed: bool = False
    failure_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "prim_path": self.prim_path,
            "retrieval_accuracy": self.retrieval_accuracy,
            "hallucination_score": self.hallucination_score,
            "consistency_score": self.consistency_score,
            "passed": self.passed,
            "failure_reasons": self.failure_reasons,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


HALLUCINATION_CHECK_SYSTEM = """You are a fact-checking expert. Your task is to compare generated content
against a source document and identify any claims NOT supported by the source.

Be strict but fair:
- Paraphrasing is acceptable if meaning is preserved
- Reasonable inferences from the source are acceptable
- Claims that go beyond the source are hallucinations
- Made-up details not in the source are hallucinations

Output ONLY valid JSON, no other text."""

HALLUCINATION_CHECK_PROMPT = """Compare this generated content against the source document.
Identify claims in the generated content that are NOT supported by the source.

Generated Content:
---
{content}
---

Source Document:
---
{source}
---

Analyze and respond in this JSON format:
{{
  "supported_claims": ["claim 1", "claim 2"],
  "unsupported_claims": ["claim that is not in source"],
  "hallucination_score": 0.0-1.0,
  "analysis": "Brief explanation of your evaluation"
}}

hallucination_score:
- 0.0 = All claims fully supported by source
- 0.5 = Some claims unsupported
- 1.0 = Most claims unsupported or fabricated"""


class Validator:
    """Validates distilled knowledge prims.

    Performs multiple validation stages:
    1. Heuristic checks (length, structure)
    2. Source quote verification
    3. LLM hallucination detection
    4. Consistency scoring

    Attributes:
        config: Distillation configuration
        llm_client: LLM client for validation
    """

    def __init__(
        self,
        config: DistillationConfig,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.config = config
        self.llm_client = llm_client
        self._validations_performed = 0
        self._validations_passed = 0
        self._hallucinations_detected = 0

    async def validate(
        self,
        prim: KnowledgePrim,
        answer: GeneratedAnswer,
    ) -> ValidationResult:
        """Validate a knowledge prim against its source.

        Args:
            prim: The prim to validate
            answer: The GeneratedAnswer it came from

        Returns:
            ValidationResult with scores and pass/fail
        """
        self._validations_performed += 1
        result = ValidationResult(prim_path=prim.canonical_path)

        # Stage 1: Heuristic checks
        heuristic_issues = self._heuristic_validation(prim, answer)
        result.warnings.extend(heuristic_issues)

        # Stage 2: Source quote verification
        quote_accuracy = self._verify_source_quotes(answer)
        result.metadata["quote_accuracy"] = quote_accuracy

        # Stage 3: Retrieval accuracy (text similarity)
        if answer.source_chunk:
            result.retrieval_accuracy = self._calculate_retrieval_accuracy(
                prim.content,
                answer.source_chunk.content,
            )
        else:
            result.retrieval_accuracy = answer.confidence_hint

        # Stage 4: LLM hallucination detection
        if self.llm_client and answer.source_chunk:
            hallucination_result = await self._llm_hallucination_check(
                prim.content,
                answer.source_chunk.content,
            )
            result.hallucination_score = hallucination_result.get("hallucination_score", 0.5)
            result.metadata["hallucination_analysis"] = hallucination_result.get("analysis", "")

            unsupported = hallucination_result.get("unsupported_claims", [])
            if unsupported:
                self._hallucinations_detected += 1
                result.warnings.append(f"Unsupported claims: {unsupported}")
        else:
            # Fallback: use source quotes as proxy
            result.hallucination_score = 1.0 - quote_accuracy

        # Stage 5: Consistency scoring
        result.consistency_score = self._calculate_consistency(prim, answer)

        # Determine pass/fail
        thresholds = self.config.effective_thresholds
        result.passed = self._check_thresholds(result, thresholds)

        if result.passed:
            self._validations_passed += 1

        logger.debug(
            f"Validated {prim.canonical_path}: "
            f"passed={result.passed}, "
            f"hallucination={result.hallucination_score:.2f}"
        )

        return result

    def _heuristic_validation(
        self,
        prim: KnowledgePrim,
        answer: GeneratedAnswer,
    ) -> list[str]:
        """Perform basic heuristic checks.

        Args:
            prim: The prim to check
            answer: Source answer

        Returns:
            List of warning messages
        """
        warnings = []

        # Check content length
        if len(prim.content) < 50:
            warnings.append("Content very short (<50 chars)")
        elif len(prim.content) > 5000:
            warnings.append("Content very long (>5000 chars)")

        # Check summary length
        if len(prim.summary) < 10:
            warnings.append("Summary too short (<10 chars)")
        elif len(prim.summary) > 200:
            warnings.append("Summary too long (>200 chars)")

        # Check for key concepts
        if not prim.key_concepts:
            warnings.append("No key concepts extracted")

        # Check for triggers
        if len(prim.triggers) < 3:
            warnings.append("Few triggers (<3)")

        # Check confidence alignment
        if answer.confidence_hint < 0.5:
            warnings.append(f"Low source confidence: {answer.confidence_hint:.2f}")

        return warnings

    def _verify_source_quotes(self, answer: GeneratedAnswer) -> float:
        """Verify that source quotes actually appear in source.

        Args:
            answer: The generated answer

        Returns:
            Fraction of quotes found in source (0.0-1.0)
        """
        if not answer.source_quotes or not answer.source_chunk:
            return 0.0

        source_text = answer.source_chunk.content.lower()
        found = 0

        for quote in answer.source_quotes:
            # Allow some flexibility with quote matching
            quote_lower = quote.lower().strip()
            if len(quote_lower) < 10:
                continue

            # Check for exact match or high similarity
            if quote_lower in source_text:
                found += 1
            else:
                # Check for fuzzy match
                similarity = self._text_similarity(quote_lower, source_text)
                if similarity > 0.8:
                    found += 0.8  # Partial credit

        return found / len(answer.source_quotes) if answer.source_quotes else 0.0

    def _calculate_retrieval_accuracy(
        self, content: str, source: str
    ) -> float:
        """Calculate how well content matches source.

        Args:
            content: Generated content
            source: Source document

        Returns:
            Similarity score (0.0-1.0)
        """
        # Use word overlap approach
        content_words = set(re.findall(r"\b\w{3,}\b", content.lower()))
        source_words = set(re.findall(r"\b\w{3,}\b", source.lower()))

        if not content_words:
            return 0.0

        overlap = content_words & source_words
        coverage = len(overlap) / len(content_words)

        return coverage

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using SequenceMatcher.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0.0-1.0)
        """
        return SequenceMatcher(None, text1, text2).ratio()

    async def _llm_hallucination_check(
        self, content: str, source: str
    ) -> dict[str, Any]:
        """Use LLM to detect hallucinations.

        Uses Pydantic schemas for robust parsing.
        Production Hardening: Handles malformed LLM responses gracefully.

        Args:
            content: Generated content to check
            source: Source document

        Returns:
            Dict with hallucination_score and analysis
        """
        if not self.llm_client:
            return {"hallucination_score": 0.5, "analysis": "No LLM available"}

        prompt = HALLUCINATION_CHECK_PROMPT.format(
            content=content[:2000],  # Truncate for token limits
            source=source[:3000],
        )

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system=HALLUCINATION_CHECK_SYSTEM,
            )

            # Use Pydantic-based parsing
            parsed = parse_hallucination_response(response.content)

            if parsed:
                return {
                    "supported_claims": parsed.supported_claims,
                    "unsupported_claims": parsed.unsupported_claims,
                    "hallucination_score": parsed.hallucination_score,
                    "analysis": parsed.analysis,
                }

            return {
                "hallucination_score": 0.5,
                "analysis": "Failed to parse response",
            }

        except Exception as e:
            logger.warning(f"LLM hallucination check failed: {e}")
            return {
                "hallucination_score": 0.5,
                "analysis": f"LLM check failed: {e}",
            }

    def _calculate_consistency(
        self, prim: KnowledgePrim, answer: GeneratedAnswer
    ) -> float:
        """Calculate internal consistency of the prim.

        Args:
            prim: The prim
            answer: Source answer

        Returns:
            Consistency score (0.0-1.0)
        """
        scores = []

        # Check summary vs content consistency
        if prim.summary and prim.content:
            summary_words = set(prim.summary.lower().split())
            content_words = set(prim.content.lower().split()[:50])
            if summary_words:
                overlap = summary_words & content_words
                scores.append(len(overlap) / len(summary_words))

        # Check key concepts appear in content
        if prim.key_concepts and prim.content:
            content_lower = prim.content.lower()
            found = sum(1 for c in prim.key_concepts if c.lower() in content_lower)
            scores.append(found / len(prim.key_concepts))

        # Check triggers are relevant
        if prim.triggers and prim.content:
            content_lower = prim.content.lower()
            found = sum(1 for t in prim.triggers if t.lower() in content_lower)
            scores.append(found / len(prim.triggers))

        return sum(scores) / len(scores) if scores else 0.0

    def _check_thresholds(
        self, result: ValidationResult, thresholds: dict[str, float]
    ) -> bool:
        """Check if validation result meets thresholds.

        Args:
            result: Validation result
            thresholds: Threshold values

        Returns:
            True if all thresholds met
        """
        failures = []

        if result.hallucination_score > thresholds["hallucination"]:
            failures.append(
                f"Hallucination score {result.hallucination_score:.2f} > {thresholds['hallucination']:.2f}"
            )

        if result.consistency_score < thresholds["consistency"]:
            failures.append(
                f"Consistency score {result.consistency_score:.2f} < {thresholds['consistency']:.2f}"
            )

        combined_score = (
            (1 - result.hallucination_score) * 0.5 +
            result.consistency_score * 0.3 +
            result.retrieval_accuracy * 0.2
        )

        if combined_score < thresholds["validation"]:
            failures.append(
                f"Combined score {combined_score:.2f} < {thresholds['validation']:.2f}"
            )

        result.failure_reasons = failures
        return len(failures) == 0

    async def validate_batch(
        self,
        prim_answer_pairs: list[tuple[KnowledgePrim, GeneratedAnswer]],
    ) -> list[ValidationResult]:
        """Validate multiple prims.

        Args:
            prim_answer_pairs: List of (prim, answer) tuples

        Returns:
            List of validation results
        """
        results = []

        for i, (prim, answer) in enumerate(prim_answer_pairs):
            result = await self.validate(prim, answer)
            results.append(result)

            if (i + 1) % 10 == 0:
                passed = sum(1 for r in results if r.passed)
                logger.info(
                    f"Validated {i + 1}/{len(prim_answer_pairs)}: "
                    f"{passed} passed ({100 * passed / (i + 1):.1f}%)"
                )

        return results

    @property
    def stats(self) -> dict[str, Any]:
        """Get validation statistics."""
        return {
            "validations_performed": self._validations_performed,
            "validations_passed": self._validations_passed,
            "hallucinations_detected": self._hallucinations_detected,
            "pass_rate": (
                self._validations_passed / self._validations_performed
                if self._validations_performed > 0 else 0.0
            ),
        }
