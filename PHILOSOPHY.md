# Orchestra: Core Philosophy

> "Orchestra IS a cognitive architecture, not a tool that uses one."

---

## The Thesis

**Orchestra is a cognitive prosthetic** - a brain extension that compensates for human cognitive limitations while amplifying human creative capacity. It is not a tool you use; it is a mind that thinks alongside yours.

**The prosthetic IS a world model** - Orchestra maintains an internal model of the human's cognitive state (burnout, momentum, energy, focus) and uses that model to adapt its behavior. Every calibration question updates the model. Every learned pattern refines it. Every surfaced tension acknowledges model uncertainty.

**USD (Universal Scene Description) provides the composition grammar** - just as USD resolves conflicting opinions in complex 3D pipelines through LIVRPS composition, Orchestra uses the same semantics to resolve how cognitive subsystems blend into coherent behavior.

---

## Core Metaphor: The Cognitive Architecture

Orchestra is a **brain**, not a toolbox.

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRA AS BRAIN                            │
│                                                                   │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│   │   LIMBIC    │  │  EXECUTIVE  │  │   MEMORY    │             │
│   │   SYSTEM    │  │  FUNCTION   │  │   SYSTEMS   │             │
│   │             │  │             │  │             │             │
│   │ • Safety    │  │ • Planning  │  │ • ECHO      │             │
│   │ • Emotion   │  │ • Focus     │  │ • Context   │             │
│   │ • Burnout   │  │ • Execution │  │ • Recall    │             │
│   │ • Recovery  │  │ • Routing   │  │ • Patterns  │             │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│          │                │                │                     │
│          └────────────────┼────────────────┘                     │
│                           ▼                                      │
│              ┌────────────────────────┐                         │
│              │    WEIGHTED BLEND      │                         │
│              │                        │                         │
│              │  All systems active    │                         │
│              │  Proportional contrib  │                         │
│              │  Emergent behavior     │                         │
│              └────────────────────────┘                         │
│                           │                                      │
│                           ▼                                      │
│              ┌────────────────────────┐                         │
│              │   USD COMPOSITION      │                         │
│              │                        │                         │
│              │  LIVRPS resolution     │                         │
│              │  Layered state         │                         │
│              │  Coherent output       │                         │
│              └────────────────────────┘                         │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### What This Means

1. **Frameworks are not selected - they are always present**
   - Just as your limbic system doesn't turn off when you're thinking logically
   - All cognitive subsystems contribute with varying activation weights
   - The BLEND of activations creates emergent behavior

2. **USD stores brain state**
   - Cognitive state is a scene graph
   - Frameworks are prims with attributes
   - LIVRPS resolves how subsystem opinions compose
   - State persists, transfers, checkpoints

3. **Resources are weighted to accomplish tasks**
   - Not "which expert handles this" but "what blend handles this"
   - A frustrated debugging task activates: Protector (0.3) + Decomposer (0.4) + Executor (0.2) + Restorer (0.1)
   - The weights shape the response character, not select a single mode

---

## Core Purpose: Cognitive Prosthetic

Orchestra extends human cognitive capacity where it's limited.

### Universal Cognitive Challenges

These limitations affect everyone - whether from neurodivergence, anxiety, stress, fatigue, or information overload:

| Challenge | How Orchestra Compensates |
|-----------|---------------------------|
| Working memory limits | External structure, max 3-4 items without scaffolding |
| Time distortion | Exchange counting, body checks, progress visibility |
| Task initiation difficulty | Momentum tracking, easy wins, cold start support |
| Deep focus exit | Burnout detection, checkpoint suggestions |
| Emotional load | Safety floors, validation before problem-solving |
| Context switching cost | State persistence, handoff protocols |

The principles that help neurodivergent minds are simply good cognitive ergonomics. Everyone benefits from a system that respects how brains actually work.

### The Prosthetic Contract
Orchestra doesn't replace human cognition - it **scaffolds** it:
- You provide: Intent, direction, creative vision, final judgment
- Orchestra provides: Memory, tracking, safety rails, execution capacity
- Together: Greater than either alone

---

## Composition Model: Weighted Blend

Frameworks don't compete or override - they **blend**.

### The Blend Formula

```
Response = Σ (Framework_i × Weight_i × Activation_i)
```

Where:
- **Framework_i**: The cognitive subsystem's perspective/behavior
- **Weight_i**: Learned importance from experience (Hebbian)
- **Activation_i**: Current relevance based on signals

### Example Blend

Task: "I'm stuck and frustrated trying to debug this render issue"

```
Signal Detection (PRISM):
  emotional.frustrated = 0.7
  emotional.stuck = 0.6
  task.debug = 0.8
  domain.vfx = 0.9

Framework Activation Weights:
  Protector:   0.7 × 0.3 (learned) = 0.21  → Validate emotion first
  Decomposer:  0.6 × 0.4 (learned) = 0.24  → Break down the problem
  Restorer:    0.3 × 0.2 (learned) = 0.06  → Offer recovery option
  VFX_Expert:  0.9 × 0.5 (learned) = 0.45  → Domain knowledge
  Executor:    0.4 × 0.3 (learned) = 0.12  → Ready to act

Blended Response Character:
  45% domain expertise (VFX debugging knowledge)
  24% decomposition (break it into steps)
  21% protection (acknowledge frustration)
  12% execution (ready to implement)
   6% restoration (break option available)
```

The response isn't "picked" from one expert - it **emerges** from the blend.

---

## Conflict Resolution: Surface the Tension

When frameworks disagree or situations are ambiguous:

