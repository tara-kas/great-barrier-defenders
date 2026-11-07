#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ISAAC_INSTALL="${ISAAC_INSTALL:-/home/smint/isaacsim}"
if [[ ! -x "$ISAAC_INSTALL/python.sh" ]]; then
  echo "Set ISAAC_INSTALL to your Isaac Sim 6.0 installation." >&2
  exit 1
fi
cd "$PROJECT_ROOT"
exec "$ISAAC_INSTALL/python.sh" "$PROJECT_ROOT/scripts/run_isaac.py" "$@"
