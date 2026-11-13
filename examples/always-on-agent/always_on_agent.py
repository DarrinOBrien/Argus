#!/usr/bin/env python3
"""Always-on local agent: observe -> decide -> act -> explain -> log.

Each iteration:
  1. observe   read the board's own telemetry (SoC thermal zones, CPU load) by default
  2. decide    --gate d1 (default): d1-2B (Transformers, CPU, fp32) returns p_alert, category, severity
               --gate rule: a threshold rule in code; needs no d1 venv, torch, or snapshot
  3. act       choose an action; only allowlisted actions run, anything else is refused
  4. explain   only when the action is log_alert: LFM3-1.7B (GenieX, NPU) writes one sentence through
               lfm_client.py (capped raw completion, reasoning block closed, validated, one retry)
  5. log       one flushed JSON line per iteration; sensor, gate, and explanation errors are logged too

The loop is sequential: d1 slows down substantially while the LFM generates. Re-measure the chosen
configuration before changing the scheduling policy.

Requires a GenieX server on --server with the --llm model cached. --gate d1 also needs the d1 venv and
the snapshot at --model-dir (see examples/system-one-decision/README.md); --gate rule runs on python3.
"""

import argparse
import collections
import importlib
import json
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
# scaffold.sh copies both helpers next to the app and rewrites these two lines.
LFM_CLIENT_DIR = os.path.join(HERE, "..", "..", "skills", "iq9-geniex-lfm", "scripts")
D1_QUESTIONS = (os.path.join(HERE, "..", "system-one-decision"), "system_one_example")

sys.path.insert(0, LFM_CLIENT_DIR)
from lfm_client import LFM  # noqa: E402  (capped requests, output checks, one retry, errors as data)

# Only these actions can run. Anything else is refused and logged.
ALLOWED_ACTIONS = ("no_op", "log_alert")
EXPLAIN_TIMEOUT_S = 60
THERMAL_ROOT = "/sys/class/thermal"
HISTORY_S = 300
SYSTEM_LINE = "You write one-sentence alerts for operators. Reply with the sentence only."


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class BoardTelemetry:
    """The board's own temperatures from sysfs thermal zones. No extra hardware.

    Observation: the hottest zone now, the same value about one minute ago, and the 1-minute CPU load.
    The 1-minute value is the sample closest to 60 s ago. Until 60 s of history exists, it is the oldest sample.
    """

    def __init__(self):
        self.zones = []
        if os.path.isdir(THERMAL_ROOT):
            for name in sorted(os.listdir(THERMAL_ROOT)):
                if not name.startswith("thermal_zone"):
                    continue
                base = os.path.join(THERMAL_ROOT, name)
                try:
                    with open(os.path.join(base, "type")) as f:
                        typ = f.read().strip()
                    self._read_temp(os.path.join(base, "temp"))  # must be readable
                except (OSError, ValueError):
                    continue
                self.zones.append((typ, os.path.join(base, "temp")))
        if not self.zones:
            raise RuntimeError("no readable thermal zones in /sys/class/thermal")
        self.history = collections.deque()  # (monotonic seconds, hottest temperature)

    @staticmethod
    def _read_temp(path):
        with open(path) as f:
            return int(f.read().strip()) / 1000.0  # sysfs reports millidegrees

    def read(self):
        readings = []
        for typ, path in self.zones:
            try:
                readings.append((self._read_temp(path), typ))
            except (OSError, ValueError):
                continue
        if not readings:
            raise RuntimeError("thermal zones stopped answering")
        hottest, zone = max(readings)
        now = time.monotonic()
        self.history.append((now, hottest))
        while self.history and now - self.history[0][0] > HISTORY_S:
            self.history.popleft()
        target = now - 60.0
        past = min(self.history, key=lambda s: abs(s[0] - target))[1]
        return {
            "soc_temp_c": round(hottest, 1),
            "soc_temp_c_1min_ago": round(past, 1),
            "cpu_load_1min": round(os.getloadavg()[0], 2),
            "hottest_zone": zone,
        }


def read_sensors(mode, rng, telemetry=None):
    """The loop's observation. Every mode returns the same keys, so gates and prompts see one shape.

    'board' reads the SoC telemetry (default). 'simulated' returns random states and 'fixed' repeats
    one hot state; both are for tests.
    """
    if mode == "board":
        return telemetry.read()
    if mode == "fixed":
        return {"soc_temp_c": 71.5, "soc_temp_c_1min_ago": 58.0, "cpu_load_1min": 0.5, "hottest_zone": "fixed"}
    if rng.random() < 0.5:
        t = round(rng.uniform(34, 40), 1)
        prev = round(t + rng.uniform(-0.5, 0.5), 1)
    else:
        t = round(rng.uniform(65, 80), 1)
        prev = round(rng.uniform(50, 62), 1)
    return {"soc_temp_c": t, "soc_temp_c_1min_ago": prev, "cpu_load_1min": round(rng.uniform(0.1, 4.0), 2),
            "hottest_zone": "simulated"}


