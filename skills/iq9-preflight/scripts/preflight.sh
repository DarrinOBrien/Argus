#!/usr/bin/env bash
# shellcheck disable=SC2015  # `test && add ok || add FAIL` is intended: add() always returns 0
# preflight.sh: is this IQ-9075 ready for the hackathon stack? Read-only; changes nothing, downloads nothing.
#
#   preflight.sh            human-readable report
#   preflight.sh --json     one JSON object (for agents)
#
# Exit 0: no FAIL. Exit 1: at least one FAIL. WARN never fails the run.
# Env: D1_PYTHON (default ~/.venvs/d1/bin/python), D1_MODEL_DIR (default ~/models/d1-3B),
#      EXPECT_GENIEX (default v0.8.0), MIN_FREE_GB (default 10), GENIEX_PORT (default 18181)

set -uo pipefail

JSON=0; [ "${1:-}" = "--json" ] && JSON=1
D1_PYTHON="${D1_PYTHON:-$HOME/.venvs/d1/bin/python}"
D1_MODEL_DIR="${D1_MODEL_DIR:-$HOME/models/d1-3B}"
EXPECT_GENIEX="${EXPECT_GENIEX:-v0.8.0}"
MIN_FREE_GB="${MIN_FREE_GB:-10}"
PORT="${GENIEX_PORT:-18181}"
D1_REVISION="051bcc464b01b9f92942b364d9586b0ef5912432"

RESULTS=()
FAILS=0
add() {  # status name detail fix
  local s="$1" n="$2" d="$3" f="${4:-}"
  if [ "$s" = FAIL ]; then FAILS=$((FAILS + 1)); fi
  RESULTS+=("$s"$'\t'"$n"$'\t'"$d"$'\t'"$f")
  return 0
}

# ---- board ------------------------------------------------------------------------------------------
arch="$(uname -m)"
[ "$arch" = aarch64 ] && add ok arch "$arch" || add FAIL arch "$arch" "run this on the IQ-9075"

nodes="$(find /dev -maxdepth 1 -name 'fastrpc-cdsp*' ! -name '*-secure' 2>/dev/null | wc -l | tr -d ' ')"
[ "$nodes" -ge 2 ] && add ok npu-nodes "$nodes CDSP nodes (/dev/fastrpc-cdsp, -cdsp1)" \
  || add FAIL npu-nodes "$nodes CDSP nodes (expect 2)" "sudo apt-get install -y qcom-adreno1 qcom-fastrpc1 libqnn1 (ask the user first)"

first_node="$(find /dev -maxdepth 1 -name 'fastrpc-cdsp*' ! -name '*-secure' 2>/dev/null | sort | head -1)"
if [ -n "$first_node" ]; then
  if [ -r "$first_node" ]; then add ok npu-access "readable by $(id -un)"
  else add FAIL npu-access "not readable by $(id -un)" "sudo usermod -aG fastrpc $(id -un), then log in again (ask the user first)"; fi
fi

free_gb="$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9')"
if [ -n "$free_gb" ]; then
  [ "$free_gb" -ge "$MIN_FREE_GB" ] && add ok disk "${free_gb}G free on /" \
    || add WARN disk "${free_gb}G free on / (< ${MIN_FREE_GB}G)" "geniex list; remove only models the user confirms are unused"
fi

mem_gb="$(awk '/MemAvailable/ {printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null)"
[ -n "$mem_gb" ] && { [ "$mem_gb" -ge 20 ] && add ok memory "${mem_gb}G available" \
  || add WARN memory "${mem_gb}G available (d1 fp32 peaks at ~19.4 GB)" "stop other large processes"; }

