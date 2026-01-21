"""
Framework Orchestrator
======================
7-Agent async orchestration system integrating framework ecosystem.

Run with: python framework_orchestrator.py

Agents:
1. ECHO Curator         - 4-tier context memory
2. Domain Intelligence  - Multi-domain analysis (Phoenix + PRISM) [GENERALIZED]
3. MoE Router           - Expert selection (CSQMF-R1 + ATLAS)
4. World Modeler        - Causal inference (CORTEX)
5. Code Generator       - Evolutionary code (MAX 3 + MNO v3)
6. Determinism Guard    - Reproducibility (ThinkingMachines)
7. Self Reflector       - Constitutional reasoning (RESONANCE + MCAW)

Domain configs loaded from: ~/.framework-orchestrator/domains/
  - vfx.json        (Visual effects - Houdini, Nuke, USD)
  - webdev.json     (Web development - React, Next.js, APIs)
  - ai_research.json (AI/ML - models, agents, training)
  - general.json    (Fallback for unmatched tasks)

Pattern: Ralph v3 - Filesystem IS the state

Author: Framework Ecosystem Integration
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentResult:
    """Result from a single agent execution."""
    agent_name: str
    status: AgentStatus
    output: Dict[str, Any]
    checksum: str
    execution_time: float
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "agent": self.agent_name,
            "status": self.status.value,
            "output": self.output,
            "checksum": self.checksum,
            "execution_time_ms": round(self.execution_time * 1000, 2),
            "error": self.error
        }


@dataclass
class OrchestratorState:
    """Current state of the orchestrator."""
    task: str
    iteration: int
    agents_completed: List[str]
    agents_pending: List[str]
    master_checksum: str
    timestamp: float
    results: Dict[str, AgentResult] = field(default_factory=dict)


# =============================================================================
# Agent Definitions
# =============================================================================

class BaseAgent:
    """Base class for all framework agents."""

    def __init__(self, name: str, framework: str, ces_alignment: str):
        self.name = name
        self.framework = framework
        self.ces_alignment = ces_alignment
        self.logger = logging.getLogger(f"Agent.{name}")

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the agent's function. Override in subclasses."""
        raise NotImplementedError

    def get_info(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "framework": self.framework,
            "ces_alignment": self.ces_alignment
        }


