#!/usr/bin/env python3
"""
Orchestra CLI - Main Entry Point

Commands:
  orchestra              # Launch TUI dashboard
  orchestra status       # Show status line
  orchestra status -s    # Short status for prompts
  orchestra set          # Set cognitive state
  orchestra init         # Initialize shell integration

Zero-friction cognitive awareness for developers.
"""

import argparse
import sys
from pathlib import Path


def cmd_status(args):
    """Show cognitive status."""
    from .status import read_state, format_short, format_prompt, format_full, format_tmux, format_json

    state = read_state()
    use_color = not args.no_color and sys.stdout.isatty()

    if args.json:
        print(format_json(state))
    elif args.tmux:
        print(format_tmux(state))
    elif args.short:
        print(format_short(state, color=use_color))
    elif args.prompt:
        print(format_prompt(state, color=use_color))
    else:
        print(format_full(state, color=use_color))


def cmd_tui(args):
    """Launch TUI dashboard."""
    from .tui import run_tui, run_once

    if args.once:
        run_once()
    else:
        run_tui(watch=args.watch)


def cmd_set(args):
    """Set cognitive state values."""
    from .status import read_state
    import json

    state_file = Path.home() / ".orchestra" / "state" / "cognitive_state.json"
    state = read_state()

    if args.burnout:
        if args.burnout.upper() in ("GREEN", "YELLOW", "ORANGE", "RED"):
            state["burnout_level"] = args.burnout.upper()
        else:
            print(f"Invalid burnout level: {args.burnout}")
            print("Valid: GREEN, YELLOW, ORANGE, RED")
            return 1

    if args.mode:
        if args.mode.lower() in ("work", "delegate", "protect"):
            state["decision_mode"] = args.mode.lower()
        else:
            print(f"Invalid mode: {args.mode}")
            print("Valid: work, delegate, protect")
            return 1

    if args.momentum:
        valid = ("cold_start", "building", "rolling", "peak", "crashed")
        if args.momentum.lower() in valid:
            state["momentum_phase"] = args.momentum.lower()
        else:
            print(f"Invalid momentum: {args.momentum}")
            print(f"Valid: {', '.join(valid)}")
            return 1

    if args.energy:
        valid = ("high", "medium", "low", "depleted")
        if args.energy.lower() in valid:
            state["energy_level"] = args.energy.lower()
        else:
            print(f"Invalid energy: {args.energy}")
            print(f"Valid: {', '.join(valid)}")
            return 1

    if args.task:
        state["current_task"] = args.task

    # Write state
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

    print("State updated.")
    return 0


def cmd_init(args):
    """Initialize shell integration."""
    shell = args.shell or detect_shell()

    if shell == "bash":
        print(BASH_INTEGRATION)
    elif shell == "zsh":
        print(ZSH_INTEGRATION)
    elif shell == "fish":
        print(FISH_INTEGRATION)
    elif shell == "tmux":
        print(TMUX_INTEGRATION)
    elif shell == "starship":
        print(STARSHIP_INTEGRATION)
    else:
        print(f"Unknown shell: {shell}")
        print("Supported: bash, zsh, fish, tmux, starship")
        return 1

    return 0


