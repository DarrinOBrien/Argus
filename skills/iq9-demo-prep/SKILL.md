---
name: iq9-demo-prep
description: Prepare a LiquidAI × Dragonwing hackathon demo and pitch. Covers the judging rubric, the "why not a cloud API call?" answer, collecting measured latency, decode, memory, and endurance numbers on the IQ-9075, geniex-bench, the two-minute demo structure, and backups. Use when the user is getting ready for judging, wants performance numbers, a pitch, a README for judges, or is going for the Fastest Agent or Best Tiny Agent awards.
compatibility: Metrics script runs on the IQ-9075 with geniex serve running.
metadata:
  version: "0.1"
---

# Demo prep

Rubric and format: `docs/judging.md`. If it ever differs from the organisers' brief, the brief wins.

| Weight | Criterion |
|---|---|
| 25% | Edge-native value: why is this better on-device, or only possible there? |
| 20% | Technical execution: reliable, integrated, and running locally |
| 20% | Originality: not another generic chatbot |
| 15% | Real-world usefulness: a clear user and a clear need |
| 10% | Performance and efficiency |
| 10% | Demo quality: a short, credible offline proof |

## 1. The first question: "Why should this not simply be a cloud API call?"

Help the user write a two-sentence answer that names a **specific constraint**. "It runs on-device" is not an answer. Constraints that work:
- No network where it runs (a field site, a vehicle, a disaster zone, or tonight's network cut).
- The data can't leave the device (camera or mic in a private space, medical, or industrial IP).
- The reaction has to beat a round trip, or has to keep working while the link is down.
- At this volume, a flat marginal cost beats paying per token.

Then tie it to the architecture: what d1 decides locally, how often, and what that costs (the numbers come from step 2).

## 2. Numbers (measure them; never quote the docs as your own)

```bash
skills/iq9-geniex-lfm/scripts/serve.sh start
skills/iq9-demo-prep/scripts/collect_metrics.sh --log apps/<name>/agent_log.jsonl --out apps/<name>/metrics.json
```

It records the LFM TTFT, decode tok/s, and end-to-end time (median of 5 streamed runs after one warm-up), plus server RSS, memory, disk, and the hottest thermal zone. With `--log`, it also adds the app's gate and loop medians, the alert count, and the time span. For reference, a warm LFM2.5-2.6B Q4_0 on the NPU gave about 0.1–0.2 s TTFT and about 23 tok/s.

For the Fastest Agent or Best Tiny Agent awards, add:
- **End-to-end loop time** from the app log: `loop_ms` median and p95, not just model speed.
- **Footprint:** model size on disk (`geniex list`), server RSS, and peak RSS of the app (`/usr/bin/time -v`, "Maximum resident set size"). Note that d1 fp32 alone peaks at about 19.4 GB, so tiny-agent entries usually drop d1 or use a smaller model.
- **Endurance:** run for 30 minutes or more, and report the iteration count, errors, and the temperature trend.
- **Bench, optional:** `geniex-bench` (see `docs/developer-guide.md` §10). Use the v0.8.0 bench to match the runtime, and set `LD_LIBRARY_PATH` as shown there.

Write the numbers into the app's README with the GenieX version, the model and precision, and n. Mark anything not measured as ⚠️.

## 3. Two-minute demo

| Time | Show |
|---|---|
| 0:00–0:20 | The user, their problem, and the constraint (from step 1) |
| 0:20–0:35 | **Unplug the network on stage**, then show `curl huggingface.co` failing |
| 0:35–1:30 | The loop running live: an input changes, d1 decides, the action fires, the one-sentence explanation appears |
| 1:30–1:50 | The local JSONL log scrolling (the proof) plus 2–3 numbers from `metrics.json` |
| 1:50–2:00 | The next step for a real deployment |

Keep a visible timer, a recorded backup video, and a recorded log ready.

## 4. Pre-demo checklist

- [ ] `skills/iq9-preflight/scripts/preflight.sh` shows no FAIL.
- [ ] The `iq9-offline-rehearsal` network-off run is done, and its evidence is saved.
- [ ] Start the server with a long keepalive (`serve.sh start` uses 1800 s), and send one warm-up request just before going on.
- [ ] Use fresh, varied prompts (zero-token risk), and have `serve.sh restart` ready.
- [ ] Read the licence for every model shown. LiquidAI GGUF repos are tagged `other`; d1-3B uses the LFM Open License v1.0.
