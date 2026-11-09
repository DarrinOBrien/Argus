# On-Device AI Hackathon: Cleared for Takeoff

**LiquidAI × Qualcomm Dragonwing**

Reference documentation for the hackathon: build on-device AI agents with **LiquidAI** models on the **Qualcomm Dragonwing IQ-9075 EVK**, then demonstrate them with the network removed.

> **Start here:** [`docs/developer-guide.md`](docs/developer-guide.md). Using a coding agent? Open this repo in your agent and use the prompt below. [`AGENTS.md`](AGENTS.md) and the [getting-started skill](skills/iq9-getting-started/SKILL.md) guide it through access, setup, and verification.

## Get started with your agent

> Let's get started with this repo on my IQ9. Read `AGENTS.md` and `docs/developer-guide.md`.
>
> First, help me access the board and get it connected to the internet for setup. Ask what connections I have available and guide me through any manual steps.
>
> Then check what's already installed and propose a setup plan. Reuse existing software and models, and ask before installations, downloads, or system and network changes.
>
> Start with the reference LFM generator; leave d1 optional. Verify a useful local response and confirm NPU execution, then summarize what's working, what remains unverified, and which example to try next.

No SSH connection yet? Start with the board's **micro-USB debug UART**, then configure Wi-Fi with `nmcli` or use Ethernet. Event boards use username **`ubuntu`**, password **`liquidxqualcomm`** for UART and SSH. See [board access and internet for setup](docs/developer-guide.md#0-board-access-and-internet-for-setup) for host-specific steps, password handling, and network checks. Internet is for approved setup/staging; the final demo still runs without external network access.

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

**Start from working examples:** First complete [generator setup and verification](skills/iq9-getting-started/SKILL.md#5-verify-the-first-generator-milestone), without requiring d1. Then explore model requests, a local agent, or guarded tool calling. `./starter/run.sh` is an optional **full two-model reference check** after setting up both LFM and d1, not the first onboarding step.

## Developer Notes

### External monitors and headless setups

**Organizer-reported setup issue:** the current Adreno APT update causes a GPU-driver issue when using an external monitor on the IQ-9075. Teams using a monitor must **remove/roll back the Adreno APT update** before using that setup. This repo's setup recipes no longer recommend installing/updating `qcom-adreno1`. Check installed versions and confirm the removal/rollback procedure with the organizers and board owner before changing drivers; the affected/fixed package versions are not recorded here.

**SSH is not affected by this monitor issue.** A headless setup using SSH and an app web server over a configured **USB-C network link** is allowed during the network-off demo. Keep the link local-only: disable internet sharing/forwarding on the laptop and remove all external uplinks. Serve UI assets locally and keep inference on the board. See [display and USB-C access](docs/offline-readiness.md#display-and-usb-c-access) for the checklist and SSH port forwarding.

### Rules for the reference stack

These apply to GenieX v0.10.0 with LFM3-1.7B Q4_0 on the NPU and, if used, d1-2B on the CPU. Re-check them for any other model or runtime.

* **Run d1-2B through Transformers on the CPU**, not GenieX's `/v1/decisions` or `/v1/systemone` endpoints.
* **Cap every request and validate the answer.** Use `max_completion_tokens` on chat and `max_tokens` on raw completions. A reply can report tokens and still have empty `content`: treat that as a failure for text requests, and validate `tool_calls` for tool requests. Keep one retry as a fallback.
* **LFM3-1.7B reasons by default.** For direct answers, use `enable_think: false` on chat or a raw completion with the reasoning block closed. Neither guarantees a usable answer, so check `content`.
* **Make raw-completion prompts unique.** Identical `/v1/completions` prompts can return continuing commentary instead of a fresh answer. Add an event timestamp or tag.
* **Plan for idle unloading.** The default keepalive is 300 s. Set `--keepalive` or `GENIEX_KEEPALIVE` longer than the demo's quiet gaps, or send a warm-up request. See [`docs/runtimes.md`](docs/runtimes.md#server-lifecycle-model-loading-and-idle-unloading).
* **Run the decision gate and the generator one at a time.** d1 slows down substantially while the LFM is generating.
* **Calibrate the decision gate on your own task.** Do not use 0.5 or another app's threshold. Label your app's states and evaluate on held-out data with [`calibrate_threshold.py`](skills/iq9-d1-decision-gate/scripts/calibrate_threshold.py).

## Quick start

On the IQ-9075, after the [setup steps](docs/developer-guide.md#3-setup), from the repo root:

```bash
bash skills/iq9-preflight/scripts/preflight.sh --profile generator --json
```

Reuse an appropriate existing server, or run this in a separate board terminal:

```bash
skills/iq9-geniex-lfm/scripts/serve.sh run
```

Then send a capped, validated request and inspect the current server's NPU evidence:

```bash
python3 skills/iq9-geniex-lfm/scripts/lfm_client.py --sentence 'Explain why local inference is useful when the internet is unavailable.'
skills/iq9-geniex-lfm/scripts/serve.sh status
```

Check the answer and the current server's `HTP0` log line; a preflight pass alone is not verification. See the [generator skill](skills/iq9-geniex-lfm/SKILL.md) for server reuse and output guards. If your project needs d1, set it up separately with [`examples/system-one-decision`](examples/system-one-decision/README.md); it is optional.

## Licensing

This repository's code and docs are under the [MIT License](LICENSE). They do not include LiquidAI model weights or model code. The models are downloaded separately, by `geniex pull` and `fetch_d1.py`, and each one keeps its own licence:

* `LiquidAI/d1-2B` and `LiquidAI/LFM3-1.7B-GGUF` are under the **LFM Open License v1.0** (`lfm1.0`). It includes a commercial-use limit for organisations above US$10M annual revenue. Read each model card's LICENSE before you publish or commercialise a demo.
* Other checkpoints may have different terms. Read the LICENSE for each selected model's weights and code; the Hub's license tag alone is not a substitute for those terms.
* GenieX is distributed by Qualcomm under its own terms.
