"""Pytest configuration and fixtures."""

import pytest
import asyncio
import sys
from pathlib import Path

# Add src directory to Python path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Create module aliases for backward compatibility with old import paths
# Old: from orchestra import ...
# New: from orchestra.framework_orchestrator import ...
import orchestra
import orchestra.framework_orchestrator
import orchestra.config
import orchestra.resilience
import orchestra.file_ops
import orchestra.validation
import orchestra.cognitive_state
import orchestra.prism_detector
import orchestra.adhd_support  # Provides both new and backward-compat names
import orchestra.cognitive_support

sys.modules['framework_orchestrator'] = orchestra.framework_orchestrator
sys.modules['config'] = orchestra.config
sys.modules['resilience'] = orchestra.resilience
sys.modules['file_ops'] = orchestra.file_ops
sys.modules['validation'] = orchestra.validation
sys.modules['cognitive_state'] = orchestra.cognitive_state
sys.modules['prism_detector'] = orchestra.prism_detector
sys.modules['adhd_support'] = orchestra.adhd_support  # Backward compatibility
sys.modules['cognitive_safety'] = orchestra.adhd_support  # New name alias
sys.modules['cognitive_support'] = orchestra.cognitive_support


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_principles():
    """Sample principles configuration for testing."""
    return {
        "_meta": {
            "name": "Test Principles",
            "version": "1.0",
            "authority": "highest_immutable",
        },
        "constitutional": {
            "principles": [
                {
                    "id": "test_principle",
                    "statement": "Test principle statement",
                    "triggers": ["test", "trigger"],
                    "action": "Test action",
                }
            ]
        },
        "memory_modes": {
            "focused_recall": {
                "search_depth": "deep",
                "search_breadth": "narrow",
                "use_when": ["debugging"],
            },
            "exploratory_recall": {
                "search_depth": "shallow",
                "search_breadth": "wide",
                "use_when": ["brainstorming"],
            },
            "recovery_recall": {
                "search_depth": "principles_only",
                "search_breadth": "minimal",
                "use_when": ["burnout"],
            },
        },
    }


@pytest.fixture
def sample_domain():
    """Sample domain configuration for testing."""
    return {
        "name": "Test Domain",
        "description": "Domain for testing",
        "version": "1.0",
        "specialists": {
            "specialist_a": {
                "keywords": ["keyword1", "keyword2"],
                "tools": ["Tool1"],
                "analysis_focus": ["focus1"],
            },
            "specialist_b": {
                "keywords": ["keyword3"],
                "tools": ["Tool2"],
                "analysis_focus": ["focus2"],
            },
        },
        "routing_keywords": ["route1", "route2"],
        "prism_perspectives": ["causal", "optimization"],
    }
