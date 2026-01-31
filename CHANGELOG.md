# Changelog

All notable changes to Orchestra will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [7.0.0] - 2026-01-31

### Added

- **BCM Stigmergic Reinforcement Learning**: Bienenstock-Cooper-Munro learning rule for expert routing
  - Trail confidence tracks expert success rates over time
  - Plasticity windows boost learning during crash recovery or burnout
  - Signal reliability correlates detected signals with routing outcomes
  - **Critical:** BCM is metadata only—never changes routing order (ThinkingMachines compliance preserved)

- **Plasticity Auto-Triggers**: Automatic plasticity window management
  - Auto-OPEN on `momentum=crashed` + `burnout=ORANGE`
  - Auto-OPEN on `burnout=RED` (emergency learning mode, divergence=1.0)
  - Auto-CLOSE on convergence + 3 stable exchanges

- **Signal Reliability Tracking**: Fingerprint-based signal outcome correlation
  - `SignalVector.get_signal_fingerprint()` captures compact signal representation
  - Outcomes recorded via `record_outcome(success)` method
  - Batch-invariant: fingerprints captured but not used during processing

- **TUI Dashboard BCM Metrics**: New Row 4 with BCM visualization
  - BCM confidence bar chart with percentage
  - BCM status indicator (`◈ PLASTIC` yellow or `◇ STABLE` green)
  - `b` keyboard shortcut to toggle plasticity window manually

- **Hook Integration Tests**: 17 new tests for BCM + hook compliance
  - `TestHookLoadsBCMTrail`: Trail loading on first message
  - `TestHookIncludesBCMAnchor`: Anchor BCM metadata verification
  - `TestDeterminismThroughHook`: Same input → same routing
  - `TestBCMDoesntChangeRoutingOrder`: Trail data is metadata only
  - `TestThinkingMachinesCompliance`: Fixed priority order, queued updates

- **BCM Public API Exports**: Full BCM module access via `orchestra` package
  - `BCMConfig`, `Trail`, `PlasticityState`, `OrchestraTrail`
  - `BCMPipelineAdapter`, `load_trail`, `save_trail`, `get_trail_path`
  - Helper functions: `calculate_theta_m`, `calculate_saturation_factor`, `apply_decay`, `reinforce_trail`

### Changed

- **Domain Focus**: AI Research and cognitive substrate development (primary)
  - VFX payloads (USD/Houdini/Karma/Nuke) moved to extension modules
  - Not bundled by default—reduces base context load
  - Keeps Orchestra focused on core mission: cognitive safety for AI-assisted development

- **Pipeline**: 5-Phase → 8-Phase NEXUS Pipeline
  - Phase 0: RETRIEVE (knowledge check, fast path)
  - Phase 0b: CLASSIFY (source mode: LEARN/ACCESS/HYBRID)
  - Phase 0c: GROUND (oracle query if ACCESS/HYBRID)
  - Phases 1-5 unchanged

- **State Schema**: 37 core fields + 7 BCM fields = 44 total
  - BCM trail persistence at `~/.orchestra/bcm/trail_{session}.json`

- Test count: 917 → 1047 (all passing)
  - 66 BCM integration tests
  - 17 hook integration tests
  - 118 distillation tests (carried from 5.0.2)

### Fixed

- Floating-point comparison in BCM trail loading tests (use `pytest.approx`)
- Trail file path resolution for session-based persistence

## [5.0.2] - 2026-01-26

### Added

- **Knowledge Distillation Pipeline**: Production-hardened pipeline for transforming documentation into searchable Knowledge Prims
  - 9-stage pipeline: Ingest → Query → Answer → Extract → Trigger → Validate → Score → Write → Benchmark
  - **Checkpointing**: Resume from any stage after failures (atomic saves, config hash validation)
  - **Pydantic Schemas**: Robust LLM response parsing with automatic coercion ("high" → 0.85)
  - **Async Batch Executor**: Rate-limited parallel processing with configurable concurrency
  - **Multi-stage Validation**: Heuristic checks, source quote verification, LLM hallucination detection
  - **Atomic Writes**: Temp file → rename pattern prevents corruption

- **Frontier AI Enhancements** (Optional, configurable)
  - **Self-Consistency Verification**: Multi-sample voting for claim validation
  - **Entailment Grounding**: NLI-based claim verification against source documents

- **Production Hardening**
  - `response_schemas.py`: Pydantic models for all LLM response types
  - `errors.py`: Structured exception hierarchy (DistillationError, LLMResponseError, etc.)
  - `async_executor.py`: Semaphore-based rate limiting with retries
  - `checkpoint.py`: Pipeline resumability with stage data serialization
  - Encoding fallbacks in corpus ingestion (UTF-8 → Latin-1 → CP1252)

- **ThinkingMachines [He2025] Determinism Fixes**
  - Fixed hash truncations (16→64 chars for cache keys, 6→12 chars for prim IDs)
  - Fixed iteration order (sorted() on sets, dicts, file discovery)
  - Fixed accumulation order (COMPONENT_ORDER constant for confidence scoring)
  - Added `deterministic_checksum` to PipelineStats

- **118 New Distillation Tests**
  - Batch invariance tests (hash determinism, iteration order, checksum reproducibility)
  - Pydantic schema tests (coercion, edge cases, malformed responses)
  - Async executor tests (rate limiting, concurrency, timeouts)
  - Checkpoint tests (save/load, resume, atomic writes)
  - Frontier AI tests (self-consistency verification, entailment grounding)
  - Pipeline integration tests (E2E, determinism, error handling)

### Changed

- Test count: 798 → 917 (all passing)
- Updated README with Knowledge Distillation section
- Added `distillation` optional dependency group in pyproject.toml

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
