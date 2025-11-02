#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROMPT_TEMPLATE="${PROMPT_TEMPLATE:-$ROOT_DIR/prompts/information_weight_prompt.txt}"
JOBS="${JOBS:-16}"
MANIFEST=""
TARGET_DIR="$ROOT_DIR/data/chunks_1000_20"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest)
      MANIFEST="$2"
      shift 2
      ;;
    -h|--help)
      cat <<USAGE
Usage: $(basename "$0") [DIRECTORY] [--manifest FILE]

When --manifest is provided, process only the newline-separated CSV paths listed in FILE.
Otherwise, all *.csv files under DIRECTORY (default: data/chunks_1000_20) are processed.
Set JOBS to control parallelism (default: 16).
USAGE
      exit 0
      ;;
    *)
      TARGET_DIR="$1"
      shift
      ;;
  esac
done

TARGET_DIR="${TARGET_DIR%/}"

if [[ ! -f "$PROMPT_TEMPLATE" ]]; then
  echo "[run_codex_weights] prompt template missing: $PROMPT_TEMPLATE" >&2
  exit 1
fi

cd "$ROOT_DIR"

process_file() {
  local file="$1"
  local abs_path
  if [[ "$file" == /* ]]; then
    abs_path="$file"
  else
    abs_path="$ROOT_DIR/$file"
  fi

  if [[ ! -f "$abs_path" ]]; then
    echo "[run_codex_weights] skipping missing file: $file" >&2
    return
  fi

  local rel_path="${abs_path#$ROOT_DIR/}"

  export TARGET_FILE="$rel_path"
  envsubst < "$PROMPT_TEMPLATE" \
    | codex exec --full-auto --cd "$ROOT_DIR" -
}

export ROOT_DIR PROMPT_TEMPLATE
export -f process_file

FILES=()

if [[ -n "$MANIFEST" ]]; then
  if [[ ! -f "$MANIFEST" ]]; then
    echo "[run_codex_weights] manifest not found: $MANIFEST" >&2
    exit 1
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    FILES+=("$line")
  done <"$MANIFEST"
else
  if [[ ! -d "$TARGET_DIR" ]]; then
    echo "[run_codex_weights] target directory not found: $TARGET_DIR" >&2
    exit 1
  fi
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    FILES+=("$path")
  done < <(find "$TARGET_DIR" -type f -name '*.csv' | sort)
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "[run_codex_weights] no files to process" >&2
  exit 0
fi

printf '%s\0' "${FILES[@]}" \
  | xargs -0 -n1 -P"$JOBS" -I{} bash -lc 'process_file "$1"' _ {}
