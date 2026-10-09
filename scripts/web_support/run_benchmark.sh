#!/usr/bin/env bash
# Run the web_support benchmark: same agent, same user simulator, same 20 tasks,
# only the search backend changes between arms.
#
# Usage:
#   scripts/web_support/run_benchmark.sh [run_name] [num_trials] [arms...]
# Example:
#   scripts/web_support/run_benchmark.sh oct09 1 keenable tavily exa none
#
# Env (optional):
#   AGENT_LLM   default anthropic/claude-sonnet-5-5
#   USER_LLM    default anthropic/claude-haiku-5-5
#   JUDGE_LLM   default anthropic/claude-sonnet-5-5   (NL-assertion judge)
#   TIER        fast | standard (default fast: Keenable realtime, Tavily ultra-fast, Exa instant)
#   TASK_SPLIT  base | changed | evergreen (default base = all 20)
#   CONCURRENCY default 4
#
# Keys are read from .env (KEENABLE_API_KEY, TAVILY_API_KEY, EXA_API_KEY, ANTHROPIC_API_KEY).
set -euo pipefail
cd "$(dirname "$0")/../.."

RUN_NAME="${1:-run}"
TRIALS="${2:-1}"
shift 2 2>/dev/null || true
ARMS=("$@")
if [ ${#ARMS[@]} -eq 0 ]; then ARMS=(keenable tavily exa none); fi

AGENT_LLM="${AGENT_LLM:-anthropic/claude-sonnet-5-5}"
USER_LLM="${USER_LLM:-anthropic/claude-haiku-5-5}"
JUDGE_LLM="${JUDGE_LLM:-anthropic/claude-sonnet-5-5}"
TIER="${TIER:-fast}"
TASK_SPLIT="${TASK_SPLIT:-base}"
CONCURRENCY="${CONCURRENCY:-4}"

if [ -f .env ]; then set -a; . ./.env; set +a; fi
export TAU2_LLM_NL_ASSERTIONS="$JUDGE_LLM"
export TAU2_WEB_SEARCH_TIER="$TIER"

for arm in "${ARMS[@]}"; do
  export TAU2_WEB_SEARCH_LOG="${RUN_NAME}_${arm}_${TIER}.jsonl"
  echo "=== arm=$arm tier=$TIER trials=$TRIALS split=$TASK_SPLIT ==="
  uv run --no-sync tau2 run \
    --domain "web_support_${arm}" \
    --task-split-name "$TASK_SPLIT" \
    --agent-llm "$AGENT_LLM" \
    --user-llm "$USER_LLM" \
    --num-trials "$TRIALS" \
    --max-steps 30 \
    --max-concurrency "$CONCURRENCY" \
    --save-to "web_support/${RUN_NAME}_${arm}_${TIER}" \
    --auto-resume \
    --log-level ERROR \
    2>&1 | grep -v "UV_NATIVE\|PydanticSerial\|serialized value\|pydantic_serializer" | tail -25
done

uv run --no-sync python scripts/web_support/aggregate.py "$RUN_NAME" --tier "$TIER"
