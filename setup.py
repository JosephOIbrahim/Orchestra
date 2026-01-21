"""Setup script for Framework Orchestrator."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name="framework-orchestrator",
    version="1.0.0",
    author="josephoibrahim",
    author_email="",
    description="USD Composition Semantics for AI Agent Orchestration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/josephoibrahim/framework-orchestrator",
    py_modules=["framework_orchestrator"],
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "mypy>=1.0.0",
        ],
        "torch": [
            "torch>=2.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords="ai agents orchestration usd cognitive llm async",
    project_urls={
        "Bug Reports": "https://github.com/josephoibrahim/framework-orchestrator/issues",
        "Source": "https://github.com/josephoibrahim/framework-orchestrator",
    },
)
