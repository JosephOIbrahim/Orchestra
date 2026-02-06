#!/usr/bin/env python3
"""
Orchestra Cognitive Engine Hook for Claude Code
===============================================

This hook runs on every UserPromptSubmit event and processes the message
through the 5-Phase NEXUS Pipeline.

Integrates with USD Cognitive Substrate tier loading system for context
efficiency (83% reduction in base context load).

Usage:
    python -m orchestra.hooks < input.json

ThinkingMachines [He2025] Compliance:
- Same message -> same signals -> same routing -> same params
- Deterministic execution anchor
- FIXED evaluation order (5 phases)
- FIXED priority order (experts, signals)

Output:
- systemMessage with execution anchor and expert guidance
- hookSpecificOutput with full pipeline result
- Tier regeneration notifications when substrate changes
"""

import json
import os
import sys
from pathlib import Path

try:
    from ..cognitive_orchestrator import CognitiveOrchestrator, create_orchestrator
    from ..dashboard_bridge import DashboardBridge, create_bridge
    from ..parameter_locker import ThinkDepth
except ImportError:
    # Fallback for direct execution during development
    try:
        from orchestra.cognitive_orchestrator import CognitiveOrchestrator, create_orchestrator  # noqa: F401
        from orchestra.dashboard_bridge import DashboardBridge, create_bridge  # noqa: F401
        from orchestra.parameter_locker import ThinkDepth  # noqa: F401
    except ImportError as e:
        # Output minimal response if imports fail
        error_result = {
            "systemMessage": f"[Orchestra import error: {e}]"
        }
        print(json.dumps(error_result))
        sys.exit(0)


# Agent mode detection (L2↔L3 wire)
# When running inside Docker (ORCHESTRA_AGENT_MODE=true):
# - Skip interactive safety gates (burnout prompts) — agents run autonomously
# - Still apply deterministic routing cascade
# - Still enforce MAX3 limits
AGENT_MODE = os.environ.get("ORCHESTRA_AGENT_MODE", "").lower() == "true"

# Singleton instances
_orchestrator = None
_bridge = None
_tier_hook = None


def get_tier_hook():
    """Get or create singleton tier hook (lazy load)."""
    global _tier_hook
    if _tier_hook is None:
        try:
            # Add substrate tools to path
            substrate_tools = Path.home() / ".claude" / "substrate" / "tools"
            if str(substrate_tools) not in sys.path:
                sys.path.insert(0, str(substrate_tools))

            from tier_loader import TierHookIntegration
            _tier_hook = TierHookIntegration()
        except ImportError:
            _tier_hook = False  # Mark as unavailable
    return _tier_hook if _tier_hook else None


def check_tier_notification():
    """Check for pending tier regeneration notifications."""
    tier_hook = get_tier_hook()
    if tier_hook:
        try:
            notification = tier_hook._check_pending_notification()
            return notification
        except Exception:
            pass
    return None


def get_orchestrator():
    """Get or create singleton orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = create_orchestrator()
    return _orchestrator


def get_bridge():
    """Get or create singleton bridge."""
    global _bridge
    if _bridge is None:
        _bridge = create_bridge(get_orchestrator())
    return _bridge


def build_guidance(result):
    """Build expert-specific guidance.

    In agent mode (ORCHESTRA_AGENT_MODE=true), skip interactive safety gates
    like burnout prompts. Agents run autonomously but still get deterministic
    routing and expert selection.
    """
    expert = result.routing.expert.value
    paradigm = result.lock.params.paradigm

    expert_guidance = {
        "validator": "EMPATHY FIRST. Acknowledge the struggle. Normalize difficulty.",
        "scaffolder": "BREAK DOWN the task. Provide structure. Reduce scope if needed.",
        "restorer": "EASY WINS mode. Suggest simple tasks. Rest is OK.",
        "refocuser": "GENTLE REDIRECT. Acknowledge tangent, guide back to goal.",
        "celebrator": "ACKNOWLEDGE THE WIN. Provide dopamine boost.",
        "socratic": "GUIDE DISCOVERY. Follow threads. Ask questions.",
        "direct": "MINIMAL FRICTION. Stay out of the way. Direct execution."
    }

    guidance = expert_guidance.get(expert, "Proceed with standard response.")

    # Agent mode: skip interactive safety prompts but preserve routing decision
    if AGENT_MODE:
        if not result.routing.safety_gate_pass:
            guidance = "AGENT MODE: Safety gate noted (non-interactive). " + guidance
    else:
        if not result.routing.safety_gate_pass:
            guidance = "SAFETY GATE TRIGGERED. " + guidance

    if paradigm == "Mycelium":
        guidance += " Follow associative threads."
    else:
        guidance += " Stay structured and explicit."

    return guidance


def process_message(user_prompt, context=None):
    """Process message through NEXUS pipeline."""
    try:
        bridge = get_bridge()
        result = bridge.process_and_broadcast(user_prompt, context or {})

        # Build system message
        anchor = result.to_anchor()
        guidance = build_guidance(result)

        system_message = f"{anchor}\n\n{guidance}"

        # Check for tier regeneration notifications
        tier_notification = check_tier_notification()
        if tier_notification:
            system_message = tier_notification + "\n\n" + system_message

        # Build hook output
        hook_output = {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"Orchestra: expert={result.routing.expert.value}, tension={result.convergence.epistemic_tension:.2f}"
        }

        # Add tier notification flag if present
        if tier_notification:
            hook_output["tierRegenerationNotified"] = True

        return {
            "systemMessage": system_message,
            "hookSpecificOutput": hook_output
        }

    except Exception as e:
        return {
            "systemMessage": f"[EXEC:error|Direct|Cortex|30000ft|standard] (Error: {str(e)[:50]})"
        }


def main():
    """Main entry point for hook."""
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)

        # Extract user prompt
        user_prompt = input_data.get("user_prompt", "")

        if not user_prompt:
            # No prompt, return empty
            print(json.dumps({}))
            sys.exit(0)

        # Process through cognitive engine
        result = process_message(user_prompt)

        # Output result
        print(json.dumps(result))

    except json.JSONDecodeError:
        # Invalid JSON input
        print(json.dumps({"systemMessage": "[Orchestra: invalid input]"}))

    except Exception as e:
        # General error
        print(json.dumps({"systemMessage": f"[Orchestra error: {str(e)[:100]}]"}))

    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
