FROM python:3.12-slim

# Install Node.js for Claude Code CLI
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Install Orchestra
COPY . /app
WORKDIR /app
RUN pip install --no-cache-dir -e ".[dev]"

# Make scripts executable
RUN chmod +x /app/scripts/*.sh

# Agent workspace
WORKDIR /workspace

# Default environment
ENV TASK_DIR=/workspace/tasks
ENV LOG_DIR=/workspace/logs
ENV PROMPT_FILE=/workspace/AGENT_PROMPT.md
ENV NUM_AGENTS=3
ENV ORCHESTRA_AGENT_MODE=true

# Entry point
ENTRYPOINT ["/app/scripts/long_running_agent.sh"]
