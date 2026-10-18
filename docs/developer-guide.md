# Developer Guide - LiquidAI on Qualcomm Dragonwing IQ-9075

Build environment for the On-Device AI Hackathon: Cleared for Takeoff ✈️.

* Target hardware: **Dragonwing IQ-9075 EVK** only.
* Generator: LiquidAI Models (LFM2.5-2.6B GGUF suggested, but not required) via GenieX.
* Decision layer: d1-3B, run natively with transformers on the CPU. See [`decision-models.md`](decision-models.md).

## Table of contents

1. [Pre-work](#1-pre-work)
2. [Architecture](#2-architecture)
3. [Day-one setup](#3-day-one-setup)
4. [First model in five minutes](#4-first-model-in-five-minutes)
5. [Local server (OpenAI-compatible)](#5-local-server-openai-compatible)
6. [The decision layer](#6-the-decision-layer)
7. [Choosing a model](#7-choosing-a-model)
8. [Building an always-on agent](#8-building-an-always-on-agent)
9. [Tool calling](#9-tool-calling)
10. [Measuring performance](#10-measuring-performance)
11. [Running offline](#11-running-offline)
12. [Troubleshooting](#12-troubleshooting)

***

## 1. Pre-work

* GenieX quickstart: <https://geniex.aihub.qualcomm.com/en/get-started/quickstart> 
* GenieX platforms and runtimes: <https://geniex.aihub.qualcomm.com/en/get-started/platforms> 
* IQ-9075 EVK setup: <https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device> 
* LFM2.5-2.6B GGUF: <https://huggingface.co/LiquidAI/LFM2.5-2.6B-GGUF> 
* d1-3B model card: <https://huggingface.co/LiquidAI/d1-3B> 

## 2. Architecture

### 2.1 Two models, two jobs

```
Sensors · camera · logs
   │ observe
   ▼
d1-3B  — decision gate
   │     transformers system_one() on the CPU, fp32                                  4.5 s / state
   │     "alert?"  "category?"  "severity?"    calibrated, zero output tokens
   │
   ├─ below threshold ─→ no_op, log the decision
   │
   └─ above threshold ─→ LFM2.5-2.6B  (GenieX · llama_cpp · NPU)   explanation
                              │       one sentence, capped with max_completion_tokens
                              ▼
                       allowlisted action + local decision log   ← the offline proof
```

### 2.2 Runtimes and routes

| Model / route    | Runtime                           |
| ---------------- | --------------------------------- |
| LFM2.5-2.6B GGUF | GenieX `llama_cpp`, server or CLI |
| d1-3B Path A     | transformers, `trust_remote_code` |

### 2.3 Compute units

| `--compute`     | Effect                       | Use it for                                                                                        |
| --------------- | ---------------------------- | ------------------------------------------------------------------------------------------------- |
| `npu` (default) | Hexagon NPU (`HTP0`)         | Prefill and decode latency                                                                        |
| `hybrid`        | HTP and CPU split per tensor | Measured slower on decode here                                                                    |
| `cpu`           | CPU only                     | Fallback. Slow through the server (see [`runtimes.md`](runtimes.md#known-gap-server-cpu-decode)). |
| `gpu`           | Adreno via OpenCL            |                                                                                                   |

**Silent-fallback trap:** if the Hexagon driver fails to load, `--compute hybrid` still gives correct text, but it runs on the CPU with no error. Check the NPU is in use (§4). 

### 2.4 Hardware budget

* Hexagon v73 NPU and 36 GB LPDDR5 
* **Disk, not RAM, is the constraint.** Check `df -h /` before every pull. (see [`models.md`](models.md#disk-budget))

## 3. Setup

### 3.1 Confirm the board

```bash
uname -m      # aarch64
df -h /       # plan the models in models.md before pulling
free -h
geniex version   # v0.8.0 is the active install; see runtimes.md
```

### 3.2 Driver packages

Required for the NPU. Install if `geniex` reports missing libraries:

```bash
sudo apt update
sudo apt install -y libatomic1 libglib2.0-0 ocl-icd-libopencl1
sudo apt-get install -y qcom-adreno1 qcom-fastrpc1 libqnn1
```

* The Qualcomm PPA is already on the stock image. Do not add it again. 
* Check the two CDSP nodes: `ls /dev/fastrpc-cdsp*`. 
* If you get permission errors: `sudo usermod -aG fastrpc "$(id -un)"`, then log in again. 

### 3.3 GenieX CLI

```bash
curl -fsSL https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-geniex/install.sh | sh -s -- --version v0.8.0
geniex --help
geniex config get chipset     # Dragonwing IQ-9075 EVK
```

Pin `--version` to the version this guide was tested on (v0.8.0). Without it, the installer takes the newest stable release, which may differ. The installer replaces any existing install and moves the old one aside first. Per the installer source, the launcher goes to `~/.local/bin/geniex` even with `--prefix`, so a side install overwrites the active launcher. Back up the launcher first. 

### 3.4 Python environment for the decision layer

Needed for Path A:

```bash
python3 -m venv --system-site-packages ~/.venvs/d1
source ~/.venvs/d1/bin/activate
python -m pip install -r examples/system-one-decision/requirements.txt
```

The board already has torch 2.11.0 and torchvision 0.26.0 in the user site, so only transformers and its dependencies are new. Full detail in [`examples/system-one-decision/README.md`](../examples/system-one-decision/README.md).

## 4. First model in five minutes

```bash
geniex pull LiquidAI/LFM2.5-2.6B-GGUF:Q4_0
geniex infer LiquidAI/LFM2.5-2.6B-GGUF:Q4_0 --compute npu
```

Confirm the NPU is in use:

```bash
GGML_HEX_VERBOSE=1 geniex infer LiquidAI/LFM2.5-2.6B-GGUF:Q4_0 --compute npu
```

If there are no Hexagon lines, see §12.

**Do not re-pull a model you already have.** On v0.4.0 a re-pull downloaded an extra 1.6 GB QAD variant and rewrote `geniex.json`. See the pitfall in [`runtimes.md`](runtimes.md#pitfalls).

## 5. Local server (OpenAI-compatible)

```bash
geniex serve                  # http://127.0.0.1:18181 — does not download models
```

```bash
curl http://127.0.0.1:18181/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "LiquidAI/LFM2.5-2.6B-GGUF:Q4_0",
    "messages": [{"role": "user", "content": "Say hello in five words."}],
    "max_completion_tokens": 64,
    "stream": false
  }'
```

* **Use `max_completion_tokens`.** On v0.8.0 both `max_tokens` and `max_completion_tokens` work. If both are set, `max_completion_tokens` wins (measured). `max_tokens` was ignored on v0.4.0. Use `max_completion_tokens` in all examples. 
* LFM2.5-2.6B writes its reasoning into the answer. Without a cap, a one-sentence request ran to 200–1,400 tokens.
* `compute` and `power_mode` can be set per request. `burst` gave 14.4 tok/s against 11.7 at the default on v0.4.0, in one test. 
* On v0.8.0, after several identical requests the server returns zero tokens. Streamed and non-streamed calls are both affected, so switching to non-streamed does not help. Restart `geniex serve` when you see `completion_tokens: 0`, and vary the prompt (see [`runtimes.md`](runtimes.md#known-gap-zero-token-responses-on-v080)).
* **Idle unloading.** The model unloads after 300 s with no requests, so the next request takes about 5 s longer. Change it with `--keepalive` or `GENIEX_KEEPALIVE` when you start the server. See [`runtimes.md`](runtimes.md#server-lifecycle-model-loading-and-idle-unloading). 
* Any OpenAI-compatible client works. Point it at `http://127.0.0.1:18181/v1`.
* A runnable version that starts the server on the NPU, sends one capped request, and stops it: [`examples/lfm-server-npu`](../examples/lfm-server-npu/README.md).

## 6. The decision layer

Path A is the decision route on the board. It runs d1-3B natively with transformers on the CPU in fp32: about 4.5 s per state (three questions, one pass, zero output tokens). It does not use GenieX.

```python
import json, os, sys
import torch
from transformers import AutoModel

sys.path.insert(0, "examples/system-one-decision")
from system_one_example import SENSOR_QUESTIONS   # alert, category, severity

model = AutoModel.from_pretrained(os.path.expanduser("~/models/d1-3B"), trust_remote_code=True, dtype=torch.float32)
model = model.to("cpu").eval()

obs = {"temp_c": 71.5, "temp_c_1min_ago": 58.0, "motion": "none"}
with torch.inference_mode():
    answers = model.system_one(json.dumps(obs), SENSOR_QUESTIONS)["answers"]
print(answers["alert"]["noul"], answers["category"]["choice"], answers["severity"]["score"])
```

Path A details, including the image question: [`examples/system-one-decision`](../examples/system-one-decision/README.md).

The GenieX endpoint `POST /v1/systemone` is absent from v0.4.0 and v0.8.0. Don't build on it. 

## 7. Choosing a model

| Use case                           | Start with                          |
| ---------------------------------- | ----------------------------------- |
| General generator and explanations | `LFM2.5-2.6B-GGUF` Q4_0 (1,594 MB)  |
| Decision gate                      | `d1-3B`, Path A on the CPU          |
| Smallest footprint                 | `LFM2.5-350M-GGUF` Q4_0 (219 MB)    |
| Camera and image questions         | `LFM2.5-VL-1.6B-GGUF`               |
| Tool-call experiments              | `LFM2-1.2B-Tool-GGUF` Q4_0 (696 MB) |

Results and sizes: [`models.md`](models.md).

## 8. Building an always-on agent

The loop: **observe** → **decide** (d1) → **explain** (LFM, only when needed) → **act** (allowlisted) → **log**.

Design rules:

1. **Decide before you generate.** The gate runs on every observation. The generator runs only when the decision says an explanation is worth it.
2. **Threshold probabilities, tuned locally.** Don't copy numbers from a model card or another project.
3. **Constrain actions.** The agent can only do what is on its allowlist.
4. **Log every observation and decision.** The log is the offline proof judges will look at.
5. **Cap generation.** Cap every LFM call: `max_tokens` on `/v1/completions` (the explanation path) and `max_completion_tokens` on chat. For one-sentence answers, use a raw completion with the reasoning block closed ([runtimes.md](runtimes.md)).
6. **Degrade gracefully.** If the generator times out, log the decision and keep the sensor loop running.

The runnable version is [`examples/always-on-agent`](../examples/always-on-agent/README.md). It is the same loop: observe, decide with d1, act through an allowlist, explain only alerts, and log each iteration as JSON. On the IQ-9075 it ran 8 iterations with simulated sensors (3 alerts, all explained) and 14 iterations with a fixed hot state (the zero-token replies were all recovered by the retry). The observation is the board's own thermal telemetry, so no extra hardware is needed. The d1 gate does not track these temperatures (measured; see the always-on example), so its alerts are not usable as-is. The explanation uses a raw completion, not the chat endpoint, because chat replies carry reasoning text ([details](../examples/always-on-agent/README.md#explanations-why-a-raw-completion)).

What to check on the board before trusting this loop:

* The decision latency per iteration (about 4.5 s per state on the CPU, measured with fp32) and the explanation latency at your cap: about 2.8 s for 64 tokens and 5.9 s for 128 tokens on a warm v0.8.0 server, streamed or non-streamed. The first call after `geniex serve` starts adds about 5 s for the model load. 
* That the gate and the generator don't slow each other down when both run. Not free. A decision took **7.7 s** while a generation ran alongside, against **4.1 s** alone. The generator barely changed: 3.2 s against 3.0 s. Lowering torch threads from 8 to 4 did not help (7.5 s), so CPU oversubscription is not the cause. The sequential loop above never runs the two at once. Its iterations take about 4 s with no alert and about 7 s with one. If you move explanations into a separate thread or process, budget about 7.5 s per decision during them.

## 9. Tool calling

* **GenieX parses tool calls for you.** Send the OpenAI `tools` array to `/v1/chat/completions`, and the reply carries `message.tool_calls` with `finish_reason: "tool_calls"`. Confirmed with `LiquidAI/LFM2-1.2B-Tool-GGUF:Q4_0` on v0.8.0.
* Measured on the IQ-9075: about 0.9 s per model turn (median, warm server).
* **Don't let the model decide whether to act.** In our tests it chose to alert on 12 of 12 readings, including 39 °C. Without making a tool call, it said it had logged an alert in 4 of 7 runs. Validate every call against its schema, run only allowlisted tools, check write actions against a rule in code, and report what ran from your own record.
* Keep the tool list to 3–5 functions for small models.
* Test tool calls with the network off.

Runnable version, with measured behaviour: [`examples/tool-calling`](../examples/tool-calling/README.md).

## 10. Measuring performance

`geniex-bench` measures TTFT, prefill, and decode for GGUF models on `llama_cpp`. Match its version to the runtime you are using: v0.8.0 for the active install (22.6 tok/s decode on the NPU bench, 23.4 streamed on the server). The v0.4.0 bench shows 14.3 tok/s.

```bash
D=~/geniex-bench-linux-arm64-v0.8.0          # matches the active install
export LD_LIBRARY_PATH=$D/lib:$D/lib/llama_cpp:$D/lib/qairt
$D/bin/geniex-bench --plugin llama_cpp --device npu -m LiquidAI/LFM2.5-2.6B-GGUF:Q4_0 -r 5 -p 512 -n 128
```

* Defaults: 5 measured runs, 512-token prefill, 128 generated tokens. The summary line is the median.
* The bench does not measure d1. Measure Path A with `system_one_example.py` (about 4.5 s per state on the CPU).
* Record the numbers in [`models.md`](models.md).

## 11. Running offline

1. Pull every model and install every package while the network is up.
2. Point code at local paths: a `.gguf` in the GenieX cache for LFM, and the local snapshot at `~/models/d1-3B` for Path A.
3. Turn the network off and run the whole loop once.

Full checklist: [`offline-readiness.md`](offline-readiness.md).

## 12. Troubleshooting

| Symptom                                                                       | Likely cause                                                                                                | Fix                                                                                                                                       |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `geniex: command not found`                                                   | `PATH` not updated                                                                                          | Open a new shell, or add the printed `PATH` line                                                                                          |
| Missing `libCB.so.1`, `libOpenCL_adreno.so.1`, or `libcdsprpc.so.1.0.0`       | Driver packages missing                                                                                     | `sudo apt-get install -y qcom-adreno1 qcom-fastrpc1 libqnn1`                                                                              |
| Permission denied on `/dev/fastrpc-cdsp`                                      | User not in `fastrpc` group                                                                                 | `sudo usermod -aG fastrpc "$(id -un)"`, then log in again                                                                                 |
| Works but slow; no Hexagon lines with `GGML_HEX_VERBOSE=1`                    | Silent CPU fallback                                                                                         | Fix the driver packages and recheck                                                                                                       |
| Output runs to hundreds of tokens                                             | No cap set (LFM2.5-2.6B writes its reasoning into the reply), or `max_tokens` on v0.4.0, which ignored it    | Set `max_completion_tokens` on every call                                                                                                 |
| `POST /v1/systemone` returns 404                                              | Endpoint not in v0.4.0 or v0.8.0                                                                            | Use Path A                                                                                                                                |
| Replies with `completion_tokens: 0` after several identical requests (v0.8.0) | Server state after repeated identical prompts. Streamed and non-streamed both affected. Cause not confirmed | Restart `geniex serve`; vary the prompt. See [`runtimes.md`](runtimes.md#known-gap-zero-token-responses-on-v080)                          |
| First request after a pause or a start takes about 5 s longer                 | Model load, or idle unloading after the keepalive (300 s default)                                           | Expected. Change `--keepalive` or `GENIEX_KEEPALIVE`; see [`runtimes.md`](runtimes.md#server-lifecycle-model-loading-and-idle-unloading)  |
| `geniex-bench: libgeniex.so: not found`                                       | Bench libraries not on the path                                                                             | `export LD_LIBRARY_PATH=$D/lib:$D/lib/llama_cpp:$D/lib/qairt`                                                                             |
| Extra `…-QAD-Q4_0.gguf` in the cache after a re-pull                          | Known v0.4.0 pull behaviour                                                                                 | Remove it as described in [`runtimes.md`](runtimes.md#pitfalls)                                                                           |
| `No space left on device`                                                     | Staged models exceed free disk                                                                              | Check `geniex list`, then remove unused models                                                                                            |
| `ImportError` for transformers or torchvision                                 | Venv not set up                                                                                             | Recreate it from §3.4                                                                                                                     |
| d1 load asks for remote code approval                                         | `trust_remote_code` not set                                                                                 | Set `trust_remote_code=True` after reviewing the code                                                                                     |
