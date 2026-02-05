#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "未检测到虚拟环境，先安装依赖…" >&2
  bash "$ROOT_DIR/scripts/install.sh"
fi

if [[ ! -f "config.json" ]]; then
  cp config.example.json config.json
  echo "已生成 config.json，请填写飞书 webhook，并确保 channels 里仅启用 1 个渠道（enabled=true）。" >&2
  exit 2
fi

if [[ ! -s "cookie.txt" ]]; then
  echo "缺少 cookie.txt 或文件为空：请将浏览器抓到的 Cookie 粘贴到 cookie.txt（一行）。" >&2
  exit 2
fi

HAS_ONCE="false"
HAS_LOOP="false"
for arg in "$@"; do
  if [[ "$arg" == "--once" ]]; then
    HAS_ONCE="true"
  fi
  if [[ "$arg" == "--loop" ]]; then
    HAS_LOOP="true"
  fi
done

MODE="loop"
if [[ "$HAS_ONCE" == "true" ]]; then
  MODE="once"
fi

"$VENV_PY" - "$MODE" <<'PY'
import json
import sys

def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(2)

mode = sys.argv[1] if len(sys.argv) > 1 else "loop"
with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

channels = cfg.get("channels") or []
if not isinstance(channels, list) or not channels:
    fail("config.json 缺少 channels：请按 config.example.json 配置，并启用 1 个渠道。")

enabled = [c for c in channels if isinstance(c, dict) and c.get("enabled") is True]
if len(enabled) != 1:
    fail("config.json: channels 必须且只能启用 1 个渠道（enabled=true）。")

ch = enabled[0]
if (ch.get("type") or "").strip() != "feishu":
    fail("当前仅支持 feishu 渠道：请将启用的渠道 type 设置为 feishu。")

webhook = (ch.get("webhook") or "").strip()
if not webhook or "hook/xxx" in webhook:
    fail("请在 config.json 填写真实的飞书 webhook（不要保留 hook/xxx 占位符）。")

if mode != "once":
    schedule = cfg.get("schedule")
    if not isinstance(schedule, dict):
        fail("config.json 缺少 schedule：请配置 schedule.interval_minutes（分钟）。")
    iv = schedule.get("interval_minutes")
    try:
        iv = int(iv)
    except Exception:
        fail("schedule.interval_minutes 必须是整数。")
    if iv <= 0:
        fail("schedule.interval_minutes 必须 > 0。")
PY

echo "启动监控（退出用 Ctrl+C）…" >&2
if [[ "$HAS_ONCE" == "true" || "$HAS_LOOP" == "true" ]]; then
  exec "$VENV_PY" icity_friends_monitor.py "$@"
fi

exec "$VENV_PY" icity_friends_monitor.py --loop "$@"
