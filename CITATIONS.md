# Citations and Acknowledgments

Framework Orchestrator builds upon foundational research and open standards from multiple domains. This document provides comprehensive attribution for all technologies, research, and methodologies incorporated into this project.

---

## Core Theoretical Foundations

### Universal Scene Description (USD)

The composition semantics (LIVRPS) that form the architectural backbone of this project originate from Pixar's Universal Scene Description:

> **Pixar Animation Studios.** (2016). *Universal Scene Description*.
> Graphics Software Team, Pixar Animation Studios.
> https://graphics.pixar.com/usd/
> https://github.com/PixarAnimationStudios/USD

**Specific contributions applied:**
- LIVRPS composition order (Local, Inherits, VariantSets, References, Payloads, Specializes)
- Layered override resolution semantics
- Variant switching for mode management
- Payload lazy-loading for domain knowledge

**License:** Modified Apache 2.0 License

---

### Batch-Invariance for LLM Determinism

The determinism guarantees in this project implement the batch-invariance principles from:

> **He, Horace and Thinking Machines Lab.** (2025). "Defeating Nondeterminism in LLM Inference."
> *Thinking Machines Lab: Connectionism*, September 2025.
> https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/

**Specific contributions applied:**
- `batch_size = 1` requirement for reproducibility
- `torch.backends.cudnn.deterministic = True`
- `torch.backends.cudnn.benchmark = False`
- Fixed evaluation order for deterministic routing
- Parameter locking during generation phase

**Key insight:** "The key to defeating nondeterminism is controlling every source of randomness and ensuring evaluation order is fixed."

---

### Recursive Language Model (RLM) Paradigm

The navigation patterns for large files and codebases implement:

> **Zhang, S., Kraska, T., & Khattab, O.** (2025). "Recursive Language Models."
> *arXiv preprint arXiv:2512.24601*.
> https://arxiv.org/abs/2512.24601

**Specific contributions applied:**
- Program-environment paradigm (LLM operates ON data, not WITH data in context)
- Prior-based filtering for targeted extraction
- Recursive decomposition for large file navigation
- Answer verification with context sampling

**Key insight:** "Treat long prompts as part of an external environment and allow the LLM to programmatically examine, decompose, and recursively call itself over snippets."

---

## Production Engineering Standards

### OpenTelemetry

Distributed tracing integration follows:

> **OpenTelemetry Authors.** (2019-2025). *OpenTelemetry Specification*.
> Cloud Native Computing Foundation (CNCF).
> https://opentelemetry.io/
> https://github.com/open-telemetry/opentelemetry-specification

**Specific standards implemented:**
- W3C Trace Context propagation format
- OTLP (OpenTelemetry Protocol) export
- Span hierarchy and attribute conventions
- Jaeger and Zipkin compatibility

**License:** Apache 2.0 License

---

### Prometheus Metrics

Observability metrics follow:

> **Prometheus Authors.** (2012-2025). *Prometheus Monitoring System*.
> Cloud Native Computing Foundation (CNCF).
> https://prometheus.io/
> https://github.com/prometheus/prometheus

**Specific standards implemented:**
- Counter, Gauge, Histogram metric types
- Exposition format for `/metrics` endpoint
- Label conventions for multi-dimensional metrics

**License:** Apache 2.0 License

---

### Kubernetes

Container orchestration patterns follow:

> **The Kubernetes Authors.** (2014-2025). *Kubernetes*.
> Cloud Native Computing Foundation (CNCF).
> https://kubernetes.io/
> https://github.com/kubernetes/kubernetes

**Specific patterns implemented:**
- Liveness and Readiness probe conventions
- ConfigMap externalized configuration
- Deployment with rolling update strategy
- Service discovery via ClusterIP

**License:** Apache 2.0 License

---

## Resilience Patterns

### Circuit Breaker Pattern

> **Nygard, Michael T.** (2007). *Release It! Design and Deploy Production-Ready Software*.
> Pragmatic Bookshelf. ISBN: 978-0978739218.

> **Fowler, Martin.** (2014). "CircuitBreaker."
> https://martinfowler.com/bliki/CircuitBreaker.html

**Implementation:** `resilience.py:CircuitBreaker`

---

### Bulkhead Pattern

> **Nygard, Michael T.** (2007). *Release It!*
> Chapter 5: Stability Patterns - Bulkheads.

