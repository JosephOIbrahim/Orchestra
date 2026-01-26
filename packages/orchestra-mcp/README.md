# Orchestra MCP Server

Model Context Protocol (MCP) server for Orchestra cognitive safety layer.

## Overview

This MCP server exposes Orchestra's cognitive state management to any MCP-compatible client (Claude Desktop, Cursor, VS Code, etc.). It enables cross-tool safety gating and cognitive state awareness.

## Installation

```bash
pip install orchestra-mcp
```

Or install from source:

```bash
cd Orchestra/packages/orchestra-mcp
pip install -e .
```

## Configuration

### Claude Desktop

Add to your Claude Desktop config (`~/.config/claude-desktop/config.json` on Linux/macOS or `%APPDATA%\Claude\config.json` on Windows):

```json
{
  "mcpServers": {
    "orchestra": {
      "command": "orchestra-mcp"
    }
  }
}
```

### Cursor / VS Code

Add to your MCP settings:

```json
{
  "mcp": {
    "servers": {
      "orchestra": {
        "command": "orchestra-mcp"
      }
    }
  }
}
```

## Tools

### `orchestra_status`

Get current cognitive state.

```
Burnout: GREEN | Energy: medium | Max Depth: deep

{
  "burnout_level": "green",
  "energy_level": "medium",
  "momentum_phase": "building",
  "mode": "focused",
  "max_thinking_depth": "deep",
  "should_intervene": false,
  ...
}
```

### `orchestra_check`

Check if an operation is safe given current state.

**Input:**
```json
{
  "operation": "deep architecture analysis",
  "thinking_depth": "ultradeep"
}
```

**Output:**
```
ADJUST DEPTH: Burnout at ORANGE - depth capped at standard

{
  "operation": "deep architecture analysis",
  "requested_depth": "ultradeep",
  "allowed": false,
  "recommended_depth": "standard",
  "reason": "Burnout at ORANGE - depth capped at standard"
}
```

### `orchestra_calibrate`

Set focus and urgency calibration.

**Input:**
```json
{
  "focus_level": "locked_in",
  "urgency": "deadline"
}
```

### `orchestra_expert`

Get recommended intervention expert for a message.

**Input:**
```json
{
  "message": "I'm so frustrated, nothing is working!"
}
```

**Output:**
```
Expert: VALIDATOR (priority 1)
Trigger: frustrated_detected

{
  "expert": "validator",
  "trigger": "frustrated_detected",
  "priority": 1,
  "safety_gate_pass": true
}
```

### `orchestra_set_burnout`

Manually set burnout level.

**Input:**
```json
{
  "level": "yellow"
}
```

### `orchestra_set_energy`

Manually set energy level.

**Input:**
```json
{
  "level": "low"
}
```

## Safety Gating

The MCP server enforces Orchestra's safety invariants:

| State | Max Thinking Depth |
|-------|-------------------|
| `energy=depleted` | minimal |
| `energy=low` | standard |
| `burnout>=ORANGE` | standard |
| `burnout=RED` | minimal |
| `energy=high` | ultradeep (if requested) |

**Rule:** Safety state ALWAYS overrides requested depth. Can reduce, never increase.

## Use Cases

1. **Cross-tool safety:** Check cognitive state before starting complex operations in any tool
2. **Context awareness:** Let AI assistants know your current capacity
3. **Intervention routing:** Route messages to appropriate experts based on emotional signals
4. **Session calibration:** Set focus/urgency at the start of work sessions

## Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run server directly
python -m orchestra_mcp.server
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.

## References

- [MCP Specification](https://modelcontextprotocol.io/)
- [Orchestra](https://github.com/JosephOIbrahim/Orchestra)
- [ThinkingMachines batch-invariance [He2025]](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)
