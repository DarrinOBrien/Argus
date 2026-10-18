#!/usr/bin/env bash
# collect_metrics.sh: numbers for the judges, from the running stack on the IQ-9075.
#
#   collect_metrics.sh [--model M] [--runs N] [--log app_log.jsonl] [--out metrics.json]
#
# Needs geniex serve running (skills/iq9-geniex-lfm/scripts/serve.sh start). Measures, with N streamed requests:
#   TTFT (time to first content chunk), decode tok/s (tokens after the first / time after the first), end-to-end.
# Also records: geniex version, device in use, server RSS, system memory, disk, hottest thermal zone,
# and, if --log points at an always-on-agent style JSONL, gate/loop latency medians and alert counts.
# Prompts are varied per run to avoid the v0.8.0 zero-token state. Read-only apart from --out.

set -euo pipefail

MODEL="LiquidAI/LFM2.5-2.6B-GGUF:Q4_0"; RUNS=5; APPLOG=""; OUT=""
PORT="${GENIEX_PORT:-18181}"
while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;;
    --runs) RUNS="$2"; shift 2 ;;
    --log) APPLOG="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 64 ;;
  esac
done
curl -s -o /dev/null -m 3 "http://127.0.0.1:$PORT/v1/models" || { echo "no geniex serve on :$PORT" >&2; exit 1; }

PID="$(ss -ltnp 2>/dev/null | sed -n "s/.*127.0.0.1:$PORT .*pid=\([0-9]*\).*/\1/p" | head -1)"
export MODEL RUNS APPLOG PORT PID
python3 - "$OUT" <<'EOF'
import json, os, statistics, subprocess, sys, time, urllib.request, uuid
model, runs, applog, port, pid = os.environ["MODEL"], int(os.environ["RUNS"]), os.environ["APPLOG"], os.environ["PORT"], os.environ["PID"]
base = f"http://127.0.0.1:{port}"

def sh(cmd):
    try: return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception: return ""

def stream_once(i):
    body = {"model": model, "stream": True, "max_completion_tokens": 64, "compute": "npu",
            "stream_options": {"include_usage": True},
            "messages": [{"role": "user", "content": f"Describe an edge AI use case number {i} ({uuid.uuid4().hex[:6]})."}]}
    req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter(); first = None; chunks = 0; usage = None
    with urllib.request.urlopen(req, timeout=120) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:"): continue
            data = line[5:].strip()
            if data == "[DONE]": break
            d = json.loads(data)
            if d.get("usage"): usage = d["usage"]
            for c in d.get("choices", []):
                if (c.get("delta") or {}).get("content"):
                    chunks += 1
                    if first is None: first = time.perf_counter()
    end = time.perf_counter()
    tokens = (usage or {}).get("completion_tokens", chunks)
    return {"ttft_s": round(first - t0, 3) if first else None, "e2e_s": round(end - t0, 3), "tokens": tokens,
            "decode_tok_s": round((tokens - 1) / (end - first), 1) if first and tokens > 1 and end > first else None}

stream_once(0)  # warm-up: the first request after a start or idle unload loads the model (~5 s)
samples = [stream_once(i) for i in range(1, runs + 1)]
ok = [s for s in samples if s["tokens"]]
med = lambda xs: round(statistics.median(xs), 3) if xs else None

out = {
    "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "board": sh("geniex config get chipset | tail -1"),
    "geniex": sh("geniex version | awk -F': *' '/CLI Version/ {print $2}'"),
    "model": model,
    "llm": {"runs": runs, "zero_token_runs": runs - len(ok), "max_completion_tokens": 64,
            "ttft_s_median": med([s["ttft_s"] for s in ok if s["ttft_s"]]),
            "decode_tok_s_median": med([s["decode_tok_s"] for s in ok if s["decode_tok_s"]]),
            "e2e_s_median": med([s["e2e_s"] for s in ok]), "samples": samples},
    "server_rss_mb": round(int(sh(f"ps -o rss= -p {pid}") or 0) / 1024, 1) if pid else None,
    "mem": sh("free -m | awk '/Mem:/ {print $3\" MB used / \"$2\" MB total\"}'"),
    "disk_free": sh("df -h / | awk 'NR==2 {print $4}'"),
    "hottest_zone_c": None,
}
temps = []
for z in sorted(os.listdir("/sys/class/thermal")) if os.path.isdir("/sys/class/thermal") else []:
    try: temps.append(int(open(f"/sys/class/thermal/{z}/temp").read()) / 1000)
    except Exception: pass
out["hottest_zone_c"] = max(temps) if temps else None

if applog and os.path.exists(applog):
    rows = [json.loads(l) for l in open(applog) if l.strip()]
    rows = [r for r in rows if "decision" in r]
    gate = [r["decision"].get("gate_ms") for r in rows if r["decision"].get("gate_ms")]
    loop = [r.get("loop_ms") for r in rows if r.get("loop_ms")]
    ex = [r["explanation"] for r in rows if r.get("explanation")]
    out["app"] = {"log": applog, "iterations": len(rows),
                  "alerts": sum(1 for r in rows if r.get("action") == "log_alert"),
                  "gate_ms_median": med(gate), "loop_ms_median": med(loop),
                  "explanations_ok": sum(1 for e in ex if e.get("ok")), "explanations": len(ex),
                  "first_t": rows[0].get("t") if rows else None, "last_t": rows[-1].get("t") if rows else None}

text = json.dumps(out, indent=1)
if sys.argv[1]:
    open(sys.argv[1], "w").write(text + "\n")
print(text)
EOF
