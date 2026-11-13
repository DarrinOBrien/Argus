# Example: always-on local agent

The loop from [`docs/developer-guide.md` §8](../../docs/developer-guide.md#8-building-an-always-on-agent), runnable. Every iteration reads the board's own telemetry, runs a decision gate, takes an allowlisted action, explains alerts with the generator, and writes one JSON line to a log.

Script: [`always_on_agent.py`](always_on_agent.py). Standard library only with `--gate rule`; `--gate d1` adds the d1 venv (`transformers`, `torch`, `pillow`).

```
observe ─→ decide (rule, or d1-2B on the CPU) ─→ act (allowlist) ─→ explain (LFM3-1.7B, NPU, only on alerts) ─→ log
   ▲                                                                                                          │
   └────────────────────────────────────────── wait --interval seconds ───────────────────────────────────────┘
```

This is a reference design, not a requirement. d1 is optional, and other LFM3-family models are welcome after verifying runtime/NPU support and task behavior. External sensors are optional and not supplied.

## Prerequisites

- A GenieX server on `127.0.0.1:18181` with `LiquidAI/LFM3-1.7B-GGUF:Q4_0` in the cache:

  ```bash
  bash skills/iq9-geniex-lfm/scripts/serve.sh run  # repo root, separate terminal
  ```

- Only for `--gate d1`: the d1-2B snapshot at `~/models/d1-2B` and the venv from [`examples/system-one-decision`](../system-one-decision/README.md).

## Run

```bash
cd examples/always-on-agent

# Rule gate: no d1, torch, or venv
python3 always_on_agent.py --gate rule --sensor-mode simulated --iterations 8 --interval 1 --log test.jsonl  # smoke test
python3 always_on_agent.py --gate rule                      # board telemetry, runs until Ctrl-C

# d1 gate (the default)
~/.venvs/d1/bin/python always_on_agent.py --iterations 8 --interval 1 --log test-d1.jsonl
```

| Option | Default | Meaning |
|---|---|---|
| `--gate` | `d1` | `d1`: d1-2B through Transformers on the CPU. `rule`: temperature limits in code, with no d1 dependencies |
| `--rule-temp-c`, `--rule-rise-c` | 70, 8 | `--gate rule`: alert at or above this temperature, or when the one-minute rise reaches this. Example values; set them from your own readings |
| `--threshold` | 0.5 | `--gate d1`: `p_alert` that triggers `log_alert`. An example value; tune it on labeled states |
| `--iterations` | 0 (forever) | number of loop iterations; 0 runs until Ctrl-C |
| `--interval` | 5 | seconds to wait between iterations |
| `--max-explain-tokens` | 80 | cap on the explanation; tune and verify usable answers for your task |
| `--sensor-mode` | `board` | `board` reads the SoC thermal zones (default). `simulated` makes random states and `fixed` repeats one hot state; both are for tests. All three return the same keys |
| `--stable-prompt` | off | diagnostics only: intentionally repeat raw prompts without request tags |
| `--log` | `agent_log.jsonl` | JSONL log, appended to |
| `--model-dir`, `--server`, `--llm` | `~/models/d1-2B`, `http://127.0.0.1:18181`, `LiquidAI/LFM3-1.7B-GGUF:Q4_0` | where the models are |

Ctrl-C finishes the current iteration, writes its log line, and prints a summary.

## What the code does

| Step | Function | Notes |
|---|---|---|
| Observe | `read_sensors()`, `BoardTelemetry` | Reads the board's thermal zones from `/sys/class/thermal`. The observation is the hottest zone now, the same value about one minute ago, and the 1-minute CPU load. No extra hardware. |
| Decide | `rule_decide()`, or `load_d1()` | The rule alerts on a temperature limit or a one-minute rise and records which one fired in `reason`. d1 answers three typed questions through `system_one()` and returns `p_alert`, `category`, and `severity`. Both return `alert` and `gate_ms`. |
| Act | `choose_action()`, `run_action()` | Policy picks `log_alert` when the gate alerts, otherwise `no_op`. `run_action()` runs an action only if it is in `ALLOWED_ACTIONS`; otherwise it returns `refused:<name>`, which is logged. |
| Explain | `explain()`, `build_prompt()` | Only for `log_alert`. Sends one capped request through the shared [`lfm_client.py`](../../skills/iq9-geniex-lfm/scripts/lfm_client.py). |
| Log | `main()` | One flushed JSON object per iteration, including failed reads and failed decisions. |

### Allowlist

`ALLOWED_ACTIONS = ("no_op", "log_alert")`. `log_alert` prints an alert line and logs it. The policy in this example only ever produces allowlisted actions, so a refusal can't happen yet. The check is in `run_action()` so that any future action has to be added to the list on purpose.

### Explanations

LFM3-1.7B reasons by default, so the agent uses the client's `sentence()`: a raw completion with the reasoning block already closed. That gives direct answers but does not guarantee correctness or carry over to other models.

The client caps the request, tags the prompt so it is unique **before the first call**, rejects zero-token and empty replies, and retries once. A reply that is still unusable is logged with `ok: false` and an `error`, and the loop continues without restarting the server. `--stable-prompt` turns the tags off, for diagnostics only: identical raw prompts can return continuing commentary instead of a fresh answer.

### Errors are data

A failed sensor read or a gate that raises is written to the log as `{"iteration": ..., "error": "sensor failed: ..."}` (or `decision failed`), counted in the summary, and the loop carries on.

With `--gate d1`, the gate loads the pinned local snapshot with `local_files_only=True` and the offline settings. Nothing is downloaded or installed at runtime in either mode.

## Log format

The shape of one alert line with `--gate rule` (values are illustrative):

```json
{"t": "2026-10-12T20:04:10.123+00:00", "iteration": 4,
 "obs": {"soc_temp_c": 71.5, "soc_temp_c_1min_ago": 58.0, "cpu_load_1min": 0.5, "hottest_zone": "<zone type>"},
 "decision": {"gate": "rule", "alert": true, "category": "thermal",
              "reason": "temperature 71.5 C is at or above the 70.0 C limit; rose 13.5 C in one minute (limit 8.0 C)",
              "gate_ms": 0.0},
 "action": "log_alert",
 "explanation": {"ok": true, "text": "...", "tokens": 41, "finish": "stop", "ms": 7092.6,
                 "retried": false, "error": null},
 "loop_ms": 7100.0}
```

With `--gate d1`, `decision` holds `"gate": "d1"`, `p_alert`, `alert`, `category`, `severity`, and `gate_ms` instead of `reason`. `explanation` is `null` unless the action was `log_alert`. Each line is written and flushed before the next iteration, so the file is safe to read while the loop runs.

## Limits

- **The limits and threshold are examples.** Set `--rule-temp-c` and `--rule-rise-c` from the range your board actually shows. For d1, calibrate `--threshold` on labeled data from your own signal; for a plain thermal alarm, the rule is usually the safer choice.
- **Pass the direction of change explicitly.** If the prompt gives values but not the trend, the LFM can describe a falling reading as rising. The rule's `reason` carries the rise; add the same to your own prompts.
- **Explanations describe the gate's decision. They don't check it.** If the gate is wrong, the explanation repeats the error.
- **Restart is not automatic.** If a reply is still empty after the retry, restart `geniex serve` by hand.
- **Keep d1 and the generator sequential.** d1 slows down substantially while the generator runs; see the [reference-stack rules](../../README.md#rules-for-the-reference-stack).
- **Offline settings are not a network-off test.** Use [`docs/offline-readiness.md`](../../docs/offline-readiness.md) for the rehearsal.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `no GenieX server at ...` | Start `serve.sh run` in a separate terminal and check `geniex list` for the model. |
| `--gate d1 needs the d1 venv` | Run with `~/.venvs/d1/bin/python`, or use `--gate rule`. |
| `d1 snapshot not found` | Copy the pinned snapshot from the USB model drive, or use `--gate rule`; see [`examples/system-one-decision`](../system-one-decision/README.md). |
| The rule never alerts, or always alerts | The example limits do not fit your board's range. Watch `obs.soc_temp_c` in the log and set `--rule-temp-c` / `--rule-rise-c`. |
| `ok: false` or `error` set on an explanation | Read the message. Timeouts, HTTP errors, and unusable replies are logged and the loop continues. Restart your server if it persists. |
| First alert or post-idle request is slower | Model loading or idle unloading. The default keepalive is 300 s (`serve.sh` sets 1800 s); measure your model's reload time. |
