---
name: iq9-always-on-agent
description: Design and build an always-on local agent on the Dragonwing IQ-9075. It watches a signal continuously and acts when something matters, using the loop observe → decide (a rule or d1-2B) → act (allowlist) → explain (LFM3, only on alerts) → log. Use when the user wants a monitor, a watcher, an autonomous agent, an alerting loop, or an edge agent that runs without prompts, or wants to adapt examples/always-on-agent.
compatibility: IQ-9075 with geniex serve and LFM3-1.7B Q4_0. The d1-2B venv and snapshot are needed only for --gate d1. Check with the iq9-preflight skill.
metadata:
  version: "0.3"
---

# Always-on local agent

This is the flagship track ("02 — Always-On Local Agent"). Start from `examples/always-on-agent/` and adapt it. The scaffold is a **reference design**, not a requirement. It runs with a rule gate and the LFM alone (`--gate rule`); d1 (`--gate d1`, the default) is optional. Any LFM3-family model is welcome; verify its runtime/NPU support and task behavior. External sensors are optional and not provided: local files/events, simulated inputs, or internal board readings work too.

## Start

```bash
skills/iq9-always-on-agent/scripts/scaffold.sh apps/my-agent   # choose your app's name
```

The new folder holds `agent.py` (the example loop), `lfm_client.py` (from `iq9-geniex-lfm`, used for explanations), `questions.py` (the d1 questions, loaded only by `--gate d1`), and a README to fill in. Run the smoke test in that README before you change anything.

## Design rules

1. **Decide before you generate.** The loop runs a gate on every observation: a rule in code (`rule_decide()`) or d1. Start with the rule; add d1 where a threshold is not enough. The LFM runs only when the action needs words.
2. **Sequential, not parallel.** d1 slows down substantially while the LFM generates. Keep sequential execution; re-measure before changing it.
3. **Allowlist actions in code.** `ALLOWED_ACTIONS` plus `run_action()`. A new action goes on the list on purpose. Anything else is refused and logged. Actions that change the outside world (GPIO, a relay, a message) need a rule in code *in addition to* the d1 probability.
4. **Calibrated threshold.** d1 may not track raw board temperature. Use `iq9-d1-decision-gate` to calibrate d1-2B, or use a rule, before trusting alerts.
5. **Log every iteration** as one JSON line, flushed: state, decision, action, explanation, timings, and errors. It is the judges' offline proof.
6. **Degrade gracefully.** Sensor errors, gate errors, timeouts, zero tokens, and empty/reasoning-only answers are logged and the loop keeps going. `lfm_client.py` tags raw prompts and validates answers; keep using it.

## Adapting the loop

| Part | Where | Advice |
|---|---|---|
| Observe | `read_sensors()`, `BoardTelemetry` | Return a small dict with clear key names. Add derived fields such as the change, its direction, and the time since the last event. The board's thermal zones work with no extra hardware |
| Camera | Your own read | d1 takes images directly: `system_one(state_or_None, questions, media=[PIL.Image])`. Measure latency on the board. For GStreamer and camera pipelines, see the IM SDK skills (outside this repo; see AGENTS.md) |
| Decide | `rule_decide()`; `questions.py` and `load_d1()` for d1 | Ask only what you act on. For d1: `noul` for "act?", `choice` for routing, `score` for severity |
| Act | `choose_action()`, `run_action()` | The policy maps the decision to one allowlisted action |
| Explain | `explain()`, `build_prompt()` | One sentence through `lfm_client.sentence()` (raw completion, closed think block). Pass the trend and direction explicitly; the model got the direction wrong when it had only two values |
| Log | `main()` | Keep the fields. Add yours |

## Check before you call it done

Run these from the generated app's directory. Use a separate terminal for long runs, and verify exit status and the flushed JSONL.

```bash
python3 agent.py --gate rule --sensor-mode simulated --iterations 6 --interval 1 --log test.jsonl        # no d1 needed
~/.venvs/d1/bin/python agent.py --sensor-mode simulated --iterations 6 --interval 1 --log test-d1.jsonl  # d1 gate
python3 agent.py --gate rule --sensor-mode fixed --stable-prompt --iterations 10 --interval 1 --log repeat.jsonl  # diagnostics only: repeats raw prompts
```

- Normal iteration lines have `decision`, `action`, and `loop_ms`; sensor and gate failures record an `error` instead. Successful alert explanations require `ok: true`, positive tokens, and nonempty text. Failed explanations require an error and must not stop the loop.
- `explanation.retried` records that the first reply was unusable; check `ok` and `error`, not just the flag.
- Identical raw prompts can yield unwanted continuing commentary with positive tokens. Treat `--stable-prompt` as diagnostics only; normal runs tag the first request. The repetition test is not an answer-quality benchmark.
- Run it on real input for as long as time allows (10 minutes is a good target), and look at the spread of your readings (or of `p_alert` with d1) before you pick limits or a threshold.
- Then rehearse with the network off (`iq9-offline-rehearsal`).

## Common mistakes to avoid

- Loading d1 inside the loop. Load it once.
- Calling the LFM on every iteration.
- Running the gate and generator in separate threads despite the reference contention result, without fresh evidence for the changed configuration.
- Trusting the LFM's explanation as a check. It repeats whatever the gate decided.
- A `while True` loop with no `--iterations` flag, so you can't smoke-test it.
