---
name: iq9-geniex-lfm
description: Call LiquidAI LFM models through GenieX on the Dragonwing IQ-9075. Covers starting and stopping geniex serve, capped chat and raw-completion requests, one-sentence answers from LFM2.5-2.6B, zero-token replies, cold starts, idle unloading, NPU checks, and model choice. Use whenever app code talks to an LFM, to geniex serve, or to http://127.0.0.1:18181.
compatibility: Runs on the IQ-9075 (aarch64, Ubuntu 24.04) with GenieX CLI v0.8.0. The client works from any Python 3.10+ that can reach the server.
metadata:
  version: "0.1"
---

# GenieX and LFM on the IQ-9075

The repo's docs are the source of truth: `docs/runtimes.md` (server, request fields, known gaps) and `docs/models.md` (measured numbers). This skill boils them down into the steps to follow.

## 1. Server

Use `scripts/serve.sh` instead of starting the server by hand:

```bash
scripts/serve.sh start            # npu, keepalive 1800 s, --log info to /tmp/geniex-serve.log
scripts/serve.sh status           # pid, device in use (expect HTP0), cached models
scripts/serve.sh restart          # clears the zero-token state
scripts/serve.sh stop
```

- The server listens on loopback only, at `127.0.0.1:18181`, and never downloads models.
- `kill $!` does not stop it, because `geniex` is a launcher. `serve.sh stop` stops the process that holds the port. Never use `pkill -f "geniex serve"` over SSH; it also matches the SSH command itself.
- **Cold start:** the first request after a start loads the model, which adds about 5 s.
- **Idle unload:** the model unloads after `--keepalive` seconds idle (300 s by default). `serve.sh` sets 1800 s. Before a demo, send one warm-up request.
- **Is the NPU in use?** With `--log info`, the log shows `Using 1 device(s): HTP0`. `serve.sh status` prints that line. No `HTP0` means the server fell back to the CPU without saying so; see `docs/developer-guide.md` §12. `geniex infer` is interactive, so don't run it from an agent.

## 2. Requests: always use `scripts/lfm_client.py`

Copy `scripts/lfm_client.py` into the app, or import it. It uses only the standard library.

```python
from lfm_client import LFM
lfm = LFM()                                                        # LFM2.5-2.6B Q4_0 on the NPU
r = lfm.sentence("Explain to an operator: SoC 74 C, up 13 C in one minute (rising).")
if r["ok"]: print(r["text"])                                       # ~20-47 tokens, ~1.5-2 s warm
else: log(r["error"])                                              # never raises on HTTP/timeouts
```

Rules the client follows. Keep them if you write your own client:

| Rule | Why (measured on the board, v0.8.0) |
|---|---|
| Cap every call: `max_completion_tokens` on chat, `max_tokens` on `/v1/completions` | LFM2.5-2.6B ran 200–1,400 tokens for a "one sentence" request |
| For a direct answer from LFM2.5-2.6B, use a raw `/v1/completions` call with `<think>\n\n</think>\n\n` after the assistant tag (`lfm.sentence`) | Chat replies start with reasoning ("The user wants…"). `enable_think`, `chat_template_kwargs`, `reasoning_format`, and `stop` did not change that |
| Treat `completion_tokens == 0` as a failure. Retry once with a unique tag, then restart the server | v0.8.0 returns HTTP 200 with zero tokens after 5–7 identical prompts. Restarting clears it |
| Vary prompts: include a timestamp or a short tag | The same trigger |
| Send `"stream": false` unless you need streaming | Easier token accounting. Streaming doesn't avoid the zero-token bug |
| Set `compute` on each request (`npu`) | Server CPU decode is about 2.8 tok/s, against about 23 tok/s on the NPU |
| Give the model numbers *and* direction ("rising 13 C/min") | It described a falling temperature as rising when it only had the two values |

`python3 scripts/lfm_client.py --check` checks the server and lists its models. `--sentence "..."` and `--chat "..."` are quick tests. Exit code 2 means the reply was empty or failed.

## 3. Timing to plan around (IQ-9075, warm server, NPU)

| | |
|---|---|
| Decode | about 23 tok/s |
| 64 / 128 tokens | about 2.8 s / about 5.6–5.9 s |
| `lfm.sentence()` | about 1.5–2 s |
| First token (streamed) | 0.13–0.16 s |
| First request after a start or an idle unload | add about 5 s |

LFM calls slow the d1 gate from about 4 s to about 7.7 s if both run at once. Keep them sequential (see `iq9-d1-decision-gate`).

## 4. Picking a model

Run `geniex list` before you pull anything. Pull only what is missing, and check `df -h /` first. **Never re-pull a model you already have** (on v0.4.0 it fetched an extra 1.6 GB), and never run `geniex clean` or `geniex remove` without the user's OK.

| Job | Model | Notes |
|---|---|---|
| Explanations, general text | `LiquidAI/LFM2.5-2.6B-GGUF:Q4_0` | Measured. Use `sentence()` for direct answers |
| Tool calls | `LiquidAI/LFM2-1.2B-Tool-GGUF:Q4_0` | Measured. See the `iq9-lfm-tool-calling` skill. No reasoning preamble, so `close_think=False` is fine |
| Smallest footprint | `LiquidAI/LFM2.5-350M-GGUF:Q4_0` (219 MB) | Not measured on the board. Measure it before you claim anything |
| Images | `LiquidAI/LFM2.5-VL-1.6B-GGUF` or `-VL-450M-GGUF` | Run `geniex model set-type <model> vlm`. Not measured |
| Audio | `LiquidAI/LFM2.5-Audio-1.5B-GGUF` | Four files. Audio input is llama.cpp-only. Not measured |

Put any new number in the app's README with its marker (🧪 measured, ⚠️ unverified) and the GenieX version.

## 5. Don'ts

- Don't use `POST /v1/systemone`. It returns 404 on v0.4.0 and v0.8.0. d1 runs through transformers (`iq9-d1-decision-gate`).
- Don't load models by Hugging Face repo ID from app code. It fails offline.
- Don't bind the server to `0.0.0.0` unless the user asks for it.
- Don't upgrade or reinstall GenieX during the event. The numbers above are for v0.8.0.
