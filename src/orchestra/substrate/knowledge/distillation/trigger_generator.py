"""
Trigger Generator

Auto-generates search triggers for KnowledgePrims using TF-IDF and LLM.
Ensures prims are discoverable via diverse query patterns.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..schemas import KnowledgePrim
from .config import DistillationConfig
from .llm_client import BaseLLMClient
from .response_schemas import parse_trigger_response

logger = logging.getLogger(__name__)


# Common stop words to filter out
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "up",
    "about", "into", "through", "during", "before", "after", "above",
    "below", "between", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "just", "and",
    "but", "if", "or", "because", "as", "until", "while", "this", "that",
    "these", "those", "what", "which", "who", "whom", "it", "its", "you",
    "your", "he", "she", "they", "them", "we", "us", "i", "my", "me",
}


@dataclass
class TriggerSet:
    """A set of triggers for a prim.

    Attributes:
        prim_path: Path to the prim
        tfidf_triggers: Triggers from TF-IDF analysis
        llm_triggers: Triggers from LLM enhancement
        combined_triggers: Final merged trigger list
        scores: Relevance scores for each trigger
    """
    prim_path: str
    tfidf_triggers: list[str] = field(default_factory=list)
    llm_triggers: list[str] = field(default_factory=list)
    combined_triggers: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "prim_path": self.prim_path,
            "tfidf_triggers": self.tfidf_triggers,
            "llm_triggers": self.llm_triggers,
            "combined_triggers": self.combined_triggers,
            "scores": self.scores,
        }


class TriggerGenerator:
    """Generates search triggers for KnowledgePrims.

    Uses a hybrid approach:
    1. TF-IDF for statistically significant terms
    2. LLM for semantic synonym/variant generation

    Attributes:
        config: Distillation configuration
        llm_client: Optional LLM client for enhancement
    """

    def __init__(
        self,
        config: DistillationConfig,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.config = config
        self.llm_client = llm_client
        self._corpus_term_counts: Counter = Counter()
        self._document_count = 0

    def build_corpus_stats(self, prims: list[KnowledgePrim]) -> None:
        """Build corpus-level statistics for TF-IDF.

        Args:
            prims: All prims in the corpus
        """
        self._document_count = len(prims)

        for prim in prims:
            # Count unique terms per document
            # DETERMINISM: sorted() ensures consistent iteration order
            # ThinkingMachines [He2025] batch-invariance compliant
            terms = self._extract_terms(prim.content + " " + prim.summary)
            unique_terms = sorted(set(terms))
            for term in unique_terms:
                self._corpus_term_counts[term] += 1

        logger.info(
            f"Built corpus stats: {self._document_count} docs, "
            f"{len(self._corpus_term_counts)} unique terms"
        )

    def _extract_terms(self, text: str) -> list[str]:
        """Extract terms from text.

        Args:
            text: Input text

        Returns:
            List of normalized terms
        """
        # Lowercase and split on non-word characters
        text = text.lower()
        words = re.findall(r"\b[a-z][a-z0-9_]+\b", text)

        # Filter stop words and very short words
        terms = [w for w in words if w not in STOP_WORDS and len(w) > 2]

        return terms

    def _calculate_tfidf(
        self, term: str, term_freq: int, doc_length: int
    ) -> float:
        """Calculate TF-IDF score for a term.

        Args:
            term: The term
            term_freq: Frequency in document
            doc_length: Total terms in document

        Returns:
            TF-IDF score
        """
        if self._document_count == 0:
            return 0.0

        # Term frequency (normalized)
        tf = term_freq / doc_length if doc_length > 0 else 0

        # Inverse document frequency
        doc_freq = self._corpus_term_counts.get(term, 1)
        idf = math.log(self._document_count / doc_freq) + 1

        return tf * idf

    def generate_tfidf_triggers(
        self, prim: KnowledgePrim, max_triggers: int = 15
    ) -> list[tuple[str, float]]:
        """Generate triggers using TF-IDF scoring.

        Args:
            prim: The knowledge prim
            max_triggers: Maximum number of triggers

        Returns:
            List of (term, score) tuples
        """
        text = prim.content + " " + prim.summary + " " + " ".join(prim.key_concepts)
        terms = self._extract_terms(text)
        term_counts = Counter(terms)
        doc_length = len(terms)

        scored_terms = []
        for term, count in term_counts.items():
            score = self._calculate_tfidf(term, count, doc_length)
            scored_terms.append((term, score))

        # Sort by score and take top N
        scored_terms.sort(key=lambda x: x[1], reverse=True)

        return scored_terms[:max_triggers]

    async def generate_llm_triggers(
        self, prim: KnowledgePrim, max_triggers: int = 10
    ) -> list[str]:
        """Generate additional triggers using LLM.

        Uses Pydantic schemas for robust parsing.
        Production Hardening: Handles malformed array responses.

        Args:
            prim: The knowledge prim
            max_triggers: Maximum number of triggers

        Returns:
            List of trigger terms/phrases
        """
        if not self.llm_client:
            return []

        prompt = f"""Given this knowledge content, generate search trigger terms and phrases
