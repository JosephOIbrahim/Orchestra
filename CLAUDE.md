# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Orchestra is a cognitive safety layer for AI-assisted development. It sits between the user and Claude Code, tracking energy, momentum, and burnout to adapt AI behavior to actual user capacity.

**Core principle:** Same signals → Same routing → Same behavior (ThinkingMachines [He2025] batch-invariance)

## Development Commands

```bash
# Install
pip install -e ".[dev]"           # Dev dependencies
pip install -e ".[dev,tui]"       # With TUI dashboard
pip install -e ".[distillation]"  # With knowledge distillation

# Test
pytest                                    # All 964+ tests (v6.0.x)
pytest tests/test_cognitive_engine.py -v  # Single file
pytest tests/test_cognitive_engine.py::test_routing_determinism -v  # Single test
pytest -k "routing"                       # Tests matching pattern
pytest -m unit                            # Fast, isolated tests
pytest -m integration                     # Full workflow tests
pytest -m chaos                           # Fault injection tests
pytest -m performance                     # SLA verification
pytest --cov=src/orchestra --cov-report=html  # Coverage report

# Hook testing
echo '{"user_prompt": "test"}' | python -m orchestra.hooks

# CLI
orchestra                    # Launch TUI dashboard
orchestra status             # Show cognitive state
orchestra install-hook       # Install Claude Code integration
```

## Architecture: 8-Phase NEXUS Pipeline (v6.0.x)

Every message passes through this deterministic pipeline:

```
Phase 0:  RETRIEVE → Knowledge check (fast path, can short-circuit)
Phase 0b: CLASSIFY → Determine source mode: LEARN | ACCESS | HYBRID
Phase 0c: GROUND   → Oracle query if ACCESS/HYBRID mode
Phase 1:  DETECT   → PRISM extracts signals (priority: emotional > grounding > mode > domain > task)
Phase 2:  CASCADE  → Safety gates + ADHD_MoE + GROUNDING_MoE routes to experts
Phase 3:  LOCK     → MAX3 bounded reflection + safety gating locks parameters + source_mode
Phase 4:  EXECUTE  → Claude generates with locked params → [EXEC:checksum|expert|paradigm|altitude|depth|source_mode]
Phase 5:  UPDATE   → RC^+xi convergence tracking updates attractor basins + grounding metrics
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `cognitive_orchestrator.py` | 8-Phase pipeline coordination (entry point) |
| `prism_detector.py` | Signal extraction (emotional > grounding > mode > domain > task priority) |
| `expert_router.py` | ADHD_MoE (7 experts) + GROUNDING_MoE (4 experts), fixed priority |
| `grounding_bridge.py` | Grounding layer adapter (v6.0.x) - ACCESS/LEARN/HYBRID routing |
| `parameter_locker.py` | MAX3 bounded reflection + ADHD safety gating + source_mode |
| `convergence_tracker.py` | RC^+xi epistemic tension tracking |
| `cognitive_state.py` | State persistence (37 core + 7 grounding fields) |

### ADHD_MoE: 7 Intervention Experts (Fixed Priority Order)

1. **Validator** - frustrated/RED/caps → Empathy first
2. **Scaffolder** - overwhelmed/stuck → Break down scope
3. **Restorer** - depleted/ORANGE → Easy wins
4. **Refocuser** - tangent/distracted → Redirect
5. **Celebrator** - task_complete → Acknowledge
6. **Socratic** - exploring/what_if → Guide discovery
7. **Direct** - focused/flow → Minimal friction

### GROUNDING_MoE: 4 Grounding Experts (v6.0.x)

1. **OracleResolver** - oracle_conflict/mismatch → Reconcile sources
2. **EvidenceBuilder** - cite_needed/source_request → Build evidence chain
3. **ConfidenceAdj** - hallucination_detected → Adjust confidence
4. **AccessGatekeeper** - oracle_required/fresh_need → Route to grounding layer

### Safety Gating

User state overrides requests—`energy=depleted` forces minimal thinking depth, `burnout=RED` forces minimal. Safety can reduce depth, never increase.

## ThinkingMachines Compliance

All code must maintain batch-invariance:

1. **Fixed evaluation order** — Never reorder phases or priority lists
2. **No dynamic algorithm switching** — Selection must be deterministic
3. **Parameter locking** — Lock all params before generation
4. **Reproducible checksums** — Same inputs → same EXEC anchor
5. **Sorted iteration** — Always sort sets/dicts before iteration

```python
# Good: Fixed priority, explicit ordering
EXPERT_PRIORITY = [Expert.VALIDATOR, Expert.SCAFFOLDER, ...]

# Bad: Dynamic ordering violates batch-invariance
experts = sorted(experts, key=lambda e: compute_priority(e, state))
```

## Key Files

```
src/orchestra/
├── cognitive_orchestrator.py   # Entry point, 8-phase pipeline (v6.0.x)
├── expert_router.py            # CRITICAL: Expert selection (determinism here)
├── prism_detector.py           # Signal detection (FIXED priority order, includes GROUNDING)
├── grounding_bridge.py         # v6.0.x: Grounding layer adapter (ACCESS/LEARN/HYBRID)
├── cognitive_state.py          # State persistence (37 core + 7 grounding fields)
├── parameter_locker.py         # Safety gating + source_mode locking
├── hooks/cognitive_hook.py     # Claude Code integration
└── cli/main.py                 # CLI entry point

tests/
├── test_grounding_integration.py  # v6.0.x: 48 grounding integration tests
└── ...

~/.orchestra/
├── state/cognitive_state.json  # Runtime state (44 fields with grounding)
└── config/orchestra.json       # User preferences
```

## Adding New Experts

1. Add to `Expert` enum in `expert_router.py` at correct priority position
2. Add triggers in `EXPERT_TRIGGERS` dict
3. Add to `EXPERT_PRIORITY` list at correct position
4. Add determinism tests (same input → same routing)

## Adding New Signal Categories

Signal priority order (emotional > mode > domain > task > energy) is core specification. Changes require careful consideration. Modify `SignalCategory` enum, `SIGNAL_PATTERNS`, `SignalVector` dataclass, and `PRISMDetector.detect()`.
