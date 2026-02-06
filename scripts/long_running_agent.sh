#!/bin/bash
# =============================================================================
# He2025-aligned Long-Running Claude Agent
# =============================================================================
#
# Implements the Anthropic blog pattern (continuous execution loop)
# with He2025 determinism constraints:
# - Fixed task partitions (not race conditions)
# - Deterministic task selection via DeterministicTaskQueue
# - Git-based coordination for multi-agent work
#
# MUST run inside Docker container (not bare metal)
#
# Environment variables:
#   TASK_DIR       - Directory containing task JSON files (default: /workspace/tasks)
#   LOG_DIR        - Directory for agent logs (default: /workspace/logs)
#   AGENT_ID       - Agent identifier (default: agent_$(hostname))
#   PROMPT_FILE    - Path to agent prompt template (default: /workspace/AGENT_PROMPT.md)
#   NUM_AGENTS     - Number of agents in fleet (default: 3)
#   SLEEP_INTERVAL - Seconds between task checks (default: 30)
#   MAX_RETRIES    - Max retries per task (default: 2)
# =============================================================================

set -euo pipefail

# Configuration
TASK_DIR="${TASK_DIR:-/workspace/tasks}"
LOG_DIR="${LOG_DIR:-/workspace/logs}"
AGENT_ID="${AGENT_ID:-agent_$(hostname)}"
PROMPT_FILE="${PROMPT_FILE:-/workspace/AGENT_PROMPT.md}"
NUM_AGENTS="${NUM_AGENTS:-3}"
SLEEP_INTERVAL="${SLEEP_INTERVAL:-30}"
MAX_RETRIES="${MAX_RETRIES:-2}"

# Ensure directories exist
mkdir -p "$LOG_DIR" "$TASK_DIR/claimed" "$TASK_DIR/completed" "$TASK_DIR/failed" "$TASK_DIR/dead_letter"

echo "[$AGENT_ID] Starting long-running agent"
echo "[$AGENT_ID] Task dir: $TASK_DIR"
echo "[$AGENT_ID] Log dir: $LOG_DIR"
echo "[$AGENT_ID] Num agents: $NUM_AGENTS"
echo "[$AGENT_ID] Prompt file: $PROMPT_FILE"

# Verify prompt file exists
if [ ! -f "$PROMPT_FILE" ]; then
    echo "[$AGENT_ID] ERROR: Prompt file not found: $PROMPT_FILE"
    exit 1
fi

# Verify claude CLI is available
if ! command -v claude &> /dev/null; then
    echo "[$AGENT_ID] ERROR: claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# =============================================================================
# Main Loop
# =============================================================================

TASK_COUNT=0
ERROR_COUNT=0

while true; do
    # DETERMINISTIC task selection (He2025: fixed partition, not race)
    # Agent claims tasks from its pre-assigned partition
    TASK_JSON=$(python -m orchestra.task_queue claim \
        --agent-id "$AGENT_ID" \
        --task-dir "$TASK_DIR" \
        --num-agents "$NUM_AGENTS" 2>/dev/null || echo "")

    if [ -z "$TASK_JSON" ]; then
        echo "[$AGENT_ID] No tasks available. Sleeping ${SLEEP_INTERVAL}s..."
        sleep "$SLEEP_INTERVAL"
        continue
    fi

    # Extract task info
    TASK_ID=$(echo "$TASK_JSON" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "unknown")
    TASK_DESC=$(echo "$TASK_JSON" | python -c "import sys,json; print(json.load(sys.stdin)['description'][:100])" 2>/dev/null || echo "")

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOGFILE="$LOG_DIR/${AGENT_ID}_${TASK_ID}_${TIMESTAMP}.log"

    echo "[$AGENT_ID] Claimed task: $TASK_ID - $TASK_DESC"
    echo "[$AGENT_ID] Log: $LOGFILE"

    TASK_COUNT=$((TASK_COUNT + 1))

    # Build prompt with task context
    TASK_PROMPT="$(cat "$PROMPT_FILE")

