<p align="center">
  <img src="logo.png" alt="Orchestra Logo" width="400"/>
</p>

<p align="center">
  <a href="CHANGELOG.md"><img src="https://img.shields.io/badge/v7.1.0-Production%2FStable-success" alt="Production"></a>
  <a href="tests/"><img src="https://img.shields.io/badge/tests-1494%20passed-brightgreen" alt="Tests"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="License"></a>
</p>

<p align="center"><strong>Cognitive safety layer for AI-assisted development</strong></p>

<p align="center"><em>Deterministic behavior. Burnout protection. Built for neurodivergent brains.</em></p>

<p align="center"><code>Same signals → Same routing → Same behavior</code></p>

---

## Why Orchestra?

You know the pattern:

> **Hyperfocus → ship fast → crash hard → forget where you were → start over**

AI-assisted development makes this worse. You build at the speed of thought—until you can't think anymore. The AI doesn't know you're running on empty. It keeps generating, you keep accepting, and then you hit the wall.

**Orchestra is the guardrail you can't build for yourself.**

It sits between you and the AI, tracking what you can't track in the moment: your energy, your momentum, your approaching burnout. It adapts the AI's behavior to your actual capacity—not the capacity you wish you had.

| What you're experiencing | What Orchestra does |
|--------------------------|---------------------|
| Depleted but pushing through | Blocks deep analysis, offers easy wins |
| Frustrated and spiraling | Empathy first, solutions second |
| Lost the thread | Resurfaces your goal and context |
| Hyperfocused for hours | Gentle checkpoint: "still good?" |
| In flow, shipping fast | Disappears. Stays out of your way. |

**This isn't productivity software. It's cognitive sustainability.**

### What's Novel

Most tools optimize for *output*. Orchestra optimizes for *sustainable output*.

- **Your state overrides your requests.** Ask for deep analysis while depleted? You get minimal. Safety gating isn't optional.

- **Emotional signals outrank task signals.** Frustrated + exploring = empathy first. The routing priority is fixed: human needs before task completion.

- **Behavior is deterministic.** Same input, same routing, every time. No more "why is the AI different today?" The uncertainty tax is gone.

- **Memory is external.** Sessions persist. Context survives. You pick up where you left off, not where you vaguely remember being.

*Built for brains that burn bright and need structure to fly.*

---

## Quick Start

### Install

```bash
# From source (recommended)
git clone https://github.com/JosephOIbrahim/Orchestra.git
cd Orchestra
pip install -e ".[dev]"

# From PyPI (coming soon)
pip install cognitive-orchestra
```

### Integrate with Claude Code

```bash
orchestra install-hook
# Restart Claude Code
```

That's it. Every message now passes through the cognitive engine.

---

## What's New in v7.1.0

### Cognitive Batch Invariance

Orchestra now implements **full ThinkingMachines [He2025] batch invariance** at the application layer:

- **Fixed tile size**: `COGNITIVE_TILE_SIZE = 32` for all memory operations
- **Kahan summation**: Numerically stable, order-independent accumulation
- **5 aggregation strategies**: MAX, MEAN, WEIGHTED_MEAN, DECAY_MEAN, THRESHOLD_FILTER
- **Verification tools**: `verify_round_trip()`, `verify_determinism()`, `verify_batch_invariance()`
- **18 new state fields**: Temporal coherence, session lifecycle, deterministic hashing

```python
from orchestra import kahan_sum, BatchInvariantAggregator, AggregationStrategy

# Deterministic summation regardless of order
result = kahan_sum([1e10, 1.0, -1e10, 2.0])  # Always 3.0

# Batch-invariant aggregation
aggregator = BatchInvariantAggregator(strategy=AggregationStrategy.MAX)
confidence = aggregator.aggregate(instances)  # Same result regardless of batch size
```

---

## What's New in v7.0.0

### BCM Stigmergic Reinforcement Learning

Orchestra now learns from routing outcomes using the **Bienenstock-Cooper-Munro (BCM)** learning rule:

- **Trail confidence** tracks expert success rates over time
- **Plasticity windows** boost learning during crash recovery or burnout
- **Signal reliability** correlates detected signals with routing outcomes

**Critical:** BCM is **metadata only**—it never changes routing order. ThinkingMachines compliance preserved.

### TUI Dashboard Enhancements

```
BCM CONFIDENCE  ████████░░ 85%    BCM STATUS  ◇ STABLE v0.1.0
```

Press `b` to toggle plasticity window manually.

### Plasticity Auto-Triggers

| Condition | Action |
|-----------|--------|
| `momentum=crashed` + `burnout=ORANGE` | Auto-open plasticity window |
| `burnout=RED` | Emergency learning mode (divergence=1.0) |
| `converged` + 3 stable exchanges | Auto-close plasticity window |

### Domain Focus

