#!/bin/bash
# Start Argus on the board (run from the board shell). Logs to apps/argus/run/.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p run
export TZ="${TZ:-America/Los_Angeles}"
exec python3 argus.py --speak "$@"
