"""
Response Schemas

Pydantic models for validating and parsing LLM responses.
Provides type-safe parsing with coercion and error handling.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
ThinkingMachines [He2025] Production Hardening.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class GeneratedQuestionSchema(BaseModel):
    """Schema for a generated question from LLM."""

    question: str = Field(..., min_length=5, description="The question text")
    question_type: str = Field(
        default="factual",
        description="Type: factual|conceptual|procedural|definitional|comparative",
    )
    abstraction_level: str = Field(
        default="ground",
        description="Level: ground|component|architecture|vision",
    )
    expected_concepts: list[str] = Field(
        default_factory=list,
        description="Key concepts the answer should cover",
    )

    @field_validator("question_type")
    @classmethod
    def validate_question_type(cls, v: str) -> str:
        """Validate and normalize question type."""
        valid_types = {"factual", "conceptual", "procedural", "definitional", "comparative"}
        v_lower = v.lower().strip()
        if v_lower in valid_types:
            return v_lower
        # Try to match partial
        for t in valid_types:
            if t.startswith(v_lower[:3]):
                return t
        return "factual"  # Default fallback

    @field_validator("abstraction_level")
    @classmethod
    def validate_abstraction_level(cls, v: str) -> str:
        """Validate and normalize abstraction level."""
        valid_levels = {"ground", "component", "architecture", "vision"}
        v_lower = v.lower().strip()
        if v_lower in valid_levels:
            return v_lower
        return "ground"  # Default fallback


class QueryGenerationResponse(BaseModel):
    """Schema for query generation LLM response."""

    questions: list[GeneratedQuestionSchema] = Field(
        default_factory=list,
        description="Generated questions",
    )


class AnswerGenerationResponse(BaseModel):
    """Schema for answer generation LLM response."""

    answer: str = Field(..., min_length=1, description="The answer text")
    summary: str = Field(default="", max_length=200, description="Brief summary")
    reasoning: str = Field(default="", description="Reasoning trace")
    key_concepts: list[str] = Field(
        default_factory=list,
        description="Key concepts covered",
    )
    source_quotes: list[str] = Field(
        default_factory=list,
        description="Direct quotes from source",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0)",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v: Any) -> float:
        """Coerce confidence to float, handling string values."""
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        if isinstance(v, str):
            # Handle descriptive confidence like "high", "medium", "low"
            confidence_map = {
                "very high": 0.95,
                "high": 0.85,
                "medium": 0.65,
                "moderate": 0.65,
                "low": 0.35,
                "very low": 0.15,
                "none": 0.0,
            }
            v_lower = v.lower().strip()
            if v_lower in confidence_map:
                return confidence_map[v_lower]
            # Try to parse as number
            try:
                return max(0.0, min(1.0, float(v)))
            except ValueError:
                return 0.5
        return 0.5

    @field_validator("summary", mode="before")
    @classmethod
    def truncate_summary(cls, v: Any) -> str:
        """Ensure summary doesn't exceed max length."""
        if isinstance(v, str):
            return v[:200]
        return ""


class HallucinationCheckResponse(BaseModel):
    """Schema for hallucination check LLM response."""

    supported_claims: list[str] = Field(
        default_factory=list,
        description="Claims supported by source",
    )
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Claims not in source (hallucinations)",
    )
    hallucination_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Hallucination score (0.0=none, 1.0=all)",
    )
    analysis: str = Field(
        default="",
        description="Explanation of evaluation",
    )

    @field_validator("hallucination_score", mode="before")
    @classmethod
    def coerce_hallucination_score(cls, v: Any) -> float:
        """Coerce hallucination score to float."""
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        if isinstance(v, str):
            try:
                return max(0.0, min(1.0, float(v)))
            except ValueError:
                return 0.5
        return 0.5


class TriggerGenerationResponse(BaseModel):
    """Schema for trigger generation LLM response (simple array)."""

    triggers: list[str] = Field(
        default_factory=list,
        description="Generated trigger terms",
    )


def extract_json_from_response(content: str) -> str:
    """Extract JSON from LLM response, handling markdown code blocks.

    Args:
        content: Raw LLM response content

    Returns:
        Extracted JSON string
    """
    content = content.strip()

    # Handle markdown code blocks
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if json_match:
        return json_match.group(1)

    # Handle array in code block
    array_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
    if array_match:
        return array_match.group(1)

    # Try to find JSON object
    if not content.startswith("{") and not content.startswith("["):
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return content[json_start:json_end]

        # Try to find array
        array_start = content.find("[")
        array_end = content.rfind("]") + 1
        if array_start >= 0 and array_end > array_start:
            return content[array_start:array_end]

    return content


def parse_llm_json(
    content: str,
    schema: type[BaseModel],
    *,
    lenient: bool = True,
) -> BaseModel | None:
    """Parse LLM response content into a Pydantic model.

    Args:
        content: Raw LLM response content
        schema: Pydantic model class to parse into
        lenient: If True, return None on failure instead of raising

    Returns:
        Parsed model instance or None if parsing failed

    Raises:
        ValidationError: If lenient=False and parsing fails
    """
    try:
        json_str = extract_json_from_response(content)
        data = json.loads(json_str)

        # Handle array responses (e.g., trigger generation)
        if isinstance(data, list):
            if schema == TriggerGenerationResponse:
                data = {"triggers": data}
            else:
                # Wrap in expected format
                data = {"items": data}

        return schema.model_validate(data)

    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}")
        logger.debug(f"Content: {content[:500]}")
        if not lenient:
            raise
        return None

    except Exception as e:
        logger.warning(f"Schema validation error: {e}")
        if not lenient:
            raise
        return None


def parse_query_response(content: str) -> list[GeneratedQuestionSchema]:
    """Parse query generation response.

    Args:
        content: LLM response content

    Returns:
        List of parsed questions (empty on failure)
    """
    response = parse_llm_json(content, QueryGenerationResponse)
    if response:
        return response.questions
    return []


def parse_answer_response(content: str) -> AnswerGenerationResponse | None:
    """Parse answer generation response.

    Args:
        content: LLM response content

    Returns:
        Parsed answer or None on failure
    """
    return parse_llm_json(content, AnswerGenerationResponse)


def parse_hallucination_response(content: str) -> HallucinationCheckResponse | None:
    """Parse hallucination check response.

    Args:
        content: LLM response content

    Returns:
        Parsed result or None on failure
    """
    result = parse_llm_json(content, HallucinationCheckResponse)
    if result:
        return result

    # Fallback: try to extract just the score
    try:
        json_str = extract_json_from_response(content)
        data = json.loads(json_str)
        if "hallucination_score" in data:
            return HallucinationCheckResponse(
                hallucination_score=float(data["hallucination_score"]),
                analysis=data.get("analysis", ""),
            )
    except Exception:
        pass

    return None


def parse_trigger_response(content: str) -> list[str]:
    """Parse trigger generation response.

    Args:
        content: LLM response content

    Returns:
        List of trigger strings (empty on failure)
    """
    try:
        json_str = extract_json_from_response(content)
        data = json.loads(json_str)

        # Handle direct array response
        if isinstance(data, list):
            return [str(t).lower().strip() for t in data if t]

        # Handle wrapped response
        if isinstance(data, dict) and "triggers" in data:
            return [str(t).lower().strip() for t in data["triggers"] if t]

    except Exception as e:
        logger.debug(f"Trigger parse failed: {e}")

    return []
