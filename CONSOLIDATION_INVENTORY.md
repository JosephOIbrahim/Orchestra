# Orchestra Consolidation Inventory

**Date:** 2026-01-23
**Methodology:** ThinkingMachines [He2025] batch-invariance compliant

---

## Source Locations (Now Deprecated)

| Location | Size | Purpose |
|----------|------|---------|
| `C:\Users\User\.claude\Framework_Orchestrator\` | ~52MB | Source code, React dashboard, git repo |
| `C:\Users\User\.framework-orchestrator\` | ~206KB | Runtime config, state, domains |

---

## Target Location

```
C:\Users\User\Orchestra\
```

---

## Consolidated Assets

### Python Backend (src/orchestra/)

| Module | Lines | Purpose |
|--------|-------|---------|
| `framework_orchestrator.py` | 2100+ | Main 7-agent orchestrator |
| `config.py` | 400+ | Configuration with env var support |
| `resilience.py` | 500+ | Circuit breaker, retry logic |
| `checkpoint.py` | 500+ | Crash recovery checkpoints |
| `bulkhead.py` | 400+ | Concurrency isolation |
| `metrics.py` | 450+ | Prometheus metrics |
| `tracing.py` | 500+ | OpenTelemetry tracing |
| `health.py` | 270+ | Health check endpoints |
| `lifecycle.py` | 300+ | Graceful shutdown |
| `http_server.py` | 300+ | HTTP API server |
| `fallback.py` | 450+ | Fallback strategies |
| `rate_limit.py` | 360+ | Rate limiting |
| `idempotency.py` | 340+ | Request deduplication |
| `validation.py` | 230+ | Input validation |
| `file_ops.py` | 180+ | Safe file operations |
| `logging_setup.py` | 270+ | Structured logging |
| `schemas.py` | 320+ | JSON schemas |
| `cogroute_bench.py` | 700+ | Benchmark suite |
| `otel_adapter.py` | 280+ | OpenTelemetry adapter |
| `__init__.py` | 220+ | Package exports |
| `__main__.py` | 15 | CLI entry point |

**Total: 22 Python modules**

### React Dashboard (src/dashboard/)

#### Components (22 files)
- `SimplifiedDashboard.jsx` - Maeda-inspired minimal UI
- `CognitiveAppShell.jsx` - Main cognitive dashboard shell
- `CognitiveStatePanel.jsx` - Burnout/momentum display
- `ConvergenceMonitor.jsx` - RC^+xi convergence tracking
- `RoutingDisplay.jsx` - Expert routing visualization
- `LayerStackViewer.jsx` - USD layer stack
- `AgentOrchestra.jsx` - Agent status visualization
- `ADHDSupportPanel.jsx` - Executive function support
- `TaskInterface.jsx` - Task input/output
- `Header.jsx`, `Icons.jsx`, `AppShell.jsx`
- `ActivityPanel.jsx`, `MetricsPanel.jsx`
- `AgentCard.jsx`, `AgentsList.jsx`, `StatusCard.jsx`
- `LatencyChart.jsx`, `TaskInput.jsx`
- `Modal.jsx`, `Toast.jsx`

#### Styles (5 files)
- `maeda.css` - John Maeda's Laws of Simplicity
- `cognitive.css` - Cognitive state styling
- `components.css` - Component styles
- `variables.css` - CSS variables
- `layout.css` - Layout system

#### Support Files
- `server.py` - Flask API server
- `package.json` - npm dependencies
- `vite.config.js` - Vite build config
- `index.html` - Entry HTML
- `dist/` - Production build

### Configuration (config/)

#### Domain Configs (5 files)
| Domain | Specialists | Keywords |
|--------|-------------|----------|
| `vfx.json` | 9 | USD, Houdini, Nuke, Karma |
| `webdev.json` | 6 | React, Next.js, CSS, API |
| `ai_research.json` | 7 | ML, agents, prompts |
| `ai_conductor.json` | 10 | Orchestration, cognitive |
| `general.json` | 5 | Default domain |

#### Framework Modules (5 directories)
- `adhd_moe/` - ADHD intervention experts
- `cortex_world/` - World modeling
- `echo_memory/` - Context memory
- `max_reflection/` - Bounded reflection
- `nova_oracle/` - Self-play generation

#### Principles
- `principles.json` - 7 constitutional rules

### Tests (tests/)

**25 test files** covering:
- Orchestrator core
- All resilience modules
- Configuration
- Integration tests
- Performance benchmarks
- Chaos testing

### Documentation (docs/)

- Architecture diagrams
- API documentation
- History/changelog
- Images/assets

### Examples (examples/)

- Sample domain configurations
- Usage examples

---

## Path Mappings

| Old Path | New Path |
|----------|----------|
| `~/.framework-orchestrator/` | `~/Orchestra/` |
| `~/.framework-orchestrator/domains/` | `~/Orchestra/config/domains/` |
| `~/.framework-orchestrator/frameworks/` | `~/Orchestra/config/frameworks/` |
| `~/.framework-orchestrator/principles.json` | `~/Orchestra/config/principles.json` |
| `~/.framework-orchestrator/results/` | `~/Orchestra/state/results/` |
| `~/.framework-orchestrator/checkpoints/` | `~/Orchestra/state/checkpoints/` |
| `~/.framework-orchestrator/.orchestrator-state.json` | `~/Orchestra/state/.orchestrator-state.json` |

---

## Code Changes Made

1. **config.py** (lines 108-165)
   - Default workspace: `~/Orchestra`
   - Added `config_dir` and `state_dir` properties
   - Updated all path properties to use new structure

2. **framework_orchestrator.py**
   - Line 16: Updated docstring path
   - Line 166: `PRINCIPLES_PATH` → `~/Orchestra/config/principles.json`
   - Line 449: `DEFAULT_DOMAINS_PATH` → `~/Orchestra/config/domains`
   - Line 2089: Updated help text

3. **server.py** (dashboard)
   - Removed legacy vanilla JS fallback
   - `REACT_DIST_DIR` now same directory as server.py
   - Simplified to React-only

---

## Files NOT Consolidated (Intentionally Excluded)

| File | Reason |
|------|--------|
| `create_icon.py` | Utility script, not core functionality |
| `setup.py` | Can be regenerated from pyproject.toml |
| `test_local_orchestration.py` | Local test file |
| `node_modules/` | Reinstall with npm |
| `.git/` | Fresh git history for Orchestra |
| `dashboard/templates/` | Legacy vanilla JS (replaced by React) |
| `dashboard/static/` | Legacy vanilla JS assets |
| Various `.bat`, `.ps1` scripts | Windows shortcuts, can regenerate |

---

## Verification Results

```
✓ Orchestrator loads: 7 agents, 5 domains, 7 principles
✓ Checkpoint path: ~/Orchestra/state/checkpoints
✓ Domains path: ~/Orchestra/config/domains
✓ Dashboard server module loads
✓ React build exists in dist/
✓ All 25 test files present
```

---

## Usage

```bash
# Run orchestrator
cd C:\Users\User\Orchestra
python -m src.orchestra --task "your task"
python -m src.orchestra --info

# Run dashboard
cd src/dashboard
npm install  # first time only
npm run build
python server.py
# Visit http://localhost:5050
```
