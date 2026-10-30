---
name: iq9-d1-decision-gate
description: Use LiquidAI d1-2B as a calibrated decision gate on the IQ-9075. Covers writing typed questions, running system_one() through transformers on the CPU (Path A), threshold calibration on labeled data, and when to use a plain rule instead. Use when an app has to triage, classify, route, gate an action, or decide whether to alert, or whenever d1, system_one, or /v1/systemone comes up.
compatibility: IQ-9075 with the ~/.venvs/d1 venv (transformers>=5.19, CPU torch) and the pinned ~/models/d1-2B snapshot. Performance is not yet measured on this board. See examples/system-one-decision.
metadata:
  version: "0.1"
---

# d1-2B decision gate

d1-2B takes a state (text, JSON, images) and named questions. It returns calibrated, typed answers from one forward pass, with **zero output tokens**. It is not a chat model. Sources of truth: `docs/decision-models.md` and `examples/system-one-decision/`.

## Hard rules

1. **Use Path A:** `AutoModel.from_pretrained(<local dir>, trust_remote_code=True, dtype=torch.float32)` on the CPU. GenieX decision serving is not yet verified for this stack.
2. **Load from `~/models/d1-2B`, never from a repo ID.** A repo ID downloads, and that fails offline. The snapshot is pinned to `10e7671d44e4` (`fetch_d1.py`). Before moving the pin, review the remote code again and ask the user.
3. **Start with fp32.** Measure fp32 and bf16 on the board before choosing; the old d1-3B numbers do not transfer.
4. **Load once, reuse.** Never load per request.
5. **Keep it sequential with the LFM** until concurrency is measured.
6. **d1 gates, the allowlist decides.** Only allowlisted actions run, whatever the probability says.

## Budget

d1-2B is not yet measured on the IQ-9075. Measure one state, one image, batch behavior, fp32/bf16 peak RSS, and loop latency before setting the interval. For fast loops, put a cheap rule first and call d1 only on candidate events.

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

The previous d1-3B gate did **not** track the board's thermal readings. Do not transfer its threshold to d1-2B. Calibrate:

1. Log states while the app runs, with their `p_alert` (the always-on agent's log has `decision.p_alert`).
2. Label 30 or more of them by hand (`"label": true/false`), with at least 10 per class.
3. Run:

```bash
python3 skills/iq9-d1-decision-gate/scripts/calibrate_threshold.py labeled.jsonl
~/.venvs/d1/bin/python skills/iq9-d1-decision-gate/scripts/calibrate_threshold.py labeled.jsonl --score   # rows with only "obs"
python3 skills/iq9-d1-decision-gate/scripts/calibrate_threshold.py labeled.jsonl --objective recall --min-precision 0.8
```

4. **AUC below about 0.65 means d1 can't separate your classes. A threshold won't fix that.** Then rewrite the state and questions, and calibrate again. If it still fails, use a rule (`temp > X or rise > Y`) for that signal. Keep d1 where it adds value: fuzzy categories, images, mixed signals, and ranking severity.

Tell the user the AUC and the confusion matrix at the chosen threshold. Don't just report "calibrated".

## Logging

Log every decision as one JSON line, whether or not it acts: timestamp, state, `p_alert`, the other answers, `gate_ms`, the threshold, and the action taken. That log is your tuning data and the judges' offline proof.
