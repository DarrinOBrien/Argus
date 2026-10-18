---
name: iq9-d1-decision-gate
description: Use LiquidAI d1-3B as a calibrated decision gate on the IQ-9075. Covers writing noul/choice/score questions, running system_one() through transformers on the CPU (Path A), latency and memory budgets, threshold calibration on labeled data, and when to use a plain rule instead. Use when an app has to triage, classify, route, gate an action, or decide whether to alert, or whenever d1, system_one, or /v1/systemone comes up.
compatibility: IQ-9075 with the ~/.venvs/d1 venv (transformers>=5.14, CPU torch) and the pinned ~/models/d1-3B snapshot. See examples/system-one-decision.
metadata:
  version: "0.1"
---

# d1-3B decision gate

d1-3B takes a state (text, JSON, images) and named questions. It returns calibrated, typed answers from one forward pass, with **zero output tokens**. It is not a chat model. Sources of truth: `docs/decision-models.md` and `examples/system-one-decision/`.

## Hard rules

1. **Path A only:** `AutoModel.from_pretrained(<local dir>, trust_remote_code=True, dtype=torch.float32)` on the CPU. `POST /v1/systemone` returns 404 on GenieX v0.4.0 and v0.8.0, and the `d1-3B-GGUF` entry in `geniex list` can't run it.
2. **Load from `~/models/d1-3B`, never from a repo ID.** A repo ID downloads, and that fails offline. The snapshot is pinned to `051bcc464b01` (`fetch_d1.py`). Before moving the pin, review the remote code again (`modeling_d1.py`, `api.py`, `runner.py`, `hybrid.py`, `prompt.py`, `lfm2_vl.py`), and ask the user.
3. **fp32.** bf16 is about 5× slower on this CPU. Use it only for memory (7.2 GB peak, against 19.4 GB).
4. **Load once, reuse.** Loading takes 3–6 s. Never load per request.
5. **Keep it sequential with the LFM.** A decision takes about 4.1 s alone and about 7.7 s while a generation runs.
6. **d1 gates, the allowlist decides.** Only allowlisted actions run, whatever the probability says.

## Budget (IQ-9075, measured)

| | |
|---|---|
| One state, 3 questions, one pass | about 4.0–4.5 s |
| One image + one `noul` (256×256) | about 6.8–7.6 s |
| Batch of N | about N × single. Batching doesn't help on this CPU |
| Peak RSS | 19.4 GB (fp32) |

So d1 fits a loop that observes every 5 s or more, not one that needs sub-second reactions. For fast loops, put a cheap rule first and call d1 only on candidate events.

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
| `score` | `score` (expected level index, 0-based), `confidence`, `probabilities`, `legend` | 2–10 levels, lowest first |

Images: `model.system_one(None, {"q": {...}}, images=[PIL.Image])`, or a state plus images.

State design matters more than wording:
- **Name fields so they explain themselves, and put the derived signal in.** Give the change and its direction (`"change_c_per_min": 13.2, "trend": "rising"`), not just two raw numbers.
- **Keep keys consistent** between calibration and production. In our tests, changing `temp_c` to `soc_temp_c` changed the scores a lot.
- Ask only the questions you act on. Every question adds input tokens.

## Calibrate. Don't copy 0.5

On the board's own thermal readings, d1 did **not** track temperature. It alerted on 53 of 75 heat-up states, and `p_alert` had r = −0.08 against temperature. The default threshold is not usable on real board data. Calibrate:

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