# ---- decision gates: each returns a dict with "gate", "alert", "category", and "gate_ms" -------------

def load_d1(model_dir):
    """Load d1-2B once and return its decide(obs, threshold) function.

    torch and Transformers are imported here, not at module level, so --gate rule needs neither.
    """
    os.environ["HF_HUB_OFFLINE"] = "1"  # before the Transformers import
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        import torch
        from transformers import AutoModel
        sys.path.insert(0, D1_QUESTIONS[0])
        questions = importlib.import_module(D1_QUESTIONS[1]).SENSOR_QUESTIONS  # alert, category, severity
    except ImportError as e:
        sys.exit(f"--gate d1 needs the d1 venv ({e}). Run with ~/.venvs/d1/bin/python, "
                 "or use --gate rule to run without d1.")
    if not os.path.isdir(model_dir):
        sys.exit(f"d1 snapshot not found at {model_dir}. See examples/system-one-decision/README.md, "
                 "or use --gate rule to run without d1.")
    model = AutoModel.from_pretrained(model_dir, trust_remote_code=True, local_files_only=True,
                                      dtype=torch.float32)
    model = model.to("cpu").eval()

    def decide(obs, threshold):
        t0 = time.perf_counter()
        with torch.inference_mode():
            a = model.system_one(json.dumps(obs), questions)["answers"]
        p_alert = float(a["alert"]["noul"])  # Preserve precision for calibration and policy.
        return {
            "gate": "d1",
            "p_alert": p_alert,
            "alert": p_alert >= threshold,
            "category": a["category"]["choice"],
            "severity": round(a["severity"]["score"], 3),
            "gate_ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    return decide, f"d1-2B fp32 on CPU, threads={torch.get_num_threads()}"


def rule_decide(obs, limit_c, rise_c):
    """--gate rule: alert when the temperature or its one-minute rise reaches a limit. No model."""
    t0 = time.perf_counter()
    temp = obs["soc_temp_c"]
    rise = round(temp - obs["soc_temp_c_1min_ago"], 1)
    reasons = []
    if temp >= limit_c:
        reasons.append(f"temperature {temp} C is at or above the {limit_c} C limit")
    if rise >= rise_c:
        reasons.append(f"rose {rise} C in one minute (limit {rise_c} C)")
    return {
        "gate": "rule",
        "alert": bool(reasons),
        "category": "thermal" if reasons else "normal",
        "reason": "; ".join(reasons) or "within limits",
        "gate_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def choose_action(decision):
    return "log_alert" if decision["alert"] else "no_op"


def describe(decision):
    """The gate's evidence, for the console line: a probability (d1) or the rule that fired."""
    if "p_alert" in decision:
        return f"p_alert={decision['p_alert']:.3f}"
    return f"rule: {decision['reason']}"


def run_action(name, decision):
    """Run an action only if it is on the allowlist. Refusals are returned, not raised."""
    if name not in ALLOWED_ACTIONS:
        return f"refused:{name}"
    if name == "log_alert":
        print(f"  ALERT category={decision['category']} {describe(decision)}", flush=True)
    return name


def build_prompt(obs, decision):
    # Only stable decision fields go in the prompt; gate_ms would make every prompt unique by accident.
    d = {k: decision[k] for k in ("p_alert", "category", "severity", "reason") if k in decision}
    return ("Explain this alert to an operator in one sentence. "
            f"Observation: {json.dumps(obs)}. Decision: {json.dumps(d)}.")


def explain(lfm, obs, decision, max_tokens, stable_prompt):
    """One capped sentence. The client tags the prompt, rejects zero-token or empty replies, retries once,
    and returns errors as data. LFM3-1.7B reasons by default, so sentence() closes the reasoning block."""
    r = lfm.sentence(build_prompt(obs, decision), system=SYSTEM_LINE, max_tokens=max_tokens,
                     unique=not stable_prompt)
    return {k: r[k] for k in ("ok", "text", "tokens", "finish", "ms", "retried", "error")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate", choices=["d1", "rule"], default="d1",
                    help="d1: d1-2B through Transformers (needs the d1 venv and snapshot). "
                         "rule: temperature limits in code (no d1, torch, or venv)")
    ap.add_argument("--model-dir", default="~/models/d1-2B", help="d1 snapshot (--gate d1)")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="--gate d1: p_alert that triggers log_alert (example value; tune on labeled states)")
    ap.add_argument("--rule-temp-c", type=float, default=70.0,
                    help="--gate rule: alert at or above this temperature (example value; set from your readings)")
    ap.add_argument("--rule-rise-c", type=float, default=8.0,
                    help="--gate rule: alert when the one-minute rise reaches this (example value)")
    ap.add_argument("--server", default="http://127.0.0.1:18181")
    ap.add_argument("--llm", default="LiquidAI/LFM3-1.7B-GGUF:Q4_0")
    ap.add_argument("--iterations", type=int, default=0, help="0 = run until Ctrl-C")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds to wait between iterations")
    ap.add_argument("--max-explain-tokens", type=int, default=80)
    ap.add_argument("--sensor-mode", choices=["board", "simulated", "fixed"], default="board",
                    help="board: the board's thermal zones (default). simulated: random states. "
                         "fixed: one hot state (for tests)")
    ap.add_argument("--stable-prompt", action="store_true",
                    help="diagnostics only: repeat initial raw prompts without request tags")
    ap.add_argument("--log", default="agent_log.jsonl")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    telemetry = None
    if args.sensor_mode == "board":
        try:
            telemetry = BoardTelemetry()
        except RuntimeError as e:
            sys.exit(f"{e}. Use --sensor-mode simulated on a machine without thermal zones.")

    lfm = LFM(args.server, args.llm, timeout=EXPLAIN_TIMEOUT_S)
    if not lfm.ready():
        sys.exit(f"no GenieX server at {args.server}. In a separate terminal, from the repo root: "
                 "bash skills/iq9-geniex-lfm/scripts/serve.sh run")

    if args.gate == "d1":
        d1_decide, gate_info = load_d1(os.path.expanduser(args.model_dir))

        def gate(obs):
            return d1_decide(obs, args.threshold)
    else:
        gate_info = (f"rule (soc_temp_c >= {args.rule_temp_c} C, or a one-minute rise >= {args.rule_rise_c} C); "
                     "no d1")

        def gate(obs):
            return rule_decide(obs, args.rule_temp_c, args.rule_rise_c)

    print(f"gate:        {gate_info}", flush=True)
    print(f"generator:   {args.llm} via {args.server}", flush=True)
    print(f"sensors:     {args.sensor_mode}" + (f" ({len(telemetry.zones)} thermal zones)" if telemetry else ""),
          flush=True)
    print(f"log:         {os.path.abspath(args.log)}", flush=True)

    stop = {"flag": False}

    def _stop(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    rng = random.Random(args.seed)
    counts = {"iterations": 0, "alerts": 0, "explanations_ok": 0, "explain_retries": 0,
              "explain_errors": 0, "sensor_errors": 0, "decision_errors": 0}
    i = 0
    with open(args.log, "a") as log:

        def write(rec):
            log.write(json.dumps(rec) + "\n")
            log.flush()

        def more():
            return not stop["flag"] and (args.iterations == 0 or i < args.iterations)

        while more():
            t_loop = time.perf_counter()
            rec = {"t": now_iso(), "iteration": i}
            # A monitor logs a failed read or decision as data and keeps running.
            try:
                stage = "sensor"
                rec["obs"] = obs = read_sensors(args.sensor_mode, rng, telemetry)
                stage = "decision"
                rec["decision"] = decision = gate(obs)
            except Exception as e:  # noqa: BLE001
                rec["error"] = f"{stage} failed: {type(e).__name__}: {e}"[:300]
                write(rec)
                counts[f"{stage}_errors"] += 1
                print(f"[{i}] {rec['error']}", flush=True)
                i += 1
                if more():
                    time.sleep(args.interval)
                continue

            action = choose_action(decision)
            rec["action"] = run_action(action, decision)
            rec["explanation"] = None
            if action == "log_alert":
                rec["explanation"] = explain(lfm, obs, decision, args.max_explain_tokens, args.stable_prompt)
            rec["loop_ms"] = round((time.perf_counter() - t_loop) * 1000, 1)
            write(rec)

            counts["iterations"] += 1
            counts["alerts"] += decision["alert"]
            ex = rec["explanation"]
            if ex:
                counts["explanations_ok"] += ex["ok"]
                counts["explain_retries"] += ex["retried"]
                counts["explain_errors"] += ex["error"] is not None
            print(f"[{i}] {describe(decision)} action={action} "
                  f"gate={decision['gate_ms'] / 1000:.1f}s loop={rec['loop_ms'] / 1000:.1f}s"
                  + (f" explain_tokens={ex['tokens']}{' (retried)' if ex['retried'] else ''}" if ex else ""),
                  flush=True)
            i += 1
            if more():
                time.sleep(args.interval)

    print("summary: " + json.dumps(counts), flush=True)


if __name__ == "__main__":
    main()
