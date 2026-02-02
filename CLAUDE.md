# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Orchestra is a cognitive safety layer for AI-assisted development (v7.0.0). It sits between the user and Claude Code, tracking energy, momentum, and burnout to adapt AI behavior to actual user capacity.

**Core principle:** Same signals → Same routing → Same behavior (ThinkingMachines [He2025] batch-invariance)

## Development Commands

```bash
# Install
pip install -e ".[dev]"           # Dev dependencies
pip install -e ".[dev,tui]"       # With TUI dashboard
pip install -e ".[distillation]"  # With knowledge distillation

# Test
pytest                                    # All 1,047 tests
pytest tests/test_cognitive_engine.py -v  # Single file
pytest tests/test_cognitive_engine.py::test_routing_determinism -v  # Single test
pytest -k "routing"                       # Tests matching pattern
pytest -m unit                            # Fast, isolated tests
pytest -m integration                     # Full workflow tests
pytest -m chaos                           # Fault injection tests
pytest -m performance                     # SLA verification
pytest tests/distillation/ -v             # Knowledge distillation (118 tests)
pytest --cov=src/orchestra --cov-report=html  # Coverage report

# Hook testing
echo '{"user_prompt": "test"}' | python -m orchestra.hooks

# Knowledge distillation pipeline
python -m orchestra.substrate.knowledge.distillation.pipeline \
    --corpus ./docs --output ./knowledge --model claude-sonnet-4-20250514
python -m orchestra.substrate.knowledge.distillation.pipeline \
    --corpus ./docs --output ./knowledge  # Resume from checkpoint

# CLI
orchestra                    # Launch TUI dashboard
orchestra status             # Show cognitive state
orchestra status --short     # Minimal status line
orchestra set -b YELLOW      # Set burnout level
orchestra set -e low         # Set energy level
orchestra install-hook       # Install Claude Code integration
orchestra init bash          # Get bash prompt config
orchestra init zsh           # Get zsh prompt config

# Lint
ruff check .                 # Fast linting
black src/ tests/            # Format code
isort src/ tests/            # Sort imports
mypy src/                    # Type checking
```

## CI/CD

Tests run on GitHub Actions across Python 3.10, 3.11, 3.12 on Ubuntu and Windows (9 matrix jobs). All tests must pass before merge.

## Architecture: 8-Phase NEXUS Pipeline

Every message passes through this deterministic pipeline:

