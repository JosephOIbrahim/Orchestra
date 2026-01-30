"""
Test Grounding Layer Integration (v6.0.0)
==========================================

Tests the integration of the Grounding Layer (L7.5) with Orchestra's
NEXUS Pipeline.

Tests cover:
- GroundingBridge basic operations
- Phase 0b: CLASSIFY (source mode determination)
- Phase 0c: GROUND (oracle queries)
- GROUNDING signal detection in PRISM
- GROUNDING_MoE expert routing
- Anchor format with source_mode
- State tracking for grounding fields

Reference: [GWM2026] "Grounded World Models"
Core Thesis: "LLMs don't need to LEARN physics—they need ACCESS to physics"
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

# Import grounding modules
from orchestra.grounding_bridge import (
    GroundingBridge, GroundingResult, SourceMode,
    GROUNDING_SIGNALS, create_grounding_bridge
)

# Import Orchestra core modules
from orchestra.prism_detector import (
    PRISMDetector, SignalVector, SignalCategory, create_detector
)
from orchestra.expert_router import (
    ExpertRouter, Expert, RoutingResult,
    GROUNDING_EXPERT_PRIORITY, GROUNDING_EXPERT_TRIGGERS, create_router
)
from orchestra.parameter_locker import (
    ParameterLocker, LockedParams, LockResult, ThinkDepth, create_locker
)
from orchestra.cognitive_state import (
    CognitiveState, CognitiveStateManager, BurnoutLevel, EnergyLevel,
    MomentumPhase, Altitude
)
from orchestra.cognitive_orchestrator import (
    CognitiveOrchestrator, NexusResult, create_orchestrator
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def grounding_bridge():
    """Create a GroundingBridge for testing."""
    return create_grounding_bridge(grounding_budget=5)


@pytest.fixture
def detector():
    """Create a PRISMDetector for testing."""
    return create_detector()


@pytest.fixture
def router():
    """Create an ExpertRouter for testing."""
    return create_router()


@pytest.fixture
def locker():
    """Create a ParameterLocker for testing."""
    return create_locker()


@pytest.fixture
def orchestrator():
    """Create a CognitiveOrchestrator for testing."""
    return create_orchestrator()


# =============================================================================
# GroundingBridge Tests
# =============================================================================

class TestGroundingBridge:
    """Tests for the GroundingBridge adapter."""

    def test_bridge_creation(self, grounding_bridge):
        """Test GroundingBridge creation."""
        assert grounding_bridge is not None
        assert grounding_bridge.grounding_budget == 5

    def test_bridge_budget_management(self, grounding_bridge):
        """Test grounding budget management."""
        assert grounding_bridge.get_budget() == 5
        grounding_bridge.reset_budget(10)
        assert grounding_bridge.get_budget() == 10

    def test_classify_query_physics(self, grounding_bridge):
        """Test classification of physics query."""
        mode, reason, signals = grounding_bridge.classify_query(
            "What is the position of the ball?"
        )
        assert mode in (SourceMode.ACCESS, SourceMode.HYBRID)
        assert len(signals) > 0
        assert any("physics" in s for s in signals)

    def test_classify_query_no_grounding(self, grounding_bridge):
        """Test classification of non-grounding query."""
        mode, reason, signals = grounding_bridge.classify_query(
            "Help me write a function"
        )
        assert mode == SourceMode.LEARN
        assert reason == "no_grounding_signals"

    def test_classify_query_hybrid(self, grounding_bridge):
        """Test classification triggers HYBRID for 'why' questions."""
        mode, reason, signals = grounding_bridge.classify_query(
            "Why did the ball bounce?"
        )
        # Should be HYBRID because "why" requires interpretation
        assert mode == SourceMode.HYBRID
        assert "hybrid" in reason or any("hybrid" in s for s in signals)

    def test_classify_query_simulate(self, grounding_bridge):
        """Test classification of simulation query."""
        mode, reason, signals = grounding_bridge.classify_query(
            "Simulate the collision for 10 frames"
        )
        assert mode in (SourceMode.ACCESS, SourceMode.HYBRID)
        assert any("simulate" in s for s in signals)

    def test_classify_query_factual(self, grounding_bridge):
        """Test classification of factual query."""
        mode, reason, signals = grounding_bridge.classify_query(
            "What is the capital of France?"  # Non-physics factual query
        )
        # Factual queries without physics signals stay in LEARN or route to HYBRID
        assert mode in (SourceMode.LEARN, SourceMode.HYBRID)
        assert any("factual" in s for s in signals)

    def test_process_grounding_returns_result(self, grounding_bridge):
        """Test process_grounding returns GroundingResult."""
        result = grounding_bridge.process_grounding("Calculate the distance")
        assert isinstance(result, GroundingResult)
        assert result.source_mode in (SourceMode.LEARN, SourceMode.ACCESS, SourceMode.HYBRID)

    def test_grounding_result_is_grounded(self):
        """Test GroundingResult.is_grounded method."""
        learn_result = GroundingResult(source_mode=SourceMode.LEARN)
        access_result = GroundingResult(source_mode=SourceMode.ACCESS)
        hybrid_result = GroundingResult(source_mode=SourceMode.HYBRID)

        assert not learn_result.is_grounded()
        assert access_result.is_grounded()
        assert hybrid_result.is_grounded()

    def test_grounding_result_anchor_component(self):
        """Test GroundingResult anchor component format."""
        result = GroundingResult(
            source_mode=SourceMode.ACCESS,
            confidence=0.95
        )
        anchor = result.to_anchor_component()
        assert anchor == "access:0.95"

        learn_result = GroundingResult(source_mode=SourceMode.LEARN)
        assert learn_result.to_anchor_component() == "learn:na"


class TestGroundingResultSerialization:
    """Tests for GroundingResult serialization."""

    def test_to_dict_complete(self):
        """Test GroundingResult.to_dict includes all fields."""
        result = GroundingResult(
            source_mode=SourceMode.ACCESS,
            classification_reason="physics_signal",
            grounding_signals=["physics:position"],
            oracle_id="houdini_rbd",
            oracle_latency_ms=5.2,
            confidence=1.0,
            grounding_budget_remaining=4
        )
        d = result.to_dict()

        assert d["source_mode"] == "access"
        assert d["classification_reason"] == "physics_signal"
        assert d["grounding_signals"] == ["physics:position"]
        assert d["oracle_id"] == "houdini_rbd"
        assert d["oracle_latency_ms"] == 5.2
        assert d["confidence"] == 1.0
        assert d["grounding_budget_remaining"] == 4
        assert d["is_grounded"] is True


# =============================================================================
# PRISM Grounding Signal Detection Tests
# =============================================================================

class TestPRISMGroundingSignals:
    """Tests for GROUNDING signal detection in PRISM."""

    def test_grounding_category_exists(self):
        """Test SignalCategory.GROUNDING exists."""
        assert hasattr(SignalCategory, 'GROUNDING')
        assert SignalCategory.GROUNDING.value == 2

    def test_grounding_priority_order(self, detector):
        """Test GROUNDING is between EMOTIONAL and MODE in priority."""
        priority = detector.SIGNAL_PRIORITY
        emotional_idx = priority.index(SignalCategory.EMOTIONAL)
        grounding_idx = priority.index(SignalCategory.GROUNDING)
        mode_idx = priority.index(SignalCategory.MODE)

        assert emotional_idx < grounding_idx < mode_idx

    def test_detect_physics_signals(self, detector):
        """Test detection of physics grounding signals."""
        result = detector.detect("What is the velocity of the object?")

        assert hasattr(result, 'grounding')
        assert hasattr(result, 'grounding_score')
        assert hasattr(result, 'grounding_type')
        assert result.grounding_score > 0

    def test_detect_simulate_signals(self, detector):
        """Test detection of simulation signals."""
        result = detector.detect("Run the simulation for frame 100")

        assert result.grounding.get("simulate", 0) > 0 or result.grounding_score > 0

    def test_detect_calculate_signals(self, detector):
        """Test detection of calculation signals."""
        result = detector.detect("Calculate the distance between A and B")

        assert result.grounding_score > 0 or result.grounding.get("calculate", 0) > 0

    def test_requires_grounding_method(self, detector):
        """Test SignalVector.requires_grounding method."""
        physics_result = detector.detect("Get the position of the ball")
        code_result = detector.detect("Write a Python function")

        # Physics query should require grounding
        if physics_result.grounding_score >= 0.3:
            assert physics_result.requires_grounding()

        # Code query should not require grounding
        assert not code_result.requires_grounding()

    def test_grounding_in_signal_vector_dict(self, detector):
        """Test grounding fields appear in SignalVector.to_dict()."""
        result = detector.detect("Check the collision detection")
        d = result.to_dict()

        assert "grounding" in d
        assert "grounding_score" in d
        assert "grounding_type" in d


# =============================================================================
# Expert Router GROUNDING_MoE Tests
# =============================================================================

class TestGroundingMoEExperts:
    """Tests for GROUNDING_MoE expert routing."""

    def test_grounding_experts_defined(self):
        """Test all GROUNDING_MoE experts are defined."""
        assert Expert.ORACLE_RESOLVER is not None
        assert Expert.EVIDENCE_BUILDER is not None
        assert Expert.CONFIDENCE_ADJ is not None
        assert Expert.ACCESS_GATEKEEPER is not None

    def test_grounding_priority_order(self):
        """Test GROUNDING_MoE priority order."""
        assert GROUNDING_EXPERT_PRIORITY[0] == Expert.ORACLE_RESOLVER
        assert GROUNDING_EXPERT_PRIORITY[1] == Expert.EVIDENCE_BUILDER
        assert GROUNDING_EXPERT_PRIORITY[2] == Expert.CONFIDENCE_ADJ
        assert GROUNDING_EXPERT_PRIORITY[3] == Expert.ACCESS_GATEKEEPER

    def test_routing_includes_grounding_fields(self, router, detector):
        """Test RoutingResult includes grounding fields."""
        signals = detector.detect("What is the position?")
        result = router.route(
            signals=signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.HIGH,
            momentum=MomentumPhase.ROLLING,
            hallucination_score=0.0
        )

        assert hasattr(result, 'grounding_expert')
        assert hasattr(result, 'grounding_trigger')
        assert hasattr(result, 'requires_grounding')

    def test_hallucination_triggers_confidence_adj(self, router, detector):
        """Test high hallucination score triggers ConfidenceAdj expert."""
        signals = detector.detect("Some query")
        result = router.route(
            signals=signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.HIGH,
            momentum=MomentumPhase.ROLLING,
            hallucination_score=0.7  # High hallucination
        )

        if result.grounding_expert:
            assert result.grounding_expert == Expert.CONFIDENCE_ADJ
            assert "hallucination" in result.grounding_trigger

    def test_get_expert_info_grounding(self, router):
        """Test get_expert_info works for grounding experts."""
        info = router.get_expert_info(Expert.ACCESS_GATEKEEPER)

        assert info["name"] == "access_gatekeeper"
        assert info["type"] == "grounding_moe"
        assert "description" in info


# =============================================================================
# Parameter Locker Source Mode Tests
# =============================================================================

class TestParameterLockerSourceMode:
    """Tests for source_mode in ParameterLocker."""

    def test_locked_params_includes_source_mode(self):
        """Test LockedParams includes source_mode field."""
        params = LockedParams(
            expert="direct",
            paradigm="Cortex",
            altitude="30000ft",
            think_depth="standard",
            source_mode="access"
        )
        assert params.source_mode == "access"

    def test_anchor_includes_source_mode(self):
        """Test anchor format includes source_mode."""
        params = LockedParams(
            expert="direct",
            paradigm="Cortex",
            altitude="30000ft",
            think_depth="standard",
            source_mode="hybrid"
        )
        anchor = params.to_anchor()
        assert "|hybrid]" in anchor

    def test_checksum_includes_source_mode(self):
        """Test different source_modes produce different checksums."""
        params_learn = LockedParams(
            expert="direct",
            paradigm="Cortex",
            altitude="30000ft",
            think_depth="standard",
            source_mode="learn"
        )
        params_access = LockedParams(
            expert="direct",
            paradigm="Cortex",
            altitude="30000ft",
            think_depth="standard",
            source_mode="access"
        )
        assert params_learn.checksum != params_access.checksum

    def test_locker_accepts_source_mode(self, locker, router, detector):
        """Test locker.lock accepts source_mode parameter."""
        signals = detector.detect("Test query")
        routing = router.route(
            signals=signals,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.HIGH,
            momentum=MomentumPhase.ROLLING
        )

        result = locker.lock(
            routing=routing,
            burnout=BurnoutLevel.GREEN,
            energy=EnergyLevel.HIGH,
            altitude=Altitude.VISION,
            source_mode="access"
        )

        assert result.params.source_mode == "access"

    def test_to_dict_includes_source_mode(self):
        """Test LockedParams.to_dict includes source_mode."""
        params = LockedParams(
            expert="direct",
            paradigm="Cortex",
            altitude="30000ft",
            think_depth="standard",
            source_mode="hybrid"
        )
        d = params.to_dict()
        assert d["source_mode"] == "hybrid"


# =============================================================================
# Cognitive State Grounding Fields Tests
# =============================================================================

class TestCognitiveStateGrounding:
    """Tests for grounding fields in CognitiveState."""

    def test_grounding_fields_exist(self):
        """Test CognitiveState has grounding fields."""
        state = CognitiveState()

        assert hasattr(state, 'grounding_mode')
        assert hasattr(state, 'grounding_budget')
        assert hasattr(state, 'oracle_cache_age')
        assert hasattr(state, 'evidence_chain_length')
        assert hasattr(state, 'hallucination_score')
        assert hasattr(state, 'last_oracle_latency')
        assert hasattr(state, 'grounding_queries_total')

    def test_grounding_defaults(self):
        """Test grounding field defaults."""
        state = CognitiveState()

        assert state.grounding_mode == "learn"
        assert state.grounding_budget == 5
        assert state.oracle_cache_age == 0
        assert state.evidence_chain_length == 0
        assert state.hallucination_score == 0.0
        assert state.last_oracle_latency == 0.0
        assert state.grounding_queries_total == 0

    def test_snapshot_includes_grounding(self):
        """Test snapshot includes grounding fields."""
        state = CognitiveState()
        state.grounding_mode = "access"
        state.grounding_budget = 3
        state.hallucination_score = 0.5

        snapshot = state.snapshot()

        assert snapshot.grounding_mode == "access"
        assert snapshot.grounding_budget == 3
        assert snapshot.hallucination_score == 0.5

    def test_batch_update_grounding(self):
        """Test batch_update works with grounding fields."""
        state = CognitiveState()
        state.batch_update({
            "grounding_mode": "hybrid",
            "grounding_budget": 2,
            "hallucination_score": 0.3
        })

        assert state.grounding_mode == "hybrid"
        assert state.grounding_budget == 2
        assert state.hallucination_score == 0.3

    def test_to_dict_includes_grounding(self):
        """Test to_dict includes grounding fields."""
        state = CognitiveState()
        state.grounding_mode = "access"
        d = state.to_dict()

        assert d["grounding_mode"] == "access"
        assert "grounding_budget" in d
        assert "hallucination_score" in d

    def test_from_dict_loads_grounding(self):
        """Test from_dict loads grounding fields."""
        data = {
            "grounding_mode": "hybrid",
            "grounding_budget": 3,
            "hallucination_score": 0.4
        }
        state = CognitiveState.from_dict(data)

        assert state.grounding_mode == "hybrid"
        assert state.grounding_budget == 3
        assert state.hallucination_score == 0.4


# =============================================================================
# Orchestrator Integration Tests
# =============================================================================

class TestOrchestratorGrounding:
    """Tests for grounding integration in CognitiveOrchestrator."""

    def test_orchestrator_has_grounding(self, orchestrator):
        """Test orchestrator has grounding bridge."""
        assert hasattr(orchestrator, 'grounding')
        assert isinstance(orchestrator.grounding, GroundingBridge)

    def test_nexus_result_includes_grounding(self, orchestrator):
        """Test NexusResult includes grounding."""
        result = orchestrator.process_message("What is the velocity?")

        assert hasattr(result, 'grounding')
        assert isinstance(result.grounding, GroundingResult)

    def test_anchor_format_v6(self, orchestrator):
        """Test anchor includes v6.0.0 grounding component."""
        result = orchestrator.process_message("Simple query")
        anchor = result.to_anchor()

        # v6.0.0 format should include source_mode
        assert "|learn" in anchor or "|access" in anchor or "|hybrid" in anchor

    def test_physics_query_triggers_grounding(self, orchestrator):
        """Test physics query triggers grounding phases."""
        result = orchestrator.process_message("Get the position of object A")

        # Should have grounding signals
        assert result.grounding is not None
        assert len(result.grounding.grounding_signals) > 0 or result.signals.grounding_score > 0

    def test_reset_session_resets_grounding(self, orchestrator):
        """Test reset_session resets grounding budget."""
        orchestrator.grounding.grounding_budget = 2
        orchestrator.reset_session()

        assert orchestrator.grounding.grounding_budget == 5

    def test_to_dict_includes_grounding_fields(self, orchestrator):
        """Test NexusResult.to_dict includes grounding fields."""
        result = orchestrator.process_message("Test query")
        d = result.to_dict()

        assert "source_mode" in d
        assert "grounding_type" in d
        assert "oracle_id" in d
        assert "grounding_confidence" in d
        assert "hallucination_score" in d
        assert "grounding_expert" in d
        assert "requires_grounding" in d


# =============================================================================
# Determinism Tests
# =============================================================================

class TestGroundingDeterminism:
    """Tests for grounding layer determinism."""

    def test_classify_deterministic(self, grounding_bridge):
        """Test classify_query is deterministic."""
        query = "Calculate the trajectory of the ball"

        result1 = grounding_bridge.classify_query(query)
        result2 = grounding_bridge.classify_query(query)

        assert result1[0] == result2[0]  # Same mode
        assert result1[1] == result2[1]  # Same reason
        assert result1[2] == result2[2]  # Same signals

    def test_signal_detection_deterministic(self, detector):
        """Test grounding signal detection is deterministic."""
        message = "Get the velocity at frame 48"

        result1 = detector.detect(message)
        result2 = detector.detect(message)

        assert result1.grounding_score == result2.grounding_score
        assert result1.grounding_type == result2.grounding_type
        assert result1.grounding == result2.grounding

    def test_checksum_deterministic(self):
        """Test LockedParams checksum is deterministic."""
        params1 = LockedParams(
            expert="direct",
            paradigm="Cortex",
            altitude="30000ft",
            think_depth="standard",
            source_mode="access"
        )
        params2 = LockedParams(
            expert="direct",
            paradigm="Cortex",
            altitude="30000ft",
            think_depth="standard",
            source_mode="access"
        )

        assert params1.checksum == params2.checksum


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestGroundingEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_message(self, grounding_bridge):
        """Test handling of empty message."""
        result = grounding_bridge.process_grounding("")
        assert result.source_mode == SourceMode.LEARN

    def test_budget_depleted(self, grounding_bridge):
        """Test behavior when grounding budget is depleted."""
        grounding_bridge.grounding_budget = 0

        result = grounding_bridge.query_oracle(
            query_type="get_position",
            params={},
            source_mode=SourceMode.ACCESS
        )

        # Should fall back to LEARN when budget depleted
        assert result.source_mode == SourceMode.LEARN
        assert "budget" in result.classification_reason

    def test_context_override(self, grounding_bridge):
        """Test context can force source mode."""
        mode, reason, signals = grounding_bridge.classify_query(
            "Some query",
            context={"force_source_mode": "access"}
        )

        assert mode == SourceMode.ACCESS
        assert reason == "context_override"

    def test_hallucination_heuristic(self, grounding_bridge):
        """Test heuristic hallucination detection."""
        score, speculation, caveats = grounding_bridge.detect_hallucination(
            "The ball will probably land at position 5",
            SourceMode.LEARN
        )

        assert speculation is True  # "probably" detected
        assert score > 0

    def test_physics_claim_in_learn_mode(self, grounding_bridge):
        """Test physics claim detection in LEARN mode."""
        score, speculation, caveats = grounding_bridge.detect_hallucination(
            "The ball will hit the wall at exactly 2.5 seconds",
            SourceMode.LEARN
        )

        assert score > 0
        assert len(caveats) > 0
