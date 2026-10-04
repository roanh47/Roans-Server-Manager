#!/usr/bin/env bash
# Run the panel locally (no Docker). Used for development and for the tests.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

BIND="${SM_BIND:-127.0.0.1}"
PORT="${SM_PORT:-8303}"

# Deliberately not 0.0.0.0: remote access goes over Tailscale, never by widening
# the bind. See AGENTS.md.
exec .venv/bin/python -m uvicorn servermanager.web.app:app \
  --host "$BIND" --port "$PORT" --reload