that someone might use to find this information.

Content summary: {prim.summary}

Key concepts: {", ".join(prim.key_concepts)}

Existing triggers: {", ".join(prim.triggers[:5])}

Generate {max_triggers} additional search terms/phrases that:
1. Are synonyms or variants of key terms
2. Are common ways to ask about this topic
3. Include abbreviations, acronyms, or alternate names
4. Are phrases someone might search for

Output as JSON array of strings only:
["term1", "term2", ...]"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system="Generate search triggers as a JSON array. Output only valid JSON.",
                max_tokens=500,
            )

            # Use Pydantic-based parsing
            triggers = parse_trigger_response(response.content)
            return triggers[:max_triggers]

        except Exception as e:
            logger.debug(f"LLM trigger generation failed: {e}")

        return []

    async def generate_triggers(
        self, prim: KnowledgePrim
    ) -> TriggerSet:
        """Generate complete trigger set for a prim.

        Args:
            prim: The knowledge prim

        Returns:
            TriggerSet with all triggers
        """
        # Get TF-IDF triggers
        tfidf_results = self.generate_tfidf_triggers(prim)
        tfidf_triggers = [term for term, _ in tfidf_results]
        scores = {term: score for term, score in tfidf_results}

        # Get LLM triggers if available
        llm_triggers = []
        if self.llm_client:
            llm_triggers = await self.generate_llm_triggers(prim)

        # Combine and deduplicate
        combined = []
        seen = set()

        # Start with existing triggers
        for t in prim.triggers:
            t_lower = t.lower()
            if t_lower not in seen:
                combined.append(t_lower)
                seen.add(t_lower)

        # Add TF-IDF triggers
        for t in tfidf_triggers:
            if t not in seen:
                combined.append(t)
                seen.add(t)

        # Add LLM triggers
        for t in llm_triggers:
            if t not in seen:
                combined.append(t)
                seen.add(t)

        return TriggerSet(
            prim_path=prim.canonical_path,
            tfidf_triggers=tfidf_triggers,
            llm_triggers=llm_triggers,
            combined_triggers=combined[:25],  # Cap at 25 triggers
            scores=scores,
        )

    async def enhance_prims(
        self, prims: list[KnowledgePrim]
    ) -> list[KnowledgePrim]:
        """Enhance prims with generated triggers.

        Args:
            prims: List of prims to enhance

        Returns:
            List of prims with updated triggers
        """
        # Build corpus stats first
        self.build_corpus_stats(prims)

        enhanced = []
        for i, prim in enumerate(prims):
            trigger_set = await self.generate_triggers(prim)

            # Create new prim with enhanced triggers
            enhanced_prim = KnowledgePrim(
                canonical_path=prim.canonical_path,
                content=prim.content,
                summary=prim.summary,
                confidence=prim.confidence,
                provenance=prim.provenance,
                domains=prim.domains,
                triggers=trigger_set.combined_triggers,
                requires=prim.requires,
                enables=prim.enables,
                related_to=prim.related_to,
                teaching_altitude=prim.teaching_altitude,
                key_concepts=prim.key_concepts,
            )
            enhanced.append(enhanced_prim)

            if (i + 1) % 10 == 0:
                logger.info(f"Enhanced {i + 1}/{len(prims)} prims with triggers")

        return enhanced
