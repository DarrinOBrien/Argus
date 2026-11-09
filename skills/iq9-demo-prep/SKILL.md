---
name: iq9-demo-prep
description: Prepare a LiquidAI × Dragonwing hackathon demo and pitch. Covers the judging rubric, the "why not a cloud API call?" answer, collecting measured latency, decode, memory, and endurance numbers on the IQ-9075, geniex-bench, the two-minute demo structure, and backups. Use when the user is getting ready for judging or wants performance numbers, a pitch, or a README for judges.
compatibility: Metrics script runs on the IQ-9075 with geniex serve running.
metadata:
  version: "0.3"
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

Then tie it to the architecture: what the local rule, optional d1 gate, or other decision design does, how often, and what it costs (measure in step 2). LFM3-1.7B is a reference default, not a required model. External sensors are optional and not provided.

## 2. Numbers (measure them; never quote the docs as your own)

```bash
# Separate terminal, from the repo root:
skills/iq9-geniex-lfm/scripts/serve.sh run
# Another terminal (choose the app's already-cached model):
skills/iq9-demo-prep/scripts/collect_metrics.sh --model 'cached-name:precision' --log apps/my-agent/agent_log.jsonl --out apps/my-agent/metrics.json
# Long-answer workload: representative prompt, generous safety cap
skills/iq9-demo-prep/scripts/collect_metrics.sh --prompt 'Explain what a transformer is in an LLM.' --max-tokens 2048 --timeout 300
```

`collect_metrics.sh` invokes the standard-library `collect_metrics.py`. Defaults: five measured streamed requests after one separately recorded warm-up, a 128-token cap, `enable_think: false`, and a 120 s per-request timeout. Change the cap with `--max-tokens`; `--enable-think` includes reasoning. Neither choice guarantees a usable answer.

- **The default prompt asks for one sentence.** Those numbers describe short answers, where TTFT and prefill dominate. Pass `--prompt` with your app's real request; a unique tag is still appended to each request. The output records `prompt` and `prompt_is_default`.
- **Long answers:** treat `--max-tokens` as a generous safety cap, not a target, and raise `--timeout` to match. Each sample records `finish_reason`, and `cap_hit_runs` counts `length` stops. Report how many runs stopped naturally (`stop`). A run that hit the cap measured the cap, not the answer.
- **Token counts include reasoning.** With `enable_think: false`, LFM3-1.7B can still emit reasoning, so a long request can spend its whole cap on reasoning and is then scored as a failure (empty answer). Rates cover all generated tokens, not just answer text.

- `ttft_s` times the first generated reasoning **or** answer delta; `answer_ttft_s` separately times the first answer delta.
- Empty/reasoning-only answers, missing usage, cap violations, and HTTP errors are failures, excluded from successful-run medians. Report n successful **and** failed, plus the warm-up outcome.
- `decode_tok_s` is explicitly an **SSE timing estimate**, using server completion usage and first-to-last generated delta timing. SSE chunks can bundle tokens; do not call it an exact tokenizer benchmark. Missing usage leaves rates null, never substitutes chunk counts. `generation_tok_s` includes the full request time (prefill/transport), not pure decode.
- It records runtime/model metadata, a device-log excerpt, instantaneous server RSS, system memory/disk/thermal state, and optional app gate/loop medians, errors, alerts, and time span. Verify that the device log belongs to this server after a capped request.

Report only numbers measured for this app. The collector exits 2 if any measured request fails; it never installs or pulls models.

Depending on your project's goals, useful additional demo measurements include:
- **End-to-end loop time** from the app log: `loop_ms` median and p95, not just model speed.
- **Footprint:** model size on disk (`geniex list`), server RSS, and peak RSS of the app (`/usr/bin/time -v`, "Maximum resident set size"). Measure the chosen d1/model/configuration. Instantaneous server RSS, peak app RSS, and NPU/device memory are distinct. d1 is optional for tiny-agent designs.
- **Endurance:** run for 30 minutes or more, and report the iteration count, errors, and the temperature trend.
- **Bench, optional:** `geniex-bench` (see `docs/developer-guide.md` §10). Use the v0.10.0 bench to match the runtime, and set `LD_LIBRARY_PATH` as shown there.

Write numbers into the app's README with the board, date, GenieX version, actual model/build and precision, workload, n, and medians. Label estimates as estimates. Any new helper behavior must pass local checks and a bounded IQ9 integration check before being called board-verified.

## 3. Two-minute demo

| Time | Show |
|---|---|
| 0:00–0:20 | The user, their problem, and the constraint (from step 1) |
| 0:20–0:35 | **Disconnect external uplinks on stage**, then show an external `curl` failing; an isolated USB-C SSH/web UI link may remain, without laptop internet sharing/forwarding |
| 0:35–1:30 | The loop running live: an input changes, the local decision runs, the action fires, the one-sentence explanation appears |
| 1:30–1:50 | The local JSONL log scrolling (the proof) plus 2–3 numbers from `metrics.json` |
| 1:50–2:00 | The next step for a real deployment |

Keep a visible timer, a recorded backup video, and a recorded log ready.

## 4. Pre-demo checklist

- [ ] Preflight shows no FAIL for the app's selected profile/model (`reference`, `generator`, or `board`); the app also passes its end-to-end smoke test.
- [ ] The `iq9-offline-rehearsal` network-off run is done, and its evidence is saved.
- [ ] Display/control path is rehearsed: monitor setups require removing/rolling back the current Adreno APT update with approval; SSH is unaffected. For a headless USB-C SSH/web UI setup, verify the isolated link, local browser assets, and no laptop internet sharing/forwarding after the cut. See [Developer Notes](../../README.md#external-monitors-and-headless-setups) and [USB-C access](../../docs/offline-readiness.md#display-and-usb-c-access).
- [ ] Run a visible foreground server with a keepalive covering quiet gaps (`serve.sh run` defaults to 1800 s); verify a usable capped warm-up and HTP0 before showing metrics.
- [ ] Use unique initial raw prompts and validate answer/tool content. Know how to safely relaunch the owned foreground server; do not interrupt a shared one or silently detach it.
- [ ] Read the licence for every model shown. LFM3-1.7B and d1-2B use the LFM Open License v1.0.
