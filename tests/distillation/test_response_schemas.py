"""
Response Schema Tests

Tests for Pydantic LLM response parsing and validation.
"""

from __future__ import annotations

import pytest

from orchestra.substrate.knowledge.distillation.response_schemas import (
    AnswerGenerationResponse,
    GeneratedQuestionSchema,
    HallucinationCheckResponse,
    QueryGenerationResponse,
    TriggerGenerationResponse,
    extract_json_from_response,
    parse_answer_response,
    parse_hallucination_response,
    parse_llm_json,
    parse_query_response,
    parse_trigger_response,
)


class TestJSONExtraction:
    """Test JSON extraction from LLM responses."""

    def test_extract_json_simple(self):
        """Extract JSON from clean response."""
        content = '{"key": "value"}'
        result = extract_json_from_response(content)
        assert result == '{"key": "value"}'

    def test_extract_json_from_markdown_block(self):
        """Extract JSON from markdown code block."""
        content = """Here's the result:
```json
{"key": "value"}
```
That's all."""
        result = extract_json_from_response(content)
        assert result == '{"key": "value"}'

    def test_extract_json_from_plain_block(self):
        """Extract JSON from plain code block."""
        content = """```
{"key": "value"}
```"""
        result = extract_json_from_response(content)
        assert result == '{"key": "value"}'

    def test_extract_json_with_text_before(self):
        """Extract JSON when there's text before it."""
        content = "Here's my response: {\"key\": \"value\"}"
        result = extract_json_from_response(content)
        assert result == '{"key": "value"}'

    def test_extract_array_from_response(self):
        """Extract JSON array from response."""
        content = '```json\n["item1", "item2"]\n```'
        result = extract_json_from_response(content)
        assert result == '["item1", "item2"]'


class TestQueryGenerationSchema:
    """Test query generation response parsing."""

    def test_parse_valid_query_response(self):
        """Parse valid query generation response."""
        content = """{
            "questions": [
                {
                    "question": "What is USD?",
                    "question_type": "definitional",
                    "abstraction_level": "ground",
                    "expected_concepts": ["USD", "3D"]
                }
            ]
        }"""

        questions = parse_query_response(content)

        assert len(questions) == 1
        assert questions[0].question == "What is USD?"
        assert questions[0].question_type == "definitional"

    def test_parse_with_markdown_wrapper(self):
        """Parse query response wrapped in markdown."""
        content = """```json
{
    "questions": [
        {"question": "Test question?", "question_type": "factual"}
    ]
}
```"""

        questions = parse_query_response(content)

        assert len(questions) == 1
        assert questions[0].question == "Test question?"

    def test_invalid_question_type_coerced(self):
        """Invalid question types should be coerced to valid ones."""
        content = """{
            "questions": [
                {"question": "Test?", "question_type": "invalid"}
            ]
        }"""

        questions = parse_query_response(content)

        assert len(questions) == 1
        assert questions[0].question_type == "factual"  # Default fallback

    def test_partial_match_question_type(self):
        """Partial question type matches should work."""
        content = """{
            "questions": [
                {"question": "Test?", "question_type": "fac"}
            ]
        }"""

        questions = parse_query_response(content)

        assert questions[0].question_type == "factual"

    def test_empty_questions_array(self):
        """Handle empty questions array."""
        content = '{"questions": []}'

        questions = parse_query_response(content)

        assert questions == []

    def test_malformed_json_returns_empty(self):
        """Malformed JSON should return empty list."""
        content = "This is not valid JSON"

        questions = parse_query_response(content)

        assert questions == []


