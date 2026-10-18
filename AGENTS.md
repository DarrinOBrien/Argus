# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Cursor, Copilot, Gemini, pi, and others) helping developers build on-device AI apps at the **On-Device AI Hackathon: Cleared for Takeoff ✈️** (LiquidAI × Qualcomm Dragonwing). People read the docs; this file is for agents.

## What this repo is

A knowledge base and set of working examples for one target: the **Dragonwing IQ-9075 EVK** (QCS9075, Hexagon v73 NPU, 36 GB, Ubuntu 24.04 aarch64) running LiquidAI models:

- **Generator:** `LiquidAI/LFM2.5-2.6B-GGUF:Q4_0` through **GenieX v0.8.0** (`geniex serve`, OpenAI-compatible, `127.0.0.1:18181`, NPU).
- **Decision gate:** `LiquidAI/d1-3B` through **transformers on the CPU** ("Path A"), from a local snapshot at `~/models/d1-3B`.
- **Tool calls:** `LiquidAI/LFM2-1.2B-Tool-GGUF:Q4_0` through the same server.

Every project's final demo runs **with the network unplugged**. Assume that from the first line of code.

## Where you are running

Check this before running any command:

- **On the board** (`uname -m` prints `aarch64`, and `geniex` is on PATH): run commands directly.
- **On a laptop:** the board is reachable over SSH. Use the host the user gives you (call it `$IQ9_HOST`). Run board commands as `ssh "$IQ9_HOST" '<cmd>'`, and copy files with `rsync`/`scp`. Never assume the laptop has `geniex`, the NPU, or the models.

Start each session with the preflight check: `skills/iq9-preflight/scripts/preflight.sh` (over SSH: `ssh "$IQ9_HOST" 'bash -s -- --json' < skills/iq9-preflight/scripts/preflight.sh`).

## Skills

Each folder under `skills/` has a `SKILL.md` and tested scripts. Read the skill before doing that kind of work.

| Skill | Use it for |
|---|---|
| [`iq9-preflight`](skills/iq9-preflight/SKILL.md) | "Is the board ready?", the start of a session, "it stopped working" |
| [`iq9-geniex-lfm`](skills/iq9-geniex-lfm/SKILL.md) | Any code that calls an LFM model or `geniex serve`. Includes `lfm_client.py` and `serve.sh` |
| [`iq9-d1-decision-gate`](skills/iq9-d1-decision-gate/SKILL.md) | Triage, classification, gating, alerts, d1 questions, threshold calibration |
| [`iq9-always-on-agent`](skills/iq9-always-on-agent/SKILL.md) | Building a monitor or autonomous loop. Includes `scaffold.sh` |
| [`iq9-lfm-tool-calling`](skills/iq9-lfm-tool-calling/SKILL.md) | Function and tool calling, multi-step agents |
| [`iq9-offline-rehearsal`](skills/iq9-offline-rehearsal/SKILL.md) | Offline audit, staging everything before the cut, the network-off test |
| [`iq9-demo-prep`](skills/iq9-demo-prep/SKILL.md) | Judging, metrics, the pitch, the "why not cloud?" answer |

If your agent doesn't load skills automatically, read the `SKILL.md` directly. The same skills are linked from `.claude/skills/` and `.agents/skills/`.

## Rules (each one comes from a failure we measured on the board)

1. **Cap every LFM call.** Use `max_completion_tokens` on chat and `max_tokens` on `/v1/completions`. Without a cap, LFM2.5-2.6B ran 200–1,400 tokens for a one-sentence request.
2. **LFM2.5-2.6B puts its reasoning in chat replies.** For a direct answer, use a raw completion with `<think>\n\n</think>\n\n` already closed (`lfm_client.LFM().sentence()`). `enable_think`, `stop`, and `reasoning_format` don't change this.
3. **Treat `completion_tokens: 0` as a failure.** GenieX v0.8.0 returns empty replies after a few identical prompts. Make prompts unique, retry once with a tag, then run `serve.sh restart`.
4. **Never use `POST /v1/systemone`.** It returns 404 on v0.4.0 and v0.8.0. Run d1 through transformers (`trust_remote_code=True`, fp32, CPU), loaded once.
5. **Load models from local paths only.** No Hugging Face repo IDs in app code, and no `geniex pull`, `pip install`, CDN assets, or telemetry at runtime.
6. **Keep d1 and the LFM sequential.** The gate goes from about 4.1 s to about 7.7 s when a generation runs at the same time.
7. **Calibrate d1. Don't trust 0.5.** On the board's own thermal readings, d1 didn't track temperature (r = −0.08). Use `calibrate_threshold.py`, or a rule.
8. **The model proposes; code decides.** Validate tool arguments against a schema, run only allowlisted actions, put a policy in code in front of any write or real-world action, and report actions from your own record. LFM2-1.2B-Tool over-alerts and claims actions it never took.
9. **Log every iteration** as flushed JSONL. That log is the offline proof judges look for.
10. **Use the NPU.** If the server log doesn't show `Using 1 device(s): HTP0`, the server is on the CPU (about 2.8 tok/s). Fix the drivers. Don't switch to `--compute cpu`.

