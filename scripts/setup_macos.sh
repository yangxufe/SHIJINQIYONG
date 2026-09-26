#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo '此脚本只用于 macOS；没有修改运行配置。' >&2
  exit 2
fi
if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo '用法：bash scripts/setup_macos.sh <本机家庭Wi-Fi IPv4> <已确认家庭子网CIDR> [IANA时区]' >&2
  exit 2
fi
if ! command -v python3.12 >/dev/null 2>&1; then
  echo '请先安装 Python 3.12，并确认 python3.12 在 PATH 中。' >&2
  exit 2
fi
if ! command -v caddy >/dev/null 2>&1; then
  echo '请先安装 Caddy（例如 brew install caddy），并确认 caddy 在 PATH 中。' >&2
  exit 2
fi

cd "$(dirname "$0")/.."
umask 077
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python scripts/macos_setup.py "$1" "$2" --time-zone "${3:-UTC}"
.venv/bin/python scripts/macos_runtime.py manage check --deploy
.venv/bin/python scripts/macos_runtime.py manage migrate --noinput
.venv/bin/python scripts/macos_runtime.py manage collectstatic --noinput
.venv/bin/python scripts/macos_runtime.py caddy-adapt >/dev/null
echo '安装与迁移已完成。请按 docs/MACOS.md 创建本机管理员，并在两个终端分别启动 Waitress 与 Caddy。'