v7.0.0 focuses on **AI Research** and **cognitive substrate** development. VFX payloads (USD/Houdini/Karma/Nuke) have been moved to extension modules and are no longer bundled by default. This reduces the base context load and keeps Orchestra focused on its core mission: cognitive safety for AI-assisted development.

---

## What It Does

Every message you send to Claude Code passes through the **8-Phase NEXUS Pipeline**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 0: RETRIEVE                                                           │
│   Knowledge check for factual queries (fast path, can short-circuit)        │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 0b: CLASSIFY                                                          │
│   Determine source mode: LEARN | ACCESS | HYBRID                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 0c: GROUND                                                            │
│   Query oracle if ACCESS/HYBRID mode (grounding layer)                      │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: DETECT                                                             │
│   PRISM extracts signals: emotional > grounding > mode > domain > task      │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: CASCADE                                                            │
│   Safety gates + Cognitive Safety MoE (7 experts) + BCM trail metadata      │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: LOCK                                                               │
│   MAX3 bounded reflection + safety gating + BCM depth optimization          │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: EXECUTE                                                            │
│   Claude generates response with locked parameters                          │
│   Anchor: [EXEC:a3f2b8|direct|Cortex|30000ft|standard|learn:na]             │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 5: UPDATE                                                             │
│   RC^+xi convergence tracking + BCM trail updates (queued, batch-invariant) │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Expert Routing (Cognitive Safety MoE)

Signals are routed to intervention experts in **fixed priority** order:

| Priority | Expert | Triggers | Response |
|----------|--------|----------|----------|
| 1 | **Validator** | frustrated, RED, caps | Empathy first, normalize |
| 2 | **Scaffolder** | overwhelmed, stuck | Break down, reduce scope |
| 3 | **Restorer** | depleted, ORANGE | Easy wins, rest is OK |
| 4 | **Refocuser** | tangent, distracted | Gentle redirect |
| 5 | **Celebrator** | task_complete | Acknowledge win |
| 6 | **Socratic** | exploring, what_if | Guide discovery |
| 7 | **Direct** | focused, flow | Minimal friction |

**First match wins.** If you're frustrated AND exploring, Validator (priority 1) takes precedence.

---

## Safety Gating

The system protects you from yourself:

| State | Max Thinking Depth |
|-------|-------------------|
| `energy=depleted` | minimal |
| `energy=low` | standard |
| `burnout>=ORANGE` | standard |
| `burnout=RED` | minimal |
| `energy=high` | ultradeep (if requested) |

**Rule:** Safety state ALWAYS overrides user requests. Can reduce depth, never increase.

---

## Knowledge Distillation Pipeline

Orchestra includes a production-hardened pipeline for distilling documentation into searchable knowledge prims:

```
Documentation → Chunks → Queries → Answers → Prims → Triggers → Validation → USDA
```

### Features

- **Checkpointing**: Resume after failures without reprocessing completed stages
- **Pydantic Validation**: Robust LLM response parsing with automatic coercion
- **Async Batch Processing**: Rate-limited parallel execution
- **Hallucination Detection**: Multi-stage validation including LLM fact-checking
- **Atomic Writes**: Safe file operations prevent corruption

### Optional Frontier AI

- **Self-Consistency Verification**: Multi-sample voting for claim validation
- **Entailment Grounding**: NLI-based claim verification against sources

### Usage

```bash
# Run the distillation pipeline
python -m orchestra.substrate.knowledge.distillation.pipeline \
    --corpus ./docs \
    --output ./knowledge \
    --model claude-sonnet-4-20250514

# Resume from checkpoint after interruption
python -m orchestra.substrate.knowledge.distillation.pipeline \
    --corpus ./docs --output ./knowledge

# Start fresh (ignore checkpoint)
python -m orchestra.substrate.knowledge.distillation.pipeline \
    --corpus ./docs --output ./knowledge --no-resume
```

---

## CLI Commands

```bash
# Dashboard
orchestra                    # Launch TUI dashboard
orchestra status             # Show cognitive status
orchestra status --short     # Minimal status line

# State management
orchestra set -b YELLOW      # Set burnout level
orchestra set -e low         # Set energy level

# Hook management
orchestra install-hook       # Install Claude Code integration
orchestra uninstall-hook     # Remove integration

# Shell integration
orchestra init bash          # Get bash prompt config
orchestra init zsh           # Get zsh prompt config
```

---

## Session Management

Sessions auto-reset after 2 hours of inactivity:

- **Resets:** exchange counts, session timing, momentum, tangent budget
- **Preserves:** focus_level, urgency, energy_level (user preferences)
- **Clears burnout:** If you were ORANGE/RED, you start fresh at GREEN

---

## State Location

All state lives in `~/.orchestra/`:

```
~/.orchestra/
├── state/
│   └── cognitive_state.json    # 44 fields (37 core + 7 BCM)
├── bcm/
│   └── trail_{session}.json    # BCM trail persistence
└── config/
    └── orchestra.json          # User preferences (future)
```

---

## Determinism Guarantees

