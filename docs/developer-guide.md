# Developer Guide - LiquidAI on Qualcomm Dragonwing IQ-9075

Build environment for the On-Device AI Hackathon: Cleared for Takeoff ✈️.

* Target hardware: **Dragonwing IQ-9075 EVK** only.
* Generator and tools: LFM3-1.7B GGUF via GenieX.
* Decision layer: d1-2B, run natively with transformers on the CPU. See [`decision-models.md`](decision-models.md).

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
* LFM3-1.7B GGUF: <https://huggingface.co/LiquidAI/LFM3-1.7B-GGUF>
* d1-2B model card: <https://huggingface.co/LiquidAI/d1-2B>

## 2. Architecture

### 2.1 Two models, two jobs

```
Sensors · camera · logs
   │ observe
   ▼
d1-2B  — decision gate
   │     transformers system_one() on the CPU, fp32                    measure on board
   │     "alert?"  "category?"  "severity?"    calibrated, zero output tokens
   │
   ├─ below threshold ─→ no_op, log the decision
   │
   └─ above threshold ─→ LFM3-1.7B  (GenieX · llama_cpp · NPU)   explanation or tool call
                              │       one sentence, capped with max_completion_tokens
                              ▼
                       allowlisted action + local decision log   ← the offline proof
```

### 2.2 Runtimes and routes

| Model / route    | Runtime                           |
| ---------------- | --------------------------------- |
| LFM3-1.7B GGUF | GenieX `llama_cpp`, server or CLI |
| d1-2B Path A    | transformers, `trust_remote_code` |

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
geniex version   # v0.10.0 is the migration target; see runtimes.md
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
curl -fsSL https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-geniex/install.sh | sh -s -- --version v0.10.0
geniex --help
geniex config get chipset     # Dragonwing IQ-9075 EVK
```

Pin `--version` to v0.10.0 for this migration. The installer replaces any existing install and moves the old one aside first, so back up the known-good v0.8.0 install before changing the board.

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
geniex pull LiquidAI/LFM3-1.7B-GGUF:Q4_0
geniex infer LiquidAI/LFM3-1.7B-GGUF:Q4_0 --compute npu
```

Confirm the NPU is in use:

```bash
GGML_HEX_VERBOSE=1 geniex infer LiquidAI/LFM3-1.7B-GGUF:Q4_0 --compute npu
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
    "model": "LiquidAI/LFM3-1.7B-GGUF:Q4_0",
    "messages": [{"role": "user", "content": "Say hello in five words."}],
    "max_completion_tokens": 64,
    "stream": false
  }'
```