# ---- geniex -----------------------------------------------------------------------------------------
if command -v geniex >/dev/null; then
  ver="$(geniex version 2>/dev/null | awk -F': *' '/CLI Version/ {print $2}' | tr -d ' ')"
  [ "$ver" = "$EXPECT_GENIEX" ] && add ok geniex "$ver" \
    || add WARN geniex "${ver:-unknown} (docs were measured on $EXPECT_GENIEX)" "numbers in docs/ may not apply; do not reinstall without asking"
  chip="$(geniex config get chipset 2>/dev/null | tail -1)"
  case "$chip" in *IQ-9075*) add ok chipset "$chip" ;; *) add WARN chipset "${chip:-unknown}" "" ;; esac
  list="$(geniex list 2>/dev/null)"
  for m in "LiquidAI/LFM2.5-2.6B-GGUF Q4_0 FAIL" "LiquidAI/LFM2-1.2B-Tool-GGUF Q4_0 WARN"; do
    # shellcheck disable=SC2086  # split "repo precision level" on purpose
    set -- $m
    if echo "$list" | awk -F'│' -v r="$1" -v p="$2" '{gsub(/ /,"",$2); gsub(/ /,"",$4)} $2==r && $4 ~ p {f=1} END {exit !f}'; then
      add ok "model:$1" "$2 cached"
    else
      add "$3" "model:$1" "$2 not cached" "geniex pull $1:$2 (needs network; check disk first)"
    fi
  done
else
  add FAIL geniex "not on PATH" "export PATH=\"\$HOME/.local/bin:\$PATH\", or install per docs/developer-guide.md §3.3"
fi

if curl -s -o /dev/null -m 3 "http://127.0.0.1:$PORT/v1/models"; then
  add ok server "geniex serve answering on 127.0.0.1:$PORT"
else
  add WARN server "nothing on 127.0.0.1:$PORT" "start it when needed: geniex serve --compute npu"
fi

# ---- d1 (Path A) ------------------------------------------------------------------------------------
if [ -x "$D1_PYTHON" ]; then
  # shellcheck disable=SC2016
  vers="$("$D1_PYTHON" -c 'import torch, transformers; print(torch.__version__, transformers.__version__)' 2>/dev/null)"
  if [ -n "$vers" ]; then add ok d1-venv "$D1_PYTHON (torch/transformers $vers)"
  else add FAIL d1-venv "$D1_PYTHON cannot import torch/transformers" "see examples/system-one-decision/README.md (Install)"; fi
else
  add FAIL d1-venv "no python at $D1_PYTHON" "see examples/system-one-decision/README.md (Install)"
fi
if [ -f "$D1_MODEL_DIR/model.safetensors" ]; then
  rev="$(cat "$D1_MODEL_DIR/REVISION" 2>/dev/null | tr -d '[:space:]')"
  [ "$rev" = "$D1_REVISION" ] && add ok d1-snapshot "$D1_MODEL_DIR @ ${rev:0:12}" \
    || add FAIL d1-snapshot "REVISION ${rev:-missing} (expected ${D1_REVISION:0:12})" "run examples/system-one-decision/fetch_d1.py; review remote code before moving the pin"
else
  add FAIL d1-snapshot "no model.safetensors in $D1_MODEL_DIR" "$D1_PYTHON examples/system-one-decision/fetch_d1.py --dest $D1_MODEL_DIR (needs network, ~6.2 GB)"
fi

# ---- thermal (the default sensor) -------------------------------------------------------------------
zones=0
for z in /sys/class/thermal/thermal_zone*/temp; do [ -r "$z" ] && cat "$z" >/dev/null 2>&1 && zones=$((zones + 1)); done
[ "$zones" -gt 0 ] && add ok thermal "$zones readable thermal zones" || add WARN thermal "no readable thermal zones" ""

# ---- network (informational) ------------------------------------------------------------------------
if curl -s -o /dev/null -m 4 https://huggingface.co; then add ok network "online (pull/install now; the demo runs offline)"
else add ok network "offline"; fi

# ---- report -----------------------------------------------------------------------------------------
if [ "$JSON" -eq 1 ]; then
  printf '%s\n' "${RESULTS[@]}" | python3 -c '
import json, sys
rows = [l.rstrip("\n").split("\t") for l in sys.stdin if l.strip()]
checks = [{"status": r[0], "check": r[1], "detail": r[2], "fix": r[3] if len(r) > 3 and r[3] else None} for r in rows]
print(json.dumps({"ready": not any(c["status"] == "FAIL" for c in checks), "checks": checks}, indent=1))'
else
  for r in "${RESULTS[@]}"; do
    IFS=$'\t' read -r s n d f <<<"$r"
    printf '[%-4s] %-32s %s\n' "$s" "$n" "$d"
    [ -n "$f" ] && [ "$s" != ok ] && printf '       fix: %s\n' "$f"
  done
  [ "$FAILS" -eq 0 ] && echo "ready" || echo "$FAILS check(s) failed"
fi
[ "$FAILS" -eq 0 ]