def cmd_install_hook(args):
    """Install Claude Code hook for cognitive engine integration."""
    import json
    import shutil

    hooks_dir = Path.home() / ".claude" / "hooks"
    hooks_file = hooks_dir / "hooks.json"

    # Find Python executable
    python_exe = shutil.which("python") or shutil.which("python3") or sys.executable

    # Build the hook command (cross-platform)
    hook_command = f"{python_exe} -m orchestra.hooks"

    # Build the hook configuration
    hook_config = {
        "UserPromptSubmit": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": hook_command,
                        "timeout": 5
                    }
                ]
            }
        ]
    }

    # Check for existing hooks.json
    existing_hooks = {}
    if hooks_file.exists():
        try:
            with open(hooks_file) as f:
                existing_hooks = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    if args.force or not existing_hooks:
        # Create/overwrite with Orchestra hook
        hooks_dir.mkdir(parents=True, exist_ok=True)
        with open(hooks_file, "w") as f:
            json.dump(hook_config, f, indent=2)
        print(f"Installed Orchestra hook to {hooks_file}")
        print(f"Hook command: {hook_command}")
        print()
        print("Restart Claude Code to activate the cognitive engine.")
        return 0

    # Existing hooks found - check if Orchestra already configured
    existing_prompts = existing_hooks.get("UserPromptSubmit", [])
    orchestra_present = any(
        "orchestra" in str(h.get("hooks", [{}])[0].get("command", "")).lower()
        for h in existing_prompts
        if h.get("hooks")
    )

    if orchestra_present and not args.force:
        print("Orchestra hook already installed.")
        print(f"Location: {hooks_file}")
        print()
        print("Use --force to reinstall.")
        return 0

    # Merge: add Orchestra hook to existing
    if not any(h.get("matcher") == "*" for h in existing_prompts):
        # No wildcard matcher, add one
        existing_prompts.append(hook_config["UserPromptSubmit"][0])
    else:
        # Update existing wildcard matcher
        for h in existing_prompts:
            if h.get("matcher") == "*":
                hooks_list = h.get("hooks", [])
                # Remove old orchestra hook if present
                hooks_list = [
                    hook for hook in hooks_list
                    if "orchestra" not in str(hook.get("command", "")).lower()
                ]
                # Add new orchestra hook
                hooks_list.append({
                    "type": "command",
                    "command": hook_command,
                    "timeout": 5
                })
                h["hooks"] = hooks_list
                break

    existing_hooks["UserPromptSubmit"] = existing_prompts

    # Write merged config
    with open(hooks_file, "w") as f:
        json.dump(existing_hooks, f, indent=2)

    print(f"Added Orchestra hook to {hooks_file}")
    print(f"Hook command: {hook_command}")
    print()
    print("Restart Claude Code to activate the cognitive engine.")
    return 0


def cmd_uninstall_hook(args):
    """Remove Claude Code hook for cognitive engine."""
    import json

    hooks_file = Path.home() / ".claude" / "hooks" / "hooks.json"

    if not hooks_file.exists():
        print("No hooks.json found. Nothing to uninstall.")
        return 0

    try:
        with open(hooks_file) as f:
            hooks = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading hooks.json: {e}")
        return 1

    # Remove Orchestra hooks
    modified = False
    if "UserPromptSubmit" in hooks:
        for matcher in hooks["UserPromptSubmit"]:
            if "hooks" in matcher:
                original_len = len(matcher["hooks"])
                matcher["hooks"] = [
                    h for h in matcher["hooks"]
                    if "orchestra" not in str(h.get("command", "")).lower()
                ]
                if len(matcher["hooks"]) < original_len:
                    modified = True

        # Clean up empty matchers
        hooks["UserPromptSubmit"] = [
            m for m in hooks["UserPromptSubmit"]
            if m.get("hooks")
        ]

        # Clean up empty UserPromptSubmit
        if not hooks["UserPromptSubmit"]:
            del hooks["UserPromptSubmit"]

    if modified:
        if hooks:
            with open(hooks_file, "w") as f:
                json.dump(hooks, f, indent=2)
            print("Removed Orchestra hook from hooks.json")
        else:
            hooks_file.unlink()
            print("Removed hooks.json (was only Orchestra hook)")
        print()
        print("Restart Claude Code to deactivate the cognitive engine.")
    else:
        print("Orchestra hook not found in hooks.json")

    return 0


def detect_shell() -> str:
    """Detect current shell."""
    import os
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return "zsh"
    elif "fish" in shell:
        return "fish"
    elif "bash" in shell:
        return "bash"
    return "bash"


# Shell integration snippets
BASH_INTEGRATION = '''
# Orchestra Status - Add to ~/.bashrc
# Option 1: Minimal (just colored icon)
orchestra_prompt() {
  local status=$(orchestra status --short 2>/dev/null)
  [ -n "$status" ] && echo "$status "
}
PS1='$(orchestra_prompt)\\u@\\h:\\w\\$ '

# Option 2: Full status on separate line
# PS1='$(orchestra status --prompt 2>/dev/null)\\n\\u@\\h:\\w\\$ '
'''

