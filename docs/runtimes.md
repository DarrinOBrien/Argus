# Runtimes and Tooling — GenieX on the IQ-9075

GenieX is Qualcomm's local inference stack. This guide uses it for LFM generation. The decision route is Path A (transformers, CPU), which does not use GenieX. Markers: ✅ confirmed in GenieX docs or our runs on the reference board · ⚠️ unverified · ⚠️ **behaviour differs from the docs** where noted.

## Versions used in this guide

| Install | Version | Where | Status |
|---|---|---|---|
| **Active** | GenieX CLI v0.8.0, QAIRT 2.45, llama.cpp `9425611` | `/usr/local/bin/geniex` → `~/.local/bin/geniex` → `~/.local/share/geniex` | ✅ active since the switch from v0.4.0. LFM NPU decode measured on this build (see [`models.md`](models.md)). |

The docs for `POST /v1/systemone` describe a newer build than v0.4.0. v0.8.0 doesn't have it either. ✅ (both binaries checked with `strings`, and live requests return 404)

## Runtimes

| | `llama_cpp` | `qairt` (Qualcomm AI Engine Direct) |
|---|---|---|
| Model format | GGUF from Hugging Face | Qualcomm AI Hub bundles |
| Compute units | NPU / GPU / CPU / hybrid | NPU only |
| Precision | You choose (`Q4_0`, `Q8_0`, `F16`, …) | Fixed in the bundle |
| **This event** | **LFM GGUFs** ✅ | Not used |

## CLI

