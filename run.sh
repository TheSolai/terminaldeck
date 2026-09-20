#!/usr/bin/env bash
# Launch TerminalDeck from source (development).
set -e
cd "$(dirname "$0")"
exec ./.venv/bin/python run.py "$@"