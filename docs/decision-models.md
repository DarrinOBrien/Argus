# Decision Layer — LiquidAI d1-3B

`LiquidAI/d1-3B` is a 3.12B-parameter **decision model**. You give it a state (text, JSON, images, or a mix) and named questions. It returns calibrated, typed answers in **one forward pass with zero output tokens**. It is not a chat model and does not write text. ✅ (model card)

This guide uses it as the **decision gate**: a cheap, calibrated "should I act, and how urgent is it?" check. The generative LFM model runs only when the decision says an explanation is worth the tokens.

Markers: ✅ confirmed in the model card, GenieX docs, or our runs on the reference board · ⚠️ not yet verified.

## What it is

| | |
|---|---|
| Base model | LFM2.5-VL-3B ✅ |
| Parameters | 3.12B ✅ |
| Vision encoder | SigLIP2 NaFlex shape-optimized 400M ✅ |
| Context | 32,768 tokens ✅ |
| Output | Calibrated typed answers, zero output tokens ✅ |
| Interface (native) | `model.system_one(state, questions, images=None)` and `system_one_batch(...)` ✅ |
| License | LFM Open License v1.0 (tag `lfm1.0`). Read the LICENSE before any public demo. ✅ |

## Question types

✅ (model card). Each answer is typed:

| `type` | Asks | `criteria` | Answer |
|---|---|---|---|
| `noul` | Yes or no | optional `{"true": …, "false": …}` | `{"type": "noul", "noul": P(yes)}` |
| `choice` | One of named options | `{name: description}` | `choice`, `confidence`, `probabilities` |
| `score` | Rating on 2–10 ordered levels | list of level descriptions, lowest first | `score` (expected level index), `confidence`, `probabilities`, `legend` |

The full response is `{"answers": {name: answer}, "usage": {"input_tokens": n, "output_tokens": 0}}`. We confirmed this shape in `api.py` and on the reference board. ✅

## Why split the work

- **Decisions are cheap and repeatable.** The same state gives the same probabilities.
- **Thresholds are real numbers.** `p_alert` can be tuned on your data. A generated "yes" cannot.
- **Explanations cost tokens only when needed.** Most loop iterations are a no-op.

Use it for: triage, routing, guardrails on agent actions, yes/no checks on sensor readings, severity ranking, and visual checks. Not for free-form text. ✅ (model card)

The architecture diagram, with the LFM generator downstream, is in the [developer guide §2.1](developer-guide.md#21-two-models-two-jobs).

## Running it on the IQ-9075

The guide runs d1 through the model card's `system_one()` API, in-process with transformers, in fp32 on the CPU. About 4.5 s per state (three questions, one pass). ✅ (measured)

### Path A: transformers on the CPU

- Requirements: `transformers>=5.14` (installed in a venv), torch and torchvision (CPU builds), pillow. `trust_remote_code=True` runs the repo's code, so review it first.
- Weights: 6,247 MB safetensors at `~/models/d1-3B`, pinned to commit `051bcc464b01`.
- Measured: about 4.5 s per state (three questions, one pass), peak RSS 19.4 GB in fp32. bf16 on this CPU is about 5× slower (≈24 s per state) and uses 7.2 GB.
- Batching does not help on this CPU: three states took about three times one state.
- Running with the generator: with the LFM server loaded, a decision took about 7.7 s instead of 4.1 s (medians, n=8). System memory peaked at about 18 GB used out of 34 GiB, which fits. ✅ (measured)
- On the board's own telemetry the gate does not track temperature. Across 75 states from the heat-up run, the correlation between SoC temperature and `p_alert` was −0.08, and it alerted on most states. Its calibration does not carry over to these readings. ✅ (measured; see [`examples/always-on-agent`](../examples/always-on-agent/README.md))
- Images work through the same API: `state=None` with one image and one `noul` question took about 7.6 s on the reference board. ✅ (measured)
- The runnable example, with setup and sample output: [`examples/system-one-decision`](../examples/system-one-decision/README.md).

### No GenieX decision endpoint

The GenieX docs describe a `POST /v1/systemone` endpoint for this model. It returns `404` on GenieX v0.4.0 and v0.8.0, so this guide does not use it. Recheck `geniex version` and the endpoint before the event. ⚠️

## Model files and disk

| Item | Size | Path on the board | Used by |
|---|---:|---|---|
| `d1-3B` safetensors | 6.2 GB | `~/models/d1-3B` | Path A |

The snapshot includes the weights and the repo's Python code. The code runs when `trust_remote_code=True` is set. See [Safety and licensing](#safety-and-licensing).

## Calibrating thresholds

- The card gives no thresholds. Start with `ALERT_THRESHOLD = 0.5` and tune on states you have labeled yourself. ⚠️
- Log every decision with its probabilities. The log is both the tuning data and the offline proof.

## Safety and licensing

- `trust_remote_code=True` runs code from the model repo. We reviewed the shipped Python in revision `051bcc464b01`: no network calls, no subprocesses, no `eval`/`exec`/`pickle`. Record the commit hash for any future change. ✅ (our review)
- d1 gates actions; it does not replace the allowlist. Only allowlisted actions run, whatever the probabilities say.
- The LFM Open License v1.0 governs d1-3B. Read the commercial terms before publishing a demo. ✅ (model card)
