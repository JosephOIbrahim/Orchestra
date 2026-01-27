# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Orchestra is a cognitive safety layer for AI-assisted development. It sits between the user and Claude Code, tracking energy, momentum, and burnout to adapt AI behavior to actual user capacity.

**Core principle:** Same signals → Same routing → Same behavior (ThinkingMachines [He2025] batch-invariance)

## Development Commands

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Install with TUI dashboard support
pip install -e ".[dev,tui]"

# Run all tests
pytest

# Run specific test file
pytest tests/test_cognitive_engine.py -v

# Run tests with coverage
pytest --cov=src/orchestra --cov-report=html

# Run tests by marker
pytest -m unit          # Fast, isolated
pytest -m integration   # Full workflow
pytest -m chaos         # Fault injection
pytest -m performance   # SLA verification

# Test the hook directly
echo '{"user_prompt": "test"}' | python -m orchestra.hooks

# CLI commands
orchestra status             # Show cognitive state
orchestra install-hook       # Install Claude Code integration
orchestra                    # Launch TUI dashboard
```

## Architecture

Orchestra implements a **5-Phase NEXUS Pipeline**:

```
DETECT → CASCADE → LOCK → EXECUTE → UPDATE
(PRISM)  (MoE)    (MAX3)  (Claude)  (RC^+xi)
```

### Core Modules (`src/orchestra/`)

| Module | Purpose |
|--------|---------|
| `cognitive_orchestrator.py` | 5-Phase pipeline coordination |
| `prism_detector.py` | Signal extraction (priority: emotional > mode > domain > task) |
| `expert_router.py` | Cognitive Safety MoE (7 experts, fixed priority, first-match-wins) |
| `parameter_locker.py` | MAX3 bounded reflection + safety gating |
| `convergence_tracker.py` | RC^+xi epistemic tension tracking |
| `cognitive_state.py` | State persistence (37 fields) |

### 7 Intervention Experts (Fixed Priority Order)

1. **Validator** - frustrated/RED/caps → Empathy first
2. **Scaffolder** - overwhelmed/stuck → Break down scope
3. **Restorer** - depleted/ORANGE → Easy wins
4. **Refocuser** - tangent/distracted → Redirect
5. **Celebrator** - task_complete → Acknowledge
6. **Socratic** - exploring/what_if → Guide discovery
7. **Direct** - focused/flow → Minimal friction

### Safety Gating

User state overrides requests—energy=depleted forces minimal thinking depth, burnout=RED forces minimal. Safety can reduce depth, never increase.

## ThinkingMachines Compliance Requirements

All code must maintain batch-invariance:

1. **Fixed evaluation order** — Never reorder phases or priority lists
2. **No dynamic algorithm switching** — Selection must be deterministic
3. **Parameter locking** — Lock all params before generation
4. **Reproducible checksums** — Same inputs → same EXEC anchor

```python
# Good: Fixed priority, explicit ordering
EXPERT_PRIORITY = [Expert.VALIDATOR, Expert.SCAFFOLDER, ...]

# Bad: Dynamic ordering
experts = sorted(experts, key=lambda e: compute_priority(e, state))
```

## State Storage

```
~/.orchestra/
├── state/cognitive_state.json   # Runtime state (37 fields)
└── config/orchestra.json        # User preferences
```

## Adding New Experts

1. Add to `Expert` enum in `expert_router.py` at correct priority position
2. Add triggers in `EXPERT_TRIGGERS` dict
3. Add to `EXPERT_PRIORITY` list at correct position
4. Add determinism tests (same input → same routing)

## Adding New Signal Categories

Signal priority order (emotional > mode > domain > task > energy) is core specification. Changes require careful consideration. Modify `SignalCategory` enum, `SIGNAL_PATTERNS`, `SignalVector` dataclass, and `PRISMDetector.detect()`.
