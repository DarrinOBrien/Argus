# On-Device AI Hackathon: Cleared for Takeoff ✈️

**LiquidAI × Qualcomm Dragonwing**

Reference documentation for the hackathon: build on-device AI agents with **LiquidAI** models on the **Qualcomm Dragonwing IQ-9075 EVK**, then demonstrate them with the network removed.

> **Start here:** [`docs/developer-guide.md`](docs/developer-guide.md). Using a coding agent? Point it at [`AGENTS.md`](AGENTS.md).

## Platform and models

* **Hardware:** Dragonwing IQ-9075 EVK only (QCS9075, Hexagon v73 NPU, 36 GB LPDDR5). External sensors are optional and will not be provided; participants are welcome to bring their own.
* **Generator and tools:** Choose **any model in LiquidAI's LFM3 family** that fits your project.
* **Reference generator:** This repo's examples use `LiquidAI/LFM3-1.7B-GGUF` (Q4_0) via GenieX v0.10.0—a starting point, not a required model.
* **Optional decision layer:** `LiquidAI/d1-2B`, a decision model that answers typed questions in one pass with no output tokens.

Start with [LiquidAI's LFM3 family on Hugging Face](https://huggingface.co/collections/LiquidAI/lfm3), then review each model's card and file list. Other LFM models are also options. The example READMEs explain their reference choices.

For any model you choose, verify [format, precision, runtime, and NPU compatibility](docs/runtimes.md#model-format-and-precision), [stage its required assets before the network cut](docs/offline-readiness.md#disk-first), and test it on the board offline before a demo. Reference-stack results do not verify another model or precision.

## Goals

Build intelligence that does not need the internet. The event isolates the moments where local inference creates real value:

* **Privacy:** data never leaves the board
* **Resilience:** the system keeps working when the network is down
* **Latency:** local responses without a network round trip
* **Autonomy:** the agent acts on its own between human prompts
* **Predictable marginal cost:** no per-token API bill

The proof: a competing system is still functional when the network is removed.

## Objectives

The event is organized around three pillars:

| Pillar                           | Focus             | What a winning project does                                                                          |
| -------------------------------- | ----------------- | ---------------------------------------------------------------------------------------------------- |
| **01 — The Network Has Crashed** | Main constraint   | Delivers its core value offline and explains why edge-native architecture matters                    |
| **02 — Always-On Local Agent**   | Flagship track    | Monitors local signals persistently and acts when something matters, beyond prompt-and-response chat |
| **03 — Tiny Agent Olympics**     | Performance layer | Shows speed, footprint, endurance, tool use, or multimodal execution on a common platform            |

Judging weights and the "why not just a cloud API call?" question are in [`docs/judging.md`](docs/judging.md).

## Repository outline

| Path                            | Purpose                                                                                                                                                                        |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `README.md`                     | This file: goals, objectives, repo map                                                                                                                                         |
| `docs/developer-guide.md`       | Main guide: setup → first model → server → decision and generation loop → offline                                                                                              |
| `docs/decision-models.md`       | d1-2B: question types and Transformers on the IQ-9075 CPU                                                                                                                                |
| `docs/runtimes.md`              | GenieX versions, CLI, server endpoints and request fields, benchmarking, pitfalls                                                                                              |
| `docs/hardware.md`              | IQ-9075 facts, team board state, driver packages                                                                                                                               |
| `docs/offline-readiness.md`     | Pre-cut checklist and network-off rehearsal                                                                                                                                    |
| `docs/judging.md`               | Scoring rubric, demo format, metrics to show                                                                                                                                   |
| `examples/system-one-decision/` | `system_one()` with Transformers on the CPU. Installation, pinned fetch, environment check, example.                                                                              |
| `examples/lfm-server-npu/`      | LFM3-1.7B: start `geniex serve` on the NPU, send one capped chat request, stop it                                                                                              |
| `examples/always-on-agent/`     | The always-on loop, runnable: observe, decide (d1), act through an allowlist, explain alerts (LFM, raw completion), log to JSONL                                               |
| `examples/tool-calling/`        | LFM3-1.7B: native `tools` calls, schema validation, allowlist, and a policy check before any write action                                                                      |
| `starter/`                      | `run.sh`: checks the board, runs one decision pass and one generation, and points to the next example                                                                          |
| `skills/`                       | Agent skills with tested scripts: preflight, GenieX/LFM client, d1 calibration, agent scaffold, tool calling, offline audit, demo metrics. Start with [`AGENTS.md`](AGENTS.md) |
| `AGENTS.md`                     | Instructions for coding agents: rules, skills, where to run, what to ask before doing                                                                                          |
| `apps/`                         | Where hackathon projects go (`skills/iq9-always-on-agent/scripts/scaffold.sh apps/<name>`)                                                                                     |

**Start from working examples:** This repo includes a model inference sample, a local agent, a guarded tool-calling example, and a starter check. After completing setup, run `./starter/run.sh` to check your board and models before building your project.

## Developer Notes

### External monitors and headless setups

**Organizer-reported setup issue:** the current Adreno APT update causes a GPU-driver issue when using an external monitor on the IQ-9075. Teams using a monitor must **remove/roll back the Adreno APT update** before using that setup. This repo's setup recipes no longer recommend installing/updating `qcom-adreno1`. Check installed versions and confirm the removal/rollback procedure with the organizers and board owner before changing drivers; the affected/fixed package versions are not recorded here.

**SSH is not affected by this monitor issue.** A headless setup using SSH and an app web server over a configured **USB-C network link** is allowed during the network-off demo. Keep the link local-only: disable internet sharing/forwarding on the laptop and remove all external uplinks. Serve UI assets locally and keep inference on the board. See [display and USB-C access](docs/offline-readiness.md#display-and-usb-c-access) for the checklist and SSH port forwarding.

This setup warning is separate from the dated model/runtime checks below; those checks did not verify monitor recovery or a USB-C network-off demo.

### Reference-stack checks — 2026-11-05

🧪 Checked on an IQ-9075 on **2026-11-05**, with **GenieX v0.10.0**, **LFM3-1.7B Q4_0 on HTP0**, and **d1-2B fp32 on the CPU (8 threads)**. These observations apply to the tested configuration, not every LFM3-family model; re-test your chosen model and runtime.

* **If using d1-2B, run it through Transformers on the CPU.** Transformers passed the typed-answer, image, and batch checks. GenieX `/v1/decisions` requests with d1-2B **Q4_K_M GGUF on CPU** returned an unsupported-parameter error in all five attempts; `/v1/systemone` returned 404. Keep the decision layer on Transformers for this stack.
* **Cap every request and validate the answer.** Use `max_completion_tokens` on chat and `max_tokens` on raw completions. Caps were honored and no zero-token replies occurred in 205 recorded LFM requests; retain the retry as a defensive fallback. **Positive token usage can still accompany empty answer content.** For text-answer requests, treat empty `content` as a failure; for tool requests, validate `tool_calls` instead.
* **LFM3-1.7B reasons by default.** For direct answers, try `enable_think: false` on chat or a raw completion with the reasoning block closed. Both helped in the one-sentence probes, but the chat flag did not guarantee a usable answer in a tight-cap test. Check `content` and `reasoning_content` before the demo.
* **Avoid identical raw-completion prompts.** Repeated identical `/v1/completions` requests returned continuing commentary instead of fresh direct answers, despite nonzero token counts. Include a unique event timestamp or tag in each prompt and validate the output; cache/state handling is only a suspected cause.
* **Allow for idle unloading.** The default keepalive is 300 s, and idle unloading was observed. Both `--keepalive` and `GENIEX_KEEPALIVE` worked in the tests. Set the timeout longer than the demo's quiet gaps or send a warm-up request. Measure reload latency for your model rather than using the previous stack's figures. See [`docs/runtimes.md`](docs/runtimes.md#server-lifecycle-model-loading-and-idle-unloading).
* **Keep the gate and generator sequential.** With the configuration above, the same three-question decision took a median **2.848 s alone** versus **5.572 s during LFM generation** (**n=5 per condition**, paired runs). Re-measure before changing the scheduling policy.
* **Calibrate the decision gate on your task.** In a 36-state synthetic check, threshold 0.5 missed 9 of 18 positive cases. This is an illustration, not production calibration. Label your app's own states, evaluate on held-out data, and do not copy thresholds between models or tasks. See [`calibrate_threshold.py`](skills/iq9-d1-decision-gate/scripts/calibrate_threshold.py).

## Quick start

On the IQ-9075, after the setup steps in the developer guide:

```bash
geniex list                                              # check what is already cached before pulling
geniex infer LiquidAI/LFM3-1.7B-GGUF:Q4_0 --compute npu
```

Then set up the decision layer: [`examples/system-one-decision`](examples/system-one-decision/README.md).

## Licensing

This repository's code and docs are under the [MIT License](LICENSE). They do not include LiquidAI model weights or model code. The models are downloaded separately, by `geniex pull` and `fetch_d1.py`, and each one keeps its own licence:

* `LiquidAI/d1-2B` and `LiquidAI/LFM3-1.7B-GGUF` are under the **LFM Open License v1.0** (`lfm1.0`). It includes a commercial-use limit for organisations above US$10M annual revenue. Read each model card's LICENSE before you publish or commercialise a demo.
* Other checkpoints may have different terms. Read the LICENSE for each selected model's weights and code; the Hub's license tag alone is not a substitute for those terms.
* GenieX is distributed by Qualcomm under its own terms.