ZSH_INTEGRATION = '''
# Orchestra Status - Add to ~/.zshrc
# Option 1: Right prompt (recommended)
orchestra_rprompt() {
  orchestra status --prompt 2>/dev/null
}
RPROMPT='$(orchestra_rprompt)'

# Option 2: Left prompt prefix
# orchestra_prompt() {
#   echo "$(orchestra status --short 2>/dev/null) "
# }
# PROMPT='$(orchestra_prompt)'$PROMPT
'''

FISH_INTEGRATION = '''
# Orchestra Status - Add to ~/.config/fish/config.fish
function fish_right_prompt
  orchestra status --prompt 2>/dev/null
end

# Or for left prompt:
# function fish_prompt
#   echo (orchestra status --short 2>/dev/null)" "
#   # ... rest of prompt
# end
'''

TMUX_INTEGRATION = '''
# Orchestra Status - Add to ~/.tmux.conf
set -g status-right '#(orchestra status --tmux) │ %H:%M'
set -g status-interval 5

# With more space:
# set -g status-right-length 60
# set -g status-right '#(orchestra status --tmux) │ #H │ %Y-%m-%d %H:%M'
'''

STARSHIP_INTEGRATION = '''
# Orchestra Status - Add to ~/.config/starship.toml
[custom.orchestra]
command = "orchestra status --short --no-color"
when = "test -f ~/.orchestra/state/cognitive_state.json"
format = "[$output]($style) "
style = "green"

# Or with full status:
# [custom.orchestra]
# command = "orchestra status --prompt --no-color"
# when = "test -f ~/.orchestra/state/cognitive_state.json"
# format = "\\n[$output]($style)"
'''


def main():
    parser = argparse.ArgumentParser(
        description="Orchestra - Cognitive state awareness for developers",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # status command
    status_parser = subparsers.add_parser("status", help="Show cognitive status")
    status_parser.add_argument("-s", "--short", action="store_true", help="Minimal output")
    status_parser.add_argument("-p", "--prompt", action="store_true", help="Prompt format")
    status_parser.add_argument("--tmux", action="store_true", help="tmux format")
    status_parser.add_argument("--json", action="store_true", help="JSON output")
    status_parser.add_argument("--no-color", action="store_true", help="Disable colors")

    # set command
    set_parser = subparsers.add_parser("set", help="Set cognitive state")
    set_parser.add_argument("-b", "--burnout", help="Set burnout level (GREEN/YELLOW/ORANGE/RED)")
    set_parser.add_argument("-m", "--mode", help="Set decision mode (work/delegate/protect)")
    set_parser.add_argument("--momentum", help="Set momentum phase")
    set_parser.add_argument("-e", "--energy", help="Set energy level")
    set_parser.add_argument("-t", "--task", help="Set current task")

    # init command
    init_parser = subparsers.add_parser("init", help="Shell integration setup")
    init_parser.add_argument("shell", nargs="?", help="Shell type (bash/zsh/fish/tmux/starship)")

    # install-hook command
    install_hook_parser = subparsers.add_parser(
        "install-hook",
        help="Install Claude Code hook for cognitive engine"
    )
    install_hook_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force reinstall even if already present"
    )

    # uninstall-hook command
    subparsers.add_parser(
        "uninstall-hook",
        help="Remove Claude Code hook for cognitive engine"
    )

    # TUI options (default command)
    parser.add_argument("-w", "--watch", action="store_true", help="Auto-refresh TUI")
    parser.add_argument("-1", "--once", action="store_true", help="Display once and exit")

    args = parser.parse_args()

    if args.command == "status":
        return cmd_status(args)
    elif args.command == "set":
        return cmd_set(args)
    elif args.command == "init":
        return cmd_init(args)
    elif args.command == "install-hook":
        return cmd_install_hook(args)
    elif args.command == "uninstall-hook":
        return cmd_uninstall_hook(args)
    else:
        # Default: launch TUI
        return cmd_tui(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