* **Use `max_completion_tokens`.** Cap every chat call; use `max_tokens` on raw completions.
* LFM3-1.7B reasons by default. Inspect the board output and keep the cap.
* `compute` and `power_mode` can be set per request. On the legacy v0.4.0 stack, `burst` gave 14.4 tok/s against 11.7 at the default in one test.
* On v0.8.0, after several identical requests the server returns zero tokens. Streamed and non-streamed calls are both affected, so switching to non-streamed does not help. Restart `geniex serve` when you see `completion_tokens: 0`, and vary the prompt (see [`runtimes.md`](runtimes.md#known-gap-zero-token-responses-on-v080)).
* **Idle unloading.** The model unloads after 300 s with no requests. The legacy model's next request took about 5 s longer; measure LFM3. Change the timeout with `--keepalive` or `GENIEX_KEEPALIVE`. See [`runtimes.md`](runtimes.md#server-lifecycle-model-loading-and-idle-unloading).
* Any OpenAI-compatible client works. Point it at `http://127.0.0.1:18181/v1`.
* A runnable version that starts the server on the NPU, sends one capped request, and stops it: [`examples/lfm-server-npu`](../examples/lfm-server-npu/README.md).

## 6. The decision layer

Path A is the decision route on the board. It runs d1-2B natively with transformers on the CPU in fp32 and does not use GenieX. Measure latency and peak RSS on the board.

```python
import json, os, sys
import torch
from transformers import AutoModel

sys.path.insert(0, "examples/system-one-decision")
from system_one_example import SENSOR_QUESTIONS   # alert, category, severity

model = AutoModel.from_pretrained(os.path.expanduser("~/models/d1-2B"), trust_remote_code=True, dtype=torch.float32)
model = model.to("cpu").eval()

obs = {"temp_c": 71.5, "temp_c_1min_ago": 58.0, "motion": "none"}
with torch.inference_mode():
    answers = model.system_one(json.dumps(obs), SENSOR_QUESTIONS)["answers"]
print(answers["alert"]["noul"], answers["category"]["choice"], answers["severity"]["score"])
```

Path A details, including the image question: [`examples/system-one-decision`](../examples/system-one-decision/README.md).

GenieX decision serving is not yet verified with d1-2B on the IQ-9075, so this repo keeps Path A.

## 7. Choosing a model

| Use case                           | Start with                          |
| ---------------------------------- | ----------------------------------- |
| General generator and explanations | `LFM3-1.7B-GGUF` Q4_0 (~1.05 GB)    |
| Decision gate                      | `d1-2B`, Path A on the CPU          |
| Smallest footprint                 | `LFM2.5-350M-GGUF` Q4_0 (219 MB)    |
| Camera and image questions         | `LFM2.5-VL-1.6B-GGUF`               |
| Tool calls                         | `LFM3-1.7B-GGUF` Q4_0 (shared)      |

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

The runnable version is [`examples/always-on-agent`](../examples/always-on-agent/README.md). It observes, decides with d1, acts through an allowlist, explains only alerts, and logs each iteration as JSON. The previous LFM2.5/d1-3B measurements in that README are a regression baseline; re-run them for LFM3/d1-2B.

What to check on the board before trusting this loop:

* Decision and explanation latency at the configured caps, cold-start cost, and peak memory.
* Whether the gate and generator slow each other down. Keep the loop sequential until measured.

## 9. Tool calling

* Send the OpenAI `tools` array to `/v1/chat/completions` and require `message.tool_calls` with `finish_reason: "tool_calls"`. Verify LFM3 parsing on the board.
* **Don't let the model decide whether to act.** In our tests it chose to alert on 12 of 12 readings, including 39 °C. Without making a tool call, it said it had logged an alert in 4 of 7 runs. Validate every call against its schema, run only allowlisted tools, check write actions against a rule in code, and report what ran from your own record.
* Keep the tool list to 3–5 functions for small models.
* Test tool calls with the network off.

Runnable version, with code-side self-tests and the legacy model baseline: [`examples/tool-calling`](../examples/tool-calling/README.md).

## 10. Measuring performance

`geniex-bench` measures TTFT, prefill, and decode for GGUF models on `llama_cpp`. Match its version to v0.10.0 and report only the new measurements.

```bash
D=~/geniex-bench-linux-arm64-v0.10.0
export LD_LIBRARY_PATH=$D/lib:$D/lib/llama_cpp:$D/lib/qairt
$D/bin/geniex-bench --plugin llama_cpp --device npu -m LiquidAI/LFM3-1.7B-GGUF:Q4_0 -r 5 -p 512 -n 128
```

* Defaults: 5 measured runs, 512-token prefill, 128 generated tokens. The summary line is the median.
* The bench does not measure d1. Measure Path A with `system_one_example.py`.
* Record the numbers in [`models.md`](models.md).

## 11. Running offline

1. Pull every model and install every package while the network is up.
2. Point code at local paths: a `.gguf` in the GenieX cache for LFM, and the local snapshot at `~/models/d1-2B` for Path A.
3. Turn the network off and run the whole loop once.

Full checklist: [`offline-readiness.md`](offline-readiness.md).

## 12. Troubleshooting

| Symptom                                                                       | Likely cause                                                                                                | Fix                                                                                                                                       |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `geniex: command not found`                                                   | `PATH` not updated                                                                                          | Open a new shell, or add the printed `PATH` line                                                                                          |
| Missing `libCB.so.1`, `libOpenCL_adreno.so.1`, or `libcdsprpc.so.1.0.0`       | Driver packages missing                                                                                     | `sudo apt-get install -y qcom-adreno1 qcom-fastrpc1 libqnn1`                                                                              |
| Permission denied on `/dev/fastrpc-cdsp`                                      | User not in `fastrpc` group                                                                                 | `sudo usermod -aG fastrpc "$(id -un)"`, then log in again                                                                                 |
| Works but slow; no Hexagon lines with `GGML_HEX_VERBOSE=1`                    | Silent CPU fallback                                                                                         | Fix the driver packages and recheck                                                                                                       |
| Output runs to hundreds of tokens                                             | No cap set, or the reasoning trace is included                                                               | Set `max_completion_tokens` on chat and `max_tokens` on raw completions                                                                  |
| `POST /v1/systemone` fails                                                    | Decision serving is not configured or verified                                                               | Use Path A                                                                                                                                |
| Replies with `completion_tokens: 0` after several identical requests (v0.8.0) | Server state after repeated identical prompts. Streamed and non-streamed both affected. Cause not confirmed | Restart `geniex serve`; vary the prompt. See [`runtimes.md`](runtimes.md#known-gap-zero-token-responses-on-v080)                          |
| First request after a pause or start is slower                                | Model load, or idle unloading after the keepalive (300 s default)                                           | Expected; measure the LFM3 delay. Change `--keepalive` or `GENIEX_KEEPALIVE`; see [`runtimes.md`](runtimes.md#server-lifecycle-model-loading-and-idle-unloading)  |
| `geniex-bench: libgeniex.so: not found`                                       | Bench libraries not on the path                                                                             | `export LD_LIBRARY_PATH=$D/lib:$D/lib/llama_cpp:$D/lib/qairt`                                                                             |
| Extra `…-QAD-Q4_0.gguf` in the cache after a re-pull                          | Known v0.4.0 pull behaviour                                                                                 | Remove it as described in [`runtimes.md`](runtimes.md#pitfalls)                                                                           |
| `No space left on device`                                                     | Staged models exceed free disk                                                                              | Check `geniex list`, then remove unused models                                                                                            |
| `ImportError` for transformers or torchvision                                 | Venv not set up                                                                                             | Recreate it from §3.4                                                                                                                     |
| d1 load asks for remote code approval                                         | `trust_remote_code` not set                                                                                 | Set `trust_remote_code=True` after reviewing the code                                                                                     |
