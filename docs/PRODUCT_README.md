# Framework Orchestrator v5.0

**7-Agent async orchestration system implementing the USD Cognitive Substrate specification.**

## Overview

The Framework Orchestrator provides a deterministic, reproducible cognitive routing system that implements V5 intervention experts with safety floors.

### Key Features

- **7 Agents**: ECHO Curator, Domain Intelligence, MoE Router, World Modeler, Code Generator, Determinism Guard, Self Reflector
- **V5 Intervention Experts**: protector, decomposer, restorer, redirector, acknowledger, guide, executor
- **Safety Floors**: Hard minimums (protector: 10%, decomposer: 5%, restorer: 5%)
- **5-Phase Routing**: ACTIVATE → WEIGHT → BOUND → SELECT → UPDATE
- **ThinkingMachines Compliance**: Batch-invariant execution [He2025]
- **USD Payload Architecture**: Lazy-loadable framework modules

## Installation

```bash
# Clone/copy the Framework Orchestrator directory
cp -r Framework_Orchestrator ~/.framework-orchestrator/core/

# Install dependencies
pip install -r requirements.txt
```

## Usage

### CLI Mode

```bash
# Single task
python framework_orchestrator.py --task "Implement the feature"

# Interactive mode
python framework_orchestrator.py

# Show agent info
python framework_orchestrator.py --info
```

### Programmatic Usage

```python
from framework_orchestrator import FrameworkOrchestrator, Mycelium

# Initialize
orchestrator = FrameworkOrchestrator()

# Execute task
result = await orchestrator.orchestrate(
    task="Debug the configuration",
    context={"seed": 42}
)

print(f"Agents executed: {result['agents_executed']}")
print(f"Master checksum: {result['master_checksum']}")
```

### Mycelium Weight Calibration

```python
from framework_orchestrator import Mycelium

mycelium = Mycelium()

# Manual calibration (no automatic self-improvement)
mycelium.set_weight("executor", 0.4)  # Boost task execution
mycelium.save_weights()  # Persist to REFERENCES layer

# Check loading strategy
strategy = mycelium.get_loading_strategy()
print(f"Strategy: {strategy['strategy']}")  # fast/weighted/thorough
```

## Directory Structure

```
~/.framework-orchestrator/
├── core/
│   ├── framework_orchestrator.py    # Main orchestrator
│   └── tests/                       # Test suite
├── domains/                         # Domain configs (JSON) - user-defined
│   ├── <your_domain>.json           # Add domain configs as needed
│   └── general.json                 # Fallback (auto-created if missing)
├── frameworks/                      # Payload modules
│   ├── adhd_moe/                   # Safety tier (always loaded)
│   ├── max_reflection/             # Weighted tier
│   ├── nova_oracle/                # Deferred tier
│   ├── echo_memory/                # Weighted tier
│   └── cortex_world/               # Deferred tier
├── principles.json                  # SPECIALIZES layer (never compressed)
└── mycelium_weights.json           # Calibrated weights (REFERENCES layer)
```

## Architecture

### Agent Responsibilities

| Agent | Framework | Purpose |
|-------|-----------|---------|
| ECHO Curator | ECHO 2.0 + LIVRPS | Memory management with USD composition semantics |
| Domain Intelligence | Phoenix v6 + PRISM | Multi-domain analysis with pluggable specialists |
| MoE Router | V5 Intervention Experts | 5-phase routing with safety floors |
| World Modeler | CORTEX | Context graph construction |
| Code Generator | MAX 3 + MNO v3 | Deterministic code generation |
| Determinism Guard | ThinkingMachines | Reproducibility enforcement |
| Self Reflector | Resonance + RC^+xi | Meta-cognition and convergence tracking |

### V5 Expert Archetypes

| Priority | Expert | Triggers | Safety Floor |
|----------|--------|----------|--------------|
| 1 | Protector | frustrated, overwhelmed, safety | 10% |
| 2 | Decomposer | stuck, complex, break_down | 5% |
| 3 | Restorer | depleted, burnout, tired | 5% |
| 4 | Redirector | tangent, distracted, off_topic | 0% |
| 5 | Acknowledger | done, complete, milestone | 0% |
| 6 | Guide | exploring, what_if, curious | 0% |
| 7 | Executor | implement, code, do, execute | 0% |

### Design Decisions

1. **No Automatic Self-Improvement**: Weights are static, calibrated manually. This preserves:
   - Determinism (same signals → same routing)
   - Auditability (weights don't change unexpectedly)
   - ThinkingMachines compliance [He2025]

2. **Safety Floors are HARD**: Protector can never drop below 10% weight. This ensures safety experts are always available.

3. **5-Phase Routing**: Fixed execution order prevents batch-variance.

## Tests

```bash
cd ~/.framework-orchestrator/core
pytest tests/test_orchestrator.py -v --asyncio-mode=auto
```

**31/31 tests passing**

## Configuration

### Domain Configs

Create custom domain configs in `~/.framework-orchestrator/domains/`:

```json
{
  "name": "my_domain",
  "specialists": {
    "specialist_name": {
      "keywords": ["keyword1", "keyword2"],
      "analysis_focus": ["focus_area"]
    }
  },
  "routing_keywords": ["domain_keyword"],
  "prism_perspectives": ["causal", "optimization", "risk"]
}
```

### Principles (SPECIALIZES Layer)

The principles layer is NEVER compressed. Create `~/.framework-orchestrator/principles.json`:

```json
{
  "constitutional": {
    "principles": [
      {"id": "safety_first", "statement": "Safety first: Emotional safety before productivity"},
      {"id": "user_knows_best", "statement": "User signal trumps Claude's guess"}
    ]
  }
}
```

## References

- USD Cognitive Substrate: `~/.claude/substrate/cognitive_substrate_v4.usda`
- ThinkingMachines [He2025]: https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/
- V5 Framework Synthesis: `V5_FRAMEWORK_SYNTHESIS.md`

---

*Framework Orchestrator v5.0*
*Generated: 2026-01-21*
