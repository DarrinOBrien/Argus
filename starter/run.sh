#!/usr/bin/env bash
# starter/run.sh: check the board, then run one decision pass (d1-2B) and one generation (LFM3-1.7B).
#
# Usage: ./starter/run.sh [--skip-lfm]
#
# Downloads nothing. If something is missing, it prints the command to fix it and exits.
# Env overrides: D1_PYTHON (default ~/.venvs/d1/bin/python), D1_MODEL_DIR (default ~/models/d1-2B)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
D1_PYTHON="${D1_PYTHON:-$HOME/.venvs/d1/bin/python}"
D1_MODEL_DIR="${D1_MODEL_DIR:-$HOME/models/d1-2B}"
LFM="LiquidAI/LFM3-1.7B-GGUF"
LOG="$REPO_ROOT/starter/demo_log.jsonl"
SKIP_LFM=0
case "${1:-}" in
  "") ;;
  --skip-lfm) SKIP_LFM=1 ;;
  --help|-h) echo "usage: starter/run.sh [--skip-lfm]   (run on the IQ-9075 after LFM and d1 setup; downloads nothing)"; exit 0 ;;
  *) echo "unknown flag: $1 (usage: starter/run.sh [--skip-lfm])" >&2; exit 64 ;;
esac

fail() { echo "FAIL: $1"; echo "  fix: $2"; exit 1; }

echo "==> 1. Board"
[ "$(uname -m)" = "aarch64" ] || fail "not an aarch64 board ($(uname -m))" "run this on the IQ-9075"
command -v geniex >/dev/null || fail "geniex not on PATH" "see docs/developer-guide.md §3.3, or add ~/.local/bin to PATH"
echo "    $(geniex version | head -1)"
echo "    chipset: $(geniex config get chipset)"
ls /dev/fastrpc-cdsp* >/dev/null 2>&1 || fail "no /dev/fastrpc-cdsp* nodes" "install the driver packages, docs/developer-guide.md §3.2"
echo "    disk free on /: $(df -h / | awk 'NR==2 {print $4}')"

echo "==> 2. Decision layer (d1-2B, Transformers on CPU)"
[ -x "$D1_PYTHON" ] || fail "no d1 venv at $D1_PYTHON" "follow examples/system-one-decision/README.md (Install)"
[ -d "$D1_MODEL_DIR" ] || fail "no d1 snapshot at $D1_MODEL_DIR" "copy the pinned snapshot from the supplied USB model drive (docs/developer-guide.md §4); fetch_d1.py is the approved download fallback"
(cd "$REPO_ROOT/examples/system-one-decision" && "$D1_PYTHON" check_env.py) \
  || fail "check_env.py reported a problem" "read the [FAIL] lines above"

echo "==> 3. One decision pass (3 sensor states, 1 image, 1 batch)"
(cd "$REPO_ROOT/examples/system-one-decision" && \
  "$D1_PYTHON" system_one_example.py --model-dir "$D1_MODEL_DIR" --log "$LOG" --dtype float32)
echo "    decisions appended to $LOG"

if [ "$SKIP_LFM" -eq 1 ]; then
  echo "==> 4. Skipped LFM check (--skip-lfm)"
else
  echo "==> 4. One generation (LFM3-1.7B on the NPU)"
  # Capture first: with pipefail, grep -q closing the pipe early can look like a missing model.
  cached="$(geniex list 2>/dev/null || true)"
  grep -q "$LFM" <<<"$cached" || fail "$LFM is not in the GenieX cache" "import it from the supplied USB model drive (docs/developer-guide.md §4); a download is the approved fallback"
  # Requires a foreground server in another terminal; never manages shared servers.
  (cd "$REPO_ROOT/examples/lfm-server-npu" && python3 serve_lfm_npu.py --max-tokens 48)
fi

echo ""
echo "==> Done. Next: examples/always-on-agent (the full loop) or examples/tool-calling."