TASK: $TASK_DESC

TASK_ID: $TASK_ID
AGENT_ID: $AGENT_ID
"

    # Execute with Claude
    RETRY=0
    SUCCESS=false

    while [ $RETRY -lt "$MAX_RETRIES" ] && [ "$SUCCESS" = "false" ]; do
        echo "[$AGENT_ID] Executing task $TASK_ID (attempt $((RETRY + 1))/$MAX_RETRIES)"

        if claude --dangerously-skip-permissions \
                 -p "$TASK_PROMPT" \
                 --model claude-sonnet-4-5-20250929 &> "$LOGFILE"; then
            SUCCESS=true
        else
            RETRY=$((RETRY + 1))
            if [ $RETRY -lt "$MAX_RETRIES" ]; then
                echo "[$AGENT_ID] Task $TASK_ID failed, retrying with backoff..."

                # Use task_queue retry for exponential backoff (replaces fixed sleep 5)
                RETRY_RESULT=$(python -m orchestra.task_queue retry \
                    --task-id "$TASK_ID" \
                    --task-dir "$TASK_DIR" \
                    --max-retries "$MAX_RETRIES" \
                    --error "Attempt $RETRY failed" 2>/dev/null || echo "FAILED")

                # Check if task was dead-lettered (retries exhausted)
                if [ "$RETRY_RESULT" = "DEAD_LETTER" ]; then
                    echo "[$AGENT_ID] Task $TASK_ID moved to dead letter queue"
                    break
                fi

                # Get computed backoff delay
                DELAY=$(python -m orchestra.task_queue retry-delay \
                    --task-id "$TASK_ID" \
                    --task-dir "$TASK_DIR" 2>/dev/null || echo "5.00")

                echo "[$AGENT_ID] Backoff delay: ${DELAY}s"
                sleep "$DELAY"

                # Re-claim the task after backoff
                TASK_JSON=$(python -m orchestra.task_queue claim \
                    --agent-id "$AGENT_ID" \
                    --task-dir "$TASK_DIR" \
                    --num-agents "$NUM_AGENTS" 2>/dev/null || echo "")

                if [ -z "$TASK_JSON" ]; then
                    echo "[$AGENT_ID] Could not re-claim task $TASK_ID after backoff"
                    break
                fi
            fi
        fi
    done

    # Mark task status
    if [ "$SUCCESS" = "true" ]; then
        python -m orchestra.task_queue complete \
            --task-id "$TASK_ID" \
            --task-dir "$TASK_DIR" 2>/dev/null || true

        echo "[$AGENT_ID] Completed task: $TASK_ID (${TASK_COUNT} total)"

        # Git commit if in a git repo
        if git rev-parse --is-inside-work-tree &>/dev/null; then
            COMMIT_MSG="[$AGENT_ID] Complete: $TASK_ID"
            git add -A && git commit -m "$COMMIT_MSG" 2>/dev/null || true
            # Deterministic merge (rebase, not merge)
            git pull --rebase origin main 2>/dev/null || true
            git push origin main 2>/dev/null || true
        fi
    else
        ERROR_COUNT=$((ERROR_COUNT + 1))

        # Check if dead-lettered vs regular failure
        if python -m orchestra.task_queue dead-letter --task-dir "$TASK_DIR" 2>/dev/null | python -c "
import sys, json
tasks = json.load(sys.stdin)
sys.exit(0 if any(t['id'] == '$TASK_ID' for t in tasks) else 1)
" 2>/dev/null; then
            echo "[$AGENT_ID] DEAD LETTER: $TASK_ID (retries exhausted)"
        else
            echo "[$AGENT_ID] FAILED task: $TASK_ID after $MAX_RETRIES attempts"
        fi
        echo "[$AGENT_ID] Errors so far: $ERROR_COUNT"
    fi

    # Brief pause between tasks
    sleep 2
done
