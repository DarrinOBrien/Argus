# Models — LiquidAI on the IQ-9075

Recommended generator and tool model: **LFM3-1.7B GGUF via GenieX**. Decision layer: **d1-2B** (see [`decision-models.md`](decision-models.md)). This migrated stack is not yet measured on the reference board; the older LFM2.5/d1-3B measurements remain below as a regression baseline.

Markers: ✅ confirmed in docs, model card, or the Hub · 🧪 measured on a reference IQ-9075 (numbers below) · ⚠️ not yet verified.

**Source:** repo IDs, sizes, and licence tags from the public Hugging Face API. Sizes are GGUF file sizes unless noted. ✅

## LFM3-1.7B — generator and tools

| Model | Precision | Size | Status |
|---|---|---:|---|
| `LiquidAI/LFM3-1.7B-GGUF` | **QAD-Q4_0** | 1.05 GB | Upstream QAD build; GenieX model ID uses `:Q4_0`. ⚠️ IQ-9075 performance unverified |
| `LiquidAI/LFM3-1.7B-GGUF` | Q4_K_M | 1.10 GB | Upstream llama.cpp option; Hexagon path unverified |
| `LiquidAI/LFM3-1.7B-GGUF` | Q8_0 | 1.85 GB | Larger reference option |

The same checkpoint handles explanations and tool calls, replacing two cached models. Cap every request, validate every tool call, and measure native `tool_calls` parsing on the board.

## Legacy baseline: LFM2.5-2.6B

