# Orchestra Advancement Roadmap

**Status:** v5.0.1 Shipped | Public Repository | CI Green

---

## Current State (2026-01-26)

### Shipped
- ✅ Orchestra v5.0.1 production-stable
- ✅ 792 tests passing (including 15 property-based)
- ✅ CI/CD with matrix testing (Ubuntu/Windows × Python 3.10-3.12)
- ✅ Branch protection on main
- ✅ ThinkingMachines [He2025] compliant
- ✅ Public on GitHub

### Tier 1 Features (Just Completed)
- ✅ Property-based testing with Hypothesis
- ✅ MCP server package (orchestra-mcp)
- ✅ Context engineering alignment documentation

---

## Next Steps by Priority

### Tier 2: Medium-Impact (Next Sprint)

| Feature | Skill | Effort | Impact |
|---------|-------|--------|--------|
| **Fuzz testing** | atheris | Medium | Find edge cases in safety gating |
| **Semgrep rules** | semgrep | Low | Custom rules for determinism patterns |
| **Coverage in CI** | coverage-analysis | Low | Ensure safety paths tested |
| **Code maturity audit** | code-maturity-assessor | Low | External quality validation |

### Tier 3: Documentation & Polish

| Feature | Description | Effort |
|---------|-------------|--------|
| **PDF generation** | Academic paper format for substrate | Low |
| **PR automation** | differential-review for PRs | Low |
| **Security audit** | audit-context-building | Medium |

---

## MCP Server Deployment

The `orchestra-mcp` package needs:

1. **PyPI publication** - Make installable via `pip install orchestra-mcp`
2. **Claude Desktop testing** - Verify integration
3. **Cursor integration** - Test in VS Code/Cursor

### Installation (Current)
```bash
cd Orchestra/packages/orchestra-mcp
pip install -e .
```

### Installation (Target)
```bash
pip install orchestra-mcp
```

---

## Academic Publication Pipeline

Three repos form a coherent publication suite:

| Repo | Content | Status |
|------|---------|--------|
| **persistent-state-hypothesis** | Theory paper | Public |
| **usd-cognitive-substrate** | Specification | Public |
| **Orchestra** | Implementation | Public, v5.0.1 |

### Next Steps
1. Convert substrate spec to LaTeX/arXiv format
2. Generate figures from architecture docs
3. Submit to arXiv (cs.AI or cs.HC)

---

## Technical Debt

| Item | Priority | Notes |
|------|----------|-------|
| MCP package not on PyPI | High | Blocks external adoption |
| No fuzz testing | Medium | Safety boundaries untested |
| No semgrep rules | Low | Could catch determinism violations |

---

## Metrics Targets

| Metric | Current | Target |
|--------|---------|--------|
| Test count | 792 | 850+ |
| Code coverage | Unknown | 90%+ |
| Determinism score | 100% | 100% |
| Property tests | 15 | 25+ |

---

## Long-Term Vision

1. **Claude Code integration** - Ship as default cognitive layer
2. **Multi-model support** - Not just Claude
3. **Academic recognition** - Cited papers on cognitive safety
4. **Community adoption** - MCP ecosystem integration

---

*Updated: 2026-01-26*