**Implementation:** `bulkhead.py:BulkheadExecutor`

The bulkhead pattern is named after ship compartments that prevent flooding from spreading.

---

### Exponential Backoff with Jitter

> **AWS Architecture Blog.** (2015). "Exponential Backoff And Jitter."
> https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

**Implementation:** `resilience.py:with_retry()` with `jitter` parameter

**Key insight:** Jitter prevents thundering herd by adding randomness to retry timing.

---

## Research Context

### USD Cognitive Substrate

This project implements the specification:

> **Ibrahim, Joseph O.** (2026). "USD Cognitive Substrate: Applying Universal Scene Description Composition Semantics to AI Agent Orchestration."
> DOI: [10.5281/zenodo.18332346](https://doi.org/10.5281/zenodo.18332346)
> https://github.com/JosephOIbrahim/usd-cognitive-substrate

---

### Persistent State Hypothesis

The theoretical foundation:

> **Ibrahim, Joseph O.** (2026). "The Persistent State Hypothesis: Preserving Emergent Capabilities in Composable Substrates."
> https://github.com/JosephOIbrahim/persistent-state-hypothesis

**Core claim:** "The emergent capabilities of large-scale neural networks can be preserved in a persistent, composable substrate that does not require constant recomputation."

---

## Software Dependencies

### Python Standard Library

- `asyncio` - Asynchronous I/O
- `dataclasses` - Structured data
- `contextvars` - Thread-safe context (correlation IDs)
- `hashlib` - Deterministic hashing
- `json` - Serialization
- `logging` - Structured logging
- `pathlib` - File operations
- `threading` - Concurrency primitives
- `typing` - Type annotations

### Optional Dependencies

| Package | Purpose | License |
|---------|---------|---------|
| `pytest` | Testing | MIT |
| `pytest-asyncio` | Async test support | Apache 2.0 |
| `opentelemetry-api` | Tracing API | Apache 2.0 |
| `opentelemetry-sdk` | Tracing SDK | Apache 2.0 |
| `torch` | Determinism settings | BSD |

---

## Acknowledgments

### Organizations

- **Pixar Animation Studios** - For creating USD and open-sourcing composition semantics that elegantly solve multi-source opinion resolution
- **Thinking Machines Lab** - For rigorous research on LLM determinism that enabled reproducible agent execution
- **Cloud Native Computing Foundation** - For OpenTelemetry, Prometheus, and Kubernetes standards
- **Anthropic** - For Claude, which collaborated on theoretical framework development

### Individuals

- **Horace He** (Thinking Machines Lab) - Batch-invariance research
- **Shuyan Zhang, Tim Kraska, Omar Khattab** - RLM paradigm
- **Michael T. Nygard** - Resilience patterns documentation
- **Martin Fowler** - Circuit breaker pattern articulation

---

## Citation Format

If you use Framework Orchestrator in academic work, please cite:

```bibtex
@software{framework_orchestrator,
  author = {Ibrahim, Joseph O.},
  title = {Framework Orchestrator: USD Composition Semantics for AI Agent Orchestration},
  year = {2026},
  publisher = {GitHub},
  url = {https://github.com/JosephOIbrahim/framework-orchestrator},
  doi = {10.5281/zenodo.18332346}
}
```

For the underlying theoretical work:

```bibtex
@article{usd_cognitive_substrate,
  author = {Ibrahim, Joseph O.},
  title = {USD Cognitive Substrate: Applying Universal Scene Description Composition Semantics to AI Agent Orchestration},
  year = {2026},
  doi = {10.5281/zenodo.18332346}
}

@article{persistent_state_hypothesis,
  author = {Ibrahim, Joseph O.},
  title = {The Persistent State Hypothesis: Preserving Emergent Capabilities in Composable Substrates},
  year = {2026}
}
```

---

## License Compliance

All incorporated technologies are used in compliance with their respective licenses:

| Technology | License | Compliance |
|------------|---------|------------|
| USD | Modified Apache 2.0 | Concepts applied, not code |
| OpenTelemetry | Apache 2.0 | Optional dependency |
| Prometheus | Apache 2.0 | Format compatibility |
| Kubernetes | Apache 2.0 | Manifest conventions |
| Python | PSF License | Runtime |

This project is released under the **MIT License**, which is compatible with all dependencies.

---

*Last updated: 2026-01-23*
