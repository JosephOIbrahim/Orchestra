"""
Entailment Grounder

NLI-based claim verification using LLM as entailment judge.
Grounds generated content against source documents.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
ThinkingMachines [He2025] Frontier AI Enhancement.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .config import DistillationConfig
from .llm_client import BaseLLMClient

logger = logging.getLogger(__name__)


class EntailmentVerdict(Enum):
    """NLI entailment verdicts."""

    ENTAILED = "entailed"  # Source supports claim
    NEUTRAL = "neutral"  # Source neither supports nor contradicts
    CONTRADICTED = "contradicted"  # Source contradicts claim


CLAIM_EXTRACTION_SYSTEM = """You are a claim extraction expert. Extract atomic claims from the
given content. An atomic claim is a single, verifiable statement.

Output ONLY valid JSON, no other text."""

CLAIM_EXTRACTION_PROMPT = """Extract atomic claims from this content.

Content:
---
{content}
---

Extract each distinct factual claim as a separate item.

Output as JSON:
{{
  "claims": [
    "claim 1",
    "claim 2",
    ...
  ]
}}"""

ENTAILMENT_SYSTEM = """You are an NLI (Natural Language Inference) expert. Your task is to determine
the entailment relationship between a premise (source document) and a hypothesis (claim).

Verdicts:
- ENTAILED: The premise clearly supports or implies the hypothesis
- NEUTRAL: The premise neither supports nor contradicts the hypothesis
- CONTRADICTED: The premise contradicts or is inconsistent with the hypothesis

Be precise and conservative. Only mark as ENTAILED if the premise clearly supports the claim.

Output ONLY valid JSON, no other text."""

ENTAILMENT_PROMPT = """Determine the entailment relationship.

Premise (Source Document):
---
{premise}
---

Hypothesis (Claim to verify):
---
{hypothesis}
---

Analyze whether the premise ENTAILS, is NEUTRAL to, or CONTRADICTS the hypothesis.

