#!/bin/bash
# Start Argus on the board (run from the board shell). Logs to apps/argus/run/.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p run
export TZ="${TZ:-America/Los_Angeles}"
# Stop it with: pkill -TERM -f "python3 argus.py"  (never kill -9: the model sessions must exit cleanly)
exec python3 argus.py --speak "$@"
