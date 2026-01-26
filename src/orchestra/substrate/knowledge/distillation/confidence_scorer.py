"""
Confidence Scorer

Calculates final confidence scores for distilled knowledge prims
based on validation results and source quality.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..schemas import KnowledgePrim
from .config import DistillationConfig
from .validator import ValidationResult

logger = logging.getLogger(__name__)


# Weight factors for confidence calculation
CONFIDENCE_WEIGHTS = {
    "hallucination": 0.35,      # Most important: content accuracy
    "consistency": 0.25,        # Internal consistency
    "retrieval_accuracy": 0.20, # Source alignment
    "source_confidence": 0.15,  # LLM self-assessment
    "heuristics": 0.05,         # Basic quality checks
}

# DETERMINISM: Fixed order for accumulation (ThinkingMachines [He2025])
# This ensures floating-point accumulation happens in consistent order
COMPONENT_ORDER = [
    "hallucination",
    "consistency",
    "retrieval_accuracy",
    "source_confidence",
    "heuristics",
]


@dataclass
class ConfidenceBreakdown:
    """Detailed breakdown of confidence score calculation.

    Attributes:
        prim_path: Path to the prim
        final_confidence: The calculated confidence score
        component_scores: Individual component scores
        component_weights: Weights used for each component
        weighted_contributions: Weighted contribution of each component
        adjustments: Any adjustments applied
        notes: Additional notes about the calculation
    """
    prim_path: str
    final_confidence: float = 0.0
    component_scores: dict[str, float] = field(default_factory=dict)
    component_weights: dict[str, float] = field(default_factory=dict)
    weighted_contributions: dict[str, float] = field(default_factory=dict)
    adjustments: list[tuple[str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "prim_path": self.prim_path,
            "final_confidence": self.final_confidence,
            "component_scores": self.component_scores,
            "component_weights": self.component_weights,
            "weighted_contributions": self.weighted_contributions,
            "adjustments": self.adjustments,
            "notes": self.notes,
        }


class ConfidenceScorer:
    """Calculates confidence scores for knowledge prims.

    Uses a weighted combination of validation metrics plus
    adjustments based on quality indicators.

    Attributes:
        config: Distillation configuration
    """

    def __init__(self, config: DistillationConfig) -> None:
        self.config = config
        self._scores_calculated = 0

    def calculate_confidence(
        self,
        prim: KnowledgePrim,
        validation: ValidationResult,
        source_confidence: float = 0.0,
    ) -> ConfidenceBreakdown:
        """Calculate confidence score for a prim.

        Args:
            prim: The knowledge prim
            validation: Validation result for the prim
            source_confidence: LLM's confidence hint from generation

        Returns:
            ConfidenceBreakdown with detailed scoring
        """
        breakdown = ConfidenceBreakdown(
            prim_path=prim.canonical_path,
            component_weights=CONFIDENCE_WEIGHTS.copy(),
        )

        # Calculate component scores
        components = {
            "hallucination": 1.0 - validation.hallucination_score,
            "consistency": validation.consistency_score,
            "retrieval_accuracy": validation.retrieval_accuracy,
            "source_confidence": source_confidence,
            "heuristics": self._calculate_heuristic_score(prim, validation),
        }
        breakdown.component_scores = components

        # Calculate weighted contributions
        # DETERMINISM: Use fixed order for floating-point accumulation
        # ThinkingMachines [He2025] batch-invariance compliant
        total_weighted = 0.0
        for component in COMPONENT_ORDER:
            score = components.get(component, 0.0)
            weight = CONFIDENCE_WEIGHTS.get(component, 0.0)
            contribution = score * weight
            breakdown.weighted_contributions[component] = contribution
            total_weighted += contribution

        # Apply adjustments in FIXED order (ThinkingMachines [He2025])
        # Compute all adjustments first, then accumulate in deterministic order
        adjustment_values: dict[str, float] = {}

        # Bonus for high quote accuracy
        quote_accuracy = validation.metadata.get("quote_accuracy", 0.0)
        if quote_accuracy > 0.8:
            adjustment_values["high_quote_accuracy"] = 0.05

        # Penalty for validation warnings
        warning_count = len(validation.warnings)
        if warning_count > 3:
            adjustment_values["excess_warnings"] = -0.05 * min(warning_count - 3, 3)

        # Penalty for very short content
        if len(prim.content) < 100:
            adjustment_values["short_content"] = -0.1

        # Bonus for rich metadata
        if len(prim.key_concepts) >= 3 and len(prim.triggers) >= 5:
            adjustment_values["rich_metadata"] = 0.03

        # DETERMINISM: Apply adjustments in fixed alphabetical order
        adjustments = []
        for adj_name in sorted(adjustment_values.keys()):
            adj_value = adjustment_values[adj_name]
            adjustments.append((adj_name, adj_value))
            total_weighted += adj_value

        breakdown.adjustments = adjustments

        # Clamp to valid range
        final_confidence = max(0.0, min(1.0, total_weighted))

        # Apply distilled confidence ceiling
        # Distilled prims should generally not exceed the configured distilled_confidence
        if final_confidence > self.config.distilled_confidence:
            breakdown.notes.append(
                f"Capped from {final_confidence:.2f} to distilled ceiling {self.config.distilled_confidence:.2f}"
            )
            final_confidence = self.config.distilled_confidence

        breakdown.final_confidence = final_confidence
        self._scores_calculated += 1

        logger.debug(
            f"Confidence for {prim.canonical_path}: {final_confidence:.2f}"
        )

        return breakdown

    def _calculate_heuristic_score(
        self,
        prim: KnowledgePrim,
        validation: ValidationResult,
    ) -> float:
        """Calculate heuristic quality score.

        Args:
            prim: The prim
            validation: Validation result

        Returns:
            Heuristic score (0.0-1.0)
        """
        score = 1.0
        deductions = 0

        # Check content length
        if len(prim.content) < 50:
            deductions += 0.3
        elif len(prim.content) < 100:
            deductions += 0.1

        # Check summary quality
        if len(prim.summary) < 20:
            deductions += 0.2

        # Check for key concepts
        if not prim.key_concepts:
            deductions += 0.2
        elif len(prim.key_concepts) < 2:
            deductions += 0.1

        # Check for triggers
        if len(prim.triggers) < 3:
            deductions += 0.15

        # Check domains
        if not prim.domains or prim.domains == ["general"]:
            deductions += 0.1

        # Deduct for each warning
        deductions += len(validation.warnings) * 0.05

        return max(0.0, score - deductions)

    def score_batch(
        self,
        prim_validation_pairs: list[tuple[KnowledgePrim, ValidationResult, float]],
    ) -> list[ConfidenceBreakdown]:
        """Score multiple prims.

        Args:
            prim_validation_pairs: List of (prim, validation, source_confidence) tuples

        Returns:
            List of confidence breakdowns
        """
        breakdowns = []

        for prim, validation, source_conf in prim_validation_pairs:
            breakdown = self.calculate_confidence(prim, validation, source_conf)
            breakdowns.append(breakdown)

        # Log summary
        scores = [b.final_confidence for b in breakdowns]
        if scores:
            avg_score = sum(scores) / len(scores)
            logger.info(
                f"Scored {len(scores)} prims: "
                f"avg={avg_score:.2f}, "
                f"min={min(scores):.2f}, "
                f"max={max(scores):.2f}"
            )

        return breakdowns

    def apply_scores_to_prims(
        self,
        prims: list[KnowledgePrim],
        breakdowns: list[ConfidenceBreakdown],
    ) -> list[KnowledgePrim]:
        """Create new prims with updated confidence scores.

        Args:
            prims: Original prims
            breakdowns: Confidence breakdowns

        Returns:
            New prim list with updated confidence values
        """
        # Build lookup by path
        score_lookup = {b.prim_path: b.final_confidence for b in breakdowns}

        updated = []
        for prim in prims:
            new_confidence = score_lookup.get(prim.canonical_path, prim.confidence)

            updated_prim = KnowledgePrim(
                canonical_path=prim.canonical_path,
                content=prim.content,
                summary=prim.summary,
                confidence=new_confidence,
                provenance=prim.provenance,
                domains=prim.domains,
                triggers=prim.triggers,
                requires=prim.requires,
                enables=prim.enables,
                related_to=prim.related_to,
                teaching_altitude=prim.teaching_altitude,
                key_concepts=prim.key_concepts,
            )
            updated.append(updated_prim)

        return updated

    @property
    def stats(self) -> dict[str, Any]:
        """Get scoring statistics."""
        return {
            "scores_calculated": self._scores_calculated,
        }
