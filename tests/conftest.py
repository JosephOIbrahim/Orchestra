"""Pytest configuration and fixtures."""

import pytest
import asyncio
from pathlib import Path


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