```
Phase 0:  RETRIEVE  → Knowledge check (fast path, can short-circuit)
Phase 0b: CLASSIFY  → Determine source mode: LEARN | ACCESS | HYBRID
Phase 0c: GROUND    → Oracle query if ACCESS/HYBRID mode
Phase 1:  DETECT    → PRISM extracts signals (priority: emotional > grounding > mode > domain > task)
Phase 2:  CASCADE   → Safety gates + ADHD_MoE + GROUNDING_MoE + BCM trail metadata
Phase 3:  LOCK      → MAX3 bounded reflection + safety gating + BCM depth optimization
Phase 4:  EXECUTE   → Claude generates with locked params → [EXEC:checksum|expert|paradigm|altitude|depth|source_mode]
Phase 5:  UPDATE    → RC^+xi convergence tracking + BCM trail updates (queued, batch-invariant)
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `cognitive_orchestrator.py` | 8-Phase pipeline coordination (entry point) |
| `prism_detector.py` | Signal extraction (emotional > grounding > mode > domain > task priority) |
| `expert_router.py` | ADHD_MoE (7 experts) + GROUNDING_MoE (4 experts), fixed priority |
| `grounding_bridge.py` | Grounding layer adapter - ACCESS/LEARN/HYBRID routing |
| `parameter_locker.py` | MAX3 bounded reflection + ADHD safety gating + source_mode |
| `bcm_trail.py` | BCM stigmergic learning (v7.0.0) - trail confidence |
| `bcm_integration.py` | BCM pipeline adapter - plasticity triggers |
| `convergence_tracker.py` | RC^+xi epistemic tension tracking |
| `cognitive_state.py` | State persistence (37 core + 7 BCM = 44 fields) |

### ADHD_MoE: 7 Intervention Experts (Fixed Priority Order)

1. **Validator** - frustrated/RED/caps → Empathy first
2. **Scaffolder** - overwhelmed/stuck → Break down scope
3. **Restorer** - depleted/ORANGE → Easy wins
4. **Refocuser** - tangent/distracted → Redirect
5. **Celebrator** - task_complete → Acknowledge
6. **Socratic** - exploring/what_if → Guide discovery
7. **Direct** - focused/flow → Minimal friction

### GROUNDING_MoE: 4 Grounding Experts

1. **OracleResolver** - oracle_conflict/mismatch → Reconcile sources
2. **EvidenceBuilder** - cite_needed/source_request → Build evidence chain
3. **ConfidenceAdj** - hallucination_detected → Adjust confidence
4. **AccessGatekeeper** - oracle_required/fresh_need → Route to grounding layer

### BCM Stigmergic Learning (v7.0.0)

Trail-based expert confidence that learns from outcomes:
- **Trail confidence** tracks expert success rates
- **Plasticity windows** boost learning during crash recovery
- **Auto-triggers**: `momentum=crashed + burnout=ORANGE` or `burnout=RED`
- **Critical**: BCM is metadata-only—never changes routing order

### Safety Gating

User state overrides requests—`energy=depleted` forces minimal thinking depth, `burnout=RED` forces minimal. Safety can reduce depth, never increase.

## ThinkingMachines Compliance

All code must maintain batch-invariance:

1. **Fixed evaluation order** — Never reorder phases or priority lists
2. **No dynamic algorithm switching** — Selection must be deterministic
3. **Parameter locking** — Lock all params before generation
4. **Reproducible checksums** — Same inputs → same EXEC anchor
5. **Sorted iteration** — Always sort sets/dicts before iteration
6. **Queued BCM updates** — Flushed AFTER processing, never during

```python
# Good: Fixed priority, explicit ordering
EXPERT_PRIORITY = [Expert.VALIDATOR, Expert.SCAFFOLDER, ...]

# Bad: Dynamic ordering violates batch-invariance
experts = sorted(experts, key=lambda e: compute_priority(e, state))
```

## Key Paths

```
src/orchestra/hooks/cognitive_hook.py     # Claude Code integration entry point
src/orchestra/bcm_trail.py                # BCM trail system (v7.0.0)
~/.orchestra/state/cognitive_state.json   # Runtime state (44 fields)
~/.orchestra/bcm/trail_{session}.json     # BCM trail persistence
~/.orchestra/config/orchestra.json        # User preferences
```

**Critical for determinism:** `expert_router.py` — Expert selection must maintain FIXED priority order.

## Adding New Experts

1. Add to `Expert` enum in `expert_router.py` at correct priority position
2. Add triggers in `EXPERT_TRIGGERS` dict
3. Add to `EXPERT_PRIORITY` list at correct position
4. Add determinism tests (same input → same routing)

## Adding New Signal Categories

Signal priority order (emotional > grounding > mode > domain > task > energy) is core specification. Changes require careful consideration. Modify `SignalCategory` enum, `SIGNAL_PATTERNS`, `SignalVector` dataclass, and `PRISMDetector.detect()`.

## Test Categories

| Category | Tests | Marker |
|----------|-------|--------|
| Core orchestration | 799 | `-m unit` or `-m integration` |
| BCM integration | 66 | `tests/test_bcm_integration.py` |
| Knowledge distillation | 118 | `tests/distillation/` |
| Grounding | 48 | `tests/test_grounding_integration.py` |
| Hook compliance | 17 | `tests/test_hook_bcm_integration.py` |

## Anti-Patterns

- **Never reorder** phase execution or priority lists
- **Never use dynamic** algorithm switching at runtime
- **Never skip** determinism tests for new features
- **Never break** parameter locking before generation
- **Never spawn agents** when burnout >= ORANGE (simplify instead)
- **Never apply BCM updates** during processing (queue for FLUSH phase)
