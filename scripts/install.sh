#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "未找到 python/python3，请先安装 Python 3.9+。" >&2
    exit 2
  fi
fi

if [[ ! -d ".venv" ]]; then
  echo "创建虚拟环境：.venv"
  "$PYTHON_BIN" -m venv .venv
fi

VENV_PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "虚拟环境不完整：$VENV_PY 不存在，尝试重新创建 .venv" >&2
  rm -rf .venv
  "$PYTHON_BIN" -m venv .venv
fi

echo "安装依赖：requirements.txt"
"$VENV_PY" -m pip install -r requirements.txt

echo "完成。"
