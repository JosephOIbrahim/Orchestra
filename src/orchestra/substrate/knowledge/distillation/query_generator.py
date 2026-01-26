"""
Query Generator

Generates questions from document chunks using LLM.
Creates diverse question types (factual, conceptual, procedural).

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .config import DistillationConfig
from .corpus_ingester import DocumentChunk
from .llm_client import BaseLLMClient, LLMResponse
from .response_schemas import parse_query_response

logger = logging.getLogger(__name__)


class QuestionType(Enum):
    """Types of questions for different knowledge aspects."""
    FACTUAL = "factual"          # "What is X?"
    CONCEPTUAL = "conceptual"    # "How does X relate to Y?"
    PROCEDURAL = "procedural"    # "How do you X?"
    DEFINITIONAL = "definitional"  # "Define X"
    COMPARATIVE = "comparative"  # "What's the difference between X and Y?"


@dataclass
class GeneratedQuery:
    """A question generated from a document chunk.

    Attributes:
        question: The question text
        question_type: Type of question
        source_chunk_id: ID of the source chunk
        abstraction_level: How abstract the question is (ground/component/architecture/vision)
        expected_concepts: Concepts the answer should cover
        metadata: Additional generation metadata
    """
    question: str
    question_type: QuestionType = QuestionType.FACTUAL
    source_chunk_id: str = ""
    abstraction_level: str = "ground"
    expected_concepts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "question": self.question,
            "question_type": self.question_type.value,
            "source_chunk_id": self.source_chunk_id,
            "abstraction_level": self.abstraction_level,
            "expected_concepts": self.expected_concepts,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GeneratedQuery:
        """Create from dictionary."""
        return cls(
            question=data.get("question", ""),
            question_type=QuestionType(data.get("question_type", "factual")),
            source_chunk_id=data.get("source_chunk_id", ""),
            abstraction_level=data.get("abstraction_level", "ground"),
            expected_concepts=data.get("expected_concepts", []),
            metadata=data.get("metadata", {}),
        )


QUERY_GENERATION_SYSTEM = """You are a question generation expert. Your task is to generate diverse,
high-quality questions from documentation that can be answered DIRECTLY from the provided content.

Generate questions that:
1. Can be answered completely from the given text (no external knowledge needed)
2. Cover different abstraction levels (definition → concept → procedure → architecture)
3. Include different question types (what, how, why, compare)
4. Focus on key concepts and important details
5. Would be useful for someone learning this topic

For each question, identify:
- The type (factual/conceptual/procedural/definitional/comparative)
- The abstraction level (ground/component/architecture/vision)
- Key concepts the answer should cover

Output ONLY valid JSON, no other text."""

QUERY_GENERATION_PROMPT = """Based on this documentation chunk, generate {count} diverse questions.

Documentation:
---
{content}
---

Source: {source}

Generate exactly {count} questions in this JSON format:
{{
  "questions": [
    {{
      "question": "The question text",
      "question_type": "factual|conceptual|procedural|definitional|comparative",
      "abstraction_level": "ground|component|architecture|vision",
      "expected_concepts": ["concept1", "concept2"]
    }}
  ]
}}

Ensure questions:
- Are diverse (don't repeat the same pattern)
- Are answerable from the text alone
- Range from simple factual to complex conceptual
- Cover the main topics in the documentation"""


class QueryGenerator:
    """Generates questions from document chunks using LLM.

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
        self._queries_generated = 0
        self._generation_errors = 0

    async def generate_queries(
        self,
        chunk: DocumentChunk,
        count: int | None = None,
    ) -> list[GeneratedQuery]:
        """Generate questions for a document chunk.

        Args:
            chunk: Document chunk to generate questions for
            count: Number of questions (default from config)

        Returns:
            List of generated queries

        Raises:
            ValueError: If LLM response cannot be parsed
        """
        query_count = count or self.config.queries_per_document

        # Skip very short chunks
        if chunk.word_count < 50:
            logger.debug(f"Skipping short chunk {chunk.chunk_id} ({chunk.word_count} words)")
            return []

        prompt = QUERY_GENERATION_PROMPT.format(
            count=query_count,
            content=chunk.content,
            source=chunk.metadata.get("relative_path", str(chunk.source_path)),
        )

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system=QUERY_GENERATION_SYSTEM,
            )

            queries = self._parse_response(response, chunk)
            self._queries_generated += len(queries)

            logger.debug(
                f"Generated {len(queries)} queries from chunk {chunk.chunk_id}"
            )

            return queries

        except Exception as e:
            self._generation_errors += 1
            logger.warning(f"Query generation failed for {chunk.chunk_id}: {e}")
            return []

    def _parse_response(
        self,
        response: LLMResponse,
        chunk: DocumentChunk,
    ) -> list[GeneratedQuery]:
        """Parse LLM response into GeneratedQuery objects.

        Uses Pydantic schemas for robust parsing with coercion.
        Production Hardening: Handles malformed LLM responses gracefully.

        Args:
            response: LLM response
            chunk: Source document chunk

        Returns:
            List of parsed queries
        """
        # Use Pydantic-based parsing with automatic coercion
        parsed_questions = parse_query_response(response.content)

        queries = []
        for q in parsed_questions:
            try:
                query = GeneratedQuery(
                    question=q.question,
                    question_type=QuestionType(q.question_type),
                    source_chunk_id=chunk.chunk_id,
                    abstraction_level=q.abstraction_level,
                    expected_concepts=q.expected_concepts,
                    metadata={
                        "source_path": str(chunk.source_path),
                        "chunk_index": chunk.chunk_index,
                        "llm_latency_ms": response.latency_ms,
                    },
                )
                queries.append(query)
            except ValueError as e:
                logger.debug(f"Invalid question data: {e}")
                continue

        return queries

    async def generate_batch(
        self,
        chunks: list[DocumentChunk],
        count_per_chunk: int | None = None,
    ) -> list[GeneratedQuery]:
        """Generate questions for multiple chunks.

        Args:
            chunks: List of document chunks
            count_per_chunk: Questions per chunk (default from config)

        Returns:
            All generated queries
        """
        all_queries = []

        for i, chunk in enumerate(chunks):
            queries = await self.generate_queries(chunk, count_per_chunk)
            all_queries.extend(queries)

            if (i + 1) % 10 == 0:
                logger.info(
                    f"Progress: {i + 1}/{len(chunks)} chunks, "
                    f"{len(all_queries)} queries generated"
                )

        return all_queries

    @property
    def stats(self) -> dict[str, Any]:
        """Get generation statistics."""
        return {
            "queries_generated": self._queries_generated,
            "generation_errors": self._generation_errors,
            "success_rate": (
                self._queries_generated / (self._queries_generated + self._generation_errors)
                if (self._queries_generated + self._generation_errors) > 0
                else 0.0
            ),
        }
