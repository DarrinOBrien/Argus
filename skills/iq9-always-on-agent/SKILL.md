---
name: iq9-always-on-agent
description: Design and build an always-on local agent on the Dragonwing IQ-9075. It watches a signal continuously and acts when something matters, using the loop observe → decide (d1-2B) → act (allowlist) → explain (LFM3, only on alerts) → log. Use when the user wants a monitor, a watcher, an autonomous agent, an alerting loop, or an edge agent that runs without prompts, or wants to adapt examples/always-on-agent.
compatibility: IQ-9075 with geniex serve, LFM3-1.7B Q4_0, and the d1-2B venv and snapshot. Check with the iq9-preflight skill.
metadata:
  version: "0.2"
---

# Always-on local agent

This is the flagship track ("02 — Always-On Local Agent"). Start from `examples/always-on-agent/` and adapt it. The scaffold is a **reference d1/LFM3-1.7B design**, not a requirement to use those models. d1 is optional and any LFM3-family model is welcome; verify its runtime/NPU support and task behavior. External sensors are optional and not provided: local files/events, simulated inputs, or internal board readings work too.

## Start

```bash
skills/iq9-always-on-agent/scripts/scaffold.sh apps/<name>
```

The new folder holds `agent.py` (the example loop), `questions.py` (the d1 questions), `lfm_client.py` (from `iq9-geniex-lfm`), and a README to fill in. Run the smoke test in that README before you change anything.

## Design rules

1. **Decide before you generate.** The reference loop calls d1 on observations; a rule or candidate prefilter may be more appropriate for your app. The LFM runs only when the action needs words.
2. **Sequential, not parallel.** [Prior IQ9 checks](../../README.md#developer-notes), 2026-11-05: GenieX v0.10.0, LFM3-1.7B QAD-Q4_0 on HTP0; d1-2B fp32 CPU, 8 threads, Transformers 5.19.0 / torch 2.11.0. The same three-question gate had median **2.848 s alone** versus **5.572 s during generation**, **n=5 per condition**, paired. Keep sequential execution; re-measure before changing it.
3. **Allowlist actions in code.** `ALLOWED_ACTIONS` plus `run_action()`. A new action goes on the list on purpose. Anything else is refused and logged. Actions that change the outside world (GPIO, a relay, a message) need a rule in code *in addition to* the d1 probability.
4. **Calibrated threshold.** The previous d1-3B gate did not track board temperature. Use `iq9-d1-decision-gate` to calibrate d1-2B, or use a rule, before trusting alerts.
5. **Log every iteration** as one JSON line, flushed: state, decision, action, explanation, timings, and errors. It is the judges' offline proof.
6. **Degrade gracefully.** Input errors, timeouts, zero tokens, and empty/reasoning-only answers must be logged. Validate actual answer content, not just `ok` or usage; the loop keeps going. Raw prompts need a unique event tag before the first call. Do not automatically interrupt a shared server.

## Adapting the loop

| Part | Where | Advice |
|---|---|---|
| Observe | `read_sensors()`, `BoardTelemetry` | Return a small dict with clear key names. Add derived fields such as the change, its direction, and the time since the last event. The board's thermal zones work with no extra hardware |
| Camera | Your own read | d1 takes images directly: `system_one(state_or_None, questions, media=[PIL.Image])`. Measure latency on the board. For GStreamer and camera pipelines, see the IM SDK skills (outside this repo; see AGENTS.md) |
| Decide | `questions.py`, `decide()` | Ask only what you act on: `noul` for "act?", `choice` for routing, `score` for severity |
| Act | `choose_action()`, `run_action()` | The policy maps the decision to one allowlisted action |
| Explain | `explain()`, `build_prompt()` | One sentence through a raw completion with a closed think block (already done). Pass the trend and direction explicitly; the model got the direction wrong when it had only two values |
| Log | `main()` | Keep the fields. Add yours |

## Check before you call it done

Run these from the generated app's directory. Use a separate terminal for long runs, and verify exit status and the flushed JSONL.

```bash
~/.venvs/d1/bin/python agent.py --sensor-mode simulated --iterations 6 --interval 1 --log test.jsonl
~/.venvs/d1/bin/python agent.py --sensor-mode fixed --stable-prompt --iterations 10 --interval 1 --log repeat.jsonl  # diagnostics only: intentionally repeats raw prompts
```

- Normal iteration lines have `decision`, `action`, and `loop_ms`; input-error lines record the error. Successful alert explanations require `ok: true`, positive tokens, and nonempty text. Failed explanations require an error and must not stop the loop.
- `zero_token_first_try` records actual zero usage; `empty_response_first_try` records an empty answer. Check retry and error fields, not just flags. The legacy zero-token bug was not reproduced in the current suite.
- Identical raw prompts can yield unwanted continuing commentary with positive tokens. Treat `--stable-prompt` as diagnostics only; normal runs tag the first request. The repetition test is not an answer-quality benchmark.
- Run it on real input for at least 10 minutes, and look at the spread of `p_alert` before you pick a threshold.
- Then rehearse with the network off (`iq9-offline-rehearsal`).

## Common mistakes to avoid

- Loading d1 inside the loop. Load it once.
- Calling the LFM on every iteration.
- Running the gate and generator in separate threads despite the reference contention result, without fresh evidence for the changed configuration.
- Trusting the LFM's explanation as a check. It repeats whatever the gate decided.
- A `while True` loop with no `--iterations` flag, so you can't smoke-test it.
