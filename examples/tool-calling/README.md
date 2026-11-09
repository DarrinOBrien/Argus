# Example: tool calling with LFM3-1.7B

The model chooses a tool and fills in its arguments. The code does everything else. It checks the arguments against a schema, runs only tools on the allowlist, applies its own rule before any write action, runs the tool, and logs each step. The code, not the model, decides whether something happens.

Script: [`tool_calling.py`](tool_calling.py). Standard library only, so no venv is needed.

```
prompt ─→ LFM3-1.7B (GenieX, NPU) ─→ tool_calls ─→ validate ─→ allowlist ─→ policy ─→ run ─→ result back to the model
                    ▲                                                                                      │
                    └─────────────────────────────── up to --max-steps turns ───────────────────────────────┘
```

## Prerequisites

```bash
geniex list  # inspect cache and existing local weights; ask before any pull/import
bash skills/iq9-geniex-lfm/scripts/serve.sh run  # repo root, separate terminal
```

LFM3-1.7B is the reference default, not a required model. Choose another cached model only after verifying its template, runtime/NPU support, and tools behavior. External sensors are optional and not provided; these read tools use internal board readings.

## Run

```bash
cd examples/tool-calling
python3 tool_calling.py --self-test                # validator and allowlist checks; no server needed
python3 tool_calling.py                            # default prompt: temperature and CPU load
python3 tool_calling.py --prompt "Is the board too hot? If so, log a note for the operator."
```

| Option         | Default                                   | Meaning                                             |
| -------------- | ----------------------------------------- | --------------------------------------------------- |
| `--prompt`     | a question about temperature and CPU load | user message                                        |
| `--model`      | `LiquidAI/LFM3-1.7B-GGUF:Q4_0`            | any cached model whose chat template supports tools |
| `--server`     | `http://127.0.0.1:18181`                  | GenieX server                                       |
| `--max-steps`  | 4                                         | model turns before it stops                         |
| `--max-tokens` | 128                                       | cap per turn, sent as `max_completion_tokens`       |
| `--log`        | `tool_calls.jsonl`                        | every model turn and every tool call, appended      |
| `--notes`      | `operator_notes.jsonl`                    | where `log_note` writes                             |

## Tools

| Tool           | Arguments                                           | Kind  | Runs when                                                                                                            |
| -------------- | --------------------------------------------------- | ----- | -------------------------------------------------------------------------------------------------------------------- |
| `read_thermal` | none                                                | read  | always. Reads the SoC zones in `/sys/class/thermal` and returns the hottest one.                                     |
| `read_system`  | none                                                | read  | always. Returns the load averages, CPU count, and memory.                                                            |
| `log_note`     | `text: string`, `severity: info\|warning\|critical` | write | only after `read_thermal` in the same run, and only if that reading is ≥ `NOTE_MIN_TEMP_C` (70 °C, an example value) |

Anything else is refused. A refusal goes back to the model as the tool result (`{"error": ...}`), so it can correct itself. It is also logged with `executed: false`.

## How it works

GenieX handles the tool-call format. You send the standard OpenAI `tools` array to `/v1/chat/completions`; the expected reply carries `message.tool_calls` with `finish_reason: "tool_calls"`. The self-test covers code-side guard cases, including empty-answer handling; revised code and LFM3 parsing still need a bounded IQ-9075 integration run.

| Step           | Function                         | Notes                                                                                                                                                                                                                                |
| -------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Ask            | `chat()`                         | Sends `tools`, `max_completion_tokens`, `compute: npu`, and `stream: false`. The system prompt includes a random request tag.                                                                                                        |
| Unusable reply | `response_error()`, `is_empty()` | Rejects zero/missing usage, empty/reasoning-only answers even with positive tokens, and malformed tool envelopes. Valid calls need no text. Retries once, then logs failure without executing that turn. HTTP errors are logged too. |
| Validate       | `validate()`                     | A small JSON-schema check: types, `required`, `enum`, and `additionalProperties: false`.                                                                                                                                             |
| Allowlist      | `run_tool()`                     | Unknown tool names are refused.                                                                                                                                                                                                      |
| Policy         | `check_policy()`                 | Write tools need a rule that passes in code. Read-only tools always pass.                                                                                                                                                            |
| Run and log    | `run_tool()`, `run()`            | Results go back as `role: tool` messages. The final summary lists the actions that ran, taken from the code's own record.                                                                                                            |

## What to plan for

Small models make predictable tool-calling mistakes. They are why the code has the validator, the policy, and the summary:

* **Over-alerting.** Given a reading and a choice between alerting and doing nothing, a small model may alert on almost everything, and its alert text can make up numbers. Do not let the model decide whether a write action runs. Use a rule, or the d1 gate after you calibrate it.
* **Claiming actions it never took.** The final answer can say "an alert has been logged" with no `log_note` call. Report actions from the code's own record; never take the model's word for them.
* **Bad arguments.** Calls can add made-up arguments or leave required ones out. Validate every call.
* **Skipping the check.** The model can call a write tool in the same turn as the read it depends on, or skip the tool and answer directly. The code runs multiple calls in order, so a `log_note` after `read_thermal` is checked against the new reading. Keep the prompt specific and the tool list short (3–5 tools).

Measure your own model's behavior on your prompts before the demo.

## Log format

One JSON line per model turn and per tool call, then a summary line:

```json
{"t": "...", "step": 0, "ms": 487.0, "retried": false, "finish": "tool_calls", "tokens": 10, "content": null, "tool_calls": [{"name": "read_thermal", "arguments": "{}"}]}
{"t": "...", "step": 0, "tool": "read_thermal", "arguments": "{}", "executed": true, "result": {"hottest_zone": "nsp-0-2-1-thermal", "temp_c": 56.1, "zones_read": 62}}
{"t": "...", "summary": true, "prompt": "...", "final": "The board is currently at 56.1 degrees Celsius...", "executed": ["read_thermal", "read_system"]}
```

## Adding a tool

1. Add its schema to `TOOLS`. Set `additionalProperties: false`, and use `enum` wherever the values are fixed.
2. Add its implementation to `run_tool()`.
3. If it changes anything, leave it out of `READ_ONLY` and add a rule for it in `check_policy()`. A write tool with no rule is refused.
4. Add a case to `self_test()`, then run `--self-test`.
5. Test it on the board with the network off.

## Troubleshooting

| Symptom                                                             | Fix                                                                                                                                              |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `no GenieX server at ...`                                           | Start `geniex serve --compute npu`.                                                                                                              |
| HTTP 404 or 500 naming the model                                    | Inspect `geniex list`, local weights, disk, and server logs. Ask before any import/download; an HTTP error is not proof the weights are missing. |
| `tool_calls` always empty                                           | Check that the request sends `tools`, and that the model's chat template supports tools.                                                         |
| `{"error": "no readable thermal zones ..."}`                        | You are not on the board. The read tools need its `/sys` and `/proc`.                                                                            |
| Final answer says it did something that isn't in `actions that ran` | Expected: the model claims actions it never took. Trust the summary, not the model's text.                                                       |
