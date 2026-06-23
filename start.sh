#!/usr/bin/env bash
set -e

PYTHON_BIN="/app/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python"
fi

exec "$PYTHON_BIN" -m Backend
