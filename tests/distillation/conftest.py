"""
Test Fixtures for Distillation Pipeline

Provides mocks, fixtures, and test utilities for distillation tests.
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestra.substrate.knowledge.distillation import (
    DistillationConfig,
    DocumentChunk,
    GeneratedAnswer,
    GeneratedQuery,
    LLMResponse,
    QuestionType,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def config(temp_dir):
    """Create a test configuration."""
    corpus_dir = temp_dir / "corpus"
    corpus_dir.mkdir()

    output_dir = temp_dir / "output"
    output_dir.mkdir()

    return DistillationConfig(
        corpus_dir=corpus_dir,
        output_dir=output_dir,
        temperature=0.0,
        enable_caching=False,
        enable_checkpointing=True,
        enable_self_consistency=False,
        enable_entailment_grounding=False,
    )


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate = AsyncMock(return_value=LLMResponse(
        content='{"answer": "test", "summary": "test", "confidence": 0.9}',
        model="test-model",
        input_tokens=100,
        output_tokens=50,
        latency_ms=100.0,
        cached=False,
    ))
    return client


@pytest.fixture
def sample_chunk():
    """Create a sample document chunk."""
    return DocumentChunk(
        content="""# Test Documentation

This is a test document about USD (Universal Scene Description).
USD is a framework for interchange of 3D graphics data.

## Key Concepts

- **Prim**: The basic building block
- **Stage**: The container for prims
- **Layer**: A collection of prims

USD uses composition to combine multiple sources.
""",
        source_path=Path("/test/docs/test.md"),
        chunk_index=0,
        total_chunks=1,
        metadata={"title": "Test Documentation"},
    )


@pytest.fixture
def sample_query():
    """Create a sample generated query."""
    return GeneratedQuery(
        question="What is USD?",
        question_type=QuestionType.DEFINITIONAL,
        source_chunk_id="test_chunk_001",
        abstraction_level="ground",
        expected_concepts=["USD", "3D graphics"],
    )


@pytest.fixture
def sample_answer(sample_query, sample_chunk):
    """Create a sample generated answer."""
    return GeneratedAnswer(
        answer="USD (Universal Scene Description) is a framework for interchange of 3D graphics data.",
        summary="USD is a 3D graphics interchange framework",
        reasoning="The document states that USD is a framework for 3D graphics.",
        key_concepts=["USD", "3D graphics", "interchange"],
        source_quotes=["USD is a framework for interchange of 3D graphics data"],
        query=sample_query,
        source_chunk=sample_chunk,
        confidence_hint=0.9,
    )


@pytest.fixture
def sample_corpus_files(temp_dir):
    """Create sample corpus files."""
    corpus_dir = temp_dir / "corpus"
    corpus_dir.mkdir(exist_ok=True)

    # Create sample files
    files = []
    for i in range(3):
        file_path = corpus_dir / f"doc_{i}.md"
        file_path.write_text(f"""# Document {i}

This is test document number {i}.
It contains information about topic {i}.

## Section A

Details about section A in document {i}.

## Section B

Details about section B in document {i}.
""")
        files.append(file_path)

    return files


@dataclass
class MockLLMResponses:
    """Container for mock LLM responses by prompt type."""

    query_generation: str = """{
        "questions": [
            {"question": "What is USD?", "question_type": "definitional", "abstraction_level": "ground", "expected_concepts": ["USD"]},
            {"question": "How does composition work?", "question_type": "procedural", "abstraction_level": "component", "expected_concepts": ["composition"]}
        ]
    }"""

    answer_generation: str = """{
        "answer": "USD is a framework for 3D graphics interchange.",
        "summary": "USD enables 3D data exchange",
        "reasoning": "Based on the documentation",
        "key_concepts": ["USD", "3D"],
        "source_quotes": ["USD is a framework"],
        "confidence": 0.9
    }"""

    hallucination_check: str = """{
        "supported_claims": ["USD is a framework"],
        "unsupported_claims": [],
        "hallucination_score": 0.1,
        "analysis": "Claims are well supported"
    }"""

    trigger_generation: str = '["usd", "universal scene description", "3d graphics"]'


@pytest.fixture
def mock_responses():
    """Provide mock LLM responses."""
    return MockLLMResponses()


def create_mock_llm_client_with_responses(responses: MockLLMResponses):
    """Create a mock LLM client that returns appropriate responses based on prompt content."""
    client = MagicMock()

    async def mock_generate(prompt: str, **kwargs) -> LLMResponse:
        content = responses.query_generation

        if "question" in prompt.lower() and "generate" in prompt.lower():
            content = responses.query_generation
        elif "answer" in prompt.lower():
            content = responses.answer_generation
        elif "hallucination" in prompt.lower() or "verify" in prompt.lower():
            content = responses.hallucination_check
        elif "trigger" in prompt.lower() or "search" in prompt.lower():
            content = responses.trigger_generation

        return LLMResponse(
            content=content,
            model="test-model",
            input_tokens=100,
            output_tokens=50,
            latency_ms=100.0,
            cached=False,
        )

    client.generate = mock_generate
    return client


@pytest.fixture
def mock_llm_client_with_responses(mock_responses):
    """Create a smart mock LLM client."""
    return create_mock_llm_client_with_responses(mock_responses)
