"""
Orchestra Hooks Module
======================

Claude Code hook integration for the cognitive engine.

Usage:
    python -m orchestra.hooks < input.json

This module processes UserPromptSubmit events through the 5-Phase NEXUS Pipeline
and returns execution anchors for deterministic behavior.

ThinkingMachines [He2025] Compliance:
- Same message -> same signals -> same routing -> same params
- Deterministic execution anchor
- FIXED evaluation order (5 phases)
- FIXED priority order (experts, signals)
"""

from .cognitive_hook import process_message, main

__all__ = ['process_message', 'main']
