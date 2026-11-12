#!/usr/bin/env bash
# Launcher for pm2: load server/.env, then run the API. Binds loopback only.
set -euo pipefail
umask 077
cd "$(dirname "$0")/../server"
set -a; . ./.env; set +a
exec .venv/bin/python -m sarf.main
