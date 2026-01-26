"""
Self-Consistency Verifier

Multi-sample voting for hallucination detection.
Generates multiple samples at varying temperatures and votes on claim agreement.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
ThinkingMachines [He2025] Frontier AI Enhancement.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .config import DistillationConfig
from .corpus_ingester import DocumentChunk
from .llm_client import BaseLLMClient

logger = logging.getLogger(__name__)


CLAIM_DECOMPOSITION_SYSTEM = """You are a claim extraction expert. Your task is to decompose
a piece of text into atomic, verifiable claims.

An atomic claim is:
1. A single factual statement that can be verified
2. Self-contained (doesn't depend on context)
3. Precise and unambiguous

Output ONLY valid JSON, no other text."""

CLAIM_DECOMPOSITION_PROMPT = """Decompose the following answer into atomic claims.

Answer:
---
{answer}
---

Extract each atomic claim as a separate item. Each claim should be:
- A single verifiable statement
- Self-contained and unambiguous
- Directly stated or clearly implied by the answer

Output as JSON:
{{
  "claims": [
    "claim 1",
    "claim 2",
    ...
  ]
}}"""

CLAIM_VERIFICATION_SYSTEM = """You are a fact-checking expert. For each claim, determine if it
is SUPPORTED by the source document.

Be precise:
- SUPPORTED: The source directly states or clearly implies this claim
- UNSUPPORTED: The source does not contain information to verify this claim
- CONTRADICTED: The source contradicts this claim

Output ONLY valid JSON, no other text."""

CLAIM_VERIFICATION_PROMPT = """Verify these claims against the source document.

Claims to verify:
{claims}

Source Document:
---
{source}
---

For each claim, determine its status:

Output as JSON:
{{
  "verifications": [
    {{"claim": "claim text", "status": "SUPPORTED|UNSUPPORTED|CONTRADICTED", "evidence": "quote from source or null"}}
  ]
}}"""


@dataclass
class ClaimVerification:
    """Verification result for a single claim."""

    claim: str
    status: str  # SUPPORTED, UNSUPPORTED, CONTRADICTED
    evidence: str | None = None
    agreement_ratio: float = 0.0  # Ratio of samples that agree


@dataclass
class ConsistencyResult:
    """Result of self-consistency verification.

    Attributes:
        answer: The answer that was verified
        claims: Decomposed atomic claims
        verifications: Verification results per claim
        consistency_score: Overall consistency (0.0-1.0)
        hallucination_score: Fraction of unsupported claims
        samples_generated: Number of samples used
        metadata: Additional metadata
    """

    answer: str
    claims: list[str] = field(default_factory=list)
    verifications: list[ClaimVerification] = field(default_factory=list)
    consistency_score: float = 0.0
    hallucination_score: float = 1.0
    samples_generated: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "answer": self.answer,
            "claims": self.claims,
            "verifications": [
                {
                    "claim": v.claim,
                    "status": v.status,
                    "evidence": v.evidence,
                    "agreement_ratio": v.agreement_ratio,
                }
                for v in self.verifications
            ],
            "consistency_score": self.consistency_score,
            "hallucination_score": self.hallucination_score,
            "samples_generated": self.samples_generated,
            "metadata": self.metadata,
        }


class SelfConsistencyVerifier:
    """Verifies answer accuracy using multi-sample voting.

    Uses the self-consistency approach:
    1. Generate N answer samples at different temperatures
    2. Decompose each answer into atomic claims
    3. Vote on claim agreement across samples
    4. Generate consensus answer at temp=0 (deterministic)

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

    async def verify(
        self,
        answer: str,
        source_chunk: DocumentChunk,
    ) -> ConsistencyResult:
        """Verify an answer using self-consistency.

        Args:
            answer: The answer to verify
            source_chunk: Source document chunk

        Returns:
            ConsistencyResult with verification details
        """
        result = ConsistencyResult(answer=answer)

        if not self.config.enable_self_consistency:
            # Return neutral result if disabled
            result.consistency_score = 0.5
            result.hallucination_score = 0.5
            return result

        try:
            # Step 1: Decompose answer into atomic claims
            claims = await self._decompose_claims(answer)
            result.claims = claims

            if not claims:
                logger.debug("No claims extracted, skipping verification")
                result.consistency_score = 0.5
                result.hallucination_score = 0.5
                return result

            # Step 2: Generate multiple samples at different temperatures
            samples = await self._generate_samples(source_chunk)
            result.samples_generated = len(samples)

            # Step 3: Decompose each sample into claims
            sample_claims_list = []
            for sample in samples:
                sample_claims = await self._decompose_claims(sample)
                sample_claims_list.append(sample_claims)

            # Step 4: Vote on claim agreement
            verifications = await self._vote_on_claims(
                claims, sample_claims_list, source_chunk
            )
            result.verifications = verifications

            # Step 5: Calculate scores
            result.consistency_score = self._calculate_consistency(verifications)
            result.hallucination_score = self._calculate_hallucination(verifications)

        except Exception as e:
            logger.warning(f"Self-consistency verification failed: {e}")
            result.consistency_score = 0.5
            result.hallucination_score = 0.5
            result.metadata["error"] = str(e)

        return result

    async def _decompose_claims(self, answer: str) -> list[str]:
        """Decompose answer into atomic claims.

        Args:
            answer: Answer to decompose

        Returns:
            List of atomic claims
        """
        prompt = CLAIM_DECOMPOSITION_PROMPT.format(answer=answer[:2000])

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system=CLAIM_DECOMPOSITION_SYSTEM,
                temperature=0.0,  # Deterministic decomposition
            )

            # Parse response
            content = self._extract_json(response.content)
            data = json.loads(content)
            claims = data.get("claims", [])

            return [str(c).strip() for c in claims if c]

        except Exception as e:
            logger.debug(f"Claim decomposition failed: {e}")
            return []

    async def _generate_samples(self, source_chunk: DocumentChunk) -> list[str]:
        """Generate multiple answer samples at different temperatures.

        Args:
            source_chunk: Source document chunk

        Returns:
            List of generated answers
        """
        samples = []
        temperatures = self.config.consistency_temperatures

        # Generate sample at each temperature
        for temp in temperatures[:self.config.consistency_samples]:
            try:
                # Use a general question prompt to generate varied answers
                prompt = f"""Based on this document, provide a comprehensive summary of the key information.

Document:
---
{source_chunk.content[:3000]}
---

Provide a detailed summary covering the main points."""

                response = await self.llm_client.generate(
                    prompt=prompt,
                    temperature=temp,
                )

                samples.append(response.content)

            except Exception as e:
                logger.debug(f"Sample generation at temp={temp} failed: {e}")

        return samples

    async def _vote_on_claims(
        self,
        original_claims: list[str],
        sample_claims_list: list[list[str]],
        source_chunk: DocumentChunk,
    ) -> list[ClaimVerification]:
        """Vote on claim agreement across samples.

        Args:
            original_claims: Claims from original answer
            sample_claims_list: Claims from each sample
            source_chunk: Source document

        Returns:
            List of claim verifications
        """
        verifications = []

        for claim in original_claims:
            # Count how many samples contain similar claim
            agreement_count = 0
            for sample_claims in sample_claims_list:
                if self._claim_matches(claim, sample_claims):
                    agreement_count += 1

            agreement_ratio = agreement_count / len(sample_claims_list) if sample_claims_list else 0

            # Verify against source
            status, evidence = await self._verify_claim(claim, source_chunk)

            verifications.append(
                ClaimVerification(
                    claim=claim,
                    status=status,
                    evidence=evidence,
                    agreement_ratio=agreement_ratio,
                )
            )

        return verifications

    def _claim_matches(self, claim: str, sample_claims: list[str]) -> bool:
        """Check if a claim matches any claim in a sample.

        Uses fuzzy matching to handle paraphrasing.

        Args:
            claim: Claim to match
            sample_claims: Claims from a sample

        Returns:
            True if claim matches any sample claim
        """
        claim_words = set(claim.lower().split())

        for sample_claim in sample_claims:
            sample_words = set(sample_claim.lower().split())

            # Calculate word overlap
            if not claim_words:
                continue

            overlap = len(claim_words & sample_words) / len(claim_words)
            if overlap > 0.6:  # 60% word overlap threshold
                return True

        return False

    async def _verify_claim(
        self,
        claim: str,
        source_chunk: DocumentChunk,
    ) -> tuple[str, str | None]:
        """Verify a single claim against the source.

        Args:
            claim: Claim to verify
            source_chunk: Source document

        Returns:
            Tuple of (status, evidence)
        """
        prompt = CLAIM_VERIFICATION_PROMPT.format(
            claims=json.dumps([claim]),
            source=source_chunk.content[:3000],
        )

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system=CLAIM_VERIFICATION_SYSTEM,
                temperature=0.0,
            )

            content = self._extract_json(response.content)
            data = json.loads(content)
            verifications = data.get("verifications", [])

            if verifications:
                v = verifications[0]
                return v.get("status", "UNSUPPORTED"), v.get("evidence")

        except Exception as e:
            logger.debug(f"Claim verification failed: {e}")

        return "UNSUPPORTED", None

    def _calculate_consistency(self, verifications: list[ClaimVerification]) -> float:
        """Calculate overall consistency score.

        Args:
            verifications: Claim verifications

        Returns:
            Consistency score (0.0-1.0)
        """
        if not verifications:
            return 0.5

        # Weight by agreement ratio and verification status
        total_score = 0.0
        for v in verifications:
            status_weight = {
                "SUPPORTED": 1.0,
                "UNSUPPORTED": 0.3,
                "CONTRADICTED": 0.0,
            }.get(v.status, 0.3)

            # Combine status with agreement
            claim_score = status_weight * (0.5 + 0.5 * v.agreement_ratio)
            total_score += claim_score

        return total_score / len(verifications)

    def _calculate_hallucination(self, verifications: list[ClaimVerification]) -> float:
        """Calculate hallucination score.

        Args:
            verifications: Claim verifications

        Returns:
            Hallucination score (0.0=none, 1.0=all)
        """
        if not verifications:
            return 0.5

        unsupported = sum(
            1 for v in verifications
            if v.status in ("UNSUPPORTED", "CONTRADICTED")
        )

        return unsupported / len(verifications)

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
