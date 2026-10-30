# Example: always-on local agent

The loop from [`docs/developer-guide.md` §8](../../docs/developer-guide.md#8-building-an-always-on-agent), runnable. Every iteration reads the board's own telemetry, asks the decision gate, takes an allowlisted action, explains alerts with the generator, and writes one JSON line to a log.

Script: [`always_on_agent.py`](always_on_agent.py). Standard library plus the d1 venv (`transformers`, `torch`, `pillow`).

```
observe ─→ decide (d1-2B, CPU) ─→ act (allowlist) ─→ explain (LFM3-1.7B, NPU, only on alerts) ─→ log
   ▲                                                                                              │
   └──────────────────────────────────── wait --interval seconds ─────────────────────────────────┘
```

The steps run in sequence. The gate and the generator never run at the same time. Running them together slows the gate about 1.9× (measured; see [`docs/developer-guide.md` §8](../../docs/developer-guide.md#8-building-an-always-on-agent)).

## Prerequisites

- The d1-2B snapshot at `~/models/d1-2B` and the venv from [`examples/system-one-decision`](../system-one-decision/README.md).
- A GenieX server on `127.0.0.1:18181` with `LiquidAI/LFM3-1.7B-GGUF:Q4_0` in the cache:

  ```bash
  geniex serve --compute npu        # keep this running in another terminal
  ```

## Run

```bash
cd examples/always-on-agent
~/.venvs/d1/bin/python always_on_agent.py                  # runs until Ctrl-C
~/.venvs/d1/bin/python always_on_agent.py --iterations 8 --interval 1 --log test.jsonl
```

| Option | Default | Meaning |
|---|---|---|
| `--iterations` | 0 (forever) | number of loop iterations; 0 runs until Ctrl-C |
| `--interval` | 5 | seconds to wait between iterations |
| `--threshold` | 0.5 | `p_alert` that triggers `log_alert`. An example value; tune it on labeled states |
| `--max-explain-tokens` | 80 | cap on the explanation. Replies take about 20–50 tokens |
| `--sensor-mode` | `board` | `board` reads the SoC thermal zones (default). `simulated` makes random states and `fixed` repeats one hot state. Both are for tests |
| `--stable-prompt` | off | leave the timestamp out of explanation prompts (for testing the zero-token retry) |
| `--log` | `agent_log.jsonl` | JSONL log, appended to |
| `--model-dir`, `--server`, `--llm` | `~/models/d1-2B`, `http://127.0.0.1:18181`, `LiquidAI/LFM3-1.7B-GGUF:Q4_0` | where the models are |

Ctrl-C finishes the current iteration, writes its log line, and prints a summary.

## What the code does

| Step | Function | Notes |
|---|---|---|
| Observe | `read_sensors()`, `BoardTelemetry` | Reads the board's thermal zones from `/sys/class/thermal` (about 60 zones). The observation is the hottest zone now, the same value about one minute ago, and the 1-minute CPU load. No extra hardware. |
| Decide | `decide()` | d1-2B through `system_one()`, the same three questions as the sensor example. Returns `p_alert`, `category`, `severity`, and `gate_ms`. |
| Act | `choose_action()`, `run_action()` | Policy picks `log_alert` (when `p_alert >= threshold`) or `no_op`. `run_action()` runs an action only if it is in `ALLOWED_ACTIONS`, otherwise it returns `refused:<name>` and logs it. |
| Explain | `explain()`, `complete()` | Only for `log_alert`. Retries once on a zero-token reply (see below). Errors are logged, and the loop keeps running. |
| Log | `main()` | One JSON object per iteration. |

### Allowlist

`ALLOWED_ACTIONS = ("no_op", "log_alert")`. `log_alert` prints an alert line and logs it. The policy in this example only ever produces allowlisted actions, so a refusal can't happen yet. The check is in `run_action()` so that any future action has to be added to the list on purpose.

### Explanations: why a raw completion

LFM3-1.7B reasons by default. The agent sends a raw completion with the reasoning block already closed; verify this shortcut on the board:

```
<|im_start|>system ... <|im_end|>
<|im_start|>user ... <|im_end|>
<|im_start|>assistant
<think>

</think>

```

The template uses LFM3's ChatML tokens. Record its output and latency on the board before the demo.

### Zero-token replies

On GenieX v0.8.0, repeated identical requests sometimes return HTTP 200 with no tokens (see [`docs/runtimes.md`](../../docs/runtimes.md#known-gap-zero-token-responses-on-v080)). The explanation prompt includes a timestamp, so each prompt is unique. If a reply still has no tokens, the agent retries once with a random tag. A reply that is still empty is logged with `ok: false`, and the loop continues. The agent does not restart the server.

## Log format

```json
{"t": "2026-10-12T20:04:10.123+00:00", "iteration": 4,
 "obs": {"temp_c": 39.0, "temp_c_1min_ago": 38.6, "motion": "none"},
 "decision": {"p_alert": 0.513, "category": "thermal", "severity": 1.311, "gate_ms": 4700.0, "alert": true},
 "action": "log_alert",
 "explanation": {"ok": true, "retried": false, "zero_token_first_try": false, "text": "...",
                 "tokens": 41, "finish": "stop", "ms": 7092.6, "error": null},
 "loop_ms": 11800.0}
```

`explanation` is `null` unless the action was `log_alert`. Each line is written and flushed before the next iteration, so the file is safe to read while the loop runs.

## Historical LFM2.5/d1-3B measurements on the IQ-9075

These v0.8.0 results are a regression baseline, not LFM3/d1-2B measurements. Re-run the same cases before the demo.

| Run | What it tested | Result |
|---|---|---|
| A (8 iterations, simulated sensors, seed 7) | basic loop | 3 alerts, 3 explanations, all OK, 32–41 tokens. First explanation after server start took 7.1 s (includes the model load). Later explanations 1.6–2.0 s. |
| B (14 iterations, fixed hot state, `--stable-prompt`) | identical prompts, zero-token retry | 14 of 14 explanations OK. 7 first replies had zero tokens. The tagged retry fixed all 7. |
| C (12 iterations, fixed hot state, default timestamps) | control | 12 of 12 OK on the first try. No zero-token replies. |
| D (heat-up: 2 min idle, 4 min generation load, then cooldown, 75 iterations, board telemetry) | Whether the board's own temperature can drive the loop | The hottest zone rose from about 57 °C to about 79 °C under load, and fell to about 64 °C after 9 minutes. The gate alerted on 53 of 75 iterations, and its `p_alert` did not follow temperature (r = −0.08). Explanations were fluent, but one said a falling temperature had risen. Gate time rose from 4.6 s to 8.6 s under load. |
| E (gate on board-style states, two key formats, flat and rising) | Whether d1 responds to temperature | Neither key format gives a steady response. With the calibration-style keys, a flat 40 °C scored 0.62 and flat 50 to 70 °C scored 0.06–0.17. With board keys (`soc_temp_c`), every state scored 0.44–0.94. |
| Offline env (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`) | no Hub access needed | 2 iterations ran. This is not a network-off test. |

Timing: the gate takes about 4.1 s per iteration. An iteration with an explanation takes about 5–6 s warm. The loop in run C had a median gate time of 4.1 s.

## Limits

- **The gate does not track board temperature.** On the board's own readings (run D and table E above), the d1 gate alerted on most states and did not follow temperature. Its calibration does not carry over to these readings. Do not use the default threshold on board data. Calibrate on labeled board data first, or use a rule for the thermal alarm.
- **Explanations can state the wrong direction.** In run D, the LFM described a falling temperature as having risen. The prompt gives the values but not the direction. Pass the change and its sign explicitly.
- **The threshold is untuned.** `--threshold 0.5` is an example value. The gate fired on 3 of 8 simulated states, and a 39 °C reading got `p_alert` 0.51 in run A.
- **Explanations describe the gate's decision. They don't check it.** If the gate is wrong, the explanation repeats the error. Run A's explanation called 39 °C "high".
- **The explanation includes the timestamp.** The model echoes "at 2026-10-12T20:04:10 UTC". Remove the `Time:` line from `build_prompt()` if that isn't wanted. Removing it reintroduces the zero-token risk, so keep a unique tag instead.
- **Restart is not automatic.** If a reply is still empty after the retry, restart `geniex serve` by hand.
- **Not tested with the network off.** Use [`docs/offline-readiness.md`](../../docs/offline-readiness.md) for the rehearsal.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `no GenieX server at ...` | Start `geniex serve --compute npu` and check `geniex list` for the model. |
| `d1 snapshot not found` | Run `fetch_d1.py` as described in [`examples/system-one-decision`](../system-one-decision/README.md). |
| `ok: false` in the log, with `zero_token_first_try: true` | Both the first try and the retry returned no tokens. Restart `geniex serve`. |
| `error` set on an explanation | Read the message. Timeouts and HTTP errors are logged and the loop continues. |
| First alert takes about 5 s longer | The model loads on the first request, and idle unloading brings that back after 300 s (see [`docs/runtimes.md`](../../docs/runtimes.md#server-lifecycle-model-loading-and-idle-unloading)). |