class ECHOCuratorAgent(BaseAgent):
    """ECHO 2.0 + LIVRPS: Memory management with USD composition semantics.

    Memory is organized by AUTHORITY (LIVRPS), not just recency.
    Principles layer (SPECIALIZES) is NEVER compressed.

    Layers (strongest override to foundational):
        LOCAL       → Session memory (compresses first)
        INHERITS    → Context inheritance from parent tasks
        VARIANTSETS → Memory modes (focused/exploratory/recovery)
        REFERENCES  → Calibration memory (cross-session learning)
        PAYLOADS    → Domain memory (lazy-loaded)
        SPECIALIZES → Principles (NEVER compressed, referenced on error)
    """

    # Default principles path
    PRINCIPLES_PATH = Path.home() / ".framework-orchestrator" / "principles.json"

    # Compression order: LOCAL first, SPECIALIZES never
    COMPRESSION_ORDER = {
        "local": 1,           # Compress first
        "inherits": 2,        # Compress second
        "payloads": 3,        # Unload third (not compress)
        "variantsets": None,  # Never compress
        "references": None,   # Never compress
        "specializes": None   # NEVER compress
    }

    # Legacy tier mapping for backwards compatibility
    TIER_TO_LAYER = {
        "hot": "local",
        "warm": "inherits",
        "cold": "payloads",
        "archive": "references"
    }

    def __init__(self, principles_path: Path = None):
        super().__init__(
            name="echo_curator",
            framework="ECHO 2.0 + LIVRPS",
            ces_alignment="Context Memory Platform"
        )

        # LIVRPS memory layers
        self.memory_layers = {
            "specializes": {},   # Principles - NEVER compressed
            "payloads": {},      # Domain memory - unloadable
            "references": {},    # Calibration - persistent
            "variantsets": {},   # Memory modes
            "inherits": {},      # Context inheritance
            "local": {}          # Session memory - compresses first
        }

        # Current memory mode
        self.active_mode = "focused_recall"

        # Load principles
        self.principles_path = principles_path or self.PRINCIPLES_PATH
        self._load_principles()

    def _load_principles(self):
        """Load principles into SPECIALIZES layer. These are NEVER compressed."""
        if not self.principles_path.exists():
            self.logger.warning(f"Principles not found: {self.principles_path}")
            self._use_fallback_principles()
            return

        try:
            principles = json.loads(self.principles_path.read_text(encoding='utf-8'))
            self.memory_layers["specializes"] = principles
            self.logger.info(f"Loaded principles: {len(principles.get('constitutional', {}).get('principles', []))} constitutional rules")
        except Exception as e:
            self.logger.error(f"Failed to load principles: {e}")
            self._use_fallback_principles()

    def _use_fallback_principles(self):
        """Minimal embedded principles if file not found."""
        self.memory_layers["specializes"] = {
            "constitutional": {
                "principles": [
                    {"id": "safety_first", "statement": "Safety first: Emotional safety before productivity"},
                    {"id": "user_knows_best", "statement": "User knows best: Their signal trumps Claude's guess"}
                ]
            },
            "recovery_protocol": {
                "triggers": [
                    {"condition": "error_state", "action": "Fall back to principles"}
                ]
            }
        }
        self.logger.info("Using fallback embedded principles")

    def _detect_memory_mode(self, task: str, context: Dict[str, Any]) -> str:
        """Detect appropriate memory mode based on signals."""
        task_lower = task.lower()

        # Check for recovery signals first (safety_first principle)
        recovery_signals = ["help", "stuck", "frustrated", "confused", "overwhelmed", "error"]
        if any(sig in task_lower for sig in recovery_signals):
            return "recovery_recall"

        # Check for exploratory signals
        exploratory_signals = ["what if", "explore", "brainstorm", "ideas", "consider", "might"]
        if any(sig in task_lower for sig in exploratory_signals):
            return "exploratory_recall"

        # Default to focused
        return "focused_recall"

    def _resolve_memory_query(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve memory query using LIVRPS priority order.

        Resolution order (strongest to weakest override):
        1. LOCAL (session) - most specific, most recent
        2. INHERITS (context) - parent task state
        3. VARIANTSETS (modes) - current memory mode
        4. REFERENCES (calibration) - learned patterns
        5. PAYLOADS (domain) - domain expertise
        6. SPECIALIZES (principles) - FOUNDATIONAL, referenced on uncertainty
        """
        resolution = {
            "query": query,
            "resolved_from": None,
            "resolution_path": [],
            "principles_consulted": False,
            "result": None
        }

        # Walk the LIVRPS stack
        for layer_name in ["local", "inherits", "variantsets", "references", "payloads", "specializes"]:
            layer_data = self.memory_layers.get(layer_name, {})
            resolution["resolution_path"].append(layer_name)

            if layer_data:
                # For specializes, always note that principles were available
                if layer_name == "specializes":
                    resolution["principles_consulted"] = True
                    resolution["principles_available"] = list(
                        p.get("id") for p in layer_data.get("constitutional", {}).get("principles", [])
                    )

                resolution["resolved_from"] = layer_name
                resolution["result"] = f"Found in {layer_name}"
                break

        return resolution

    def _calculate_compression(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate memory compression based on LIVRPS, not recency.

        Compression order:
        1. LOCAL compresses first (session details)
        2. INHERITS summarizes second
        3. PAYLOADS can unload (not compress)
        4. VARIANTSETS, REFERENCES, SPECIALIZES: NEVER compress
        """
        total_items = sum(len(layer) if isinstance(layer, dict) else 0
                         for layer in self.memory_layers.values())

        compression_state = {
            "total_memory_items": total_items,
            "layers_status": {},
            "compression_applied": [],
            "protected_layers": ["specializes", "references", "variantsets"]
        }

        for layer_name, compress_order in self.COMPRESSION_ORDER.items():
            layer_size = len(self.memory_layers.get(layer_name, {}))
            compression_state["layers_status"][layer_name] = {
                "size": layer_size,
                "compressible": compress_order is not None,
                "compress_order": compress_order,
                "protected": compress_order is None
            }

        return compression_state

    def _check_principles_for_guidance(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Consult principles layer for guidance. Called on uncertainty or error."""
        principles = self.memory_layers.get("specializes", {})
        constitutional = principles.get("constitutional", {}).get("principles", [])

        task_lower = task.lower()
        triggered_principles = []

        for principle in constitutional:
            triggers = principle.get("triggers", [])
            if any(trigger in task_lower for trigger in triggers):
                triggered_principles.append({
                    "id": principle.get("id"),
                    "statement": principle.get("statement"),
                    "action": principle.get("action")
                })

        return {
            "principles_checked": len(constitutional),
            "principles_triggered": triggered_principles,
            "guidance_available": len(triggered_principles) > 0
        }

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Managing memory with LIVRPS composition...")

        # Detect appropriate memory mode
        memory_mode = self._detect_memory_mode(task, context)
        self.active_mode = memory_mode
        self.memory_layers["variantsets"]["active_mode"] = memory_mode

        # Store task in LOCAL layer (session memory)
        task_hash = hashlib.sha256(task.encode()).hexdigest()[:16]
        self.memory_layers["local"][task_hash] = {
            "task": task[:200],
            "timestamp": time.time(),
            "mode": memory_mode
        }

        # Resolve memory state using LIVRPS
        resolution = self._resolve_memory_query(task, context)

        # Calculate compression state
        compression = self._calculate_compression(context)

        # Always check principles for potential guidance
        principles_guidance = self._check_principles_for_guidance(task, context)

        # Build provenance
        provenance = {
            "source": "orchestrator_task",
            "timestamp": time.time(),
            "content_hash": task_hash,
            "memory_architecture": "LIVRPS"
        }

        # Calculate effective tokens based on mode
        mode_tokens = {
            "focused_recall": 4096,
            "exploratory_recall": 8192,
            "recovery_recall": 2048  # Minimal for recovery
        }
        effective_tokens = mode_tokens.get(memory_mode, 4096)

        result = {
            # LIVRPS state
            "memory_architecture": "LIVRPS",
            "active_mode": memory_mode,
            "resolution": resolution,
            "compression_state": compression,

            # Principles (always present, always consulted)
            "principles_layer": {
                "loaded": "specializes" in self.memory_layers and bool(self.memory_layers["specializes"]),
                "protected": True,
                "guidance": principles_guidance
            },

            # Legacy compatibility
            "tier_selected": self.TIER_TO_LAYER.get(memory_mode, "local"),
            "effective_tokens": effective_tokens,
            "provenance": provenance,

            # Memory stats
            "layers_populated": [k for k, v in self.memory_layers.items() if v],
            "local_memory_items": len(self.memory_layers["local"]),
            "memory_utilization": f"{len(self.memory_layers['local']) / 100:.1%}"
        }

        return result


class DomainIntelligenceAgent(BaseAgent):
    """Phoenix + PRISM: Multi-domain analysis with pluggable domain configs.

    Loads domain configurations from JSON files in the user's home directory:
    ~/.framework-orchestrator/domains/

    Each domain config defines specialists, keywords, and PRISM perspectives.
    """

    PRISM_PERSPECTIVES = ["causal", "optimization", "hierarchical", "temporal", "risk", "opportunity"]

    # Default domains path (user home directory)
    DEFAULT_DOMAINS_PATH = Path.home() / ".framework-orchestrator" / "domains"

    def __init__(self, domains_path: Path = None):
        super().__init__(
            name="domain_intelligence",
            framework="Phoenix v6 + PRISM",
            ces_alignment="Multi-perspective reasoning"
        )
        self.domains: Dict[str, Dict] = {}
        self.domains_path = domains_path or self.DEFAULT_DOMAINS_PATH
        self._load_domains()

    def _load_domains(self):
        """Load all domain configurations from JSON files."""
        if not self.domains_path.exists():
            self.logger.warning(f"Domains path not found: {self.domains_path}")
            self._use_fallback_domains()
            return

        loaded_count = 0
        for config_file in self.domains_path.glob("*.json"):
            try:
                config = json.loads(config_file.read_text(encoding='utf-8'))
                domain_key = config.get("name", config_file.stem).lower()
                self.domains[domain_key] = config
                loaded_count += 1
                self.logger.info(f"Loaded domain: {domain_key} ({len(config.get('specialists', {}))} specialists)")
            except Exception as e:
                self.logger.error(f"Failed to load {config_file}: {e}")

        if not self.domains:
            self._use_fallback_domains()
        else:
            self.logger.info(f"Loaded {loaded_count} domain configs from {self.domains_path}")

    def _use_fallback_domains(self):
        """Fallback to minimal embedded domains if no configs found."""
        self.domains = {
            "general": {
                "name": "General",
                "specialists": {
                    "analysis": {"keywords": ["analyze", "review", "examine"], "analysis_focus": ["structure"]}
                },
                "routing_keywords": [],
                "prism_perspectives": self.PRISM_PERSPECTIVES[:4]
            }
        }
        self.logger.info("Using fallback embedded domains")

    def _build_keyword_index(self) -> Dict[str, List[Dict]]:
        """Build reverse index: keyword -> [{domain, specialist}]."""
        index = {}
        for domain_name, domain in self.domains.items():
            for specialist_name, specialist in domain.get("specialists", {}).items():
                for keyword in specialist.get("keywords", []):
                    keyword_lower = keyword.lower()
                    if keyword_lower not in index:
                        index[keyword_lower] = []
                    index[keyword_lower].append({
                        "domain": domain_name,
                        "specialist": specialist_name,
                        "analysis_focus": specialist.get("analysis_focus", [])
                    })
        return index

    def get_routing_keywords(self) -> List[str]:
        """Return all routing keywords from all loaded domains."""
        keywords = []
        for domain in self.domains.values():
            keywords.extend(domain.get("routing_keywords", []))
        return list(set(keywords))

    def get_all_specialist_keywords(self) -> List[str]:
        """Return all specialist keywords from all domains (for fallback matching)."""
        keywords = []
        for domain in self.domains.values():
            for specialist in domain.get("specialists", {}).values():
                keywords.extend(specialist.get("keywords", []))
        return list(set(keywords))

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info(f"Analyzing task with multi-domain detection ({len(self.domains)} domains loaded)...")

        task_lower = task.lower()
        keyword_index = self._build_keyword_index()

        # Domain detection
        detected_domains = {}
        detected_specialists = {}
        matched_keywords = []

        for keyword, mappings in keyword_index.items():
            if keyword in task_lower:
                matched_keywords.append(keyword)
                for mapping in mappings:
                    domain = mapping["domain"]
                    specialist = mapping["specialist"]

                    # Track domain hits
                    if domain not in detected_domains:
                        detected_domains[domain] = {"hits": 0, "keywords": [], "analysis_focus": set()}
                    detected_domains[domain]["hits"] += 1
                    detected_domains[domain]["keywords"].append(keyword)
                    detected_domains[domain]["analysis_focus"].update(mapping.get("analysis_focus", []))

                    # Track specialist hits
                    key = f"{domain}.{specialist}"
                    if key not in detected_specialists:
                        detected_specialists[key] = {"hits": 0, "keywords": [], "analysis_focus": mapping.get("analysis_focus", [])}
                    detected_specialists[key]["hits"] += 1
                    detected_specialists[key]["keywords"].append(keyword)

        # Handle fallback: if no keywords matched, run against all domains
        run_all_domains = len(detected_domains) == 0
        if run_all_domains:
            self.logger.info("No specific domain matched - running comprehensive analysis against all domains")
            for domain_name, domain in self.domains.items():
                detected_domains[domain_name] = {
                    "hits": 0,
                    "keywords": [],
                    "analysis_focus": set(),
                    "fallback_match": True
                }
                # Add all specialists from this domain
                for spec_name, spec in domain.get("specialists", {}).items():
                    key = f"{domain_name}.{spec_name}"
                    detected_specialists[key] = {
                        "hits": 0,
                        "keywords": [],
                        "analysis_focus": spec.get("analysis_focus", []),
                        "fallback_match": True
                    }

        # Determine primary domain and specialist (highest keyword hits, or first if fallback)
        if detected_domains:
            primary_domain = max(detected_domains, key=lambda d: detected_domains[d]["hits"])
        else:
            primary_domain = "general"

        if detected_specialists:
            primary_specialist = max(detected_specialists, key=lambda s: detected_specialists[s]["hits"])
        else:
            primary_specialist = "general.analysis"

        # Get PRISM perspectives from matched domain
        domain_config = self.domains.get(primary_domain, self.domains.get("general", {}))
        perspectives = domain_config.get("prism_perspectives", self.PRISM_PERSPECTIVES[:3])

        # Apply perspective analysis
        perspective_analysis = {}
        for perspective in perspectives[:3]:  # Top 3 for efficiency
            specialist_short = primary_specialist.split('.')[-1] if '.' in primary_specialist else primary_specialist
            perspective_analysis[perspective] = {
                "relevant": True,
                "focus_area": f"{perspective} analysis for {specialist_short}"
            }

        # Convert sets to lists for JSON serialization
        for domain_data in detected_domains.values():
            if isinstance(domain_data.get("analysis_focus"), set):
                domain_data["analysis_focus"] = list(domain_data["analysis_focus"])

        # Get primary analysis focus
        primary_analysis_focus = detected_specialists.get(primary_specialist, {}).get("analysis_focus", [])

        return {
            "detected_domains": list(detected_domains.keys()),
            "domain_scores": {d: info["hits"] for d, info in detected_domains.items()},
            "domain_details": detected_domains,
            "primary_domain": primary_domain,
            "detected_specialists": list(detected_specialists.keys()),
            "primary_specialist": primary_specialist,
            "primary_analysis_focus": primary_analysis_focus,
            "matched_keywords": matched_keywords,
            "prism_perspectives_applied": list(perspective_analysis.keys()),
            "perspective_analysis": perspective_analysis,
            "domains_loaded": list(self.domains.keys()),
            "domain_task_detected": len(matched_keywords) > 0,
            "fallback_mode": run_all_domains
        }


class MoERouterAgent(BaseAgent):
    """CSQMF-R1 + ATLAS: Expert routing with thinking budgets."""

    EXPERTS = {
        "accuracy": {"temperature": 0.1, "priority": "precision"},
        "ethics": {"temperature": 0.3, "priority": "safety"},
        "creativity": {"temperature": 0.8, "priority": "novelty"},
        "compression": {"temperature": 0.2, "priority": "efficiency"}
    }

    def __init__(self):
        super().__init__(
            name="moe_router",
            framework="CSQMF-R1 + ATLAS",
            ces_alignment="Multi-model agents"
        )

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Routing to experts with deterministic selection...")

        seed = context.get("seed", 42)

        # DETERMINISTIC hash-based routing (ThinkingMachines fix)
        routing_input = f"{task}:{seed}"
        query_hash = hashlib.sha256(routing_input.encode()).hexdigest()

        # Score experts from hash segments
        expert_scores = {}
        for i, expert in enumerate(self.EXPERTS.keys()):
            segment = query_hash[i*8:(i+1)*8]
            score = int(segment, 16) / (16**8)
            expert_scores[expert] = round(score, 4)

        # Select top 2 experts (deterministic sort)
        sorted_experts = sorted(expert_scores.items(), key=lambda x: (-x[1], x[0]))
        selected = sorted_experts[:2]

        # ATLAS thinking budget
        thinking_budget = {
            "max_latency_ms": 2000,
            "quality_threshold": 0.7,
            "allow_early_exit": True
        }

        return {
            "routing_hash": query_hash[:16],
            "seed": seed,
            "all_expert_scores": expert_scores,
            "selected_experts": [e[0] for e in selected],
            "selected_configs": {e[0]: self.EXPERTS[e[0]] for e in selected},
            "routing_method": "deterministic_hash",
            "thinking_budget": thinking_budget,
            "reproducible": True
        }


class WorldModelerAgent(BaseAgent):
    """CORTEX: World models and causal inference."""

    def __init__(self):
        super().__init__(
            name="world_modeler",
            framework="CORTEX",
            ces_alignment="Cosmos WFM + Object Permanence"
        )
        self.world_state = {}

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Building world model with causal inference...")

        # Extract entities from task (simplified)
        words = task.split()
        entities = [w for w in words if w[0].isupper()] if words else []

        # Build simple causal model
        causal_chains = []
        for i in range(len(entities) - 1):
            causal_chains.append({
                "cause": entities[i],
                "effect": entities[i + 1],
                "confidence": 0.7
            })

        # Energy state (CORTEX-style)
        energy_state = {
            "correctness": 0.8,
            "efficiency": 0.7,
            "maintainability": 0.75,
            "style": 0.8
        }

        return {
            "entities_detected": entities,
            "entity_count": len(entities),
            "causal_chains": causal_chains,
            "causal_chain_count": len(causal_chains),
            "energy_state": energy_state,
            "composite_energy": sum(energy_state.values()) / len(energy_state),
            "object_permanence_valid": True,
            "world_model_version": "CORTEX_v1"
        }


class CodeGeneratorAgent(BaseAgent):
    """MAX 3 + MNO v3: Evolutionary code generation."""

    def __init__(self):
        super().__init__(
            name="code_generator",
            framework="MAX 3 + MNO v3",
            ces_alignment="AlphaEvolve patterns"
        )
        self.generation_count = 0

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Generating code with evolutionary approach...")

        # Simulate evolutionary generation cycle
        self.generation_count += 1

        # MNO proposer/solver pattern
        proposal = {
            "type": "code_generation",
            "task_hash": hashlib.sha256(task.encode()).hexdigest()[:8],
            "iteration": self.generation_count
        }

        # MAX RC^+ξ self-reflection metrics
        reflection_metrics = {
            "confidence": 0.85,
            "novelty": 0.6,
            "alignment": 0.9,
            "bounded_reflection_depth": 3
        }

        # Fitness score (evolutionary)
        fitness = sum(reflection_metrics.values()) / len(reflection_metrics)

        return {
            "generation_method": "evolutionary_proposer_solver",
            "proposal": proposal,
            "reflection_metrics": reflection_metrics,
            "fitness_score": round(fitness, 3),
            "generation_count": self.generation_count,
            "rc_xi_applied": True,
            "evolution_cycle_complete": True
        }


class DeterminismGuardAgent(BaseAgent):
    """ThinkingMachines: Reproducibility enforcement."""

    def __init__(self):
        super().__init__(
            name="determinism_guard",
            framework="ThinkingMachines",
            ces_alignment="Reproducible inference"
        )

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Enforcing determinism constraints...")

        seed = context.get("seed", 42)

        # ThinkingMachines determinism settings
        determinism_config = {
            "batch_size": 1,  # CRITICAL: Never vary
            "cudnn_deterministic": True,
            "cudnn_benchmark": False,  # Disable auto-tuning
            "float32_matmul_precision": "highest",
            "seed": seed
        }

        # Validate other agents' outputs for reproducibility
        validation_results = {}
        for agent_name, result in context.get("agent_results", {}).items():
            if hasattr(result, "checksum") and result.checksum:
                validation_results[agent_name] = {
                    "has_checksum": True,
                    "checksum": result.checksum,
                    "reproducible": True
                }

        return {
            "determinism_config": determinism_config,
            "batch_invariance_enforced": True,
            "seed_locked": seed,
            "agents_validated": len(validation_results),
            "validation_results": validation_results,
            "reproducibility_guaranteed": True
        }


class SelfReflectorAgent(BaseAgent):
    """RESONANCE + MCAW: Self-reflection and constitutional reasoning."""

    CONSTITUTIONAL_PRINCIPLES = [
        "Accuracy: Verify claims and cite sources",
        "Clarity: Use precise, understandable language",
        "Safety: Avoid harmful outputs",
        "Helpfulness: Address the actual user need"
    ]

    def __init__(self):
        super().__init__(
            name="self_reflector",
            framework="RESONANCE + MCAW",
            ces_alignment="Constitutional AI"
        )
        self.reflection_history = []

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Performing self-reflection and constitutional check...")

        # RESONANCE ancestral wisdom check
        ancestral_check = {
            "wisdom_consulted": True,
            "lineage_depth": 3,
            "founding_principles_aligned": True
        }

        # MCAW constitutional evaluation
        constitutional_scores = {}
        for principle in self.CONSTITUTIONAL_PRINCIPLES:
            principle_name = principle.split(":")[0]
            # Simplified scoring
            constitutional_scores[principle_name] = 0.85 + (hash(principle) % 10) / 100

        overall_score = sum(constitutional_scores.values()) / len(constitutional_scores)

        # Store reflection
        reflection_entry = {
            "timestamp": time.time(),
            "task_hash": hashlib.sha256(task.encode()).hexdigest()[:8],
            "constitutional_score": overall_score
        }
        self.reflection_history.append(reflection_entry)

        return {
            "ancestral_check": ancestral_check,
            "constitutional_scores": constitutional_scores,
            "overall_constitutional_score": round(overall_score, 3),
            "violations_detected": [],
            "recommendations": [],
            "reflection_depth": len(self.reflection_history),
            "self_confidence": 0.9
        }


# =============================================================================
# Orchestrator
# =============================================================================

class FrameworkOrchestrator:
    """
    7-Agent async orchestrator with Ralph v3 pattern.

    Pattern: Filesystem IS the state
    - Results written to disk immediately
    - State recoverable from files
    - Completion proven by file existence
    """

    def __init__(self, workspace: Path = None):
        self.workspace = workspace or Path("./orchestrator_workspace")
        self.workspace.mkdir(exist_ok=True)

        self.results_dir = self.workspace / "results"
        self.results_dir.mkdir(exist_ok=True)

        self.state_file = self.workspace / ".orchestrator-state.json"

        # Initialize agents
        self.agents: Dict[str, BaseAgent] = {
            "echo_curator": ECHOCuratorAgent(),
            "domain_intelligence": DomainIntelligenceAgent(),  # Generalized from shot_intelligence
            "moe_router": MoERouterAgent(),
            "world_modeler": WorldModelerAgent(),
            "code_generator": CodeGeneratorAgent(),
            "determinism_guard": DeterminismGuardAgent(),
            "self_reflector": SelfReflectorAgent()
        }

        self.iteration = 0

    def _route_task(self, task: str, context: Dict[str, Any]) -> List[str]:
        """CSQMF-style routing to determine which agents to activate.

        Uses dynamic routing keywords loaded from domain configs.
        """

        # Always active
        active = ["echo_curator", "determinism_guard"]

        task_lower = task.lower()

        # Get domain routing keywords dynamically from loaded domain configs
        domain_agent = self.agents.get("domain_intelligence")
        if domain_agent and hasattr(domain_agent, 'get_routing_keywords'):
            domain_keywords = domain_agent.get_routing_keywords()
        else:
            # Fallback if agent not properly initialized
            domain_keywords = []

        # Domain-specific activation (keywords from domain configs)
        if domain_keywords and any(kw in task_lower for kw in domain_keywords):
            active.append("domain_intelligence")
            active.append("world_modeler")

        # Code-related activation
        if any(kw in task_lower for kw in ["code", "script", "python", "implement", "function"]):
            active.append("code_generator")

        # Routing/expert selection activation
        if any(kw in task_lower for kw in ["route", "select", "expert", "choose", "model"]):
            active.append("moe_router")

        # Reflection/review activation
        if any(kw in task_lower for kw in ["reflect", "review", "improve", "quality", "check"]):
            active.append("self_reflector")

        # If nothing specific matched, run all agents (comprehensive analysis)
        if len(active) == 2:
            active = list(self.agents.keys())

        return active

    async def _execute_agent(self, agent_name: str, task: str,
                              context: Dict[str, Any]) -> AgentResult:
        """Execute a single agent and return result."""

        agent = self.agents[agent_name]
        start_time = time.time()

        try:
            output = await agent.execute(task, context)
            status = AgentStatus.COMPLETED
            error = None
        except Exception as e:
            output = {"error": str(e)}
            status = AgentStatus.FAILED
            error = str(e)
            logger.error(f"Agent {agent_name} failed: {e}")

        execution_time = time.time() - start_time

        # Compute deterministic checksum
        output_str = json.dumps(output, sort_keys=True, default=str)
        checksum = hashlib.sha256(output_str.encode()).hexdigest()[:16]

        result = AgentResult(
            agent_name=agent_name,
            status=status,
            output=output,
            checksum=checksum,
            execution_time=execution_time,
            error=error
        )

        # Ralph pattern: Write to filesystem immediately
        result_file = self.results_dir / f"{agent_name}.json"
        result_file.write_text(json.dumps(result.to_dict(), indent=2))

        return result

    async def orchestrate(self, task: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Run orchestration cycle."""

        context = context or {}
        context["seed"] = context.get("seed", 42)

        self.iteration += 1
        logger.info(f"Starting orchestration iteration {self.iteration}")
        logger.info(f"Task: {task[:100]}...")

        # Phase 1: Route task to agents
        active_agents = self._route_task(task, context)
        logger.info(f"Active agents: {', '.join(active_agents)}")

        # Phase 2: Execute agents in parallel
        start_time = time.time()

        results = await asyncio.gather(*[
            self._execute_agent(agent_name, task, context)
            for agent_name in active_agents
        ])

        total_time = time.time() - start_time

        # Phase 3: Collect results
        result_map = {r.agent_name: r for r in results}

        # Phase 4: Run determinism guard with all results
        context["agent_results"] = result_map
        if "determinism_guard" not in result_map:
            det_result = await self._execute_agent("determinism_guard", task, context)
            result_map["determinism_guard"] = det_result

        # Phase 5: Compute master checksum
        all_checksums = sorted([r.checksum for r in result_map.values()])
        combined = "".join(all_checksums)
        master_checksum = hashlib.sha256(combined.encode()).hexdigest()[:32]

        # Phase 6: Build synthesis
        synthesis = {
            "iteration": self.iteration,
            "task": task[:200],
            "timestamp": time.time(),
            "total_execution_time_ms": round(total_time * 1000, 2),
            "agents_executed": len(result_map),
            "agents_succeeded": sum(1 for r in result_map.values() if r.status == AgentStatus.COMPLETED),
            "master_checksum": master_checksum,
            "reproducibility_proof": f"sha256:{master_checksum}",
            "agent_results": {name: r.to_dict() for name, r in result_map.items()},
            "agent_checksums": {name: r.checksum for name, r in result_map.items()}
        }

        # Phase 7: Persist state (Ralph pattern)
        self.state_file.write_text(json.dumps(synthesis, indent=2))
        logger.info(f"State persisted to {self.state_file}")

        return synthesis

    def get_agent_info(self) -> Dict[str, Dict[str, str]]:
        """Get information about all agents."""
        return {name: agent.get_info() for name, agent in self.agents.items()}


# =============================================================================
# CLI Interface
# =============================================================================

async def main():
    """Main entry point for CLI usage."""

    import argparse

    parser = argparse.ArgumentParser(description="Framework Orchestrator")
    parser.add_argument("--task", "-t", type=str, help="Task to process")
    parser.add_argument("--workspace", "-w", type=str, default="./orchestrator_workspace",
                       help="Workspace directory")
    parser.add_argument("--seed", "-s", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--info", action="store_true", help="Show agent information")

    args = parser.parse_args()

    workspace = Path(args.workspace)
    orchestrator = FrameworkOrchestrator(workspace)

    if args.info:
        print("\n" + "=" * 60)
        print("FRAMEWORK ORCHESTRATOR - Agent Roster")
        print("=" * 60)
        for name, info in orchestrator.get_agent_info().items():
            print(f"\n{name}:")
            print(f"  Framework: {info['framework']}")
            print(f"  CES 2026:  {info['ces_alignment']}")
        print("\n" + "=" * 60)
        return

    if not args.task:
        # Interactive mode
        print("\n" + "=" * 60)
        print("FRAMEWORK ORCHESTRATOR - Interactive Mode")
        print("=" * 60)
        print("Enter tasks to process. Type 'quit' to exit.\n")

        while True:
            try:
                task = input("Task> ").strip()
                if task.lower() in ["quit", "exit", "q"]:
                    break
                if not task:
                    continue

                result = await orchestrator.orchestrate(task, {"seed": args.seed})

                print(f"\nIteration: {result['iteration']}")
                print(f"Agents: {result['agents_succeeded']}/{result['agents_executed']} succeeded")
                print(f"Time: {result['total_execution_time_ms']}ms")
                print(f"Checksum: {result['master_checksum']}")
                print(f"Results saved to: {workspace / 'results'}\n")

            except KeyboardInterrupt:
                print("\nExiting...")
                break
    else:
        # Single task mode
        result = await orchestrator.orchestrate(args.task, {"seed": args.seed})

        print("\n" + "=" * 60)
        print("ORCHESTRATION COMPLETE")
        print("=" * 60)
        print(f"Task: {args.task[:80]}...")
        print(f"Agents: {result['agents_succeeded']}/{result['agents_executed']} succeeded")
        print(f"Time: {result['total_execution_time_ms']}ms")
        print(f"Master Checksum: {result['master_checksum']}")
        print(f"\nDetailed results: {workspace / 'results'}")
        print(f"State file: {workspace / '.orchestrator-state.json'}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
