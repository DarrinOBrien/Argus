#!/usr/bin/env python3
"""Always-on local agent: observe -> decide -> act -> explain -> log.

Each iteration:
  1. observe   read the board's own telemetry (SoC thermal zones, CPU load) by default
  2. decide    d1-2B gate (Path A: transformers, CPU, fp32) returns p_alert, category, severity
  3. act       choose an action; only allowlisted actions run, anything else is refused
  4. explain   only when the action is log_alert: LFM3-1.7B (GenieX, NPU) writes one sentence.
               Uses a raw completion with the reasoning block closed, because the chat path
               returns reasoning text (see README).
  5. log       one JSON line per iteration

The loop is sequential, so the gate and the generator never run at the same time. The previous
stack slowed the gate about 1.9x under concurrency; re-measure this stack before changing the design.

Requires: a GenieX server on --server with the --llm model cached, and the d1-2B snapshot
at --model-dir (see examples/system-one-decision/README.md).
"""

import argparse
import collections
import json
import os
import random
import signal
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "system-one-decision"))

import torch  # noqa: E402
from transformers import AutoModel  # noqa: E402
from system_one_example import SENSOR_QUESTIONS  # noqa: E402  (alert, category, severity)

# Only these actions can run. Anything else is refused and logged.
ALLOWED_ACTIONS = ("no_op", "log_alert")
EXPLAIN_TIMEOUT_S = 60
THERMAL_ROOT = "/sys/class/thermal"
HISTORY_S = 300


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class BoardTelemetry:
    """The board's own temperatures from sysfs (IQ-9075: about 36 thermal zones). No extra hardware.

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
    """The loop's observation. 'board' reads the SoC telemetry (default).

    'simulated' returns random states. 'fixed' repeats one hot state (used to test the zero-token retry).
    """
    if mode == "board":
        return telemetry.read()
    if mode == "fixed":
        return {"temp_c": 71.5, "temp_c_1min_ago": 58.0, "motion": "none"}
    if rng.random() < 0.5:
        t = round(rng.uniform(34, 40), 1)
        prev = round(t + rng.uniform(-0.5, 0.5), 1)
        motion = "none"
    else:
        t = round(rng.uniform(65, 80), 1)
        prev = round(rng.uniform(50, 62), 1)
        motion = rng.choice(["none", "sudden 2.1 g spike"])
    return {"temp_c": t, "temp_c_1min_ago": prev, "motion": motion}


def decide(model, obs):
    t0 = time.perf_counter()
    with torch.inference_mode():
        a = model.system_one(json.dumps(obs), SENSOR_QUESTIONS)["answers"]
    return {
        "p_alert": round(a["alert"]["noul"], 4),
        "category": a["category"]["choice"],
        "severity": round(a["severity"]["score"], 3),
        "gate_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def choose_action(decision, threshold):
    return "log_alert" if decision["p_alert"] >= threshold else "no_op"


def run_action(name, decision):
    """Run an action only if it is on the allowlist. Refusals are returned, not raised."""
    if name not in ALLOWED_ACTIONS:
        return f"refused:{name}"
    if name == "log_alert":
        print(f"  ALERT category={decision['category']} severity={decision['severity']} "
              f"p_alert={decision['p_alert']}", flush=True)
    return name


# LFM3-1.7B enables reasoning by default, and a cap can cut the chat reply before the answer. A raw
# completion with an empty <think></think> block already closed asks for the sentence directly. The
# system line and template are the model's ChatML tokens.
SYSTEM_LINE = "You write one-sentence alerts for operators. Reply with the sentence only."
TEMPLATE = ("<|startoftext|><|im_start|>system\n" + SYSTEM_LINE + "<|im_end|>\n"
            "<|im_start|>user\n{USER}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n")


def build_prompt(obs, decision, stable_prompt, tag=None):
    # Only these three decision fields go in the prompt. gate_ms would make every prompt unique by accident.
    d = {k: decision[k] for k in ("p_alert", "category", "severity")}
    p = ("Explain this alert to an operator in one sentence. "
         f"Observation: {json.dumps(obs)}. Decision: {json.dumps(d)}.")
    if not stable_prompt:
        p += f" Time: {now_iso()}."
    if tag:
        p += f" [{tag}]"
    return p


def complete(server, model_name, user_text, max_tokens):
    body = json.dumps({
        "model": model_name,
        "prompt": TEMPLATE.replace("{USER}", user_text),
        "max_tokens": max_tokens,
        "compute": "npu",
        "stream": False,  # one JSON reply per call
    }).encode()
    req = urllib.request.Request(server.rstrip("/") + "/v1/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=EXPLAIN_TIMEOUT_S) as r:
        d = json.load(r)
    choice = d["choices"][0]
    return {
        "text": (choice.get("text") or "").strip(),
        "tokens": d.get("usage", {}).get("completion_tokens", 0),
        "finish": choice["finish_reason"],
        "ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def explain(server, model_name, obs, decision, max_tokens, stable_prompt):
    """One explanation. A zero-token reply
    is retried once with a unique tag. Failures are logged and the loop keeps running."""
    out = {"ok": False, "retried": False, "zero_token_first_try": False,
           "text": None, "tokens": 0, "finish": None, "ms": None, "error": None}
    try:
        r = complete(server, model_name, build_prompt(obs, decision, stable_prompt), max_tokens)
        if r["tokens"] == 0 or not r["text"]:
            out["zero_token_first_try"] = True
            out["retried"] = True
            r = complete(server, model_name,
                         build_prompt(obs, decision, stable_prompt, tag=uuid.uuid4().hex[:8]), max_tokens)
        out.update(text=r["text"] or None, tokens=r["tokens"], finish=r["finish"], ms=r["ms"],
                   ok=r["tokens"] > 0 and bool(r["text"]))
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        out["error"] = f"{type(e).__name__}: {e}"[:200]
    return out


def server_ready(server):
    try:
        with urllib.request.urlopen(server.rstrip("/") + "/v1/models", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-dir", default="~/models/d1-2B")
    ap.add_argument("--server", default="http://127.0.0.1:18181")
    ap.add_argument("--llm", default="LiquidAI/LFM3-1.7B-GGUF:Q4_0")
    ap.add_argument("--iterations", type=int, default=0, help="0 = run until Ctrl-C")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds to wait between iterations")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="p_alert that triggers log_alert (example value; tune on labeled states)")
    ap.add_argument("--max-explain-tokens", type=int, default=80)
    ap.add_argument("--sensor-mode", choices=["board", "simulated", "fixed"], default="board",
                    help="board: the board's thermal zones (default). simulated: random states. "
                         "fixed: one hot state (for tests)")
    ap.add_argument("--stable-prompt", action="store_true",
                    help="leave the timestamp out of explanation prompts (used to test the zero-token retry)")
    ap.add_argument("--log", default="agent_log.jsonl")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    telemetry = None
    if args.sensor_mode == "board":
        try:
            telemetry = BoardTelemetry()
        except RuntimeError as e:
            sys.exit(f"{e}. Use --sensor-mode simulated on a machine without thermal zones.")

    model_dir = os.path.expanduser(args.model_dir)
    if not os.path.isdir(model_dir):
        sys.exit(f"d1 snapshot not found at {model_dir}. See examples/system-one-decision/README.md")
    if not server_ready(args.server):
        sys.exit(f"no GenieX server at {args.server}. Start it with: geniex serve --compute npu")

    model = AutoModel.from_pretrained(model_dir, trust_remote_code=True, dtype=torch.float32)
    model = model.to("cpu").eval()
    print(f"gate loaded: d1-2B fp32 on CPU, threads={torch.get_num_threads()}", flush=True)
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
    counts = {"iterations": 0, "alerts": 0, "explanations_ok": 0, "zero_token_retries": 0,
              "explain_errors": 0, "sensor_errors": 0}
    i = 0
    with open(args.log, "a") as log:
        while not stop["flag"] and (args.iterations == 0 or i < args.iterations):
            t_loop = time.perf_counter()
            try:
                obs = read_sensors(args.sensor_mode, rng, telemetry)
            except RuntimeError as e:
                # Degrade gracefully: log the failed read and keep the loop running.
                rec = {"t": now_iso(), "iteration": i, "error": f"sensor read failed: {e}"}
                log.write(json.dumps(rec) + "\n")
                log.flush()
                counts["sensor_errors"] += 1
                print(f"[{i}] sensor read failed: {e}", flush=True)
                i += 1
                time.sleep(args.interval)
                continue

            decision = decide(model, obs)
            decision["alert"] = decision["p_alert"] >= args.threshold
            action = choose_action(decision, args.threshold)
            rec = {"t": now_iso(), "iteration": i, "obs": obs, "decision": decision}
            rec["action"] = run_action(action, decision)
            rec["explanation"] = None
            if action == "log_alert":
                rec["explanation"] = explain(args.server, args.llm, obs, decision,
                                             args.max_explain_tokens, args.stable_prompt)
            rec["loop_ms"] = round((time.perf_counter() - t_loop) * 1000, 1)
            log.write(json.dumps(rec) + "\n")
            log.flush()

            counts["iterations"] += 1
            counts["alerts"] += decision["alert"]
            ex = rec["explanation"]
            if ex:
                counts["explanations_ok"] += ex["ok"]
                counts["zero_token_retries"] += ex["zero_token_first_try"]
                counts["explain_errors"] += ex["error"] is not None
            print(f"[{i}] p_alert={decision['p_alert']:.3f} action={action} "
                  f"gate={decision['gate_ms'] / 1000:.1f}s loop={rec['loop_ms'] / 1000:.1f}s"
                  + (f" explain_tokens={ex['tokens']}{' (retried)' if ex['retried'] else ''}" if ex else ""),
                  flush=True)
            i += 1
            if not stop["flag"] and (args.iterations == 0 or i < args.iterations):
                time.sleep(args.interval)

    print("summary: " + json.dumps(counts), flush=True)


if __name__ == "__main__":
    main()
