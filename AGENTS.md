# AGENTS.md

Instructions for coding agents helping teams at the **On-Device AI Hackathon: Cleared for Takeoff ✈️** (LiquidAI × Qualcomm Dragonwing).

## Project and constraints

Docs and examples for the **Dragonwing IQ-9075 EVK**, Ubuntu 24.04 aarch64. Start with the [developer guide](docs/developer-guide.md); consult [Developer Notes](README.md#developer-notes) for reference-stack evidence and setup warnings.

- **Reference generator:** `LiquidAI/LFM3-1.7B-GGUF:Q4_0`, GenieX **v0.10.0**, NPU, `127.0.0.1:18181`.
- **Optional decision gate:** `LiquidAI/d1-2B`, Transformers on the CPU, local snapshot at `~/models/d1-2B`.
- These are defaults, not eligibility restrictions. Any LFM3-family model is welcome; other LFM models are options. Verify the chosen model's format, runtime, NPU support, and task behavior. A rule can replace d1.
- External sensors are optional and not supplied. Use brought sensors, board readings, local files, or simulated inputs.
- **Final demos run without external network access.** An isolated USB-C link may carry SSH and a board-hosted web UI, without laptop internet sharing/forwarding. Keep UI assets local and inference on the board; see [offline access](docs/offline-readiness.md#display-and-usb-c-access).

**Monitor warning:** with owner approval, remove/roll back the organizer-reported Adreno APT update for external monitors. SSH is unaffected. Do not install/update `qcom-adreno1` as a generic NPU fix; confirm rollback with organizers ([details](README.md#external-monitors-and-headless-setups)).

## Before board work

- Run board commands on the board (`aarch64`, GenieX on PATH) or over the user-supplied SSH host (`$IQ9_HOST`). Never assume laptop runtime/NPU access or guess a host.
- Read the [preflight skill](skills/iq9-preflight/SKILL.md) and run the app's matching profile before board work. Example SSH invocation from the repo root:

  ```bash
  ssh "$IQ9_HOST" 'bash -s -- --json' < skills/iq9-preflight/scripts/preflight.sh
  ```

- For laptop-only documentation work without a host, report board preflight as unperformed.
- Before downloads/imports, inspect `geniex list`, local weights, and `df -h /`. Missing cache registration does not prove weights absent. Never re-pull cached models.

## Non-negotiable rules

1. **Offline at runtime:** load local snapshots/cache entries only. No downloads, installs, telemetry, cloud services, or CDN assets. Enable offline loading settings before Transformers imports and use `local_files_only=True`.

2. **Cap and validate LFM calls:** use `max_completion_tokens` for chat and `max_tokens` for completions. Reject zero/missing tokens and empty or reasoning-only text answers; validate tool calls for tool requests. Tokens or `ok` do not prove usability. Follow the generator skill.

3. **If using d1:** load the pinned local snapshot through Transformers, fp32 CPU, once—not GenieX decision endpoints. Keep d1/LFM sequential unless re-measured. Calibrate task-representative labels with held-out evaluation; never copy 0.5 or synthetic thresholds. d1's zero output tokens are expected.

4. **Code authorizes actions:** validate schemas, enforce allowlists and policy before writes or real-world actions, and report code's action records—not model prose. Log each iteration as flushed JSONL, separating proposals, actions, and errors. Return loop errors as data, not crashes.

5. **Verify generator NPU execution:** send a capped request and inspect the current server's device/offload log for `HTP0`. Missing output needs diagnosis, not an assumed CPU fallback. Do not silently switch compute routes.

6. **Get approval before changes:** system/runtime installation or upgrades; model downloads/imports/removal (`geniex pull/remove/clean`, `fetch_d1.py`); changing the d1 revision pin or user configuration; deleting user files; non-loopback server binding; or network cuts. Review snapshot code before enabling `trust_remote_code`.

7. **Protect shared boards:** inspect resolved paths and symlinks before deletion, back up replaced board files, and preserve unrelated files. Do not interrupt shared servers without permission. Before a network cut, establish a tested local console or isolated USB-C control link and restoration plan.

## Choose the relevant skill

Read the corresponding `SKILL.md` **before doing that work**. Skills supply procedures and helper boundaries; `.claude/skills/` and `.agents/skills/` link here.

| Skill | Use it for |
|---|---|
| [iq9-preflight](skills/iq9-preflight/SKILL.md) | Board readiness and diagnosis |
| [iq9-geniex-lfm](skills/iq9-geniex-lfm/SKILL.md) | LFM requests, `lfm_client.py`, server lifecycle, output guards |
| [iq9-d1-decision-gate](skills/iq9-d1-decision-gate/SKILL.md) | d1 loading, typed questions, calibration |
| [iq9-always-on-agent](skills/iq9-always-on-agent/SKILL.md) | Monitors, autonomous loops, app scaffold |
| [iq9-lfm-tool-calling](skills/iq9-lfm-tool-calling/SKILL.md) | Tool schemas, allowlists, action policy |
| [iq9-offline-rehearsal](skills/iq9-offline-rehearsal/SKILL.md) | Asset staging, offline audit, network-off rehearsal |
| [iq9-demo-prep](skills/iq9-demo-prep/SKILL.md) | Judging, metrics, pitch, demo preparation |

Flashing, camera pipelines, and model conversion/quantisation are outside this repo; use Qualcomm's [Dragonwing](https://dragonwingdocs.qualcomm.com), [IM SDK](https://imsdkdocs.qualcomm.com), and [GenieX](https://geniex.aihub.qualcomm.com) docs.

## Code guidance

- Python 3.12; standard library except d1 in `~/.venvs/d1`. New apps go in `apps/`.
- Make examples easy to try: offer `--help` and a short-run option where useful. Bash uses `set -euo pipefail`. Keep task-created temporary files in the workspace.
- Each app README covers launch, measurements, and offline status. Report board, runtime, model/precision, sample count, and medians; follow the demo skill's metric definitions.
- **Check what you change.** For documentation, check links and command examples. For runnable examples, use a short smoke run when practical. No blanket test-suite or board-run requirement.
- **Be clear about verification.** Only claim board or offline verification when performed; state what remains unverified.
- Use version-matched Developer Notes; never transfer results between models, precisions, runtimes, or boards. Label prior results as prior; distinguish **✅ confirmed**, **🧪 measured**, and **⚠️ unverified**.
