# Orchestra v7.1.0 — Comprehensive Codebase Index

**Generated**: 2026-01-31
**Version**: 7.1.0
**Tests**: 1,495 (all passing)
**Total LOC**: ~32,000 (src/orchestra/)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Module Map](#module-map)
3. [8-Phase NEXUS Pipeline](#8-phase-nexus-pipeline)
4. [Core Data Structures](#core-data-structures)
5. [Test Coverage Map](#test-coverage-map)
6. [Entry Points](#entry-points)
7. [Dependencies](#dependencies)
8. [Version History](#version-history)

---

## Architecture Overview

Orchestra is a cognitive orchestration system implementing **ThinkingMachines [He2025]** compliant deterministic execution with:

- **8-Phase NEXUS Pipeline**: RETRIEVE → CLASSIFY → GROUND → DETECT → CASCADE → LOCK → EXECUTE → UPDATE
- **Cognitive Safety MoE**: 7 intervention experts + 4 grounding experts (fixed priority, first-match-wins)
- **BCM Stigmergic Learning**: Trail-based expert confidence (v7.0.0)
- **Cognitive Batch Invariance**: Fixed tile size, Kahan summation (v7.1.0)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRA ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Message → cognitive_orchestrator.py (8-Phase NEXUS)                       │
│                    │                                                         │
│     ┌──────────────┼──────────────┐                                         │
│     ↓              ↓              ↓                                         │
│  Phase 0-0c    Phase 1-2      Phase 3-5                                     │
│  Grounding     Detection      Locking                                       │
│     │          & Routing      & Update                                      │
│     ↓              ↓              ↓                                         │
│  grounding_   prism_detector expert_router  parameter_   convergence_       │
│  bridge.py    .py           .py            locker.py    tracker.py         │
│                                                                              │
│                    ↓                                                         │
│              cognitive_state.py (44 fields)                                 │
│                    ↓                                                         │
│              bcm_trail.py + bcm_integration.py (v7.0.0)                     │
│                    ↓                                                         │
│              batch_invariance.py (v7.1.0)                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Map

### Core Pipeline Modules

| Module | Lines | Purpose | Key Exports |
|--------|-------|---------|-------------|
| `cognitive_orchestrator.py` | 642 | 8-Phase NEXUS Pipeline coordination | `NexusResult`, `CognitiveOrchestrator`, `create_orchestrator` |
| `prism_detector.py` | 594 | Signal extraction (emotional > grounding > mode > domain > task) | `PRISMDetector`, `SignalVector`, `SignalCategory`, `SIGNAL_PATTERNS` |
| `expert_router.py` | 640 | Cognitive Safety MoE (7+4 experts) | `Expert`, `ExpertRouter`, `RoutingResult`, `EXPERT_PRIORITY` |
| `parameter_locker.py` | 581 | MAX3 bounded reflection + safety gating | `ParameterLocker`, `LockedParams`, `ThinkDepth`, `Paradigm` |
| `convergence_tracker.py` | 503 | RC^+xi epistemic tension tracking | `ConvergenceTracker`, `AttractorBasin`, `StateVector` |
| `cognitive_state.py` | 834 | State management (44 fields) | `CognitiveState`, `BurnoutLevel`, `MomentumPhase`, `EnergyLevel` |
| `grounding_bridge.py` | 619 | ACCESS/LEARN/HYBRID mode routing (v6.0) | `GroundingBridge`, `GroundingResult`, `SourceMode` |

### BCM & Batch Invariance (v7.0-7.1)

| Module | Lines | Purpose | Key Exports |
|--------|-------|---------|-------------|
| `bcm_trail.py` | 663 | Trail-based stigmergic learning | `OrchestraTrail`, `PlasticityState`, `BCMConfig` |
| `bcm_integration.py` | 461 | BCM pipeline adapter | `BCMPipelineAdapter`, `load_trail`, `save_trail` |
| `batch_invariance.py` | 819 | ThinkingMachines batch invariance | `kahan_sum`, `BatchInvariantAggregator`, `COGNITIVE_TILE_SIZE` |

### Production Hardening

| Module | Lines | Purpose | Key Exports |
|--------|-------|---------|-------------|
| `framework_orchestrator.py` | 2,761 | Full orchestration framework | `FrameworkOrchestrator`, `BaseAgent`, `AgentResult` |
| `resilience.py` | 563 | Circuit breaker, retries | `CircuitBreaker`, `ResilientExecutor`, `with_retry` |
| `bulkhead.py` | 412 | Agent isolation pattern | `BulkheadExecutor`, `AdaptiveBulkhead` |
| `fallback.py` | 501 | Graceful degradation | `FallbackRegistry`, `GracefulDegradation` |
| `checkpoint.py` | 512 | Crash recovery | `OrchestrationCheckpoint`, `recover_from_crash` |
| `idempotency.py` | 365 | Idempotent execution | `IdempotencyManager`, `generate_idempotency_key` |
| `rate_limit.py` | 421 | Rate limiting | `RateLimiter`, `SlidingWindowLimiter` |

### Observability

| Module | Lines | Purpose | Key Exports |
|--------|-------|---------|-------------|
| `metrics.py` | 435 | Prometheus-compatible metrics | `OrchestratorMetrics`, `Counter`, `Histogram`, `Gauge` |
| `tracing.py` | 581 | Distributed tracing (Jaeger/Zipkin) | `DistributedTracer`, `trace`, `Span` |
| `logging_setup.py` | 327 | Structured logging | `setup_logging`, `JSONFormatter` |
| `health.py` | 315 | Health checks | `HealthChecker`, `HealthReport` |
| `otel_adapter.py` | 330 | OpenTelemetry adapter | — |

### Worker Agents

| Module | Lines | Purpose | Key Exports |
|--------|-------|---------|-------------|
| `agent_coordinator.py` | 766 | Work/delegate/protect decisions | `AgentCoordinator`, `DecisionMode`, `FlowProtector` |
| `decision_engine.py` | 723 | Task routing | `DecisionEngine`, `TaskRequest`, `ExecutionPlan` |
| `research_agent.py` | 614 | Research worker | `ResearchAgent`, `ResearchResult` |
| `synthesis_agent.py` | 573 | Synthesis worker | `SynthesisAgent`, `SynthesisMode` |
| `cognitive_support.py` | 574 | ADHD support (always active) | `CognitiveSupportManager`, `WorkingMemoryTracker` |

### Substrate Layer

| Module | Lines | Purpose | Key Exports |
|--------|-------|---------|-------------|
| `substrate/__init__.py` | 73 | Substrate exports | — |
| `substrate/knowledge/retriever.py` | 292 | O(1) factual retrieval | `KnowledgeRetriever`, `retrieve` |
| `substrate/knowledge/schemas.py` | 120 | Knowledge prim schemas | `KnowledgePrim` |
| `substrate/ewm/manager.py` | 340 | External Working Memory | `EWMManager`, `SessionAnchor` |
| `substrate/ewm/schemas.py` | 262 | EWM state schemas | `EWMState`, `Project` |
| `substrate/hardening/state_manager.py` | 432 | State persistence | `StateManager`, `StateResult` |
| `substrate/hardening/handoff.py` | 316 | Session handoff | `HandoffManager`, `HandoffDocument` |

### Knowledge Distillation Pipeline

| Module | Lines | Purpose |
|--------|-------|---------|
| `substrate/knowledge/distillation/pipeline.py` | 952 | Main orchestrator |
| `substrate/knowledge/distillation/checkpoint.py` | 444 | Resumability |
| `substrate/knowledge/distillation/validator.py` | 469 | Hallucination detection |
| `substrate/knowledge/distillation/self_consistency.py` | 458 | Multi-sample voting |
| `substrate/knowledge/distillation/corpus_ingester.py` | 402 | Document ingestion |
| `substrate/knowledge/distillation/entailment_grounder.py` | 398 | NLI-based verification |
| `substrate/knowledge/distillation/llm_client.py` | 361 | LLM API client |
| `substrate/knowledge/distillation/usda_writer.py` | 358 | USD-A output |
| `substrate/knowledge/distillation/prim_extractor.py` | 347 | Knowledge extraction |
| `substrate/knowledge/distillation/response_schemas.py` | 339 | Pydantic schemas |
| `substrate/knowledge/distillation/trigger_generator.py` | 328 | Signal triggers |
| `substrate/knowledge/distillation/async_executor.py` | 311 | Rate-limited execution |
| `substrate/knowledge/distillation/confidence_scorer.py` | 305 | Confidence calculation |
| `substrate/knowledge/distillation/errors.py` | 307 | Error handling |
| `substrate/knowledge/distillation/query_generator.py` | 271 | Query generation |
| `substrate/knowledge/distillation/answer_generator.py` | 255 | Answer generation |
| `substrate/knowledge/distillation/config.py` | 212 | Configuration |
| `substrate/knowledge/distillation/benchmark.py` | 405 | Performance testing |

### CLI & UI

| Module | Lines | Purpose | Key Exports |
|--------|-------|---------|-------------|
| `cli/main.py` | 430 | CLI entry point | `main()` |
| `cli/status.py` | 271 | Status display | — |
| `cli/tui.py` | 466 | TUI dashboard | — |
| `dashboard.py` | 503 | Dashboard core | `Dashboard` |
| `dashboard_bridge.py` | 359 | NEXUS → Dashboard mapping | `DashboardBridge` |

### Hooks

| Module | Lines | Purpose |
|--------|-------|---------|
| `hooks/__init__.py` | 22 | Hook exports |
| `hooks/__main__.py` | 22 | Hook entry point |
| `hooks/cognitive_hook.py` | 200 | Claude Code integration |
| `claude_code_hook.py` | 235 | Legacy hook |

### Miscellaneous

| Module | Lines | Purpose |
|--------|-------|---------|
| `config.py` | 543 | Configuration management |
| `schemas.py` | 381 | JSON schema validation |
| `validation.py` | 295 | Input validation |
| `file_ops.py` | 241 | Atomic file operations |
| `lifecycle.py` | 337 | Lifecycle management |
| `cognitive_stage.py` | 1,031 | USD-native cognitive stage |
| `tension_surfacer.py` | 629 | Tension detection |
| `mycelium_arc.py` | 548 | Mycelium paradigm |
| `mycelium_aggregator.py` | 426 | Mycelium aggregation |
| `peer_registry.py` | 436 | Peer discovery |
| `websocket_server.py` | 519 | WebSocket server |
| `http_server.py` | 550 | HTTP server |
| `adhd_support.py` | 523 | Legacy ADHD support |
| `cogroute_bench.py` | 667 | Benchmarking |
| `__init__.py` | 821 | Package exports |

---

## 8-Phase NEXUS Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 0: RETRIEVE                                                           │
│   Knowledge check for factual queries (fast path, can short-circuit)        │
│   Module: substrate/knowledge/retriever.py                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 0b: CLASSIFY                                                          │
│   Determine source mode: LEARN | ACCESS | HYBRID                            │
│   Module: grounding_bridge.py                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 0c: GROUND                                                            │
│   Query oracle if ACCESS/HYBRID mode (grounding layer)                      │
│   Module: grounding_bridge.py                                               │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: DETECT                                                             │
│   PRISM extracts signals: emotional > grounding > mode > domain > task      │
│   Module: prism_detector.py                                                 │
│   + BCM fingerprint capture (v7.0.0)                                        │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: CASCADE                                                            │
│   Safety gates + ADHD_MoE (7 experts) + GROUNDING_MoE (4 experts)          │
│   + BCM trail metadata (confidence, not routing order)                      │
│   Module: expert_router.py                                                  │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: LOCK                                                               │
│   MAX3 bounded reflection + safety gating + BCM depth optimization          │
│   Module: parameter_locker.py                                               │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: EXECUTE                                                            │
│   Claude generates response with locked parameters                          │
│   Anchor: [EXEC:a3f2b8|direct|Cortex|30000ft|standard|learn:na]             │
│   Module: decision_engine.py                                                │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 5: UPDATE                                                             │
│   RC^+xi convergence tracking + BCM trail updates (queued, batch-invariant) │
│   Module: convergence_tracker.py + bcm_integration.py                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Data Structures

### Expert Enum (expert_router.py)

```python
class Expert(Enum):
    # ADHD_MoE Experts (Priority 1-7)
    VALIDATOR = "validator"      # 1 - frustrated, RED, caps → empathy first
    SCAFFOLDER = "scaffolder"    # 2 - overwhelmed, stuck → break down
    RESTORER = "restorer"        # 3 - depleted, ORANGE → easy wins
    REFOCUSER = "refocuser"      # 4 - tangent_over → redirect
    CELEBRATOR = "celebrator"    # 5 - task_complete → acknowledge
    SOCRATIC = "socratic"        # 6 - exploring, what_if → guide
    DIRECT = "direct"            # 7 - focused, flow → minimal friction

    # GROUNDING_MoE Experts (v6.0.0)
    ORACLE_RESOLVER = "oracle_resolver"    # G1 - oracle conflicts
    EVIDENCE_BUILDER = "evidence_builder"  # G2 - evidence chains
    CONFIDENCE_ADJ = "confidence_adj"      # G3 - hallucination detected
    ACCESS_GATEKEEPER = "access_gatekeeper"# G4 - route to oracle
```

### CognitiveState (cognitive_state.py)

```python
@dataclass
class CognitiveState:
    # Core State
    burnout_level: BurnoutLevel = BurnoutLevel.GREEN
    momentum_phase: MomentumPhase = MomentumPhase.COLD_START
    energy_level: EnergyLevel = EnergyLevel.MEDIUM
    mode: CognitiveMode = CognitiveMode.FOCUSED
    altitude: Altitude = Altitude.VISION

    # Focus (no toggle - always active)
    focus_level: str = "moderate"  # scattered|moderate|locked_in
    urgency: str = "moderate"      # relaxed|moderate|deadline

    # Session
    exchange_count: int = 0
    rapid_exchange_count: int = 0
    tasks_completed: int = 0
    tangent_budget: int = 5
    session_start_time: float = field(default_factory=time.time)

    # Grounding (v6.0.0)
    grounding_mode: str = "learn"  # learn|access|hybrid
    oracle_cache_age: int = 0
    evidence_chain_length: int = 0
    grounding_budget: int = 5

    # BCM (v7.0.0)
    bcm_trail_version: str = "7.0.0"
    bcm_plasticity_active: bool = False
    bcm_plasticity_sigma: float = 0.5

    # Batch Invariance (v7.1.0)
    cognitive_tile_size: int = 32
    determinism_mode: str = "strict"
    aggregation_strategy: str = "max"
```

### BurnoutLevel / MomentumPhase / EnergyLevel

```python
class BurnoutLevel(Enum):
    GREEN = "green"    # Normal pace
    YELLOW = "yellow"  # Short responses, typos
    ORANGE = "orange"  # Frustration, repetition
    RED = "red"        # Caps, negativity, stop

class MomentumPhase(Enum):
    COLD_START = "cold_start"
    BUILDING = "building"
    ROLLING = "rolling"
    PEAK = "peak"
    CRASHED = "crashed"

class EnergyLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DEPLETED = "depleted"
```

### ThinkDepth / Paradigm (parameter_locker.py)

```python
class ThinkDepth(Enum):
    MINIMAL = "minimal"      # 1K tokens
    STANDARD = "standard"    # 8K tokens
    DEEP = "deep"            # 32K tokens
    ULTRADEEP = "ultradeep"  # 128K tokens

class Paradigm(Enum):
    CORTEX = "cortex"        # Hierarchical, explicit
    MYCELIUM = "mycelium"    # Distributed, emergent
```

### Batch Invariance Constants (batch_invariance.py)

```python
COGNITIVE_TILE_SIZE: int = 32      # Fixed, never changes
DETERMINISM_SEED: int = 0xCAFEBABE # Fixed seed
HASH_ALGORITHM: str = "sha256"     # For checksums

class AggregationStrategy(Enum):
    MAX = "max"
    MEAN = "mean"
    WEIGHTED_MEAN = "weighted_mean"
    DECAY_MEAN = "decay_mean"
    THRESHOLD_FILTER = "threshold_filter"
```

---

## Test Coverage Map

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_bcm_integration.py` | 1,269 lines | BCM trail, plasticity, outcomes |
| `test_cognitive_engine.py` | 938 lines | Core orchestration |
| `test_batch_invariance.py` | 859 lines | Kahan sum, aggregation, tile processing |
| `test_parameter_locker.py` | 830 lines | MAX3, safety gating |
| `test_grounding_integration.py` | 645 lines | ACCESS/LEARN/HYBRID routing |
| `test_fallback.py` | 592 lines | Graceful degradation |
| `test_decision_engine.py` | 560 lines | Task routing |
| `test_checkpoint.py` | 554 lines | Crash recovery |
| `test_schemas.py` | 547 lines | JSON validation |
| `test_bulkhead.py` | 530 lines | Agent isolation |
| `test_properties.py` | 510 lines | Property-based tests |
| `test_tracing.py` | 493 lines | Distributed tracing |
| `test_idempotency.py` | 481 lines | Idempotent execution |
| `test_hook_bcm_integration.py` | 481 lines | Hook + BCM compliance |
| `test_mycelium_arc.py` | 473 lines | Mycelium paradigm |
| `test_health.py` | 467 lines | Health checks |
| `test_metrics.py` | 466 lines | Prometheus metrics |
| `distillation/test_pipeline_integration.py` | 441 lines | Knowledge distillation |
| `test_chaos.py` | 421 lines | Chaos engineering |
| ... | ... | ... |
| **Total** | **1,495 tests** | All passing |

### Test Categories

```bash
pytest                                    # All 1,495 tests
pytest tests/test_cognitive_engine.py -v  # Core orchestration
pytest tests/test_batch_invariance.py -v  # Batch invariance (v7.1.0)
pytest tests/test_bcm_integration.py -v   # BCM trails (v7.0.0)
pytest tests/test_grounding_integration.py -v  # Grounding (v6.0.0)
pytest tests/distillation/ -v             # Knowledge distillation
pytest -m chaos                           # Chaos engineering
pytest -m performance                     # SLA verification
pytest --cov=src/orchestra --cov-report=html  # Coverage report
```

---

## Entry Points

### CLI Commands

```bash
# Main CLI
orchestra                    # Launch TUI dashboard
orchestra status             # Show cognitive status
orchestra status --short     # Minimal status line

# State Management
orchestra set -b YELLOW      # Set burnout level
orchestra set -e low         # Set energy level

# Hook Management
orchestra install-hook       # Install Claude Code integration
orchestra uninstall-hook     # Remove integration

# Shell Integration
orchestra init bash          # Get bash prompt config
orchestra init zsh           # Get zsh prompt config
```

### Python API

```python
from orchestra import create_orchestrator

# Process a message through NEXUS pipeline
orchestrator = create_orchestrator()
result = orchestrator.process_message("help me implement this feature")

# Get anchor format
print(result.to_anchor())
# [EXEC:a3f2b8|direct|Cortex|30000ft|standard|learn:na]

# Access routing decision
print(result.routing.expert)  # Expert.DIRECT

# Access convergence
print(result.convergence.epistemic_tension)  # 0.05
```

### Hook Entry Point

```bash
# For Claude Code hooks.json
echo '{"user_prompt": "test"}' | python -m orchestra.hooks
```

---

## Dependencies

### Core Dependencies (pyproject.toml)

```toml
dependencies = [
    "aiohttp>=3.8.0",
    "pydantic>=2.0.0",
    "rich>=13.0.0",
]
```

### Optional Dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "hypothesis>=6.100.0",
]
tui = [
    "textual>=0.40.0",
]
distillation = [
    "anthropic>=0.40.0",
    "openai>=1.0.0",
]
```

### Installation

```bash
pip install -e .                    # Basic
pip install -e ".[dev]"             # With dev tools
pip install -e ".[dev,tui]"         # With TUI dashboard
pip install -e ".[dev,distillation]"# With knowledge distillation
```

---

## Version History

| Version | Key Features |
|---------|--------------|
| **v7.1.0** | Cognitive Batch Invariance (COGNITIVE_TILE_SIZE=32, Kahan summation) |
| **v7.0.0** | BCM Stigmergic Learning (trail-based expert confidence) |
| **v6.0.0** | Grounding Layer (ACCESS/LEARN/HYBRID, oracle registry) |
| **v5.0.0** | 5-Phase NEXUS Pipeline, Cognitive Safety MoE |
| **v4.0.0** | Hybrid Orchestra (CognitiveState, PRISM detection) |
| **v3.0.0** | Production Excellence (metrics, tracing, bulkhead) |
| **v2.0.0** | Production Hardening (circuit breaker, retries) |

---

## ThinkingMachines [He2025] Compliance

Reference: https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/

| Requirement | Implementation |
|-------------|----------------|
| Fixed evaluation order | 8 phases, no reordering |
| Fixed signal priority | emotional > grounding > mode > domain > task |
| Fixed expert priority | Validator > Scaffolder > ... > Direct |
| Fixed tile size | `COGNITIVE_TILE_SIZE = 32` |
| Batch-invariant accumulation | Kahan summation |
| Queued updates | BCM trails flushed AFTER processing |
| Reproducible checksums | SHA-256 of locked params |

---

## File Paths

```
C:\Users\User\Orchestra\
├── src/orchestra/
│   ├── __init__.py              # Package exports (821 LOC)
│   ├── cognitive_orchestrator.py # NEXUS Pipeline (642 LOC)
│   ├── cognitive_state.py       # State management (834 LOC)
│   ├── expert_router.py         # Cognitive Safety MoE (640 LOC)
│   ├── parameter_locker.py      # MAX3 + safety gating (581 LOC)
│   ├── prism_detector.py        # Signal detection (594 LOC)
│   ├── convergence_tracker.py   # RC^+xi tracking (503 LOC)
│   ├── grounding_bridge.py      # ACCESS/LEARN/HYBRID (619 LOC)
│   ├── bcm_trail.py             # Trail system (663 LOC)
│   ├── bcm_integration.py       # BCM adapter (461 LOC)
│   ├── batch_invariance.py      # v7.1.0 invariance (819 LOC)
│   ├── framework_orchestrator.py # Full framework (2,761 LOC)
│   ├── hooks/                   # Claude Code integration
│   ├── cli/                     # CLI commands
│   └── substrate/               # Knowledge + EWM + Hardening
├── tests/                       # 1,495 tests
├── pyproject.toml               # Package config
└── README.md                    # Documentation
```

---

*Orchestra v7.1.0 — Cognitive Safety Layer for Claude Code*
*ThinkingMachines [He2025] Compliant*