Output as JSON:
{{
  "verdict": "ENTAILED|NEUTRAL|CONTRADICTED",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation",
  "supporting_evidence": "Quote from premise if ENTAILED, null otherwise"
}}"""


@dataclass
class ClaimGrounding:
    """Grounding result for a single claim."""

    claim: str
    verdict: EntailmentVerdict
    confidence: float = 0.0
    reasoning: str = ""
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "claim": self.claim,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "evidence": self.evidence,
        }


@dataclass
class GroundingResult:
    """Result of entailment grounding.

    Attributes:
        content: The content that was grounded
        source: The source document
        claims: Extracted claims
        groundings: Grounding result per claim
        grounding_score: Overall grounding score (0.0-1.0)
        hallucination_score: Fraction of ungrounded claims
        metadata: Additional metadata
    """

    content: str
    source: str
    claims: list[str] = field(default_factory=list)
    groundings: list[ClaimGrounding] = field(default_factory=list)
    grounding_score: float = 0.0
    hallucination_score: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "claims": self.claims,
            "groundings": [g.to_dict() for g in self.groundings],
            "grounding_score": self.grounding_score,
            "hallucination_score": self.hallucination_score,
            "metadata": self.metadata,
        }

    @property
    def entailed_claims(self) -> list[str]:
        """Get claims that are entailed."""
        return [g.claim for g in self.groundings if g.verdict == EntailmentVerdict.ENTAILED]

    @property
    def neutral_claims(self) -> list[str]:
        """Get claims that are neutral."""
        return [g.claim for g in self.groundings if g.verdict == EntailmentVerdict.NEUTRAL]

    @property
    def contradicted_claims(self) -> list[str]:
        """Get claims that are contradicted."""
        return [g.claim for g in self.groundings if g.verdict == EntailmentVerdict.CONTRADICTED]


class EntailmentGrounder:
    """Grounds generated content using NLI-based verification.

    Uses LLM as an entailment judge to verify each claim in
    generated content against the source document.

    Attributes:
        config: Distillation configuration
        llm_client: LLM client for generation
    """

    def __init__(
        self,
        config: DistillationConfig,
        llm_client: BaseLLMClient,
    ) -> None:
        self.config = config
        self.llm_client = llm_client

    async def ground(
        self,
        content: str,
        source: str,
    ) -> GroundingResult:
        """Ground content against source using entailment.

        Args:
            content: Generated content to verify
            source: Source document to ground against

        Returns:
            GroundingResult with verification details
        """
        result = GroundingResult(content=content, source=source)

        if not self.config.enable_entailment_grounding:
            # Return neutral result if disabled
            result.grounding_score = 0.5
            result.hallucination_score = 0.5
            return result

        try:
            # Step 1: Extract atomic claims from content
            claims = await self._extract_claims(content)
            result.claims = claims

            if not claims:
                logger.debug("No claims extracted, skipping grounding")
                result.grounding_score = 0.5
                result.hallucination_score = 0.5
                return result

            # Step 2: Ground each claim against source
            groundings = []
            for claim in claims:
                grounding = await self._ground_claim(claim, source)
                groundings.append(grounding)

            result.groundings = groundings

            # Step 3: Calculate scores
            result.grounding_score = self._calculate_grounding_score(groundings)
            result.hallucination_score = self._calculate_hallucination_score(groundings)

        except Exception as e:
            logger.warning(f"Entailment grounding failed: {e}")
            result.grounding_score = 0.5
            result.hallucination_score = 0.5
            result.metadata["error"] = str(e)

        return result

    async def _extract_claims(self, content: str) -> list[str]:
        """Extract atomic claims from content.

        Args:
            content: Content to extract claims from

        Returns:
            List of atomic claims
        """
        prompt = CLAIM_EXTRACTION_PROMPT.format(content=content[:2000])

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system=CLAIM_EXTRACTION_SYSTEM,
                temperature=0.0,
            )

            json_content = self._extract_json(response.content)
            data = json.loads(json_content)
            claims = data.get("claims", [])

            return [str(c).strip() for c in claims if c]

        except Exception as e:
            logger.debug(f"Claim extraction failed: {e}")
            return []

    async def _ground_claim(
        self,
        claim: str,
        source: str,
    ) -> ClaimGrounding:
        """Ground a single claim against source.

        Args:
            claim: Claim to ground
            source: Source document

        Returns:
            ClaimGrounding result
        """
        prompt = ENTAILMENT_PROMPT.format(
            premise=source[:3000],
            hypothesis=claim,
        )

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system=ENTAILMENT_SYSTEM,
                temperature=0.0,
            )

            json_content = self._extract_json(response.content)
            data = json.loads(json_content)

            verdict_str = data.get("verdict", "NEUTRAL").upper()
            verdict = EntailmentVerdict(verdict_str.lower())

            return ClaimGrounding(
                claim=claim,
                verdict=verdict,
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
                evidence=data.get("supporting_evidence"),
            )

        except Exception as e:
            logger.debug(f"Claim grounding failed: {e}")
            return ClaimGrounding(
                claim=claim,
                verdict=EntailmentVerdict.NEUTRAL,
                confidence=0.0,
                reasoning=f"Grounding failed: {e}",
            )

    def _calculate_grounding_score(self, groundings: list[ClaimGrounding]) -> float:
        """Calculate overall grounding score.

        Args:
            groundings: Claim groundings

        Returns:
            Grounding score (0.0-1.0)
        """
        if not groundings:
            return 0.5

        total_score = 0.0
        for g in groundings:
            if g.verdict == EntailmentVerdict.ENTAILED:
                total_score += g.confidence
            elif g.verdict == EntailmentVerdict.NEUTRAL:
                # Neutral can be configured to count as partial or no grounding
                if self.config.neutral_counts_as_hallucination:
                    total_score += 0.0
                else:
                    total_score += 0.5 * g.confidence
            else:  # CONTRADICTED
                total_score += 0.0

        return total_score / len(groundings)

    def _calculate_hallucination_score(self, groundings: list[ClaimGrounding]) -> float:
        """Calculate hallucination score.

        Args:
            groundings: Claim groundings

        Returns:
            Hallucination score (0.0=none, 1.0=all)
        """
        if not groundings:
            return 0.5

        ungrounded = 0
        for g in groundings:
            if g.verdict == EntailmentVerdict.CONTRADICTED:
                ungrounded += 1
            elif g.verdict == EntailmentVerdict.NEUTRAL:
                if self.config.neutral_counts_as_hallucination:
                    ungrounded += 1
                else:
                    ungrounded += 0.5  # Partial

        return ungrounded / len(groundings)

    def _extract_json(self, content: str) -> str:
        """Extract JSON from response content."""
        content = content.strip()

        # Handle markdown code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            return json_match.group(1)

        # Try to find JSON object
        if not content.startswith("{"):
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return content[json_start:json_end]

        return content


async def ground_content(
    content: str,
    source: str,
    config: DistillationConfig,
    llm_client: BaseLLMClient,
) -> GroundingResult:
    """Convenience function for entailment grounding.

    Args:
        content: Content to ground
        source: Source document
        config: Distillation configuration
        llm_client: LLM client

    Returns:
        GroundingResult
    """
    grounder = EntailmentGrounder(config, llm_client)
    return await grounder.ground(content, source)
