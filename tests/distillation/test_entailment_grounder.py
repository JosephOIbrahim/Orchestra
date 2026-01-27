"""
Entailment Grounding Tests

Tests for NLI-based claim verification against source documents.
ThinkingMachines [He2025] Frontier AI Enhancement.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orchestra.substrate.knowledge.distillation.entailment_grounder import (
    ClaimGrounding,
    EntailmentGrounder,
    EntailmentVerdict,
    GroundingResult,
)
from orchestra.substrate.knowledge.distillation.config import DistillationConfig


class TestEntailmentVerdict:
    """Test entailment verdict enumeration."""

    def test_verdict_values(self):
        """Should have expected verdict values."""
        assert EntailmentVerdict.ENTAILED.value == "entailed"
        assert EntailmentVerdict.NEUTRAL.value == "neutral"
        assert EntailmentVerdict.CONTRADICTED.value == "contradicted"

    def test_verdict_from_string(self):
        """Should create verdict from string."""
        assert EntailmentVerdict("entailed") == EntailmentVerdict.ENTAILED
        assert EntailmentVerdict("neutral") == EntailmentVerdict.NEUTRAL
        assert EntailmentVerdict("contradicted") == EntailmentVerdict.CONTRADICTED

    def test_all_verdicts_present(self):
        """Should have exactly three verdicts."""
        verdicts = list(EntailmentVerdict)
        assert len(verdicts) == 3


class TestClaimGrounding:
    """Test claim grounding data structure."""

    def test_grounding_creation(self):
        """Should create ClaimGrounding correctly."""
        grounding = ClaimGrounding(
            claim="The system uses Python",
            verdict=EntailmentVerdict.ENTAILED,
            evidence="Python is mentioned in the documentation",
            confidence=0.95,
        )

        assert grounding.claim == "The system uses Python"
        assert grounding.verdict == EntailmentVerdict.ENTAILED
        assert grounding.confidence == 0.95

    def test_grounding_neutral(self):
        """Should handle neutral verdicts."""
        grounding = ClaimGrounding(
            claim="Test claim",
            verdict=EntailmentVerdict.NEUTRAL,
            evidence="No clear evidence",
            confidence=0.5,
        )

        assert grounding.verdict == EntailmentVerdict.NEUTRAL

    def test_contradicted_grounding(self):
        """Should handle contradicted claims."""
        grounding = ClaimGrounding(
            claim="The sky is green",
            verdict=EntailmentVerdict.CONTRADICTED,
            evidence="Source states the sky is blue",
            confidence=0.9,
        )

        assert grounding.verdict == EntailmentVerdict.CONTRADICTED

    def test_grounding_serialization(self):
        """Should serialize to dict correctly."""
        grounding = ClaimGrounding(
            claim="Test claim",
            verdict=EntailmentVerdict.ENTAILED,
            confidence=0.8,
            reasoning="Clear evidence",
            evidence="Quote from source",
        )

        data = grounding.to_dict()

        assert data["claim"] == "Test claim"
        assert data["verdict"] == "entailed"
        assert data["confidence"] == 0.8


class TestGroundingResult:
    """Test grounding result data structure."""

    def test_result_creation(self):
        """Should create GroundingResult correctly."""
        result = GroundingResult(
            content="Generated content",
            source="Source document",
            claims=["claim1"],
            groundings=[
                ClaimGrounding("claim1", EntailmentVerdict.ENTAILED, confidence=0.9),
            ],
            grounding_score=0.85,
        )

        assert result.grounding_score == 0.85
        assert len(result.groundings) == 1

    def test_empty_result(self):
        """Should handle empty results."""
        result = GroundingResult(
            content="",
            source="",
            claims=[],
            groundings=[],
            grounding_score=0.0,
        )

        assert result.grounding_score == 0.0
        assert len(result.groundings) == 0

    def test_result_properties(self):
        """Should compute claim properties correctly."""
        result = GroundingResult(
            content="Content",
            source="Source",
            claims=["c1", "c2", "c3"],
            groundings=[
                ClaimGrounding("c1", EntailmentVerdict.ENTAILED, confidence=0.9),
                ClaimGrounding("c2", EntailmentVerdict.NEUTRAL, confidence=0.5),
                ClaimGrounding("c3", EntailmentVerdict.CONTRADICTED, confidence=0.8),
            ],
        )

        assert result.entailed_claims == ["c1"]
        assert result.neutral_claims == ["c2"]
        assert result.contradicted_claims == ["c3"]


class TestEntailmentGrounder:
    """Test entailment grounder."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        return DistillationConfig(
            corpus_dir=tmp_path / "corpus",
            output_dir=tmp_path / "output",
            enable_entailment_grounding=True,
        )

    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        return MagicMock()

    def test_grounder_initialization(self, config, mock_llm_client):
        """Should initialize with config and LLM client."""
        grounder = EntailmentGrounder(config, mock_llm_client)

        assert grounder.config is not None
        assert grounder.llm_client is not None


class TestDeterminism:
    """Test ThinkingMachines [He2025] compliance."""

    def test_verdict_enum_stable(self):
        """Verdict enum values should be stable."""
        assert EntailmentVerdict.ENTAILED.value == "entailed"
        assert EntailmentVerdict.NEUTRAL.value == "neutral"
        assert EntailmentVerdict.CONTRADICTED.value == "contradicted"

    def test_grounding_structure_deterministic(self):
        """Same inputs should produce same structure."""
        grounding1 = ClaimGrounding(
            claim="claim",
            verdict=EntailmentVerdict.ENTAILED,
            evidence="ev",
            confidence=0.9,
        )
        grounding2 = ClaimGrounding(
            claim="claim",
            verdict=EntailmentVerdict.ENTAILED,
            evidence="ev",
            confidence=0.9,
        )

        assert grounding1.claim == grounding2.claim
        assert grounding1.verdict == grounding2.verdict
        assert grounding1.confidence == grounding2.confidence

    def test_result_serialization_deterministic(self):
        """Result serialization should be deterministic."""
        grounding = ClaimGrounding(
            claim="test",
            verdict=EntailmentVerdict.NEUTRAL,
            confidence=0.5,
        )

        data1 = grounding.to_dict()
        data2 = grounding.to_dict()

        assert data1 == data2


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_claim_with_special_characters(self):
        """Should handle special characters in claims."""
        grounding = ClaimGrounding(
            claim='Claim with "quotes" and <brackets>',
            verdict=EntailmentVerdict.ENTAILED,
            confidence=0.9,
        )

        assert '"quotes"' in grounding.claim

    def test_very_long_claim(self):
        """Should handle very long claims."""
        long_claim = "This is a claim. " * 1000
        grounding = ClaimGrounding(
            claim=long_claim,
            verdict=EntailmentVerdict.NEUTRAL,
            confidence=0.5,
        )

        assert len(grounding.claim) > 10000

    def test_unicode_content(self):
        """Should handle unicode content."""
        grounding = ClaimGrounding(
            claim="Unicode claim: 你好世界. café résumé.",
            verdict=EntailmentVerdict.ENTAILED,
            evidence="Unicode evidence",
            confidence=0.9,
        )

        assert "你好" in grounding.claim

    def test_empty_evidence(self):
        """Should handle empty evidence."""
        grounding = ClaimGrounding(
            claim="Claim without evidence",
            verdict=EntailmentVerdict.NEUTRAL,
            evidence="",
            confidence=0.0,
        )

        assert grounding.evidence == ""
