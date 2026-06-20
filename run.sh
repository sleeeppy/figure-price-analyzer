#!/usr/bin/env bash
# Terminal shortcut: `./run.sh`
set -eu
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
# shellcheck disable=SC1091
source .venv/bin/activate
exec python -m gui "$@"
