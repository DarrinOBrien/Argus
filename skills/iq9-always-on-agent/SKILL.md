---
name: iq9-always-on-agent
description: Design and build an always-on local agent on the Dragonwing IQ-9075. It watches a signal continuously and acts when something matters, using the loop observe → decide (d1-3B) → act (allowlist) → explain (LFM, only on alerts) → log. Use when the user wants a monitor, a watcher, an autonomous agent, an alerting loop, or an edge agent that runs without prompts, or wants to adapt examples/always-on-agent.
compatibility: IQ-9075 with geniex serve, LFM2.5-2.6B Q4_0, and the d1 venv and snapshot. Check with the iq9-preflight skill.
metadata:
  version: "0.1"
---

# Always-on local agent

This is the flagship track ("02 — Always-On Local Agent"). Start from the working loop in `examples/always-on-agent/`. Don't start from scratch.

## Start

```bash
skills/iq9-always-on-agent/scripts/scaffold.sh apps/<name>
```

The new folder holds `agent.py` (the example loop), `questions.py` (the d1 questions), `lfm_client.py` (from `iq9-geniex-lfm`), and a README to fill in. Run the smoke test in that README before you change anything.

## Design rules (from measured runs; keep all six)

1. **Decide before you generate.** d1 runs on every observation (about 4 s). The LFM runs only when the action needs words (about 1.5–2 s). Most iterations are a `no_op` and cost no tokens.
2. **Sequential, not parallel.** Running the gate during a generation slows it from about 4.1 s to about 7.7 s. Budget about 4 s per quiet iteration and about 6–7 s per iteration that alerts.
3. **Allowlist actions in code.** `ALLOWED_ACTIONS` plus `run_action()`. A new action goes on the list on purpose. Anything else is refused and logged. Actions that change the outside world (GPIO, a relay, a message) need a rule in code *in addition to* the d1 probability.
4. **Calibrated threshold.** On board thermal data d1 did not track temperature (r = −0.08). Use `iq9-d1-decision-gate` to calibrate, or a rule, before trusting alerts.
5. **Log every iteration** as one JSON line, flushed: state, decision, action, explanation, timings, and errors. It is the judges' offline proof.
6. **Degrade gracefully.** A sensor error, an LFM timeout, or a zero-token reply gets logged, and the loop keeps going. Never crash the loop because of the explainer.

## Adapting the loop

| Part | Where | Advice |
|---|---|---|
| Observe | `read_sensors()`, `BoardTelemetry` | Return a small dict with clear key names. Add derived fields such as the change, its direction, and the time since the last event. The board's thermal zones work with no extra hardware |
| Camera | Your own read | d1 takes images directly: `system_one(state_or_None, questions, images=[PIL.Image])`, about 7 s each. For GStreamer and camera pipelines, see the IM SDK skills (outside this repo; see AGENTS.md) |
| Decide | `questions.py`, `decide()` | Ask only what you act on: `noul` for "act?", `choice` for routing, `score` for severity |
| Act | `choose_action()`, `run_action()` | The policy maps the decision to one allowlisted action |
| Explain | `explain()`, `build_prompt()` | One sentence through a raw completion with a closed think block (already done). Pass the trend and direction explicitly; the model got the direction wrong when it had only two values |
| Log | `main()` | Keep the fields. Add yours |

## Check before you call it done

```bash
~/.venvs/d1/bin/python agent.py --sensor-mode simulated --iterations 6 --interval 1 --log test.jsonl
~/.venvs/d1/bin/python agent.py --sensor-mode fixed --stable-prompt --iterations 10 --interval 1 --log zt.jsonl  # exercises the zero-token retry
```

- Every line in `test.jsonl` has `decision`, `action`, and `loop_ms`. Lines that alert have `explanation.ok: true`.
- The `zt.jsonl` lines may show `zero_token_first_try: true` with `ok: true`. That means the retry worked.
- Run it on real input for at least 10 minutes, and look at the spread of `p_alert` before you pick a threshold.
- Then rehearse with the network off (`iq9-offline-rehearsal`).

## Common mistakes to avoid

- Loading d1 inside the loop. Load it once.
- Calling the LFM on every iteration.
- Running the gate and the generator in separate threads without budgeting about 7.7 s per decision.
- Trusting the LFM's explanation as a check. It repeats whatever the gate decided.
- A `while True` loop with no `--iterations` flag, so you can't smoke-test it.
