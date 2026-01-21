"""Tests for Framework Orchestrator."""

import asyncio
import json
import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework_orchestrator import (
    BaseAgent,
    ECHOCuratorAgent,
    DomainIntelligenceAgent,
    MoERouterAgent,
    DeterminismGuardAgent,
    FrameworkOrchestrator,
)


class TestBaseAgent:
    """Tests for BaseAgent interface."""

    def test_agent_has_required_attributes(self):
        """All agents should have name, framework, ces_alignment."""

        class TestAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    name="test",
                    framework="Test Framework",
                    ces_alignment="Test alignment",
                )

            async def execute(self, task, context):
                return {"test": True}

        agent = TestAgent()
        assert agent.name == "test"
        assert agent.framework == "Test Framework"
        assert agent.ces_alignment == "Test alignment"


class TestECHOCurator:
    """Tests for ECHO Curator agent."""

    @pytest.fixture
    def agent(self):
        return ECHOCuratorAgent()

    def test_memory_layers_initialized(self, agent):
        """Memory layers should be initialized."""
        assert "local" in agent.memory_layers
        assert "inherits" in agent.memory_layers
        assert "variantsets" in agent.memory_layers
        assert "references" in agent.memory_layers
        assert "payloads" in agent.memory_layers
        assert "specializes" in agent.memory_layers

    def test_compression_order(self, agent):
        """Compression order should be defined."""
        assert agent.COMPRESSION_ORDER["local"] == 1
        assert agent.COMPRESSION_ORDER["inherits"] == 2
        assert agent.COMPRESSION_ORDER["specializes"] is None  # Never compress

    @pytest.mark.asyncio
    async def test_execute_returns_livrps_structure(self, agent):
        """Execute should return LIVRPS memory structure."""
        result = await agent.execute("test query", {})
        assert result["memory_architecture"] == "LIVRPS"
        assert "active_mode" in result
        assert "compression_state" in result
        assert "principles_layer" in result

    def test_detect_memory_mode_focused(self, agent):
        """Should detect focused mode for debugging tasks."""
        mode = agent._detect_memory_mode("debug this error", {})
        assert mode == "focused_recall"

    def test_detect_memory_mode_exploratory(self, agent):
        """Should detect exploratory mode for brainstorming."""
        mode = agent._detect_memory_mode("what if we tried", {})
        assert mode == "exploratory_recall"


class TestDomainIntelligence:
    """Tests for Domain Intelligence agent."""

    @pytest.fixture
    def agent(self, tmp_path):
        # Create a test domain
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()

        test_domain = {
            "name": "Test Domain",
            "specialists": {
                "test_specialist": {
                    "keywords": ["test", "example"],
                    "analysis_focus": ["metric1"],
                }
            },
            "routing_keywords": ["test", "example"],
            "prism_perspectives": ["causal"],
        }

        (domains_dir / "test.json").write_text(json.dumps(test_domain))
        return DomainIntelligenceAgent(domains_path=domains_dir)

    def test_domains_loaded(self, agent):
        """Domains should be loaded from path."""
        assert len(agent.domains) > 0
        assert "test domain" in agent.domains

    def test_get_routing_keywords(self, agent):
        """Should return routing keywords from all domains."""
        keywords = agent.get_routing_keywords()
        assert "test" in keywords
        assert "example" in keywords

    @pytest.mark.asyncio
    async def test_execute_detects_domain(self, agent):
        """Execute should detect matching domain."""
        result = await agent.execute("test this feature", {})
        assert "detected_domains" in result
        assert "test domain" in result["detected_domains"]


class TestMoERouter:
    """Tests for MoE Router agent."""

    @pytest.fixture
    def agent(self):
        return MoERouterAgent()

    def test_experts_defined(self, agent):
        """Experts should be defined."""
        assert len(agent.experts) > 0
        assert "systems_architect" in agent.experts

    @pytest.mark.asyncio
    async def test_hash_based_routing_deterministic(self, agent):
        """Same task should always route to same expert."""
        task = "design the system architecture"
        result1 = await agent.execute(task, {})
        result2 = await agent.execute(task, {})
        assert result1["selected_expert"] == result2["selected_expert"]
        assert result1["expert_hash"] == result2["expert_hash"]

    @pytest.mark.asyncio
    async def test_execute_returns_gating_weights(self, agent):
        """Execute should return gating weights."""
        result = await agent.execute("test task", {})
        assert "gating_weights" in result
        assert result["routing_type"] == "hash_based"


class TestDeterminismGuard:
    """Tests for Determinism Guard agent."""

    @pytest.fixture
    def agent(self):
        return DeterminismGuardAgent()

    @pytest.mark.asyncio
    async def test_batch_size_check(self, agent):
        """Should check batch size."""
        result = await agent.execute("check determinism", {})
        assert "batch_size_check" in result
        assert result["batch_size_check"]["required"] == 1

    @pytest.mark.asyncio
    async def test_cuda_settings_check(self, agent):
        """Should check CUDA settings."""
        result = await agent.execute("verify reproducibility", {})
        assert "cuda_settings" in result


class TestFrameworkOrchestrator:
    """Tests for the main orchestrator."""

    @pytest.fixture
    def orchestrator(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return FrameworkOrchestrator(workspace_path=workspace)

    def test_agents_registered(self, orchestrator):
        """All 7 agents should be registered."""
        assert len(orchestrator.agents) == 7
        assert "echo_curator" in orchestrator.agents
        assert "domain_intelligence" in orchestrator.agents
        assert "moe_router" in orchestrator.agents
        assert "world_modeler" in orchestrator.agents
        assert "code_generator" in orchestrator.agents
        assert "determinism_guard" in orchestrator.agents
        assert "self_reflector" in orchestrator.agents

    def test_route_task_always_includes_core(self, orchestrator):
        """echo_curator and determinism_guard should always be active."""
        active = orchestrator._route_task("any task", {})
        assert "echo_curator" in active
        assert "determinism_guard" in active

    @pytest.mark.asyncio
    async def test_orchestrate_returns_results(self, orchestrator):
        """Orchestrate should return results from active agents."""
        result = await orchestrator.orchestrate("test task", {})
        assert "task" in result
        assert "agents_activated" in result
        assert "results" in result
        assert "echo_curator" in result["results"]

    @pytest.mark.asyncio
    async def test_orchestrate_execution_time(self, orchestrator):
        """Orchestrate should include execution time."""
        result = await orchestrator.orchestrate("test", {})
        assert "execution_time_ms" in result


class TestChecksums:
    """Tests for checksum generation."""

    @pytest.mark.asyncio
    async def test_agent_output_has_checksum(self):
        """Agent outputs should include checksums."""
        agent = ECHOCuratorAgent()
        result = await agent.execute("test", {})
        # Checksum is added by orchestrator, but we can verify structure
        assert "provenance" in result
        assert "content_hash" in result["provenance"]

    @pytest.mark.asyncio
    async def test_checksums_reproducible(self):
        """Same input should produce same checksum."""
        agent = MoERouterAgent()
        result1 = await agent.execute("exact same task", {})
        result2 = await agent.execute("exact same task", {})
        assert result1["expert_hash"] == result2["expert_hash"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
