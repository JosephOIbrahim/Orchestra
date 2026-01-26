"""
Prim Extractor

Converts generated answers into KnowledgePrim objects.
Handles path generation, domain inference, and schema mapping.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..schemas import KnowledgePrim
from .answer_generator import GeneratedAnswer
from .config import DistillationConfig
from .query_generator import QuestionType

logger = logging.getLogger(__name__)


# Mapping from question types to teaching altitudes
ALTITUDE_MAP = {
    QuestionType.FACTUAL: "Ground",
    QuestionType.DEFINITIONAL: "Ground",
    QuestionType.PROCEDURAL: "Component",
    QuestionType.CONCEPTUAL: "Architecture",
    QuestionType.COMPARATIVE: "Architecture",
}

# Domain inference patterns
DOMAIN_PATTERNS = {
    "usd": [r"\busd\b", r"\bpxr\b", r"\bprim\b", r"\bstage\b", r"\blayer\b", r"\bcomposition\b"],
    "houdini": [r"\bhoudini\b", r"\blops\b", r"\bsops\b", r"\bvex\b", r"\bhda\b"],
    "karma": [r"\bkarma\b", r"\bxpu\b", r"\bmaterialx\b", r"\baov\b"],
    "nuke": [r"\bnuke\b", r"\bcompositing\b", r"\bdeep\b"],
    "pipeline": [r"\bpipeline\b", r"\bocio\b", r"\bversioning\b", r"\basset\b"],
    "python": [r"\bpython\b", r"\bdef\s+\w+\b", r"\bclass\s+\w+\b", r"\bimport\s+\w+\b"],
    "cognitive": [r"\bcognitive\b", r"\bsubstrate\b", r"\bprism\b", r"\bnexus\b"],
}


@dataclass
class ExtractionResult:
    """Result of prim extraction.

    Attributes:
        prim: The extracted KnowledgePrim
        answer: Source GeneratedAnswer
        extraction_notes: Notes about the extraction process
        warnings: Any warnings generated during extraction
    """
    prim: KnowledgePrim
    answer: GeneratedAnswer
    extraction_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "prim": self.prim.to_dict(),
            "extraction_notes": self.extraction_notes,
            "warnings": self.warnings,
        }


class PrimExtractor:
    """Extracts KnowledgePrim objects from generated answers.

    Attributes:
        config: Distillation configuration
    """

    def __init__(self, config: DistillationConfig) -> None:
        self.config = config
        self._prims_extracted = 0
        self._extraction_warnings = 0

    def extract(self, answer: GeneratedAnswer) -> ExtractionResult:
        """Extract a KnowledgePrim from a GeneratedAnswer.

        Args:
            answer: The generated answer to convert

        Returns:
            ExtractionResult containing the prim and metadata
        """
        notes = []
        warnings = []

        # Generate canonical path
        path = self._generate_path(answer)
        notes.append(f"Generated path: {path}")

        # Infer domains
        domains = self._infer_domains(answer)
        if not domains:
            domains = ["general"]
            warnings.append("No domain patterns matched, using 'general'")
        notes.append(f"Inferred domains: {domains}")

        # Determine teaching altitude
        altitude = self._determine_altitude(answer)

        # Build triggers (will be enhanced by TriggerGenerator later)
        triggers = self._extract_initial_triggers(answer)

        # Extract related concepts for relationship building
        requires, enables, related_to = self._extract_relationships(answer)

        # Build the prim
        prim = KnowledgePrim(
            canonical_path=path,
            content=answer.answer,
            summary=answer.summary,
            confidence=self.config.distilled_confidence,
            provenance=self._build_provenance(answer),
            domains=domains,
            triggers=triggers,
            requires=requires,
            enables=enables,
            related_to=related_to,
            teaching_altitude=altitude,
            key_concepts=answer.key_concepts,
        )

        self._prims_extracted += 1
        if warnings:
            self._extraction_warnings += len(warnings)

        logger.debug(f"Extracted prim: {path}")

        return ExtractionResult(
            prim=prim,
            answer=answer,
            extraction_notes=notes,
            warnings=warnings,
        )

    def _generate_path(self, answer: GeneratedAnswer) -> str:
        """Generate a USD-style canonical path for the prim.

        Args:
            answer: The generated answer

        Returns:
            Canonical path like /Knowledge/Domain/Concept
        """
        # Start with base path
        base = "/Knowledge"

        # Infer domain for path
        domains = self._infer_domains(answer)
        domain = domains[0].upper() if domains else "General"

        # Generate concept name from question
        question = answer.query.question if answer.query else "Unknown"
        concept = self._question_to_concept_name(question)

        # Ensure uniqueness with content-addressable hash suffix
        # Uses 12-char SHA-256 for collision resistance (ThinkingMachines [He2025])
        unique_suffix = hashlib.sha256(
            f"{question}:{answer.summary}:{answer.answer[:200]}".encode()
        ).hexdigest()[:12]

        return f"{base}/{domain}/{concept}_{unique_suffix}"

    def _question_to_concept_name(self, question: str) -> str:
        """Convert a question to a valid concept name.

        Args:
            question: The question text

        Returns:
            CamelCase concept name
        """
        # Remove question words and punctuation
        text = re.sub(r"^(what|how|why|when|where|which|is|are|does|do|can)\s+", "", question.lower())
        text = re.sub(r"[^a-z0-9\s]", "", text)

        # Take first few significant words
        words = text.split()[:4]

        # Convert to CamelCase
        if not words:
            return "Unknown"

        return "".join(word.capitalize() for word in words if word)

    def _infer_domains(self, answer: GeneratedAnswer) -> list[str]:
        """Infer domains from answer content.

        Args:
            answer: The generated answer

        Returns:
            List of inferred domain names
        """
        # Combine relevant text for matching
        text = " ".join([
            answer.answer.lower(),
            answer.summary.lower(),
            " ".join(answer.key_concepts).lower(),
        ])

        # Check for source path hints
        if answer.source_chunk:
            source_path = str(answer.source_chunk.source_path).lower()
            text += " " + source_path

        domains = []
        for domain, patterns in DOMAIN_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    if domain not in domains:
                        domains.append(domain)
                    break

        return domains

    def _determine_altitude(self, answer: GeneratedAnswer) -> str:
        """Determine teaching altitude based on question type.

        Args:
            answer: The generated answer

        Returns:
            Teaching altitude (Ground/Component/Architecture/Vision)
        """
        if answer.query:
            return ALTITUDE_MAP.get(answer.query.question_type, "Ground")

        # Infer from abstraction level hint
        if answer.query and answer.query.abstraction_level:
            level_map = {
                "ground": "Ground",
                "component": "Component",
                "architecture": "Architecture",
                "vision": "Vision",
            }
            return level_map.get(answer.query.abstraction_level, "Ground")

        return "Ground"

    def _extract_initial_triggers(self, answer: GeneratedAnswer) -> list[str]:
        """Extract initial trigger words from answer.

        Args:
            answer: The generated answer

        Returns:
            List of trigger words/phrases

        Note:
            This produces basic triggers; TriggerGenerator will enhance them.
        """
        triggers = []

        # Add key concepts as triggers
        triggers.extend(answer.key_concepts)

        # Extract question keywords
        if answer.query:
            question = answer.query.question.lower()
            question = re.sub(r"^(what|how|why|when|where|which|is|are|does|do|can)\s+", "", question)
            question = re.sub(r"[^a-z0-9\s]", "", question)
            words = question.split()
            # Add multi-word phrases and significant single words
            for word in words:
                if len(word) > 3 and word not in triggers:
                    triggers.append(word)

        # Deduplicate and limit
        triggers = list(dict.fromkeys(triggers))[:10]

        return triggers

    def _extract_relationships(
        self, answer: GeneratedAnswer
    ) -> tuple[list[str], list[str], list[str]]:
        """Extract relationship hints from answer.

        Args:
            answer: The generated answer

        Returns:
            Tuple of (requires, enables, related_to) path lists
        """
        # For now, return empty lists - relationships require cross-prim analysis
        # Future enhancement: use LLM to identify prerequisite/followup concepts
        return [], [], []

    def _build_provenance(self, answer: GeneratedAnswer) -> str:
        """Build provenance string for the prim.

        Args:
            answer: The generated answer

        Returns:
            Provenance string
        """
        parts = ["distilled"]

        if answer.source_chunk:
            source = Path(answer.source_chunk.source_path).stem
            parts.append(source)

        parts.append(self.config.model_name.split("-")[0])

        return "_".join(parts)

    def extract_batch(
        self, answers: list[GeneratedAnswer]
    ) -> list[ExtractionResult]:
        """Extract prims from multiple answers.

        Args:
            answers: List of generated answers

        Returns:
            List of extraction results
        """
        results = []

        for answer in answers:
            result = self.extract(answer)
            results.append(result)

        logger.info(
            f"Extracted {len(results)} prims, "
            f"{self._extraction_warnings} warnings"
        )

        return results

    @property
    def stats(self) -> dict[str, Any]:
        """Get extraction statistics."""
        return {
            "prims_extracted": self._prims_extracted,
            "extraction_warnings": self._extraction_warnings,
        }
