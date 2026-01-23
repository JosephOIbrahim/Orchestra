"""
Entry point for running Framework Orchestrator as a module.

Usage:
    python -m framework_orchestrator --task "Your task"
    python -m framework_orchestrator --health
    python -m framework_orchestrator --show-config
"""

import asyncio
from .framework_orchestrator import main

if __name__ == "__main__":
    asyncio.run(main())
