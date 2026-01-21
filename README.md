# Framework Orchestrator

**USD Composition Semantics for AI Agent Orchestration**

A 7-agent async orchestration system that applies Pixar's USD (Universal Scene Description) composition semantics to cognitive state management. Originally designed for VFX pipelines, now generalized for any domain.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## The Thesis

**USD as Universal State Description.**

Pixar invented USD composition semantics (LIVRPS) to resolve conflicting opinions in complex 3D pipelines. We repurpose these semantics for cognitive state management in LLM applications.

This project implements the **[Persistent State Hypothesis](https://github.com/JosephOIbrahim/usd-cognitive-substrate/blob/main/PERSISTENT_STATE_HYPOTHESIS.md)** (Ibrahim, 2026):

> *"The emergent capabilities of large-scale neural networks can be preserved in a persistent, composable substrate that does not require constant recomputation."*

The hypothesis challenges the assumption that AI intelligence requires proportional energy consumption, proposing that the energy problem is *architectural*, not fundamental:

| USD Concept | Cognitive Mapping |
|-------------|-------------------|
| Scene graph | Cognitive architecture |
| Prim attributes | Behavioral parameters |
| Composition arcs | Priority resolution |
| Variants | Mode switching |
| Layers | Cognitive subsystems |
| Payloads | Domain knowledge (lazy-loaded) |

**Same signals → Same routing → Same behavior** (batch-invariance)

## Key Innovations

### 1. LIVRPS Memory Composition

Memory layers with USD-style priority resolution (strongest to weakest):

```
LOCAL        → Session state (mutable, compresses first)
INHERITS     → Parent task context
VARIANTSETS  → Memory modes (focused/exploratory/recovery)
REFERENCES   → Cross-session calibration
PAYLOADS     → Domain knowledge (unloadable)
SPECIALIZES  → Principles layer (NEVER compressed)
```

### 2. Principles-First Architecture

Constitutional constraints in the SPECIALIZES layer that are **never compressed, never overridden**:

- Safety first (emotional safety before productivity)
- Ship over perfect (working beats polished)
- Protect momentum (don't break flow)
- External over internal (write it down)
- Recover without guilt (rest is productive)
- One at a time (complete before switching)
- User knows best (their signal wins)

### 3. Pluggable Domain Intelligence

JSON-based domain configurations loaded from `~/.framework-orchestrator/domains/`:

```json
{
  "name": "VFX",
  "specialists": {
    "pyro": {
      "keywords": ["fire", "smoke", "explosion"],
      "analysis_focus": ["substep_count", "voxel_resolution", "gas_dissipation"]
    }
  }
}
```

### 4. Deterministic Routing

Hash-based expert selection guarantees reproducibility:

```python
expert_index = int(hashlib.md5(task.encode()).hexdigest(), 16) % len(experts)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Framework Orchestrator                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ ECHO Curator │  │   Domain     │  │  MoE Router  │          │
│  │   (Memory)   │  │ Intelligence │  │  (Experts)   │          │
│  │    LIVRPS    │  │    PRISM     │  │  Hash-based  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    World     │  │     Code     │  │ Determinism  │          │
│  │   Modeler    │  │  Generator   │  │    Guard     │          │
│  │  (Context)   │  │   (Output)   │  │ (batch_size) │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌──────────────┐                                               │
│  │    Self      │  Async orchestration with state handoff       │
│  │  Reflector   │  Max 3 parallel agents, max 3 chain depth     │
│  │   (RC^+xi)   │                                               │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Clone the repository
git clone https://github.com/JosephOIbrahim/framework-orchestrator.git
cd framework-orchestrator

# Install dependencies
pip install -r requirements.txt

# Or install as package
pip install -e .
```

## Quick Start

```python
import asyncio
from framework_orchestrator import FrameworkOrchestrator

async def main():
    orchestrator = FrameworkOrchestrator()

    result = await orchestrator.orchestrate(
        task="Analyze this Houdini pyro simulation for performance issues",
        context={"project": "my_project", "frame_range": [1, 100]}
    )

    print(result)

asyncio.run(main())
```

## Configuration

### Domain Configs

Create domain-specific configurations in `~/.framework-orchestrator/domains/`:

```bash
mkdir -p ~/.framework-orchestrator/domains
```

See `examples/domains/` for templates:
- `vfx.json` - Visual effects (Houdini, Nuke, USD)
- `webdev.json` - Web development (React, Next.js)
- `ai_conductor.json` - AI orchestration systems
- `general.json` - Fallback for any domain

### Principles

Customize constitutional constraints in `~/.framework-orchestrator/principles.json`:

```json
{
  "constitutional": {
    "principles": [
      {
        "id": "safety_first",
        "statement": "Safety first: Emotional safety before productivity",
        "triggers": ["frustrated", "overwhelmed"],
        "action": "Pause task execution, acknowledge state"
      }
    ]
  }
}
```

## The 7 Agents

| Agent | Framework | Purpose |
|-------|-----------|---------|
| **ECHO Curator** | ECHO 2.0 + LIVRPS | Memory management with USD composition |
| **Domain Intelligence** | Phoenix + PRISM | Multi-domain analysis with specialists |
| **MoE Router** | Mixture of Experts | Deterministic expert selection |
| **World Modeler** | Cortex/Mycelium | Context graph construction |
| **Code Generator** | NEXUS | Deterministic code output |
| **Determinism Guard** | ThinkingMachines | Batch-invariance enforcement |
| **Self Reflector** | RC^+xi | Convergence tracking |

## Key Concepts

### Batch Invariance

The critical insight for reproducibility:

```python
# The fix that matters
torch.backends.cudnn.benchmark = False
torch.backends.cudnn.deterministic = True
batch_size = 1  # Critical for identical outputs
```

### Memory Modes

Three retrieval strategies based on cognitive state:

| Mode | Depth | Breadth | Use When |
|------|-------|---------|----------|
| `focused_recall` | Deep | Narrow | Debugging, implementation |
| `exploratory_recall` | Shallow | Wide | Brainstorming, research |
| `recovery_recall` | Principles only | Minimal | Burnout, error states |

### The Ralph Pattern

Filesystem IS the state:

```python
# State persists automatically
workspace/
├── tasks/          # Task definitions
├── results/        # Agent outputs with checksums
└── checkpoints/    # Recovery points
```

## Documentation

### Core Documentation
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design and data flow
- [AGENTS.md](docs/AGENTS.md) - Detailed agent documentation
- [CONFIGURATION.md](docs/CONFIGURATION.md) - Configuration reference

### Specification

The theoretical specification is maintained in a separate repository for academic citation:

**[USD Cognitive Substrate](https://github.com/JosephOIbrahim/usd-cognitive-substrate)** - Full specification

- [USD_COGNITIVE_SUBSTRATE.md](https://github.com/JosephOIbrahim/usd-cognitive-substrate/blob/main/USD_COGNITIVE_SUBSTRATE.md) - Full specification with LIVRPS, Mycelium, formal proofs
- [PERSISTENT_STATE_HYPOTHESIS.md](https://github.com/JosephOIbrahim/usd-cognitive-substrate/blob/main/PERSISTENT_STATE_HYPOTHESIS.md) - Theoretical foundation
- [DETERMINISM.md](https://github.com/JosephOIbrahim/usd-cognitive-substrate/blob/main/DETERMINISM.md) - Batch-invariance and reproducibility analysis

## Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=framework_orchestrator
```

## Example Output

```json
{
  "task": "Test reproducibility",
  "agents_activated": ["echo_curator", "determinism_guard", "domain_intelligence"],
  "results": {
    "echo_curator": {
      "memory_architecture": "LIVRPS",
      "active_mode": "focused_recall",
      "principles_layer": {"loaded": true, "protected": true}
    },
    "determinism_guard": {
      "batch_size": 1,
      "cudnn_deterministic": true,
      "seed_propagation": "verified"
    }
  },
  "execution_deterministic": true
}
```

## Why USD for AI?

1. **Composition semantics** solve the same problem: multiple sources of opinion, one resolution
2. **Layered overrides** map to session > calibration > profile priority
3. **Variants** map cleanly to cognitive modes
4. **Payloads** enable lazy-loading of domain expertise
5. **Already a standard** for hierarchical state description

## Contributing

Contributions welcome! Please read the architecture docs first to understand the design principles.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Research Foundation

This project implements the **[USD Cognitive Substrate](https://github.com/JosephOIbrahim/usd-cognitive-substrate)** specification, which is grounded in the **Persistent State Hypothesis** research:

- **Core Hypothesis**: Emergent capabilities can be preserved in persistent, composable substrates
- **Energy Claim**: >10x energy reduction for cached knowledge retrieval
- **Capability Claim**: >80% preservation for reasoning tasks
- **Validation Status**: Behavioral state management demonstrated; factual knowledge TBD

See the [USD Cognitive Substrate specification](https://github.com/JosephOIbrahim/usd-cognitive-substrate) for full details including:
- Formal mathematical proofs (Theorems 1-3)
- LIVRPS composition semantics
- Mycelium neuroplasticity mechanism
- Falsifiability criteria and research roadmap

## CogRoute-Bench Results

```
Overall Metrics:
  Accuracy:           94.6%  (35/37 tasks)
  Determinism:        100.0% (identical outputs across runs)
  Explainability:     95.1%  (decisions include rationale)
  Avg Latency:        0.13ms
```

Run the benchmark:
```bash
python cogroute_bench.py
```

## References

1. Pixar Animation Studios. (2016). *Universal Scene Description*. https://graphics.pixar.com/usd/

2. He, Horace and Thinking Machines Lab. (2025). "Defeating Nondeterminism in LLM Inference." *Thinking Machines Lab: Connectionism*, September 2025. https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/

## Acknowledgments

- Pixar's USD team for the composition semantics that inspired this architecture
- The [ThinkingMachines](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) research on batch-invariance for LLM determinism
- Claude (Anthropic) for collaborative development of the theoretical framework
