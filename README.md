# On-Device AI Hackathon: Cleared for Takeoff ✈️

**LiquidAI × Qualcomm Dragonwing**

Reference documentation for the hackathon: build on-device AI agents with **LiquidAI** models on the **Qualcomm Dragonwing IQ-9075 EVK**, then demonstrate them with the network removed.

> **Start here:** [`docs/developer-guide.md`](docs/developer-guide.md). Using a coding agent? Point it at [`AGENTS.md`](AGENTS.md).

## Platform and models

* **Hardware:** Dragonwing IQ-9075 EVK only (QCS9075, Hexagon v73 NPU, 36 GB LPDDR5).
* **Generator and tools:** `LiquidAI/LFM3-1.7B-GGUF` (Q4_0) via GenieX v0.10.0.
* **Decision layer:** `LiquidAI/d1-2B`, a decision model that answers typed questions in one pass with no output tokens.
* **Other LFM models** can be pulled through GenieX. Test each one on the board before a demo.

## Goals

Build intelligence that does not need the internet. The event isolates the moments where local inference creates real value:

* **Privacy:** data never leaves the board
* **Resilience:** the system keeps working when the network is down
* **Latency:** decisions happen at sensor speed, not round-trip speed
* **Autonomy:** the agent acts on its own between human prompts
* **Sensor proximity:** camera, mic, and sensor data stay local
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

| Path                            | Purpose                                                                                                                          |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `README.md`                     | This file: goals, objectives, repo map                                                                                           |
| `docs/developer-guide.md`       | Main guide: setup → first model → server → decision and generation loop → offline                                                |
| `docs/decision-models.md`       | d1-2B: question types and Path A on the IQ-9075                                                                                   |
| `docs/models.md`                | Active LFM3/d1 models plus the previous stack's measured regression baseline                                                     |
| `docs/runtimes.md`              | GenieX versions, CLI, server endpoints and request fields, benchmarking, pitfalls                                                |
| `docs/hardware.md`              | IQ-9075 facts, team board state, driver packages                                                                                 |
| `docs/offline-readiness.md`     | Pre-cut checklist and network-off rehearsal                                                                                      |
| `docs/judging.md`               | Scoring rubric, demo format, metrics to show                                                                                     |
| `examples/system-one-decision/` | Path A: `system_one()` with transformers. Installation, pinned fetch, environment check, example.                                |
| `examples/lfm-server-npu/`      | LFM3-1.7B: start `geniex serve` on the NPU, send one capped chat request, stop it                                                |
| `examples/always-on-agent/`     | The always-on loop, runnable: observe, decide (d1), act through an allowlist, explain alerts (LFM, raw completion), log to JSONL |
| `examples/tool-calling/`        | LFM3-1.7B: native `tools` calls, schema validation, allowlist, and a policy check before any write action |
| `starter/`                      | `run.sh`: checks the board, runs one decision pass and one generation, and points to the next example |
| `skills/`                       | Agent skills with tested scripts: preflight, GenieX/LFM client, d1 calibration, agent scaffold, tool calling, offline audit, demo metrics. Start with [`AGENTS.md`](AGENTS.md) |
| `AGENTS.md`                     | Instructions for coding agents: rules, skills, where to run, what to ask before doing |
| `apps/`                         | Where hackathon projects go (`skills/iq9-always-on-agent/scripts/scaffold.sh apps/<name>`) |

The event commits to a "Five-Minute Start" with an inference sample, local agent, tool-call example, and starter repository. All four pieces are included; run the migrated stack on the board before the demo.

## Known limits

* **d1-2B uses Path A in this repo.** GenieX decision serving has not been verified on the IQ-9075 with this stack.
* **Use `max_completion_tokens` on chat calls.** Cap every request and keep the zero-token retry as a defensive fallback.
* **LFM3-1.7B reasons by default.** The always-on agent uses a raw completion with the reasoning block closed; verify the output on the board before the demo.
* **Model unloads after 300 s idle** (default keepalive). The previous model's next request took about 5 s longer; measure LFM3. Change the keepalive with `--keepalive` or `GENIEX_KEEPALIVE`. See [`docs/runtimes.md`](docs/runtimes.md#server-lifecycle-model-loading-and-idle-unloading).
* **Keep the gate and generator sequential until measured.** On the previous stack, a decision rose from about 4 s alone to about 7.7 s during generation. See [`docs/developer-guide.md`](docs/developer-guide.md) §8.
* **Calibrate the new decision gate.** The previous d1-3B gate did not track the board's thermal readings; do not carry its threshold over to d1-2B. See [`examples/always-on-agent`](examples/always-on-agent/README.md).

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
* GenieX is distributed by Qualcomm under its own terms.