| Command | Purpose | Notes |
|---|---|---|
| `geniex --help`, `geniex version` | Check the install ✅ | |
| `geniex config get chipset` | Board name (`Dragonwing IQ-9075 EVK`) ✅ | |
| `geniex pull <repo>[:<precision>] [--model-type llm\|vlm]` | Download into the cache ✅ | **⚠️ On v0.4.0, `pull LiquidAI/LFM2.5-2.6B-GGUF:Q4_0` also downloaded `LFM2.5-2.6B-QAD-Q4_0.gguf` (1.6 GB) and a `qad/tokenizer.json`, and rewrote `geniex.json`.** See [pitfalls](#pitfalls). |
| `geniex list` | Cached models, sizes, precisions ✅ | Size is the sum of every file, including extras |
| `geniex model set-type <model> llm\|vlm` | Set the modality ✅ | Use `vlm` for LFM vision models ✅ |
| `geniex remove <model>[:<precision>]` | Remove a model or one precision ✅ | Without `:<precision>` it removes the whole model |
| `geniex clean` | Remove all cached models ✅ | Destructive |
| `geniex infer <model> [--compute …] [--nctx N] [--think]` | Interactive chat ✅ | |
| `geniex serve [--compute …] [--nctx N] [--log info]` | OpenAI-compatible server on `127.0.0.1:18181` ✅ | Does not download models |

## Server endpoints (v0.4.0 unless noted)

| Endpoint | Status | Notes |
|---|---|---|
| `POST /v1/chat/completions` | ✅ works | See the request-field table below |
| `POST /v1/completions` | ✅ works | `logprobs` returns `400 logprobs is not supported` |
| `POST /v1/systemone` | ❌ **404** | Documented, but absent from v0.4.0 and v0.8.0 |
| `GET /v1/models` | ✅ | Lists cached models with `:<precision>` suffixes |

### Chat request fields (what actually takes effect)

Tested on `LiquidAI/LFM2.5-2.6B-GGUF:Q4_0` on v0.4.0, unless noted:

| Field | Result | Use it? |
|---|---|---|
| `max_completion_tokens` | ✅ **honoured**: `16` in → 16 out, `finish_reason: "length"` | **Yes.** Use this to cap length. |
| `max_tokens` | ✅ **honoured on v0.8.0**: `16` in, 16 out, `finish_reason: "length"`, streamed and non-streamed. It was ignored on v0.4.0 (479 returned). If both fields are set, `max_completion_tokens` wins (measured). | Yes, but use `max_completion_tokens` in this repo's examples. |
| `stream` | ✅ SSE deltas | Yes. Count tokens with `usage` on non-stream calls. |
| `compute` (per request) | ✅ `npu`, `hybrid`, `cpu` | Yes |
| `power_mode` (per request) | ✅ `burst` gave 14.4 tok/s against 11.7 at the default, one test | Use `burst` for benchmarks and demos |
| `enable_think` | ⚠️ no effect on LFM2.5-2.6B output. `chat_template_kwargs: {"enable_thinking": false}` also had no effect (measured) | Not for this model |
| `reasoning_format: "deepseek"` | ⚠️ no effect: `reasoning_content` stayed empty | Not for this model |
| `stop` | ⚠️ `["\n\n"]` did not stop generation in one test (932 tokens) | Do not rely on it |
| `logprobs` on chat | ⚠️ accepted, but `logprobs.content` is `null` | No token probabilities via chat |

**Output length matters for latency.** LFM2.5-2.6B writes its reasoning into the visible answer ("The user wants…"), with or without a system prompt asking for a single sentence. A one-sentence alert took 200–1,400 tokens without a cap. Cap with `max_completion_tokens`, and plan the demo's latency around that. ⚠️ Untested: other LFM variants may be more concise. Chat replies carry the reasoning text, so cutting them short does not give an answer. A raw `/v1/completions` prompt with `<think>\n\n</think>\n\n` already closed after the assistant tag returns the sentence directly: about 30 tokens and about 1.5 s on the IQ-9075 (measured; see [`examples/always-on-agent`](../examples/always-on-agent/README.md#explanations-why-a-raw-completion)).

## Python SDK

Not used in this event. The verified route is the HTTP server. We have not run the SDK's Python API here, so check any vendor snippet before using it. ⚠️

## Benchmarking

`geniex-bench` measures TTFT, prefill, and decode for a GGUF on `llama_cpp`. ✅ (its `--help`)

- **Match the bench to the runtime.** The bench bundles its own `libgeniex.so` and llama.cpp. Decode on the NPU differs a lot between versions: 14.3 tok/s with the v0.4.0 bench against 22.6 with v0.8.0, on the same model and device. Use the v0.8.0 bench to match the active install. ✅ (observed)
- Put its libraries on the path: `export LD_LIBRARY_PATH=$D/lib:$D/lib/llama_cpp:$D/lib/qairt`. Without it, the binary fails with `libgeniex.so: not found`. ✅ (observed)
- Defaults: 5 measured runs, 512-token prefill, 128 generated tokens. The summary line is the median run, per the bench docs. ✅ (bench docs). We did not see per-run values.
- `--output-json-dir` only works in matrix mode (`--matrix-file`). ✅ (observed)

Download: `https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-geniex/geniex-bench-linux-arm64-v<VERSION>.tar.gz`. v0.4.0 and v0.8.0 both exist. ✅

## Known gap: server CPU decode

The server's CPU path decodes at about **2.8 tok/s**, while the bench's CPU decode is **27.1 tok/s** on the same model. The server log shows `n_threads=6, strict_cpu=true`. The bench uses `n_threads=8, strict_cpu=false`. We did not find a way to set threads on the server, so the cause is not fully confirmed. ⚠️ Use the NPU or hybrid routes through the server, or benchmark CPU with `geniex-bench`.

## Pitfalls

**Re-pulling a model can download extras.** On v0.4.0, `geniex pull LiquidAI/LFM2.5-2.6B-GGUF:Q4_0` on a board that already had the model downloaded `LFM2.5-2.6B-QAD-Q4_0.gguf` (1.6 GB) and a `qad/tokenizer.json`, and listed the QAD file under `ExtraFiles` in `geniex.json`. The Q4_0 file itself was unchanged. We removed the extra by backing up `geniex.json`, dropping the `ExtraFiles` entry, and deleting the QAD file. Check `geniex.json` after any re-pull. ✅ (observed)

**Verbose LFM output looks like a slow model.** Check `completion_tokens` against your cap before you measure decode speed. See the request-field table.

## Server lifecycle: model loading and idle unloading

- **First request after start is slow.** `geniex serve` loads the model on the first request. For LFM2.5-2.6B Q4_0 on the IQ-9075 this adds about 5 s. A cold 128-token request took 10.7–11.0 s, and a warm one took 5.5–5.9 s. ✅ (measured)
- **Idle unloading.** The model unloads after a period with no requests. The default is 300 s. Change it with `--keepalive` (env `GENIEX_KEEPALIVE`), set when the server starts. ✅ (flag in `geniex serve --help`)
  - Measured: the model was still loaded at 256 s idle and was unloaded by 316 s. A request after 330 s idle took 7.6 s, against 2.9 s warm. ✅ (measured)
  - Measured with `--keepalive 30` and with `GENIEX_KEEPALIVE=30`: the model unloaded after 60 s idle, and the next request took about 5 s longer. ✅ (measured)
  - ```bash
    geniex serve --compute npu --keepalive 600        # keep the model loaded for 10 minutes idle
    GENIEX_KEEPALIVE=600 geniex serve --compute npu   # same, using the env var
    ```
  - For a demo, set the keepalive longer than the longest quiet gap, or send one request just before the demo.
- **Memory.** Process RSS was about 172 MB with the model unloaded and about 379 MB with it loaded. This is process RSS only. Device memory is not included. ✅ (measured)

## Known gap: zero-token responses on v0.8.0

After several identical requests, `geniex serve --compute npu` returns HTTP 200 with no tokens: `completion_tokens: 0`, `finish_reason: "stop"`, about 11 ms per reply. Streamed and non-streamed calls are both affected, so this is not a streaming bug.

Observed on the IQ-9075 (v0.8.0, LFM2.5-2.6B Q4_0, `max_completion_tokens` 64):

- **Identical prompt:** full replies for the first 5–7 requests, then zero tokens. Reproduced in three fresh-server runs: one streamed, two non-streamed. The exact count varied between runs.
- Varied prompts: 240 consecutive requests (120 streamed, 120 non-streamed; 15,360 tokens) with no failures, plus 40 earlier. Median latency stayed at 2.85 s from start to finish.
- **Identical prompt, 16-token replies:** 30 requests with no failures. So the trigger is not a simple request count.
- **Restarting `geniex serve` clears it.** The next requests work.

Cause: not confirmed. `geniex-bench` resets state between runs and `geniex serve` does not, so state carried across requests is the main suspect. The default server log shows no error. The earlier "2 of 4 streamed requests" result is most likely this same issue, seen on a server that had already handled several requests.

Workaround: check each reply for `completion_tokens: 0`, restart `geniex serve` when you see one, and vary the prompt. Sensor prompts change naturally.

## Known gap: NPU decode speed

The v0.4.0 bench offloads 31 of 31 layers to `HTP0`, so the repeating layers do not fall back to the CPU. Some work still runs on the CPU: the log shows 3 graph splits, a 508 MiB CPU compute buffer, and 205 MiB of CPU-side tensors (probably the token embedding; not confirmed). Weights total about 1.7 GB (1,306 MiB in `HTP0-REPACK`). ✅ (bench log)

Reading the decode numbers against the weight size: 14.3 tok/s moves about 24 GB/s of weights, and 22.6 tok/s moves about 38 GB/s. The v0.8.0 runtime already sustains that rate, so the v0.4.0 runtime is the likely limit. ⚠️ (inference from measured sizes, not a bandwidth measurement)
