"""
Answer Generator

Generates answers to questions using LLM with reasoning traces.
Produces structured responses that can be validated and converted to prims.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .config import DistillationConfig
from .corpus_ingester import DocumentChunk
from .llm_client import BaseLLMClient, LLMResponse
from .query_generator import GeneratedQuery
from .response_schemas import parse_answer_response

logger = logging.getLogger(__name__)


@dataclass
class GeneratedAnswer:
    """An answer generated for a query.

    Attributes:
        answer: The answer text
        summary: Brief summary (for quick display)
        reasoning: Reasoning trace showing how answer was derived
        key_concepts: Main concepts covered in the answer
        source_quotes: Direct quotes from source that support the answer
        query: The original query
        source_chunk: The source document chunk
        confidence_hint: LLM's self-assessed confidence (0.0-1.0)
        metadata: Additional generation metadata
    """
    answer: str
    summary: str
    reasoning: str = ""
    key_concepts: list[str] = field(default_factory=list)
    source_quotes: list[str] = field(default_factory=list)
    query: GeneratedQuery | None = None
    source_chunk: DocumentChunk | None = None
    confidence_hint: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "answer": self.answer,
            "summary": self.summary,
            "reasoning": self.reasoning,
            "key_concepts": self.key_concepts,
            "source_quotes": self.source_quotes,
            "query": self.query.to_dict() if self.query else None,
            "source_chunk_id": self.source_chunk.chunk_id if self.source_chunk else None,
            "confidence_hint": self.confidence_hint,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GeneratedAnswer:
        """Create from dictionary."""
        return cls(
            answer=data.get("answer", ""),
            summary=data.get("summary", ""),
            reasoning=data.get("reasoning", ""),
            key_concepts=data.get("key_concepts", []),
            source_quotes=data.get("source_quotes", []),
            confidence_hint=data.get("confidence_hint", 0.0),
            metadata=data.get("metadata", {}),
        )


ANSWER_GENERATION_SYSTEM = """You are a knowledge extraction expert. Your task is to answer questions
based STRICTLY on the provided documentation. You must:

1. Answer ONLY from the provided source - no external knowledge
2. Include direct quotes from the source that support your answer
3. Provide a reasoning trace showing how you derived the answer
4. Identify key concepts covered
5. Give a confidence score based on how well the source supports the answer

If the source does not contain enough information to fully answer the question,
acknowledge this and only provide what can be answered from the source.

Output ONLY valid JSON, no other text."""

ANSWER_GENERATION_PROMPT = """Answer this question based STRICTLY on the provided documentation.

Question: {question}

Documentation:
---
{content}
---

Provide your answer in this JSON format:
{{
  "answer": "Complete, detailed answer derived from the source",
  "summary": "One sentence summary (max 150 chars)",
  "reasoning": "Step-by-step reasoning showing how you derived the answer from the source",
  "key_concepts": ["concept1", "concept2", "concept3"],
  "source_quotes": ["Exact quote 1 from source", "Exact quote 2 from source"],
  "confidence": 0.0-1.0
}}

Guidelines:
- confidence: 1.0 = answer fully supported, 0.5 = partially supported, 0.0 = not supported
- source_quotes: Include 1-3 EXACT quotes (verbatim) from the documentation
- reasoning: Explain how the quotes lead to your answer
- If information is missing, reduce confidence and note in reasoning"""


class AnswerGenerator:
    """Generates answers for queries using LLM.

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
        self._answers_generated = 0
        self._generation_errors = 0

    async def generate_answer(
        self,
        query: GeneratedQuery,
        chunk: DocumentChunk,
    ) -> GeneratedAnswer | None:
        """Generate an answer for a query from a document chunk.

        Args:
            query: The question to answer
            chunk: Source document chunk

        Returns:
            Generated answer or None if generation failed
        """
        prompt = ANSWER_GENERATION_PROMPT.format(
            question=query.question,
            content=chunk.content,
        )

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system=ANSWER_GENERATION_SYSTEM,
            )

            answer = self._parse_response(response, query, chunk)

            if answer:
                self._answers_generated += 1
                logger.debug(
                    f"Generated answer for query (confidence: {answer.confidence_hint:.2f})"
                )

            return answer

        except Exception as e:
            self._generation_errors += 1
            logger.warning(f"Answer generation failed: {e}")
            return None

    def _parse_response(
        self,
        response: LLMResponse,
        query: GeneratedQuery,
        chunk: DocumentChunk,
    ) -> GeneratedAnswer | None:
        """Parse LLM response into GeneratedAnswer.

        Uses Pydantic schemas for robust parsing with coercion.
        Production Hardening: Handles string confidence values like "high".

        Args:
            response: LLM response
            query: Original query
            chunk: Source document chunk

        Returns:
            Parsed answer or None if parsing failed
        """
        # Use Pydantic-based parsing with automatic coercion
        parsed = parse_answer_response(response.content)

        if parsed is None:
            logger.warning("Failed to parse answer response")
            return None

        return GeneratedAnswer(
            answer=parsed.answer,
            summary=parsed.summary,
            reasoning=parsed.reasoning,
            key_concepts=parsed.key_concepts,
            source_quotes=parsed.source_quotes,
            query=query,
            source_chunk=chunk,
            confidence_hint=parsed.confidence,
            metadata={
                "llm_latency_ms": response.latency_ms,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            },
        )

    async def generate_batch(
        self,
        query_chunk_pairs: list[tuple[GeneratedQuery, DocumentChunk]],
    ) -> list[GeneratedAnswer]:
        """Generate answers for multiple query-chunk pairs.

        Args:
            query_chunk_pairs: List of (query, chunk) tuples

        Returns:
            List of generated answers (excludes failures)
        """
        answers = []

        for i, (query, chunk) in enumerate(query_chunk_pairs):
            answer = await self.generate_answer(query, chunk)
            if answer:
                answers.append(answer)

            if (i + 1) % 10 == 0:
                logger.info(
                    f"Progress: {i + 1}/{len(query_chunk_pairs)} answers, "
                    f"{len(answers)} successful"
                )

        return answers

    @property
    def stats(self) -> dict[str, Any]:
        """Get generation statistics."""
        total = self._answers_generated + self._generation_errors
        return {
            "answers_generated": self._answers_generated,
            "generation_errors": self._generation_errors,
            "success_rate": (
                self._answers_generated / total if total > 0 else 0.0
            ),
        }