[ThinkingMachines [He2025]](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) compliance:

- **FIXED** evaluation order (8 phases, no reordering)
- **FIXED** signal priority (emotional > grounding > mode > domain > task)
- **FIXED** expert priority (Validator > Scaffolder > ... > Direct)
- **FIXED** reduction order for floating-point accumulation
- **LOCKED** parameters before generation
- **REPRODUCIBLE** checksums (same input → same checksum)
- **SORTED** iteration over sets and dictionaries
- **QUEUED** BCM updates (flushed AFTER processing, never during)

Every file includes `ThinkingMachines [He2025]` compliance comments where determinism matters.

---

## For Developers

### Testing

```bash
# Run all tests
pytest

# Run specific test suites
pytest tests/test_cognitive_engine.py -v      # Core orchestration
pytest tests/distillation/ -v                  # Knowledge distillation
pytest -m chaos                                # Chaos engineering

# Run with coverage
pytest --cov=src/orchestra --cov-report=html
```

### Test Suite

| Category | Tests | Description |
|----------|-------|-------------|
| Core | 799 | Cognitive engine, routing, state |
| BCM Integration | 66 | Trail, routing, locking, convergence |
| Batch Invariance | 84 | Kahan summation, aggregation, determinism (v7.1.0) |
| Hook Integration | 17 | ThinkingMachines compliance through hook |
| Distillation | 118 | Pipeline, schemas, checkpointing, Frontier AI |
| Grounding | 48 | Oracle routing, evidence tracking |
| Other | 362 | Validation, state, CLI, TUI, chaos |
| **Total** | **1494** | All passing |

### Direct API Usage

```python
from orchestra import create_orchestrator

orchestrator = create_orchestrator()
result = orchestrator.process_message("help me implement this feature")

print(result.to_anchor())  # [EXEC:a3f2b8|direct|Cortex|30000ft|standard]
print(result.routing.expert)  # Expert.DIRECT
print(result.convergence.epistemic_tension)  # 0.05
```

### Hook Testing

```bash
echo '{"user_prompt": "test"}' | python -m orchestra.hooks
```

---

## Architecture

```
Orchestra/
├── src/orchestra/
│   ├── cognitive_orchestrator.py   # 8-Phase NEXUS Pipeline
│   ├── expert_router.py            # Cognitive Safety MoE (7 experts)
│   ├── parameter_locker.py         # MAX3 + safety gating
│   ├── convergence_tracker.py      # RC^+xi tracking
│   ├── prism_detector.py           # Signal detection + fingerprinting
│   ├── cognitive_state.py          # State management (44 fields)
│   ├── bcm_trail.py                # BCM stigmergic learning
│   ├── bcm_integration.py          # BCM pipeline adapter
│   ├── grounding_bridge.py         # Grounding layer (ACCESS/LEARN)
│   ├── substrate/
│   │   └── knowledge/
│   │       └── distillation/       # Knowledge distillation pipeline
│   │           ├── pipeline.py     # Main orchestrator
│   │           ├── checkpoint.py   # Resumability
│   │           ├── validator.py    # Hallucination detection
│   │           └── ...             # 18 modules
│   ├── hooks/
│   │   └── cognitive_hook.py       # Claude Code hook
│   └── cli/
│       ├── main.py                 # CLI entry point
│       └── tui.py                  # TUI dashboard with BCM metrics
├── tests/                          # 1047 tests
│   ├── test_cognitive_engine.py    # Core orchestration
│   ├── test_bcm_integration.py     # BCM integration
│   ├── test_hook_bcm_integration.py # Hook + BCM compliance
│   ├── distillation/               # Pipeline tests
│   └── ...
└── pyproject.toml
```

---

## Philosophy

Orchestra is built for neurodivergent brains:

1. **Safety first** - Emotional safety before productivity
2. **Ship over perfect** - Working beats polished
3. **Protect momentum** - Don't break flow unnecessarily
4. **External memory** - Write it down, don't hold it in your head
5. **Recover without guilt** - Rest is productive

---

## Documentation

| Document | Description |
|----------|-------------|
| [CHANGELOG](CHANGELOG.md) | Version history and release notes |
| [QUICKSTART](docs/QUICKSTART.md) | 2-minute setup guide |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Technical deep-dive |
| [CONTRIBUTING](CONTRIBUTING.md) | Development guidelines |
| [CITATIONS](CITATIONS.md) | Academic references |

---

## Installation Options

```bash
# Basic install
pip install -e .

# With dev dependencies (testing, linting)
pip install -e ".[dev]"

# With TUI dashboard
pip install -e ".[dev,tui]"

# With distillation pipeline (LLM clients)
pip install -e ".[dev,distillation]"
```

---

## Credits

- [USD](https://graphics.pixar.com/usd/) composition semantics for cognitive state
- [ThinkingMachines [He2025]](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) for batch-invariance principles

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

*Orchestra v7.1.0 - Cognitive Safety Layer for Claude Code*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
