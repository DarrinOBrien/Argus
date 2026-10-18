# On-Device AI Hackathon: Cleared for Takeoff ✈️

**LiquidAI × Qualcomm Dragonwing**

Reference documentation for the hackathon: build on-device AI agents with **LiquidAI** models on the **Qualcomm Dragonwing IQ-9075 EVK**, then demonstrate them with the network removed.

> **Start here:** [`docs/developer-guide.md`](docs/developer-guide.md). Using a coding agent? Point it at [`AGENTS.md`](AGENTS.md).

## Platform and models

* **Hardware:** Dragonwing IQ-9075 EVK only (QCS9075, Hexagon v73 NPU, 36 GB LPDDR5).
* **Generator:** `LiquidAI/LFM2.5-2.6B-GGUF` (Q4_0) via GenieX v0.8.0.&#x20;
* **Decision layer:** `LiquidAI/d1-3B`, a decision model that answers yes/no, category, and severity questions in one pass with no output tokens.
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
| `docs/decision-models.md`       | d1-3B: question types, Path A on the IQ-9075, disk and memory budget                                                             |
| `docs/models.md`                | LiquidAI catalog: the recommended 2.6B with measured numbers, d1, other LFM models                                               |
| `docs/runtimes.md`              | GenieX versions, CLI, server endpoints and request fields, benchmarking, pitfalls                                                |
| `docs/hardware.md`              | IQ-9075 facts, team board state, driver packages                                                                                 |
| `docs/offline-readiness.md`     | Pre-cut checklist and network-off rehearsal                                                                                      |
| `docs/judging.md`               | Scoring rubric, demo format, metrics to show                                                                                     |
| `examples/system-one-decision/` | Path A: `system_one()` with transformers. Installation, pinned fetch, environment check, example.                                |
| `examples/lfm-server-npu/`      | LFM2.5-2.6B: start `geniex serve` on the NPU, send one capped chat request, stop it                                              |
| `examples/always-on-agent/`     | The always-on loop, runnable: observe, decide (d1), act through an allowlist, explain alerts (LFM, raw completion), log to JSONL |
| `examples/tool-calling/`        | LFM2-1.2B-Tool: native `tools` calls, schema validation, allowlist, and a policy check before any write action |
| `starter/`                      | `run.sh`: checks the board, runs one decision pass and one generation, and points to the next example |
| `skills/`                       | Agent skills with tested scripts: preflight, GenieX/LFM client, d1 calibration, agent scaffold, tool calling, offline audit, demo metrics. Start with [`AGENTS.md`](AGENTS.md) |
| `AGENTS.md`                     | Instructions for coding agents: rules, skills, where to run, what to ask before doing |
| `apps/`                         | Where hackathon projects go (`skills/iq9-always-on-agent/scripts/scaffold.sh apps/<name>`) |

The event commits to a "Five-Minute Start" in which an inference sample, local agent, tool-call example, and starter repository already work. All four pieces are included in this repository.

## Known limits

* **`POST /v1/systemone` is not available** in GenieX v0.4.0 or v0.8.0 (the latest stable release). Use Path A for decisions.
* **`max_tokens` was ignored on v0.4.0.** It works on v0.8.0. If both fields are set, `max_completion_tokens` wins. Use `max_completion_tokens` in all examples.
* **LFM2.5-2.6B writes its reasoning into the answer.** Cap every call. Chat replies carry the reasoning; the always-on agent uses a raw completion with the reasoning block closed (see [`examples/always-on-agent`](examples/always-on-agent/README.md)).
* **Zero-token replies on v0.8.0.** After several identical requests, `geniex serve` returns HTTP 200 with no tokens. This affects streamed and non-streamed calls alike. Restart the server and vary the prompt. See [`docs/runtimes.md`](docs/runtimes.md#known-gap-zero-token-responses-on-v080).
* **Model unloads after 300 s idle** (default keepalive). The next request takes about 5 s longer. Change it with `--keepalive` or `GENIEX_KEEPALIVE`. See [`docs/runtimes.md`](docs/runtimes.md#server-lifecycle-model-loading-and-idle-unloading).
* **The decision gate slows down while the generator runs.** Measured on the IQ-9075: about 4 s per decision alone and about 7.7 s during a generation. The generator is barely affected. Keep the loop sequential (gate, then explanation). See [`docs/developer-guide.md`](docs/developer-guide.md) §8.
* **The decision gate does not track board temperature.** Measured on the IQ-9075: on the board's own readings, it alerted on most states and its probability did not follow temperature. Calibrate on labeled board data before use. See [`examples/always-on-agent`](examples/always-on-agent/README.md).

## Quick start

On the IQ-9075, after the setup steps in the developer guide:

```bash
geniex list                                              # check what is already cached before pulling
geniex infer LiquidAI/LFM2.5-2.6B-GGUF:Q4_0 --compute npu
```

Then set up the decision layer: [`examples/system-one-decision`](examples/system-one-decision/README.md).

## Licensing

This repository's code and docs are under the [MIT License](LICENSE). They do not include LiquidAI model weights or model code. The models are downloaded separately, by `geniex pull` and `fetch_d1.py`, and each one keeps its own licence:

* `LiquidAI/d1-3B`, `LiquidAI/LFM2.5-2.6B-GGUF`, and `LiquidAI/LFM2-1.2B-Tool-GGUF` are under the **LFM Open License v1.0** (`lfm1.0`). It includes a commercial-use limit for organisations above US$10M annual revenue. Read each model card's LICENSE before you publish or commercialise a demo.
* GenieX is distributed by Qualcomm under its own terms.