class TestAnswerGenerationSchema:
    """Test answer generation response parsing."""

    def test_parse_valid_answer_response(self):
        """Parse valid answer generation response."""
        content = """{
            "answer": "USD is a framework for 3D graphics.",
            "summary": "USD enables 3D data exchange",
            "reasoning": "Based on the documentation",
            "key_concepts": ["USD", "3D"],
            "source_quotes": ["USD is a framework"],
            "confidence": 0.9
        }"""

        result = parse_answer_response(content)

        assert result is not None
        assert result.answer == "USD is a framework for 3D graphics."
        assert result.confidence == 0.9

    def test_confidence_string_high(self):
        """String confidence 'high' should be coerced to float."""
        content = """{
            "answer": "Test answer",
            "summary": "Test",
            "confidence": "high"
        }"""

        result = parse_answer_response(content)

        assert result is not None
        assert result.confidence == 0.85

    def test_confidence_string_low(self):
        """String confidence 'low' should be coerced to float."""
        content = """{
            "answer": "Test answer",
            "summary": "Test",
            "confidence": "low"
        }"""

        result = parse_answer_response(content)

        assert result.confidence == 0.35

    def test_confidence_clamped_to_range(self):
        """Confidence outside 0-1 should be clamped."""
        content = """{
            "answer": "Test answer",
            "summary": "Test",
            "confidence": 1.5
        }"""

        result = parse_answer_response(content)

        assert result.confidence == 1.0

    def test_summary_truncated(self):
        """Long summaries should be truncated to 200 chars."""
        long_summary = "x" * 300
        content = f'{{"answer": "Test", "summary": "{long_summary}"}}'

        result = parse_answer_response(content)

        assert len(result.summary) == 200

    def test_missing_answer_returns_none(self):
        """Missing 'answer' field should return None."""
        content = '{"summary": "Test"}'

        result = parse_answer_response(content)

        # This should fail validation since answer is required
        # The lenient mode should return None
        assert result is None


class TestHallucinationCheckSchema:
    """Test hallucination check response parsing."""

    def test_parse_valid_hallucination_response(self):
        """Parse valid hallucination check response."""
        content = """{
            "supported_claims": ["claim 1", "claim 2"],
            "unsupported_claims": ["claim 3"],
            "hallucination_score": 0.25,
            "analysis": "Most claims supported"
        }"""

        result = parse_hallucination_response(content)

        assert result is not None
        assert len(result.supported_claims) == 2
        assert len(result.unsupported_claims) == 1
        assert result.hallucination_score == 0.25

    def test_hallucination_score_string_coerced(self):
        """String hallucination score should be coerced."""
        content = """{
            "hallucination_score": "0.5",
            "analysis": "Partial support"
        }"""

        result = parse_hallucination_response(content)

        assert result.hallucination_score == 0.5

    def test_fallback_to_score_only(self):
        """Should extract just the score if full parsing fails."""
        content = '{"hallucination_score": 0.3, "analysis": "test"}'

        result = parse_hallucination_response(content)

        assert result is not None
        assert result.hallucination_score == 0.3


class TestTriggerGenerationSchema:
    """Test trigger generation response parsing."""

    def test_parse_trigger_array(self):
        """Parse trigger array response."""
        content = '["trigger1", "trigger2", "trigger3"]'

        triggers = parse_trigger_response(content)

        assert triggers == ["trigger1", "trigger2", "trigger3"]

    def test_parse_trigger_wrapped(self):
        """Parse trigger response wrapped in object."""
        content = '{"triggers": ["a", "b", "c"]}'

        triggers = parse_trigger_response(content)

        assert triggers == ["a", "b", "c"]

    def test_triggers_lowercased(self):
        """Triggers should be lowercased."""
        content = '["USD", "LIVRPS", "HoUdInI"]'

        triggers = parse_trigger_response(content)

        assert triggers == ["usd", "livrps", "houdini"]

    def test_triggers_stripped(self):
        """Triggers should be stripped of whitespace."""
        content = '["  trigger1  ", " trigger2 "]'

        triggers = parse_trigger_response(content)

        assert triggers == ["trigger1", "trigger2"]

    def test_empty_triggers_filtered(self):
        """Empty triggers should be filtered out."""
        content = '["valid", "", null, "also valid"]'

        triggers = parse_trigger_response(content)

        assert triggers == ["valid", "also valid"]


class TestParseLLMJSON:
    """Test the generic parse_llm_json function."""

    def test_lenient_mode_returns_none(self):
        """Lenient mode should return None on failure."""
        result = parse_llm_json("invalid json", AnswerGenerationResponse, lenient=True)

        assert result is None

    def test_strict_mode_raises(self):
        """Strict mode should raise on failure."""
        with pytest.raises(Exception):
            parse_llm_json("invalid json", AnswerGenerationResponse, lenient=False)

    def test_handles_array_for_trigger_schema(self):
        """Array responses should be wrapped for TriggerGenerationResponse."""
        content = '["a", "b", "c"]'

        result = parse_llm_json(content, TriggerGenerationResponse, lenient=True)

        assert result is not None
        assert result.triggers == ["a", "b", "c"]
