# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 3.1.x   | :white_check_mark: |
| 3.0.x   | :white_check_mark: |
| < 3.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

1. **DO NOT** open a public GitHub issue for security vulnerabilities
2. Email security concerns to the repository maintainer
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Timeline**: Depends on severity
  - Critical: 24-72 hours
  - High: 1-2 weeks
  - Medium: 2-4 weeks
  - Low: Next release cycle

### Severity Classification

| Severity | Description | Example |
|----------|-------------|---------|
| Critical | Remote code execution, data breach | Arbitrary code injection |
| High | Privilege escalation, auth bypass | Token leakage |
| Medium | Information disclosure, DoS | Error message leaks |
| Low | Minor issues | Verbose logging |

## Security Measures Implemented

### Input Validation
- All task inputs validated via `validation.py`
- Path sanitization for logging (`sanitize_path_for_logging`)
- Domain config schema validation (`schemas.py`)

### Resilience Against Abuse
- Rate limiting (`rate_limit.py`) - Prevents resource exhaustion
- Bulkhead isolation (`bulkhead.py`) - Prevents agent starvation
- Circuit breaker (`resilience.py`) - Prevents cascade failures

### Safe Defaults
- Non-root Docker user (UID 1000)
- Read-only filesystem where possible
- No secrets in default configuration
- Fail-fast environment validation

### Dependency Management
- Dependabot enabled for automated security updates
- Minimal runtime dependencies
- Optional dependencies clearly separated

## Security Checklist for Deployment

Before deploying to production, verify:

- [ ] **Secrets Management**: No secrets in environment variables visible to logs
- [ ] **Network Isolation**: API endpoints not exposed to public internet without auth
- [ ] **Resource Limits**: CPU/memory limits set in container orchestration
- [ ] **Logging**: Sensitive data redacted from logs
- [ ] **TLS**: All external communications use TLS 1.2+
- [ ] **Updates**: Running latest supported version

## Known Limitations

1. **No Built-in Authentication**: The HTTP API (`health.py`) does not include authentication. Deploy behind an API gateway or service mesh for production use.

2. **Correlation IDs**: While correlation IDs aid debugging, ensure they don't leak sensitive request information in logs.

3. **Checkpoint Files**: Checkpoint data (`checkpoint.py`) is stored as JSON. For sensitive workloads, consider encrypting checkpoint files at rest.

## Security-Related Configuration

```python
# Recommended production settings
OrchestratorConfig(
    enable_checkpoints=True,      # Enable crash recovery
    max_parallel_agents=3,        # Limit resource usage
    rate_limit_requests=100,      # Prevent abuse
    rate_limit_window=60,         # Per-minute window
)
```

## Audit Log

Security-relevant events are logged with structured format:

```
2024-01-23 10:15:30 | WARNING | Circuit breaker 'agent_x' OPENED after 5 failures
2024-01-23 10:15:31 | WARNING | Rate limit exceeded for client 'abc123'
2024-01-23 10:15:32 | INFO | Bulkhead rejected 'agent_y': queue_full
```

## Contact

For security concerns, contact the repository maintainer through GitHub.

---

*Last updated: 2026-01-23*
