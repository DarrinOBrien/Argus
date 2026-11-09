---
name: iq9-d1-decision-gate
description: Use LiquidAI d1-2B as a calibrated decision gate on the IQ-9075. Covers writing typed questions, running system_one() through Transformers on the CPU, threshold calibration on labeled data, and when to use a plain rule instead. Use when an app has to triage, classify, route, gate an action, or decide whether to alert, or whenever d1, system_one, or /v1/systemone comes up.
compatibility: IQ-9075 with the ~/.venvs/d1 venv (transformers>=5.19, CPU torch) and the pinned ~/models/d1-2B snapshot. Measure each task's latency and memory on the board. See examples/system-one-decision.
metadata:
  version: "0.3"
---

# d1-2B decision gate

d1-2B takes a state (text, JSON, images) and named questions. It returns calibrated, typed answers from one forward pass, with **zero output tokens**. It is not a chat model, and its zero output tokens are **expected**, not an LFM-generation failure. d1 is optional: use a deterministic rule or another decision design when appropriate. Latest dated evidence: [README Developer Notes](../../README.md#developer-notes); detailed API/setup: `docs/decision-models.md` and `examples/system-one-decision/`.

## Hard rules

1. **Run d1-2B through Transformers on the CPU:** `AutoModel.from_pretrained(<local dir>, trust_remote_code=True, local_files_only=True, dtype=torch.float32)` on CPU. Set offline Transformers/Hub settings before imports. The tested GenieX d1-2B GGUF requests failed; do not substitute that route.
2. **Load from `~/models/d1-2B`, never from a repo ID.** A repo ID downloads, and that fails offline. The snapshot is pinned to `10e7671d44e4` (`fetch_d1.py`). Before moving the pin, review the remote code again and ask the user.
3. **Start with fp32.** bf16 saves memory but is much slower on this CPU; measure both before choosing it.
4. **Load once, reuse.** Never load per request.
5. **Keep it sequential with the LFM.** Current reference measurements support this policy; re-measure the chosen configuration before changing it.
6. **d1 gates, the allowlist decides.** Only allowlisted actions run, whatever the probability says.

## Stage only if the app uses d1

Inspect `~/models/d1-2B` first. If the pinned snapshot is missing, **ask whether the participant has the supplied USB model drive and USB-C dongle/adapter** before proposing `fetch_d1.py`. With approval, **copy the full pinned Transformers snapshot—not a GGUF, and never move/delete the USB source—to `~/models/d1-2B`**. Follow [USB model staging](../../docs/developer-guide.md#usb-model-drive-copy-never-move): inspect paths/symlinks, preserve existing board files, copy all weights/config/tokenizer/model-code assets and `REVISION`, and verify sizes/checksums. Resolve any bundled cache symlinks into local files rather than leaving links to removable media. Confirm the full pin `10e7671d44e4b37700020b1eed3f594c5f2af0b4` and review the copied model code before enabling trust. A drive containing another revision does not authorize changing the pin. Run long copy jobs in a separate terminal; download only if compatible local/USB assets are unavailable and separately approved.

## Budget

Run d1-2B fp32 through Transformers on the CPU, and keep it sequential with the LFM: it slows down substantially during generation. With GenieX v0.10.0, `/v1/decisions` for a d1-2B GGUF returns HTTP 400 `SDKError(Parameter not supported by this plugin)` and `/v1/systemone` returns 404, so do not route d1 through GenieX.

Measure the actual task's text/image latency, batch behavior, peak RSS, and loop time before setting an interval. For fast loops, put a cheap rule first and call d1 only on candidates.

## Writing questions

```python
QUESTIONS = {
    "alert":    {"type": "noul",   "instructions": "Does this state need a human alert right now?"},
    "category": {"type": "choice", "instructions": "Which category fits best?",
                 "criteria": {"thermal": "Temperature or heat problem", "motion": "Unexpected movement",
                              "normal": "Nothing notable"}},
    "severity": {"type": "score",  "instructions": "How severe is it?", "criteria": ["Low", "Moderate", "Critical"]},
}
with torch.inference_mode():
    a = model.system_one(json.dumps(state), QUESTIONS)["answers"]
p, cat, sev = a["alert"]["noul"], a["category"]["choice"], a["severity"]["score"]
```

| Type | Returns | Notes |
|---|---|---|
| `noul` | `{"noul": P(yes)}` | Optional `criteria: {"true": ..., "false": ...}` to define yes and no |
| `choice` | `choice`, `confidence`, `probabilities` | `criteria` maps each name to a description |
| `score` | `score` (median level index, 0-based), `confidence`, `probabilities`, `legend` | 2–10 levels, lowest first |

Images: `model.system_one(None, {"q": {...}}, media=[PIL.Image])`, or a state plus media.

State design matters more than wording:
- **Name fields so they explain themselves, and put the derived signal in.** Give the change and its direction (`"change_c_per_min": 13.2, "trend": "rising"`), not just two raw numbers.
- **Keep keys consistent** between calibration and production. In our tests, changing `temp_c` to `soc_temp_c` changed the scores a lot.
- Ask only the questions you act on. Every question adds input tokens.

## Calibrate. Don't copy 0.5

A gate can fail to track raw board readings such as temperature. Do not copy a threshold from another model or task. Calibrate:

1. Log states while the app runs, with their `p_alert` (the always-on agent's log has `decision.p_alert`).
2. Label task-representative states by hand (`"label": true/false`). Aim for at least 30 calibration states and 10 per class as an initial sample, not proof of deployment readiness. Reserve separate held-out states (prefer separate time periods/events); do not fit and evaluate on the same rows.
3. Run:

```bash
python3 skills/iq9-d1-decision-gate/scripts/calibrate_threshold.py calibration.jsonl --eval held-out.jsonl
~/.venvs/d1/bin/python skills/iq9-d1-decision-gate/scripts/calibrate_threshold.py calibration.jsonl --eval held-out.jsonl --score
python3 skills/iq9-d1-decision-gate/scripts/calibrate_threshold.py calibration.jsonl --eval held-out.jsonl --objective recall --min-precision 0.8
```

When scoring edited/scaffolded app questions, add `--questions-from apps/<name>` so the script imports that app's `questions.py`, not the reference sensor questions. Existing stored probabilities must come from the same state/question format as production. Keep full probability precision through calibration and policy.

4. **AUC below about 0.65 means d1 can't separate your classes. A threshold won't fix that.** Then rewrite the state and questions, and calibrate again. If it still fails, use a rule (`temp > X or rise > Y`) for that signal. Keep d1 where it adds value: fuzzy categories, images, mixed signals, and ranking severity.

Report label provenance, the split, AUC, and confusion matrices for calibration and held-out evaluation. The script's `--eval` evaluates the fitted threshold without refitting; without it, results are explicitly in-sample. Synthetic reference checks (36 states, 18 positives; threshold 0.5 missed 9 positives) illustrate the need to calibrate, **not** a production threshold or held-out benchmark. Do not deploy the synthetic fitted threshold.

## Logging

Log every decision as one JSON line, whether or not it acts: timestamp, state, `p_alert`, the other answers, `gate_ms`, the threshold, and the action taken. That log is your tuning data and the judges' offline proof.
