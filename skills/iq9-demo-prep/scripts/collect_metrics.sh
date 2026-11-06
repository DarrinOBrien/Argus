#!/usr/bin/env bash
# Compatibility entry point; collect_metrics.py contains the testable streaming collector.
# Run on the board with a foreground GenieX server already serving a cached model.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/collect_metrics.py" "$@"
