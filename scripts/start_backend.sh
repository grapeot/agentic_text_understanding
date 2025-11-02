#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

if [[ ! -d "venv" ]]; then
  echo "[start_backend] 未找到 venv，使用 uv 创建..."
  uv venv venv
fi

# shellcheck disable=SC1091
source "venv/bin/activate"

if [[ -f "requirements.txt" ]]; then
  echo "[start_backend] 确保依赖已安装..."
  uv pip install -r requirements.txt >/dev/null
fi

declare -a required_files=(
  "data/index.faiss"
  "data/chunks.jsonl"
)

for path in "${required_files[@]}"; do
  if [[ ! -f "${path}" ]]; then
    echo "[start_backend] 缺少 ${path}，请先运行 scripts/build_index.py 生成索引。" >&2
    exit 1
  fi
done

HOST_VALUE="${HOST:-0.0.0.0}"
PORT_VALUE="${PORT:-8004}"

echo "[start_backend] 启动 FastAPI 服务 (HOST=${HOST_VALUE}, PORT=${PORT_VALUE})..."
exec uvicorn app.server:app --host "${HOST_VALUE}" --port "${PORT_VALUE}"
