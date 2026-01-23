# Changelog

All notable changes to Framework Orchestrator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Helm chart for Kubernetes deployment
- Grafana dashboard templates
- OpenTelemetry metrics export (in addition to traces)

## [3.1.0] - 2026-01-23

### Added
- **Production Hardening**
  - Retry jitter to prevent thundering herd ([AWS Best Practices](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/))
  - Correlation IDs for distributed tracing
  - Fail-fast environment validation

- **Container Deployment**
  - Multi-stage Dockerfile with non-root user
  - Docker Compose with Prometheus monitoring profile
  - Kubernetes manifests with liveness/readiness probes
  - ConfigMap externalized configuration

- **HTTP API**
  - `/health` - Full health check with component status
  - `/ready` - Kubernetes readiness probe
  - `/live` - Kubernetes liveness probe
  - `/metrics` - Prometheus format metrics

- **Observability**
  - OpenTelemetry adapter (`otel_adapter.py`) for OTLP export
  - Distributed tracing with Jaeger/Zipkin compatibility
  - Prometheus metrics exposition

- **Testing**
  - 180+ tests across 17 test suites
  - Chaos engineering tests
  - Contract tests for API stability
  - Performance benchmarks

- **Documentation**
  - `CITATIONS.md` - Academic citations for all technologies
  - `SECURITY.md` - Security policy and vulnerability reporting
  - Citation headers in source files

- **CI/CD**
  - GitHub Actions CI (multi-OS, multi-Python)
  - Release automation with Docker publishing
  - Dependabot for dependency scanning

### Changed
- Circuit breaker now includes jitter in retry delays
- Logging format includes correlation IDs when available
- Health check includes all subsystem status

### Fixed
- Race condition in checkpoint recovery
- Memory leak in long-running tracing sessions

## [3.0.0] - 2026-01-15

### Added
- **Production Modules**
  - `metrics.py` - Prometheus-compatible metrics
  - `tracing.py` - Distributed tracing with span hierarchy
  - `bulkhead.py` - Agent isolation pattern
  - `checkpoint.py` - Crash recovery with atomic writes
  - `fallback.py` - Graceful degradation strategies
  - `rate_limit.py` - Request rate limiting
  - `idempotency.py` - Safe retry management

- **Infrastructure**
  - `resilience.py` - Circuit breaker, timeout, retry patterns
  - `validation.py` - Input validation and sanitization
  - `logging_setup.py` - Structured logging configuration
  - `health.py` - Health check endpoints
  - `lifecycle.py` - Graceful shutdown management
  - `file_ops.py` - Atomic file operations
  - `config.py` - Configuration management
  - `schemas.py` - JSON schema validation

### Changed
- Refactored from monolithic to modular architecture
- Domain configs moved to `~/.framework-orchestrator/domains/`

## [2.0.0] - 2026-01-01

### Added
- 7-agent async orchestration architecture
- USD LIVRPS composition semantics for memory
- Deterministic routing with hash-based expert selection
- Domain intelligence system (Phoenix + PRISM)

### Changed
- Complete architecture redesign from v1.x

## [1.0.0] - 2025-12-01

### Added
- Initial release
- Basic agent orchestration
- Domain configuration system
- Memory management with 4-tier architecture

---

## Versioning Policy

### Semantic Versioning

- **MAJOR** (X.0.0): Breaking API changes
- **MINOR** (0.X.0): New features, backward compatible
- **PATCH** (0.0.X): Bug fixes, backward compatible

### Deprecation Policy

1. Features marked deprecated in MINOR release
2. Deprecation warning logged for one MINOR cycle
3. Removal in next MAJOR release

### Support Policy

- Current MAJOR version: Full support
- Previous MAJOR version: Security fixes only
- Older versions: No support

[Unreleased]: https://github.com/JosephOIbrahim/framework-orchestrator/compare/v3.1.0...HEAD
[3.1.0]: https://github.com/JosephOIbrahim/framework-orchestrator/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/JosephOIbrahim/framework-orchestrator/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/JosephOIbrahim/framework-orchestrator/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/JosephOIbrahim/framework-orchestrator/releases/tag/v1.0.0
