# Decision Layer — LiquidAI d1-2B

`LiquidAI/d1-2B` is a 1.92B-parameter **decision model** built on LFM3-VL-2B. You give it a state (text, JSON, images, or a mix) and named questions. It returns calibrated, typed answers in **one forward pass with zero output tokens**. It is not a chat model. ✅ (model card)

This guide uses it as the **decision gate**: a cheap, calibrated "should I act, and how urgent is it?" check. The generative LFM model runs only when the decision says an explanation is worth the tokens.

Markers: ✅ confirmed in the model card, GenieX docs, or our runs on the reference board · ⚠️ not yet verified.

## What it is

| | |
|---|---|
| Base model | LFM3-VL-2B ✅ |
| Parameters | 1.92B ✅ |
| Context | 128,000 tokens ✅ |
| Output | Calibrated typed answers, zero output tokens ✅ |
| Interface (native) | `model.system_one(state, questions, media=None)` and `system_one_batch(...)` ✅ |
| License | LFM Open License v1.0 (tag `lfm1.0`). Read the LICENSE before any public demo. ✅ |

## Question types

✅ (model card). Each answer is typed:

| `type` | Asks | `criteria` | Answer |
|---|---|---|---|
| `noul` | Yes or no | optional `{"true": …, "false": …}` | `{"type": "noul", "noul": P(yes)}` |
| `choice` | One of named options | `{name: description}` | `choice`, `confidence`, `probabilities` |
| `score` | Rating on 2–10 ordered levels | list of level descriptions, lowest first | `score` (median level index), `confidence`, `probabilities`, `legend` |

The full response is `{"answers": {name: answer}, "usage": {"input_tokens": n, "output_tokens": 0}}`. We confirmed this shape in the pinned `api.py`; the board run is pending. ⚠️

## Why split the work

- **Decisions are cheap and repeatable.** The same state gives the same probabilities.
- **Thresholds are real numbers.** `p_alert` can be tuned on your data. A generated "yes" cannot.
- **Explanations cost tokens only when needed.** Most loop iterations are a no-op.

Use it for: triage, routing, guardrails on agent actions, yes/no checks on sensor readings, severity ranking, and visual checks. Not for free-form text. ✅ (model card)

The architecture diagram, with the LFM generator downstream, is in the [developer guide §2.1](developer-guide.md#21-two-models-two-jobs).

## Running it on the IQ-9075

The guide runs d1 through the model card's `system_one()` API, in-process with transformers, in fp32 on the CPU. d1-2B latency and memory are not yet measured on the IQ-9075. ⚠️

### Path A: transformers on the CPU

- Requirements: `transformers>=5.19` (installed in a venv), torch and torchvision (CPU builds), pillow. `trust_remote_code=True` runs the repo's code, so review it first.
- Weights: 3,836 MB safetensors at `~/models/d1-2B`, pinned to commit `10e7671d44e4`.
- Measure fp32 and bf16, batching, image latency, peak RSS, and concurrency with the generator before choosing production settings. ⚠️
- Calibrate on the app's own data; the previous d1-3B thermal result does not transfer.
- The runnable example, with setup and sample output: [`examples/system-one-decision`](../examples/system-one-decision/README.md).

### No GenieX decision endpoint

GenieX decision serving changed after v0.8.0, but it is not yet verified with d1-2B on this board. This guide therefore keeps Path A. ⚠️

## Model files and disk

| Item | Size | Path on the board | Used by |
|---|---:|---|---|
| `d1-2B` safetensors | 3.8 GB | `~/models/d1-2B` | Path A |

The snapshot includes the weights and the repo's Python code. The code runs when `trust_remote_code=True` is set. See [Safety and licensing](#safety-and-licensing).

## Calibrating thresholds

- The card gives no thresholds. Start with `ALERT_THRESHOLD = 0.5` and tune on states you have labeled yourself. ⚠️
- Log every decision with its probabilities. The log is both the tuning data and the offline proof.

## Safety and licensing

- `trust_remote_code=True` runs code from the model repo. We reviewed all shipped Python in revision `10e7671d44e4`: no subprocess or shell execution and no `eval`/`exec`/pickle. Transformers file helpers resolve the local snapshot when offline. Record the commit hash for any future change. ✅
- d1 gates actions; it does not replace the allowlist. Only allowlisted actions run, whatever the probabilities say.
- The LFM Open License v1.0 governs d1-2B. Read the commercial terms before publishing a demo. ✅ (model card)