| Model | Precision | Size | Status |
|---|---|---:|---|
| `LiquidAI/LFM2.5-2.6B-GGUF` | **Q4_0** | 1,594 MB | 🧪 recommended. The GenieX recommendation for Hexagon. ✅ |
| `LiquidAI/LFM2.5-2.6B-GGUF` | Q8_0 | 2,875 MB | Optional. Larger than Q4_0 and not used by the examples. |
| `LiquidAI/LFM2.5-2.6B-GGUF` | QAD-Q4_0 | 1,594 MB | ⚠️ a separate download; see the pitfall in [`runtimes.md`](runtimes.md#pitfalls) |
| `LiquidAI/LFM2.5-2.6B-GGUF` | F16 | 5,403 MB | Reference only |

### IQ-9075 results (GenieX v0.4.0, Q4_0)

Measured with `geniex-bench` and the running server on v0.4.0:

| Route | TTFT (512-token prompt) | Prefill | Decode | Peak RSS (process) |
|---|---:|---:|---:|---:|
| **NPU** (`--device npu`) | **0.70 s** | **728 tok/s** | **14.3 tok/s** | 0.73 GB (device buffers are not in RSS) |
| CPU (`--device cpu`) | 3.95 s | 130 tok/s | 27.1 tok/s | 3.38 GB |
| hybrid (`--device hybrid`) | 1.99 s | 257 tok/s | 12.3 tok/s | 0.74 GB |

Memory growth over the idle system, sampled once per second during the v0.8.0 bench run: CPU +1.7 GB, NPU +2.5 GB. ✅ (measured)

**Server path on v0.4.0, same model, `max_completion_tokens` set:**

| Route | First token (warm, streamed; system prompt plus one alert JSON) | Decode (streamed) |
|---|---:|---:|
| NPU | ~220 ms | 14.4 tok/s |
| hybrid | — | 8.5 tok/s |
| CPU | — | 2.8 tok/s ⚠️ see the CPU gap in [`runtimes.md`](runtimes.md#known-gap-server-cpu-decode) |

The server's NPU decode matches the bench (14.3 vs 14.4 tok/s), so the server adds little overhead. The first request after a model load adds about 3 s.

### Runtime version matters for NPU decode

| Bench / runtime | NPU decode | NPU TTFT | Notes |
|---|---:|---:|---|
| v0.4.0 (earlier runtime) | 14.3 tok/s | 0.70 s | bench matches the v0.4.0 server ✅ |
| v0.8.0 (legacy) | 22.6 tok/s bench · 23.4 tok/s streamed on the server | 0.66 s bench · 0.13–0.16 s streamed | 58% faster decode. ✅ |

These measurements do not apply to LFM3 or GenieX v0.10.0. The d1 decision check runs on the CPU (Path A) and does not depend on GenieX.

### Behaviour to plan for

- **LFM2.5-2.6B writes its reasoning into the answer.** A "one plain sentence" request returned 200–1,400 tokens. Cap every call with `max_completion_tokens` (`max_tokens` was ignored on v0.4.0 and works on v0.8.0). ✅ (measured) Chat replies carry the reasoning text. A raw completion with the reasoning block closed returns the answer directly (see [`examples/always-on-agent`](../examples/always-on-agent/README.md#explanations-why-a-raw-completion)).
- **Latency on a warm server.** Decode is about 23 tok/s on v0.8.0 (bench and streamed). Measured on the IQ-9075 with a warm server: 64 tokens in about 2.8 s, and 128 tokens in about 5.6–5.9 s, streamed or non-streamed. The first request after `geniex serve` starts adds about 5 s for the model load. The earlier 11.6 tok/s figure came from a cold-start run. ✅ (measured)
- ⚠️ Not tested: whether another LFM variant (for example LFM2.5-1.2B-Instruct) answers more concisely.

## d1-2B — the decision layer

| Model | Format | Size | Status on the IQ-9075 |
|---|---|---:|---|
| `LiquidAI/d1-2B` | safetensors (Path A, transformers, fp32 on CPU) | 3,836 MB | ⚠️ code migrated; latency and peak RSS unverified on IQ-9075 |

Details: [`decision-models.md`](decision-models.md).

## Other LFM models

Any of these can be pulled with `geniex pull <repo>:Q4_0`. Each one must be tested on the board before a demo. ⚠️

| Model | Modality | Q4_0 size | Notes |
|---|---|---:|---|
| `LiquidAI/LFM2.5-350M-GGUF` | Text | 219 MB | Lowest footprint. Q8_0 is 379 MB. |
| `LiquidAI/LFM2.5-1.2B-Instruct-GGUF` | Text | 696 MB | Q8_0 is 1,246 MB. |
| `LiquidAI/LFM2.5-1.2B-Thinking-GGUF` | Text, reasoning | 696 MB | |
| `LiquidAI/LFM2-1.2B-Tool-GGUF` | Text, tool-tuned | 696 MB | Legacy rollback model. 🧪 Native `tools` parsing worked on v0.8.0, about 0.9 s per turn |
| `LiquidAI/LFM2.5-VL-450M-GGUF` | Vision | 219 MB + mmproj 103 MB | `geniex model set-type <model> vlm` for images ✅ |
| `LiquidAI/LFM2.5-VL-1.6B-GGUF` | Vision | 696 MB + mmproj 583 MB | |
| `LiquidAI/LFM2.5-Audio-1.5B-GGUF` | Audio | 696 MB + mmproj 220 MB + tokenizer 51 MB + vocoder 109 MB | Four files. Audio input is llama.cpp-only in GenieX. ✅ |
| `LiquidAI/LFM2.5-8B-A1B-GGUF` | Text, MoE | 4,845 MB | MoE "A" suffixes name active parameters. Confirm on the card. ⚠️ |
| `LiquidAI/LFM2-24B-A2B-GGUF` | Text, MoE | 13,467 MB | Large. Check free space before pulling. |
| `LiquidAI/d1-omni-600M-GGUF` | Vision decision model | Q8_0 407 MB + mmproj 263 MB | Smaller d1 variant. Not evaluated. |

## Precision guidance

- **Q4_0 on the NPU.** GenieX recommends it for Hexagon. ✅
- **QAD-Q4_0** is a separate download on this build. Compare it with Q4_0 before using it. ⚠️

## Disk budget

Disk is the constraint on the IQ-9075, not RAM. Approximate footprint of the models this guide uses:

| Item | On disk | Needed for |
|---|---:|---|
| LFM3-1.7B Q4_0 (GenieX cache) | ~1.05 GB | generator and tools |
| `~/models/d1-2B` safetensors | 3.84 GB | Path A |
| GenieX v0.10.0 bench archive | ~100 MB | benchmarks (optional) |

Check `df -h /` and `geniex list` before each pull. Remove only what you have confirmed you don't need.

## Licensing

- LiquidAI's GGUF repos carry the licence tag `other`. Read the LICENSE on each card before publishing a demo. ✅
- d1-2B is under the LFM Open License v1.0. ✅ (model card)