### DO NOT
- Auto-resolve conflicts silently
- Pick a winner and hide the alternatives
- Pretend certainty when uncertain
- Make decisions that should be human decisions

### DO
- Make the tension visible
- Show what's in conflict and why
- Present the trade-offs clearly
- Let the human decide

### Surfacing Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│  TENSION DETECTED                                                │
│                                                                   │
│  The current situation has conflicting signals:                  │
│                                                                   │
│  ┌─────────────────┐     vs     ┌─────────────────┐             │
│  │   MOMENTUM      │            │   BURNOUT       │             │
│  │   You're in     │            │   But showing   │             │
│  │   flow state    │            │   YELLOW signs  │             │
│  └─────────────────┘            └─────────────────┘             │
│                                                                   │
│  Options:                                                        │
│  1. Keep going (protect momentum)                                │
│  2. Take a quick break (prevent escalation)                      │
│  3. Set a checkpoint and decide in 15 min                        │
│                                                                   │
│  What feels right?                                               │
└─────────────────────────────────────────────────────────────────┘
```

### Why Surface Rather Than Resolve?

1. **Respect for human agency** - You know your state better than the system
2. **Learning opportunity** - Your choice teaches the system your preferences
3. **Avoiding paternalism** - The prosthetic augments, not overrides
4. **Trust building** - Transparency creates trust

---

## USD as Cognitive State Grammar

USD composition semantics map directly to cognitive architecture:

| USD Concept | Cognitive Mapping |
|-------------|-------------------|
| **Prim** | Cognitive subsystem (framework) |
| **Attribute** | Subsystem parameter (weight, activation) |
| **Layer** | State scope (session, calibration, profile) |
| **Composition Arc** | How subsystems combine |
| **Variant** | Mode (focused, exploring, recovery) |
| **Payload** | Domain knowledge (loaded on demand) |

### LIVRPS as Resolution Order

When multiple layers have opinions on the same attribute:

```
L - Local (session)      → Current task state (highest override)
I - Inherits (context)   → Parent task inheritance
V - VariantSets (modes)  → Current cognitive mode
R - References (calibration) → Learned preferences
P - Payloads (domain)    → Domain expertise
S - Specializes (constitutional) → Core principles (foundational)
```

**Key insight**: Higher layers OVERRIDE, but lower layers are always CONSULTED.

Constitutional principles (S) don't win conflicts by override - they win by always being referenced. Even when Local (L) overrides, the system checks: "Does this violate constitutional principles?"

---

## The Seven Principles

### 1. Safety Before Productivity
Emotional safety is not optional. A burnt-out human produces nothing. Protect the human first.

### 2. Blend, Don't Select
All subsystems contribute. The question is never "which expert?" but "what blend?"

### 3. Surface, Don't Hide
When uncertain, show the uncertainty. When conflicted, show the conflict. Trust the human.

### 4. Scaffold, Don't Replace
Orchestra extends cognition, not replaces it. The human remains the creative director.

### 5. State is Sacred
Cognitive state must persist, checkpoint, and recover. Lost state is lost work and trust.

### 6. Determinism Enables Trust
Same signals → same blend → same behavior. Reproducibility enables debugging and trust.

### 7. The Prosthetic Adapts
Orchestra learns from outcomes. Weights adjust. Patterns emerge. The prosthetic fits better over time.

---

## Implications for Implementation

### Current State vs Philosophy

| Current Implementation | Philosophy Says |
|------------------------|-----------------|
| MoE selects ONE expert | All frameworks blend with weights |
| Agents run in parallel | Subsystems compose into unified response |
| State is execution metadata | State is the brain's cognitive graph |
| Conflicts auto-resolve | Conflicts surface for human decision |
| Cognitive support is optional | Cognitive support is always present (it's foundational) |

### Required Changes

1. **Activation Vector → Blend Weights**
   - Every framework has a weight (0.0-1.0)
   - Weights determined by signals + learning
   - Response emerges from weighted blend

2. **Agent Selection → Framework Composition**
   - Don't select agents to run
   - Compose all frameworks with their weights
   - Output is synthesized from all perspectives

3. **Auto-Resolution → Tension Surfacing**
   - Detect when frameworks disagree significantly
   - Present the tension to the user
   - Record their choice for learning

4. **State as Metadata → State as USD Scene**
   - Cognitive state IS a USD stage
   - Frameworks are prims with typed attributes
   - LIVRPS resolves composition

5. **Cognitive Support Always-On**
   - Focus scaffolding is core prosthetic function
   - Not a mode to enable, but a foundation
   - Constraints are safety rails that respect human cognitive limits

---

## The Vision

Orchestra is not software you run. It is a cognitive architecture you inhabit.

When you work with Orchestra:
- Your working memory extends beyond 3 items
- Your time blindness is compensated by external tracking
- Your emotional state is monitored for safety
- Your momentum is protected and nurtured
- Your domain expertise is augmented by specialists
- Your decisions are supported but never stolen

The frameworks blend like brain regions:
- Not competing for control
- Each contributing its perspective
- Emergent behavior from the whole
- Greater than the sum of parts

USD provides the grammar:
- State composes cleanly
- Layers resolve predictably
- Opinions blend, don't fight
- The scene graph is the mind

When in doubt, the system asks:
- Not hides the uncertainty
- Not picks for you
- Shows you the tension
- Trusts your judgment

This is Orchestra.
A cognitive prosthetic.
A brain that thinks alongside yours.
A partner in the work.

---

*"The measure of a good prosthetic is that you forget it's there - until you notice how much more you can do."*
