#!/usr/bin/env bash
# scaffold.sh: start a new always-on agent app from examples/always-on-agent.
#
#   scaffold.sh <app-dir>          e.g. scaffold.sh apps/cold-chain-monitor
#
# Copies always_on_agent.py, the LFM client it uses, and the d1 sensor questions (loaded only by --gate d1),
# rewires the paths so the app is self-contained, and writes a README stub. Refuses to overwrite an
# existing directory.

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/../.." && pwd)"
DEST="${1:-}"
case "$DEST" in --help|-h) echo "usage: scaffold.sh <app-dir> (creates a reference always-on app; refuses existing paths)"; exit 0 ;; esac
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
python3 - "$SRC_QUESTIONS" "$DEST/questions.py" <<'PY'
import ast, sys
src = open(sys.argv[1]).read()
tree = ast.parse(src)
node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "SENSOR_QUESTIONS" for t in n.targets))
body = ast.get_source_segment(src, node)
open(sys.argv[2], "w").write('"""d1 questions for this app (--gate d1). Edit them, then recalibrate the threshold."""\n\n' + body + "\n")
PY

# Rewire the two helper paths: the example reaches into the skills and system-one-decision directories.
python3 - "$DEST/agent.py" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
old_note = "# scaffold.sh copies both helpers next to the app and rewrites these two lines.\n"
old_client = 'LFM_CLIENT_DIR = os.path.join(HERE, "..", "..", "skills", "iq9-geniex-lfm", "scripts")\n'
old_questions = 'D1_QUESTIONS = (os.path.join(HERE, "..", "system-one-decision"), "system_one_example")\n'
assert old_note in s and old_client in s and old_questions in s, "always_on_agent.py changed; update scaffold.sh"
s = s.replace(old_note, "# lfm_client.py and questions.py sit next to this file.\n")
s = s.replace(old_client, "LFM_CLIENT_DIR = HERE\n")
s = s.replace(old_questions, 'D1_QUESTIONS = (HERE, "questions")\n')
open(p, "w").write(s)
PY

NAME="$(basename "$DEST")"
cat > "$DEST/README.md" <<EOF
# $NAME

Always-on local agent on the Dragonwing IQ-9075, started from \`examples/always-on-agent\`.

The reference models are LFM3-1.7B and, optionally, d1-2B; neither is mandatory. Choose another LFM3-family model after verifying its runtime/NPU and task behavior. External sensors are optional and not provided.

## Loop

observe → decide (a rule, or d1-2B on the CPU) → act (allowlist) → explain (LFM, NPU, only on alerts) → log (JSONL)

## What to change

| File / function | Change it to |
|---|---|
| \`agent.py\` \`read_sensors()\` / \`BoardTelemetry\` | your real signal (camera frame, mic level, serial sensor, log tail) |
| \`agent.py\` \`rule_decide()\`, \`--rule-temp-c\`, \`--rule-rise-c\` | your rule and limits, set from your own readings |
| \`questions.py\`, \`--threshold\` | with \`--gate d1\`: the decisions you act on and a calibrated threshold (skills/iq9-d1-decision-gate), not 0.5 |
| \`agent.py\` \`ALLOWED_ACTIONS\`, \`run_action()\` | your actions; every new action goes on the allowlist on purpose |
| \`agent.py\` \`build_prompt()\` | include trend and direction, not just raw values |

\`agent.py\` sends explanations through \`lfm_client.py\`: capped calls, usable-output checks, unique raw prompts, and one retry. The client does not execute tools or enforce argument schemas/action policy. Keep \`--stable-prompt\` for diagnostics only.

## Run

\`\`\`bash
# From the repo root, in a separate terminal:
bash skills/iq9-geniex-lfm/scripts/serve.sh run
# From this app's directory, in another terminal. The rule gate needs no d1 venv or snapshot:
python3 agent.py --gate rule --sensor-mode simulated --iterations 4 --interval 1 --log test.jsonl   # smoke test
python3 agent.py --gate rule --log agent_log.jsonl
# With the d1 venv and snapshot set up (d1 is the default gate):
~/.venvs/d1/bin/python agent.py --threshold <calibrated> --log agent_log.jsonl
\`\`\`

## Offline and verification status

Use only an already-cached generator; with \`--gate d1\`, the pinned local snapshot loads with offline settings. No installs, pulls, CDN assets, or telemetry at runtime. A passing local test is not a network-off rehearsal.

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
echo "next: run the smoke test in $DEST/README.md, then edit read_sensors() and the gate"
