#!/usr/bin/env bash
# FigurePrice 데스크톱 런처
# Finder에서 더블클릭하면 venv 활성화 + GUI 실행.
# 터미널 창이 열리고, 앱을 끄면 창도 닫혀요.

set -eu
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [ ! -d ".venv" ]; then
  echo "ERROR: .venv 폴더가 없어요. 먼저 README의 '설치' 단계를 진행하세요."
  echo "  python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  read -rp "엔터를 누르면 닫혀요…"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec python -m gui
