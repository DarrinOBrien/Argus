# Example: always-on local agent

The loop from [`docs/developer-guide.md` §8](../../docs/developer-guide.md#8-building-an-always-on-agent), runnable. Every iteration reads the board's own telemetry, asks the decision gate, takes an allowlisted action, explains alerts with the generator, and writes one JSON line to a log.

Script: [`always_on_agent.py`](always_on_agent.py). Standard library plus the d1 venv (`transformers`, `torch`, `pillow`).

```
observe ─→ decide (d1-2B, CPU) ─→ act (allowlist) ─→ explain (LFM3-1.7B, NPU, only on alerts) ─→ log
   ▲                                                                                              │
   └──────────────────────────────────── wait --interval seconds ─────────────────────────────────┘
```

This is a reference d1/LFM3-1.7B design, not a requirement to use those models. d1 is optional and other LFM3-family models are welcome after verifying runtime/NPU support and task behavior. External sensors are optional and not supplied.

The steps run in sequence: d1 slows down substantially while the generator runs, so keep them [one at a time](../../README.md#rules-for-the-reference-stack).

## Prerequisites

- The d1-2B snapshot at `~/models/d1-2B` and the venv from [`examples/system-one-decision`](../system-one-decision/README.md).
- A GenieX server on `127.0.0.1:18181` with `LiquidAI/LFM3-1.7B-GGUF:Q4_0` in the cache:

  ```bash
  bash skills/iq9-geniex-lfm/scripts/serve.sh run  # repo root, separate terminal
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
| `--max-explain-tokens` | 80 | cap on the explanation; tune and verify usable answers for your task |
| `--sensor-mode` | `board` | `board` reads the SoC thermal zones (default). `simulated` makes random states and `fixed` repeats one hot state. Both are for tests |
| `--stable-prompt` | off | diagnostics only: intentionally repeat initial raw prompts without request tags |
| `--log` | `agent_log.jsonl` | JSONL log, appended to |
| `--model-dir`, `--server`, `--llm` | `~/models/d1-2B`, `http://127.0.0.1:18181`, `LiquidAI/LFM3-1.7B-GGUF:Q4_0` | where the models are |

Ctrl-C finishes the current iteration, writes its log line, and prints a summary.

## What the code does

| Step | Function | Notes |
|---|---|---|
| Observe | `read_sensors()`, `BoardTelemetry` | Reads the board's thermal zones from `/sys/class/thermal` (about 60 zones). The observation is the hottest zone now, the same value about one minute ago, and the 1-minute CPU load. No extra hardware. |
| Decide | `decide()` | d1-2B through `system_one()`, the same three questions as the sensor example. Returns `p_alert`, `category`, `severity`, and `gate_ms`. |
| Act | `choose_action()`, `run_action()` | Policy picks `log_alert` (when `p_alert >= threshold`) or `no_op`. `run_action()` runs an action only if it is in `ALLOWED_ACTIONS`, otherwise it returns `refused:<name>` and logs it. |
| Explain | `explain()`, `complete()` | Only for `log_alert`. Retries once on zero-token or empty-answer output (see below). Errors are logged, and the loop keeps running. |
| Log | `main()` | One JSON object per iteration. |

### Allowlist

`ALLOWED_ACTIONS = ("no_op", "log_alert")`. `log_alert` prints an alert line and logs it. The policy in this example only ever produces allowlisted actions, so a refusal can't happen yet. The check is in `run_action()` so that any future action has to be added to the list on purpose.

### Explanations: why a raw completion

LFM3-1.7B reasons by default. The agent sends a raw completion with the reasoning block already closed, which gives direct answers but does not guarantee correctness or carry over to other models:

```
<|im_start|>system ... <|im_end|>
<|im_start|>user ... <|im_end|>
<|im_start|>assistant
<think>

</think>

```

The template uses LFM3's ChatML tokens. Record its output and latency on the board before the demo.

### Unusable replies and repeated prompts

Replies can report tokens and still be empty or reasoning-only, and identical raw prompts can return continuing commentary.

Normal explanation prompts get a unique event tag **before the first call**. Zero tokens or empty text trigger one tagged retry. Persistent failure gets `ok: false` and an error; the loop continues without automatically restarting the server. `zero_token_first_try` means actual zero usage; `empty_response_first_try` separately records an empty answer. `--stable-prompt` is diagnostics only.

The gate loads the pinned local snapshot with `local_files_only=True` and offline/telemetry settings; no model downloads or installs occur at runtime.

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

## Limits

- **Calibrate before trusting alerts.** `--threshold 0.5` is an example value, not a tuned one. Calibrate on labeled data from your own signal, or use a rule; for a thermal alarm on board temperature readings, a rule is usually the safer choice.
- **Pass the direction of change explicitly.** If the prompt gives values but not the trend, the LFM can describe a falling reading as rising. Include the change and its sign.
- **Explanations describe the gate's decision. They don't check it.** If the gate is wrong, the explanation repeats the error.
- **Keep prompts unique.** The prompt uses request tags; do not remove them for normal runs. Tags do not guarantee answer correctness.
- **Restart is not automatic.** If a reply is still empty after the retry, restart `geniex serve` by hand.
- **Offline settings are not a network-off test.** Use [`docs/offline-readiness.md`](../../docs/offline-readiness.md) for the rehearsal.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `no GenieX server at ...` | Start `geniex serve --compute npu` and check `geniex list` for the model. |
| `d1 snapshot not found` | Inspect existing local snapshots and ask before `fetch_d1.py`; see [`examples/system-one-decision`](../system-one-decision/README.md). |
| `ok: false` in the log | Read the error and first-try flags. They do not establish what happened on the retry. Safely relaunch only the owned server if persistent failure warrants it. |
| `error` set on an explanation | Read the message. Timeouts and HTTP errors are logged and the loop continues. |
| First alert or post-idle request is slower | Model loading/idle unloading may contribute. Default keepalive is 300 s; measure the selected model's reload time. |
