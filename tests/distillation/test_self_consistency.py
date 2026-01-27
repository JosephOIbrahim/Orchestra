"""
Self-Consistency Verification Tests

Tests for multi-sample voting and claim validation.
ThinkingMachines [He2025] Frontier AI Enhancement.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orchestra.substrate.knowledge.distillation.self_consistency import (
    ClaimVerification,
    ConsistencyResult,
    SelfConsistencyVerifier,
)
from orchestra.substrate.knowledge.distillation.config import DistillationConfig


class TestClaimVerification:
    """Test claim verification data structure."""

    def test_claim_verification_creation(self):
        """Should create ClaimVerification correctly."""
        verification = ClaimVerification(
            claim="The sky is blue",
            status="SUPPORTED",
            evidence="The source states the sky is blue",
            agreement_ratio=0.75,
        )

        assert verification.claim == "The sky is blue"
        assert verification.status == "SUPPORTED"
        assert verification.agreement_ratio == 0.75

    def test_claim_verification_unsupported(self):
        """Should handle unsupported claims."""
        verification = ClaimVerification(
            claim="Unknown claim",
            status="UNSUPPORTED",
            evidence=None,
            agreement_ratio=0.0,
        )

        assert verification.status == "UNSUPPORTED"
        assert verification.evidence is None

    def test_claim_verification_contradicted(self):
        """Should handle contradicted claims."""
        verification = ClaimVerification(
            claim="The sky is green",
            status="CONTRADICTED",
            evidence="Source says sky is blue",
            agreement_ratio=0.9,
        )

        assert verification.status == "CONTRADICTED"


class TestConsistencyResult:
    """Test consistency result data structure."""

    def test_result_creation(self):
        """Should create ConsistencyResult correctly."""
        result = ConsistencyResult(
            answer="The verified answer",
            claims=["claim1", "claim2"],
            verifications=[
                ClaimVerification("claim1", "SUPPORTED", "evidence", 0.9),
            ],
            consistency_score=0.85,
        )

        assert result.consistency_score == 0.85
        assert len(result.verifications) == 1
        assert result.answer == "The verified answer"

    def test_empty_result(self):
        """Should handle empty results."""
        result = ConsistencyResult(
            answer="",
            claims=[],
            verifications=[],
            consistency_score=0.0,
        )

        assert result.consistency_score == 0.0
        assert len(result.verifications) == 0

    def test_result_serialization(self):
        """Should serialize to dict correctly."""
        result = ConsistencyResult(
            answer="Test answer",
            claims=["claim1"],
            verifications=[
                ClaimVerification("claim1", "SUPPORTED", "ev", 0.8),
            ],
            consistency_score=0.75,
        )

        data = result.to_dict()

        assert data["answer"] == "Test answer"
        assert data["consistency_score"] == 0.75
        assert len(data["verifications"]) == 1


class TestSelfConsistencyVerifier:
    """Test self-consistency verifier."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        return DistillationConfig(
            corpus_dir=tmp_path / "corpus",
            output_dir=tmp_path / "output",
            enable_self_consistency=True,
            consistency_samples=3,
        )

    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        return MagicMock()

    def test_verifier_initialization(self, config, mock_llm_client):
        """Should initialize with config and LLM client."""
        verifier = SelfConsistencyVerifier(config, mock_llm_client)

        assert verifier.config is not None
        assert verifier.llm_client is not None

    def test_claim_status_values(self):
        """Claim status should use expected values."""
        valid_statuses = ["SUPPORTED", "UNSUPPORTED", "CONTRADICTED"]

        verification = ClaimVerification(
            claim="test",
            status="SUPPORTED",
        )

        assert verification.status in valid_statuses


class TestDeterminism:
    """Test ThinkingMachines [He2025] compliance."""

    def test_same_claim_same_structure(self):
        """Same claim should produce same structure."""
        claim1 = ClaimVerification(
            claim="Test claim",
            status="SUPPORTED",
            evidence="Evidence",
            agreement_ratio=0.9,
        )
        claim2 = ClaimVerification(
            claim="Test claim",
            status="SUPPORTED",
            evidence="Evidence",
            agreement_ratio=0.9,
        )

        assert claim1.claim == claim2.claim
        assert claim1.status == claim2.status
        assert claim1.agreement_ratio == claim2.agreement_ratio

    def test_empty_result_deterministic(self):
        """Empty results should be consistent."""
        result1 = ConsistencyResult(
            answer="",
            claims=[],
            verifications=[],
            consistency_score=0.0,
        )
        result2 = ConsistencyResult(
            answer="",
            claims=[],
            verifications=[],
            consistency_score=0.0,
        )

        assert result1.consistency_score == result2.consistency_score
        assert result1.verifications == result2.verifications


class TestEdgeCases:
    """Test edge cases."""

    def test_claim_with_special_characters(self):
        """Should handle special characters in claims."""
        verification = ClaimVerification(
            claim='Claim with "quotes" and <brackets>',
            status="SUPPORTED",
        )

        assert '"quotes"' in verification.claim
        assert "<brackets>" in verification.claim

    def test_very_long_claim(self):
        """Should handle very long claims."""
        long_claim = "This is a very long claim. " * 100
        verification = ClaimVerification(
            claim=long_claim,
            status="SUPPORTED",
        )

        assert len(verification.claim) > 1000

    def test_unicode_claim(self):
        """Should handle unicode in claims."""
        verification = ClaimVerification(
            claim="Unicode: 你好世界 café résumé",
            status="SUPPORTED",
        )

        assert "你好" in verification.claim
