# Changelog

All notable changes to Orchestra will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.0.3] - 2026-05-14

Opus 4.7 vocabulary alignment. Additive, non-breaking.

### Added

- `DEPTH_TO_EFFORT` mapping in `parameter_locker.py` aligning Orchestra's depth
  tiers with Anthropic's `output_config.effort` levels
  (`MINIMAL→"low"`, `STANDARD→"medium"`, `DEEP→"high"`, `ULTRADEEP→"xhigh"`).
  On Opus 4.7, `thinking.budget_tokens` is removed (400 error); `effort` is the
  correct knob. `xhigh` is new on 4.7 — recommended for coding/agentic work.
- `DEPTH_TO_EFFORT` exported from the `orchestra` top-level package alongside
  the existing `DEPTH_BUDGETS`.
- "Scope of Determinism" section in `THINKINGMACHINES_COMPLIANCE.md`
  distinguishing Orchestra's batch-invariant routing (deterministic per He2025)
  from Claude API output (not deterministic, especially under adaptive thinking).
- New `TestDepthToEffort` class in `tests/test_parameter_locker.py`.

### Changed

- Softened the all-caps imperatives in `claude_code_hook.py` `expert_guidance`
  prose (`EMPATHY FIRST.`, `BREAK DOWN`, etc.) to conditional phrasing.
  Opus 4.7 follows literal instructions more strictly than 4.6; the previous
  aggressive imperative pattern overtriggered. Routing behavior unchanged.

### Compatibility

- `DEPTH_BUDGETS` remains exported and unchanged. Downstream consumers of
  `cognitive-orchestra` are not affected.
- `ThinkDepth` enum members and `.value` strings unchanged
  (`"minimal"`, `"standard"`, `"deep"`, `"ultradeep"`).
- Anchor format unchanged (`[EXEC:checksum|expert|paradigm|altitude|depth]`).
- MCP server schema unchanged.

### Deferred to 5.1.0

- MCP server `anthropic` SDK integration with prompt caching and `effort` mapping.
- Consolidation of duplicate `expert_guidance` dicts
  (`hooks/cognitive_hook.py` and `claude_code_hook.py` have drifted).
- Per-expert temperature config audit in `framework_orchestrator.py:758-774`
  (currently dict metadata only; never reaches an API call).

## [5.0.2] - 2026-02-XX

CHANGELOG entry added retroactively in 5.0.3.

### Changed

- Version bump in `pyproject.toml`. Details lost — no contemporaneous entry.

## [5.0.1] - 2026-01-26

CHANGELOG entry added retroactively in 5.0.3 (per `ADVANCEMENT_ROADMAP.md`).

### Added

- Property-based testing with Hypothesis (22 tests).
- MCP server package (`orchestra-mcp`, v1.0.0).
- Context engineering alignment documentation.
- Fuzz testing with Hypothesis (7 tests; Atheris on Linux CI).
- Semgrep determinism rules — 9 rules in `.semgrep/orchestra-determinism.yaml`
  (unseeded random, dict-iteration-unsorted, json.dumps-no-sort-keys, time-in-routing,
  state-mutation-without-batch, set-iteration, async-gather-unordered,
  thinking-depth-bypass, burnout-override).
- Code coverage in CI (50% threshold, Codecov integration).
- PyPI publish workflows (`cognitive-orchestra` and `orchestra-mcp`).
- PR automation workflow with Semgrep differential review.

## [5.0.0] - 2026-01-26

### Added

- **5-Phase NEXUS Pipeline**: Complete cognitive orchestration engine
  - Phase 1: DETECT - PRISM signal extraction (emotional > mode > domain > task)
  - Phase 2: CASCADE - Safety gates + 7-expert MoE routing
  - Phase 3: LOCK - MAX3 bounded reflection + deterministic checksums
  - Phase 4: EXECUTE - Parameter-locked generation
  - Phase 5: UPDATE - RC^+xi convergence tracking

- **Cognitive Safety MoE**: 7 intervention experts with fixed priority
  - Validator, Scaffolder, Restorer, Refocuser, Celebrator, Socratic, Direct
  - First-match-wins semantics for deterministic routing

- **ThinkingMachines [He2025] Compliance**
  - Batch-invariant kernels (same inputs → same outputs)
  - Fixed reduction order across all operations
  - No dynamic switching strategies
  - Reproducible checksums

- **Production Resilience Patterns**
  - Circuit breaker (CLOSED → OPEN → HALF_OPEN)
  - Bulkhead pattern for resource isolation
  - Fallback registry with 3-tier cascade (cache → strategy → synthetic)
  - Retry with exponential backoff and jitter
  - Atomic file operations

- **Observability Layer**
  - OpenTelemetry adapter with graceful fallback
  - Distributed tracing with W3C context propagation
  - Prometheus-compatible metrics
  - Health check endpoints

- **CLI Tools**
  - `orchestra` - TUI dashboard
  - `orchestra status` - Cognitive state display
  - `orchestra install-hook` - Claude Code integration
  - `orchestra set` - State management

- **Test Suite**: 776 tests covering
  - Core orchestration
  - Safety gating (burnout/energy → depth caps)
  - Parameter locking determinism
  - Resilience patterns
  - Integration and chaos scenarios

### Changed

- Development status upgraded to Production/Stable
- State files moved to `~/.orchestra/state/` subdirectory
- Improved histogram bucket counting (Prometheus semantics)

### Fixed

- `otel_adapter.py` relative import bug
- `deque` slicing in Mycelium state export
- Handler name access for MagicMock compatibility
- Queue size semantics in bulkhead tests

## [4.0.0] - 2026-01-15

### Added

- USD composition semantics (LIVRPS) for cognitive state
- Cognitive state persistence
- WebSocket dashboard bridge

## [3.0.0] - 2026-01-01

### Added

- Initial Framework Orchestrator
- 7 cognitive agents
- Basic resilience patterns

---

## References

- [ThinkingMachines [He2025]](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) - Batch-invariance principles
- [USD](https://graphics.pixar.com/usd/) - Composition semantics inspiration