## Ask before you

- Run `sudo`, `apt`, `usermod`, or anything that changes the system.
- Run `geniex pull` (check `geniex list` and `df -h /` first, and **never re-pull** a model that's already cached), `geniex remove`, `geniex clean`, or `fetch_d1.py`.
- Install, upgrade, or reinstall GenieX. Every number here is for v0.8.0.
- Move the d1 revision pin (`051bcc464b01`). `trust_remote_code` runs the repo's Python code, so review it first.
- Bind `geniex serve` to anything other than loopback, or cut the network. Over SSH, cutting the network also cuts your own session.
- Delete anything under `~/models` or `~/.cache/geniex`.

## Facts and evidence

- `docs/` is the source of truth. If a model card, a vendor snippet, or your training data disagrees with it, trust `docs/`, then tell the user about the conflict.
- Markers: ✅ confirmed · 🧪 measured on a reference IQ-9075 · ⚠️ unverified. Never upgrade ⚠️ to a fact without measuring it on the board.
- Report a number only if you measured it on the board, together with the GenieX version, the model and precision, n, and the median. Don't present doc numbers as the user's results.
- Model-card latencies (Jetson, Apple, GPU) don't apply to this board.

| Question | Read |
|---|---|
| Setup, architecture, troubleshooting | [`docs/developer-guide.md`](docs/developer-guide.md) |
| Server endpoints, request fields, known gaps | [`docs/runtimes.md`](docs/runtimes.md) |
| Which model, sizes, measured speeds | [`docs/models.md`](docs/models.md) |
| d1 question types and budget | [`docs/decision-models.md`](docs/decision-models.md) |
| Board facts and drivers | [`docs/hardware.md`](docs/hardware.md) |
| Network-off checklist | [`docs/offline-readiness.md`](docs/offline-readiness.md) |
| Scoring and demo format | [`docs/judging.md`](docs/judging.md) |

## Repo layout

| Path | What | Run |
|---|---|---|
| `starter/run.sh` | The five-minute smoke test | `./starter/run.sh` (about 75 s) |
| `examples/system-one-decision/` | d1 install, pinned fetch, env check, example | `~/.venvs/d1/bin/python system_one_example.py` |
| `examples/lfm-server-npu/` | Start the server, one capped request, stop | `python3 serve_lfm_npu.py` |
| `examples/always-on-agent/` | The reference loop | `~/.venvs/d1/bin/python always_on_agent.py --iterations 8` |
| `examples/tool-calling/` | Tool calls with guards | `python3 tool_calling.py --self-test`, then `python3 tool_calling.py` |
| `skills/` | Agent skills and their scripts | see the table above |
| `apps/` | Put new projects here (`scaffold.sh apps/<name>`) | — |

## Code conventions

- Python 3.12 on the board. Examples use only the standard library, except d1 code, which runs in `~/.venvs/d1` (`--system-site-packages`; it reuses the board's torch 2.11.0).
- Each script gets `--help` and a short smoke-test mode (`--iterations N`, `--self-test`, or `--sensor-mode simulated`) so you can check it without waiting.
- Return errors as data inside loops. Never let the explainer crash the loop.
- Bash scripts: `set -euo pipefail`, and they must pass shellcheck.
- Each app gets a README with how to run it, what it measured (with markers), and its offline status.

## Out of scope for this repo

Flashing or reimaging the board, camera/GStreamer pipelines, and model conversion or quantisation (QAIRT, AI Hub) are covered by Qualcomm's Dragonwing skills and docs, not here. For those, point the user to the Dragonwing docs (`https://dragonwingdocs.qualcomm.com`), the IM SDK docs (`https://imsdkdocs.qualcomm.com`), and the GenieX docs (`https://geniex.aihub.qualcomm.com`). Stay with the measured stack above unless the user asks to go beyond it.
