#!/usr/bin/env bash
# scaffold.sh: start a new always-on agent app from examples/always-on-agent.
#
#   scaffold.sh <app-dir>          e.g. scaffold.sh apps/cold-chain-monitor
#
# Copies always_on_agent.py, the d1 sensor questions it imports, and the LFM client, rewires the imports
# so the app is self-contained, and writes a README stub. Refuses to overwrite an existing directory.

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/../.." && pwd)"
DEST="${1:-}"
case "$DEST" in --help|-h) echo "usage: scaffold.sh <app-dir> (creates a reference d1/LFM app; refuses existing paths)"; exit 0 ;; esac
[ -n "$DEST" ] || { echo "usage: scaffold.sh <app-dir>" >&2; exit 64; }
DEST="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$DEST")"
{ [ -e "$DEST" ] || [ -L "$DEST" ]; } && { echo "refusing to overwrite $DEST" >&2; exit 1; }

SRC_AGENT="$REPO_ROOT/examples/always-on-agent/always_on_agent.py"
SRC_QUESTIONS="$REPO_ROOT/examples/system-one-decision/system_one_example.py"
SRC_CLIENT="$REPO_ROOT/skills/iq9-geniex-lfm/scripts/lfm_client.py"
for f in "$SRC_AGENT" "$SRC_QUESTIONS" "$SRC_CLIENT"; do [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }; done

mkdir -p "$DEST"
cp "$SRC_AGENT" "$DEST/agent.py"
cp "$SRC_CLIENT" "$DEST/lfm_client.py"

# questions.py: just the d1 questions, so the app does not depend on the example directory.
python3 - "$SRC_QUESTIONS" "$DEST/questions.py" <<'EOF'
import ast, sys
src = open(sys.argv[1]).read()
tree = ast.parse(src)
node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "SENSOR_QUESTIONS" for t in n.targets))
body = ast.get_source_segment(src, node)
open(sys.argv[2], "w").write('"""d1 questions for this app. Edit them, then recalibrate the threshold."""\n\n' + body + "\n")
EOF

# Rewire the import: the example reaches into ../system-one-decision.
python3 - "$DEST/agent.py" <<'EOF'
import sys
p = sys.argv[1]
s = open(p).read()
old_path = 'sys.path.insert(0, os.path.join(HERE, "..", "system-one-decision"))\n'
old_imp = "from system_one_example import SENSOR_QUESTIONS  # noqa: E402  (alert, category, severity)"
assert old_path in s and old_imp in s, "always_on_agent.py changed; update scaffold.sh"
s = s.replace(old_path, "sys.path.insert(0, HERE)\n")
s = s.replace(old_imp, "from questions import SENSOR_QUESTIONS  # noqa: E402  (edit questions.py)")
open(p, "w").write(s)
EOF

NAME="$(basename "$DEST")"
cat > "$DEST/README.md" <<EOF
# $NAME

Reference always-on local agent on the Dragonwing IQ-9075, started from \`examples/always-on-agent\`.

This scaffold uses d1-2B and LFM3-1.7B, not mandatory competition models. You may replace the gate with a rule or another decision design and choose another LFM3-family model after verifying its runtime/NPU and task behavior. External sensors are optional and not provided.

## Loop

observe → decide (d1-2B, CPU) → act (allowlist) → explain (LFM, NPU, only on alerts) → log (JSONL)

## What to change

| File / function | Change it to |
|---|---|
| \`agent.py\` \`read_sensors()\` / \`BoardTelemetry\` | your real signal (camera frame, mic level, serial sensor, log tail) |
| \`questions.py\` | the decisions you act on |
| \`agent.py\` \`ALLOWED_ACTIONS\`, \`run_action()\` | your actions; every new action goes on the allowlist on purpose |
| \`agent.py\` \`build_prompt()\` | include trend and direction, not just raw values |
| \`--threshold\` | calibrated value (skills/iq9-d1-decision-gate) — not 0.5 |

\`lfm_client.py\` provides capped calls, usable-output checks, unique initial raw prompts, and one retry. It does not execute tools or enforce their argument schemas/action policy. The copied \`agent.py\` currently uses its own explanation code; switch \`explain()\` to the client if preferred. Keep \`--stable-prompt\` for diagnostics only, never normal runs.

## Run

\`\`\`bash
# From the repo root, in a separate terminal:
bash skills/iq9-geniex-lfm/scripts/serve.sh run
# From this app's directory, in another terminal:
~/.venvs/d1/bin/python agent.py --sensor-mode simulated --iterations 4 --interval 1 --log test.jsonl   # smoke test
~/.venvs/d1/bin/python agent.py --threshold <calibrated> --log agent_log.jsonl
\`\`\`

## Offline and verification status

Load d1 from the pinned local snapshot with offline settings; use only an already-cached generator. No installs, pulls, CDN assets, or telemetry at runtime. Ask before any model download/import or network cut. A passing local test is not a physical network-off rehearsal.

## Measured (fill in after running this app)

Record board/date, GenieX version, model/build and precision, sample count, and medians.

| Metric | Value | How |
|---|---|---|
| Gate latency |  | median \`decision.gate_ms\` |
| Loop with explanation |  | median \`loop_ms\` where action=log_alert |
| Network-off run |  | skills/iq9-offline-rehearsal |
EOF

echo "created $DEST:"
find "$DEST" -maxdepth 1 -type f -exec basename {} \; | sort | sed 's/^/  /'
echo "next: edit read_sensors() and questions.py, then run the smoke test in $DEST/README.md"
