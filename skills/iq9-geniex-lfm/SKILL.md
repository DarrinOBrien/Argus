---
name: iq9-geniex-lfm
description: Call LiquidAI LFM models through GenieX on the Dragonwing IQ-9075. Covers starting and stopping geniex serve, capped requests, one-sentence answers from LFM3-1.7B, empty replies, cold starts, idle unloading, NPU checks, and model choice. Use whenever app code talks to an LFM, to geniex serve, or to http://127.0.0.1:18181.
compatibility: Targets the IQ-9075 (aarch64, Ubuntu 24.04) with GenieX CLI v0.10.0. The client works from any Python 3.10+ that can reach the local server.
metadata:
  version: "0.4"
---

# GenieX and LFM on the IQ-9075

Start with the [reference-stack rules](../../README.md#rules-for-the-reference-stack); [Runtimes](../../docs/runtimes.md) gives format, precision, and API guidance. LFM3-1.7B is a reference default, not a required participant model; verify any chosen model's template, format, NPU support, and task behavior.

**Missing NPU packages:** follow the [driver setup guide](../../docs/developer-guide.md#32-driver-packages) and, for package-file `404 Not Found` errors, [stale APT recovery](../../docs/developer-guide.md#stale-apt-lists-and-package-file-404s). Then verify the current server's `HTP0` line.

## 1. Server

Commands below run from the repo root. Use a **separate terminal** for the foreground server and keep its output visible. Do not send input into a busy terminal or the agent's own terminal.

```bash
skills/iq9-geniex-lfm/scripts/serve.sh run       # foreground; NPU, 1800 s, ~/geniex-serve.log
# In another terminal:
skills/iq9-geniex-lfm/scripts/serve.sh status
skills/iq9-geniex-lfm/scripts/serve.sh stop      # only when safe to interrupt this server
```

`start`/`restart` retain the detached runner for compatibility. Use them only with an agreed logged runner. For a foreground restart, stop the owned server and run `run` again in its terminal; do not silently replace it with a detached job.

- The server listens on loopback only, at `127.0.0.1:18181`, and never downloads models.
- **Headless demo:** keep GenieX on loopback and use SSH port forwarding for a board-hosted web UI over an isolated USB-C link ([USB-C access](../../docs/offline-readiness.md#display-and-usb-c-access)). The [monitor issue](../../README.md#external-monitors-and-headless-setups) does not affect SSH.
- `kill $!` does not stop it, because `geniex` is a launcher. `serve.sh stop` stops the process that holds the port. Never use `pkill -f "geniex serve"` over SSH; it also matches the SSH command itself.
- **Cold start:** the first request loads weights. Measure the chosen model's cold/reload time.
- **Idle unload:** the model unloads after `--keepalive` seconds idle (300 s by default). `serve.sh` sets 1800 s. Before a demo, send one warm-up request.
- **Is the NPU in use?** With `--log info`, the log shows `Using 1 device(s): HTP0`. `serve.sh status` prints that line from `~/geniex-serve.log` (or `GENIEX_SERVE_LOG`) from any directory, and says so when the log or the line is missing. Send a capped request first; `run`/`start` replace the log, so it belongs to the server that script started. A missing `HTP0` line calls for investigation, not a CPU-fallback conclusion; see `docs/developer-guide.md` §12. `geniex infer` is interactive, so don't run it from an agent.

## 2. Requests: always use `scripts/lfm_client.py`

Copy `scripts/lfm_client.py` into the app, or import it. It uses only the standard library. The always-on example and its scaffold use it; `examples/tool-calling` keeps its own `response_error()` with the same checks so that file stands alone.

```python
from lfm_client import LFM
lfm = LFM()                                                        # LFM3-1.7B Q4_0 on the NPU
r = lfm.sentence("Explain to an operator: SoC 74 C, up 13 C in one minute (rising).")
if r["ok"]: print(r["text"])
else: log(r["error"])                                              # never raises on HTTP/timeouts
```

Rules to preserve. The client caps by default, validates usable output/tool envelopes, tags raw prompts before the first call, and retries unusable output once. **It does not execute tools, fully validate argument schemas, automatically restart servers, or guarantee answer correctness.** Keep those checks in app code.

| Rule | Why |
|---|---|
| Cap every call: `max_completion_tokens` on chat, `max_tokens` on `/v1/completions` | Bounds latency and output on the edge |
| For direct LFM3-1.7B answers, try `chat(..., enable_think=False)` or `sentence()` with a closed reasoning block | Neither method guarantees a usable answer; re-test other models |
| Reject zero tokens, empty answers, or reasoning alone. For tools, check the envelope and validate schemas/allowlists/policy before execution | Positive token usage is not proof of usable output. Retry once; persistent failure returns `ok=False` and an error |
| Make raw prompts unique before the first call | Identical raw prompts returned continuing commentary with positive tokens. `complete()` tags them by default; `unique=False` is diagnostics only |
| Send `"stream": false` unless you need streaming | Easier token accounting |
| Set `compute` on each request (`npu`) | Keeps the generator on the Hexagon NPU; confirm `HTP0` in the log |
| Give the model numbers *and* direction ("rising 13 C/min") | It described a falling temperature as rising when it only had the two values |

`python3 skills/iq9-geniex-lfm/scripts/lfm_client.py --check` checks the server and lists its models. `--sentence "..."` and `--chat "..."` are quick tests. Exit code 2 means the reply was empty or failed.

## 3. Timing to plan around

The default idle timeout is 300 s; `--keepalive` and `GENIEX_KEEPALIVE` both change it. The first request after an unload reloads the weights. Run `skills/iq9-demo-prep/scripts/collect_metrics.sh` for this app's metrics, including usable-answer checks. Keep optional d1 and the LFM sequential.

## 4. Picking a model

Check `geniex list`, local weight directories, and `df -h /` first, and reuse registered models. For a missing model, use the supplied USB drive before any download and follow [USB model staging](../../docs/developer-guide.md#usb-model-drive-copy-never-move): copy, never move.

**Ask before every copy, pull, or local import.** Import the selected model directory with `geniex --skip-update pull <name>:<precision> --model-hub localfs --local-path <observed-directory>`, which copies into the cache without downloading. Then verify cache registration, a capped useful response, and the current server's `HTP0` line.

Download only when no compatible copy exists on the board or the drive. Never re-pull cached weights or run `geniex clean`/`geniex remove` without approval. Cached model names are fine in inference requests; runtime downloads are not.

Use [README: Platform and models](../../README.md#platform-and-models) to find LiquidAI's published models, not a fixed shortlist. The examples default to `LiquidAI/LFM3-1.7B-GGUF:Q4_0`; other LFM3-family and LFM models are options. Check the selected model's [format, precision, and compute route](../../docs/runtimes.md#model-format-and-precision), and stage its [full matching asset set](../../docs/offline-readiness.md#disk-first). Vision and audio require supported modality-specific request handling. Re-test NPU execution, usable answers, and tool calls on the board for the chosen configuration.

Put any new number in the app's README with the GenieX version, labelled as measured or unverified.

## 5. Don'ts

- If using d1-2B, use the pinned local snapshot through Transformers in fp32 on the CPU. The tested GGUF decision requests failed; this is not a blanket GenieX limitation (`iq9-d1-decision-gate`).
- Don't load models by Hugging Face repo ID from app code. It fails offline.
- Don't bind the server to `0.0.0.0` unless the user asks for it.
- Don't change GenieX versions between rehearsal and the event. The active target is v0.10.0.
