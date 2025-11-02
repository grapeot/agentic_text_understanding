#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${1:-$ROOT_DIR/data/chunks_1000_20}"
PROMPT_TEMPLATE="${PROMPT_TEMPLATE:-$ROOT_DIR/prompts/information_weight_prompt.txt}"
JOBS="${JOBS:-16}"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "[run_codex_weights] target directory not found: $TARGET_DIR" >&2
  exit 1
fi

if [[ ! -f "$PROMPT_TEMPLATE" ]]; then
  echo "[run_codex_weights] prompt template missing: $PROMPT_TEMPLATE" >&2
  exit 1
fi

process_file() {
  local file="$1"
  local rel_path="${file#$ROOT_DIR/}"
  if [[ "$rel_path" == "$file" ]]; then
    rel_path="$file"
  fi

  export TARGET_FILE="$rel_path"
  envsubst < "$PROMPT_TEMPLATE" \
    | codex exec --full-auto --cd "$ROOT_DIR" -
}

export ROOT_DIR PROMPT_TEMPLATE
export -f process_file

find "$TARGET_DIR" -type f -name '*.csv' -print0 \
  | xargs -0 -n1 -P"$JOBS" -I{} bash -lc 'process_file "$1"' _ {}
