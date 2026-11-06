---
name: iq9-geniex-lfm
description: Call LiquidAI LFM models through GenieX on the Dragonwing IQ-9075. Covers starting and stopping geniex serve, capped requests, one-sentence answers from LFM3-1.7B, empty replies, cold starts, idle unloading, NPU checks, and model choice. Use whenever app code talks to an LFM, to geniex serve, or to http://127.0.0.1:18181.
compatibility: Targets the IQ-9075 (aarch64, Ubuntu 24.04) with GenieX CLI v0.10.0. The client works from any Python 3.10+ that can reach the local server. Reference checks are dated and configuration-specific; see README Developer Notes.
metadata:
  version: "0.2"
---

# GenieX and LFM on the IQ-9075

Start with [README Developer Notes](../../README.md#developer-notes) for dated reference checks; [Runtimes](../../docs/runtimes.md) gives format, precision, and API guidance. Prefer version-matched board evidence over stale migration claims. LFM3-1.7B is a reference default, not a required participant model; verify any chosen model's template, format, NPU support, and task behavior.

## 1. Server

Commands below run from the repo root. Use a **separate terminal** for the foreground server and keep its output visible. Do not send input into a busy terminal or the agent's own terminal.

```bash
skills/iq9-geniex-lfm/scripts/serve.sh run       # foreground; NPU, 1800 s, ./geniex-serve.log
# In another terminal:
skills/iq9-geniex-lfm/scripts/serve.sh status
skills/iq9-geniex-lfm/scripts/serve.sh stop      # only when safe to interrupt this server
```

`start`/`restart` retain the detached runner for compatibility. Use them only with an agreed logged runner. For a foreground restart, stop the owned server and run `run` again in its terminal; do not silently replace it with a detached job.

- The server listens on loopback only, at `127.0.0.1:18181`, and never downloads models.
- `kill $!` does not stop it, because `geniex` is a launcher. `serve.sh stop` stops the process that holds the port. Never use `pkill -f "geniex serve"` over SSH; it also matches the SSH command itself.
- **Cold start:** the first request loads weights. Measure the chosen model's cold/reload penalty; do not transfer the legacy five-second figure.
- **Idle unload:** the model unloads after `--keepalive` seconds idle (300 s by default). `serve.sh` sets 1800 s. Before a demo, send one warm-up request.
- **Is the NPU in use?** With `--log info`, the log shows `Using 1 device(s): HTP0`. `serve.sh status` prints that line. Send a capped request first and verify that the log belongs to this server. A missing `HTP0` line calls for investigation, not a CPU-fallback conclusion; see `docs/developer-guide.md` §12. `geniex infer` is interactive, so don't run it from an agent.

## 2. Requests: always use `scripts/lfm_client.py`

Copy `scripts/lfm_client.py` into the app, or import it. It uses only the standard library.

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
| For direct LFM3-1.7B answers, try `chat(..., enable_think=False)` or `sentence()` with a closed reasoning block | Dated probes passed, but neither method guarantees a usable answer; re-test other models |
| Reject zero tokens, empty answers, or reasoning alone. For tools, check the envelope and validate schemas/allowlists/policy before execution | Positive token usage is not proof of usable output. Retry once; persistent failure returns `ok=False` and an error |
| Make raw prompts unique before the first call | Identical raw prompts returned continuing commentary with positive tokens. `complete()` tags them by default; `unique=False` is diagnostics only |
| Send `"stream": false` unless you need streaming | Easier token accounting |
| Set `compute` on each request (`npu`) | Keeps the generator on the Hexagon NPU; confirm `HTP0` in the log |
| Give the model numbers *and* direction ("rising 13 C/min") | It described a falling temperature as rising when it only had the two values |

`python3 skills/iq9-geniex-lfm/scripts/lfm_client.py --check` checks the server and lists its models. `--sentence "..."` and `--chat "..."` are quick tests. Exit code 2 means the reply was empty or failed.

## 3. Timing to plan around

🧪 Prior checks on 2026-11-05: IQ-9075, GenieX v0.10.0 / QAIRT 2.50 / llama.cpp `19cce69`, LFM3-1.7B **QAD-Q4_0** on HTP0. Caps held across 205 recorded requests; the legacy zero-token failure was not reproduced, not declared fixed. Reasoning-only empty output still occurred with positive usage. Raw-repeat cache/state handling is a hypothesis, not a confirmed cause.

The default 300-second idle timeout and both keepalive controls were observed; the default-timeout reload timing had only one post-idle observation. Run `skills/iq9-demo-prep/scripts/collect_metrics.sh` for this app's fresh metrics, including usable-answer checks. Keep optional d1 and the LFM sequential: current reference contention checks support that policy. Stored results are not fresh results for the user's board.

## 4. Picking a model

Run `geniex list`, inspect existing local weight directories, and check `df -h /` first. **Ask before every pull or local import**, and never re-pull cached weights. Existing GGUFs can be imported with approval using `geniex pull <name>:<precision> --local-path <directory>`; this copies into the cache without downloading weights. Never run `geniex clean` or `geniex remove` without approval. Cached registered model names are allowed in inference requests; runtime downloads are not.

Use [README: Platform and models](../../README.md#platform-and-models) to find LiquidAI's published models, not a fixed shortlist. The examples default to `LiquidAI/LFM3-1.7B-GGUF:Q4_0`; other LFM3-family and LFM models are options. Check the selected model's [format, precision, and compute route](../../docs/runtimes.md#model-format-and-precision), and stage its [full matching asset set](../../docs/offline-readiness.md#disk-first). Vision and audio require supported modality-specific request handling. Re-test NPU execution, usable answers, and tool calls on the board for the chosen configuration.

Put any new number in the app's README with its marker (🧪 measured, ⚠️ unverified) and the GenieX version.

## 5. Don'ts

- If using d1-2B, keep the pinned local fp32 CPU Path A. The tested GGUF decision requests failed; this is not a blanket GenieX limitation (`iq9-d1-decision-gate`).
- Don't load models by Hugging Face repo ID from app code. It fails offline.
- Don't bind the server to `0.0.0.0` unless the user asks for it.
- Don't change GenieX versions between rehearsal and the event. The active target is v0.10.0.
