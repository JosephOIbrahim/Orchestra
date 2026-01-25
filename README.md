# Orchestra

**Cognitive orchestration for Claude Code with deterministic behavior.**

Orchestra is a cognitive engine that processes every message through a 5-Phase NEXUS Pipeline, providing deterministic expert routing and ADHD-aware safety gating. Built on USD composition semantics and ThinkingMachines [He2025] batch-invariance principles.

```
Same signals → Same routing → Same behavior
```

---

## Quick Start

### Install

```bash
pip install -e .
```

### Integrate with Claude Code

```bash
orchestra install-hook
# Restart Claude Code
```

That's it. Every message now passes through the cognitive engine.

---

## What It Does

Every message you send to Claude Code:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: DETECT                                                             │
│   PRISM extracts signals: emotional > mode > domain > task                  │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: CASCADE                                                            │
│   Safety gates + ADHD_MoE expert routing (7 experts, first-match-wins)      │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: LOCK                                                               │
│   MAX3 bounded reflection + ADHD safety gating + deterministic checksum     │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: EXECUTE                                                            │
│   Claude generates response with locked parameters                          │
│   Anchor: [EXEC:a3f2b8|direct|Cortex|30000ft|standard]                      │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 5: UPDATE                                                             │
│   RC^+xi convergence tracking → attractor basins                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Expert Routing (ADHD_MoE)

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
│   └── cognitive_state.json    # 37 fields, all 5 phases
└── config/
    └── orchestra.json          # User preferences (future)
```

---

## Determinism Guarantees

ThinkingMachines [He2025] compliance:

- **FIXED** evaluation order (5 phases, no reordering)
- **FIXED** signal priority (emotional > mode > domain > task)
- **FIXED** expert priority (Validator > Scaffolder > ... > Direct)
- **LOCKED** parameters before generation
- **REPRODUCIBLE** checksums (same input → same checksum)

---

## For Developers

### Testing

```bash
pytest tests/test_cognitive_engine.py -v
```

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
│   ├── cognitive_orchestrator.py  # 5-Phase NEXUS Pipeline
│   ├── expert_router.py           # ADHD_MoE (7 experts)
│   ├── parameter_locker.py        # MAX3 + safety gating
│   ├── convergence_tracker.py     # RC^+xi tracking
│   ├── prism_detector.py          # Signal detection
│   ├── cognitive_state.py         # State management
│   ├── dashboard_bridge.py        # WebSocket sync
│   ├── websocket_server.py        # Real-time dashboard
│   ├── hooks/
│   │   └── cognitive_hook.py      # Claude Code hook
│   └── cli/
│       └── main.py                # CLI entry point
├── tests/
│   └── test_cognitive_engine.py   # 36 tests
└── pyproject.toml                 # v5.0.0
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

## Credits

- [USD](https://graphics.pixar.com/usd/) composition semantics for cognitive state
- [ThinkingMachines](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) [He2025] for batch-invariance

---

*Orchestra v5.0.0 - Cognitive Engine for Claude Code*
