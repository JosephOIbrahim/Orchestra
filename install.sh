#!/bin/bash
# Orchestra Terminal Integration Installer
# Run: curl -fsSL https://raw.githubusercontent.com/your-repo/orchestra/main/install.sh | bash

set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  Orchestra - Terminal-First Cognitive Awareness               ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PYTHON_VERSION detected"

# Install Orchestra
echo ""
echo "Installing Orchestra..."
pip install --upgrade pip
pip install -e ".[tui]" 2>/dev/null || pip install -e .

# Create state directory
mkdir -p ~/.orchestra/state

# Initialize default state
if [ ! -f ~/.orchestra/state/cognitive_state.json ]; then
    cat > ~/.orchestra/state/cognitive_state.json << 'EOF'
{
  "burnout_level": "GREEN",
  "decision_mode": "work",
  "momentum_phase": "rolling",
  "energy_level": "high",
  "working_memory_used": 2,
  "tangent_budget": 5,
  "altitude": "30000ft",
  "paradigm": "Cortex"
}
EOF
    echo "✓ Default state created"
fi

echo ""
echo "✓ Installation complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Quick Start:"
echo ""
echo "  orchestra              # Launch TUI dashboard"
echo "  orchestra status       # Show status line"
echo "  orchestra status -s    # Short status for prompts"
echo "  orchestra init bash    # Get shell integration"
echo ""
echo "Shell Integration:"
echo ""
echo "  # Add to your shell config:"
echo "  orchestra init bash    # For ~/.bashrc"
echo "  orchestra init zsh     # For ~/.zshrc"
echo "  orchestra init tmux    # For ~/.tmux.conf"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
