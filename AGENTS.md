# AGENTS.md

Instructions for coding agents helping teams at the **On-Device AI Hackathon: Cleared for Takeoff** (LiquidAI × Qualcomm Dragonwing). Schedule and logistics: [event page](https://luma.com/0nsdnkoa). Submission steps: [docs/judging.md](docs/judging.md#how-to-submit).

## Project and constraints

Docs and examples for the **Dragonwing IQ-9075 EVK**, Ubuntu 24.04 aarch64. Start with the [developer guide](docs/developer-guide.md); consult [Developer Notes](README.md#developer-notes) for setup warnings and reference-stack rules.

- **Reference generator:** `LiquidAI/LFM3-1.7B-GGUF:Q4_0`, GenieX **v0.10.0**, NPU, `127.0.0.1:18181`.
- **Optional ZETIC route:** read [the ZETIC example](examples/zetic-lfm/README.md) before using Ixian Hexagon SDK 0.2.1 with the public IQ9 packages. Its wrapper supports the four LFM3 generators' text/image/WAV → text paths as applicable, only on two-NSP `v73`. The collection also offers a separate native d1 Decision API, not integrated into the Python examples. SDK 0.2.1 and the current packages have been run on the board; still check each request's output and device evidence. Keep this separate from GenieX; do not import ZETIC packages into its cache.
- **Optional decision gate:** `LiquidAI/d1-2B`, Transformers on the CPU, local snapshot at `~/models/d1-2B`.
- These are defaults, not eligibility restrictions. Any LFM3-family model is welcome; other LFM models are options. Verify the chosen model's format, runtime, NPU support, and task behavior. A rule can replace d1: the always-on example runs without d1 using `--gate rule`.
- **Model media:** teams receive USB drives with model assets and have been asked to bring USB-C dongles/adapters. Ask whether the participant has the supplied drive and a suitable adapter before proposing model downloads. **Copy/import models onto board storage; never move them or delete/modify the source drive.** See [USB model staging](docs/developer-guide.md#usb-model-drive-copy-never-move).
- **Time budget:** the build window is two hours and boards start with a fresh Ubuntu install only. Take the shortest path: first NPU response, a working app loop, a tested offline control path, then submission ([plan](README.md#two-hours-from-a-fresh-board)). Treat d1 and its calibration, the metrics collector, long rehearsals, recovery staging, and ZETIC as extras: propose them only when the team asks or has time. Put the whole setup in one plan for one approval rather than asking step by step, shorten checks to fit, and say what was skipped.
- External sensors are optional and not supplied. Use brought sensors, board readings, local files, or simulated inputs.
- **Final demos run without external network access.** An isolated USB-C link may carry SSH and a board-hosted web UI, without laptop internet sharing/forwarding. Keep UI assets local and inference on the board; see [offline access](docs/offline-readiness.md#display-and-usb-c-access).

**Monitor warning:** organizers report that the current Adreno APT update causes a GPU-driver issue with external monitors; SSH is unaffected. Do not install/update `qcom-adreno1` as a generic NPU fix, and confirm any rollback with the organizers ([details](README.md#external-monitors-and-headless-setups)).

## Before board work

- For "get started", board access, internet setup, or an unknown installed stack, read the [getting-started skill](skills/iq9-getting-started/SKILL.md) first. Establish access → inspect board/connectivity → propose setup → approved changes → verify the generator. Help with UART/manual steps if SSH is not yet available; do not guess a host or require GenieX before initial checks.
- Run board commands on the board (`aarch64`, Ubuntu 24.04), through its UART console, or over the user-confirmed SSH host (`$IQ9_HOST`). Never assume laptop runtime/NPU access. Laptop serial-tool commands and board-shell commands are different; label where each runs.
- Event boards use the organizer-provided `ubuntu` / `liquidxqualcomm` login for UART and SSH, not the upstream first-login password. See [access and setup networking](docs/developer-guide.md#0-board-access-and-internet-for-setup). Have the user enter passwords interactively; do not log private Wi-Fi credentials or disable SSH host-key verification.
- Establish a usable control session before expecting preflight to run. Once access is available, read the [preflight skill](skills/iq9-preflight/SKILL.md); start with `--profile board` for an unknown stack, then use the app's matching profile after setup. Example from the laptop's repo root, without requiring a board-side repo copy:

  ```bash
  ssh "$IQ9_HOST" 'bash -s -- --profile board --json' < skills/iq9-preflight/scripts/preflight.sh
  ```

- For laptop-only documentation work or inaccessible boards, report board preflight as unperformed; do not run it on the laptop as a substitute.
- Internet may be used during approved setup/staging. Check connectivity from the board; preflight's informational probe is not an online-readiness test. Preserve the active control path before network changes. The final demo must still run without external network access.
- Before downloads/imports, inspect `geniex list` if available, local weights, the participant-confirmed USB model drive, and `df -h /`. If GenieX is missing, inspect local files/disk first and its cache after approved installation. Missing cache registration does not prove weights absent. Never re-pull cached models.

## Non-negotiable rules

1. **Offline at runtime:** load local snapshots/cache entries only. No downloads, installs, telemetry, cloud services, or CDN assets. Enable offline loading settings before Transformers imports and use `local_files_only=True`.

2. **Cap and validate LFM calls:** use `max_completion_tokens` for GenieX chat and `max_tokens` for completions; use `--max-tokens` for the ZETIC CLI. Reject zero/missing tokens and empty or reasoning-only text answers; validate tool calls for tool requests. Tokens or `ok` do not prove usability. Follow the generator skill for GenieX and the ZETIC example for its separate CLI.

3. **If using the reference d1 integration:** load the pinned local snapshot through Transformers, fp32 CPU, once—not GenieX decision endpoints. ZETIC's optional native Decision API uses separate local packages and needs its own result/device validation and task calibration; it does not change the reference pin or Python examples. Keep d1/LFM sequential unless re-measured. Calibrate task-representative labels with held-out evaluation; never copy 0.5, another runtime's threshold, or synthetic thresholds. d1's zero output tokens are expected.

4. **Code authorizes actions:** validate schemas, enforce allowlists and policy before writes or real-world actions, and report code's action records—not model prose. Log each iteration as flushed JSONL, separating proposals, actions, and errors. Return loop errors as data, not crashes.

5. **Verify generator NPU execution:** send a capped request. For GenieX, inspect the current server's device/offload log for `HTP0`. For ZETIC, inspect the current CLI's Hexagon v73/two-NSP load and device logs; CPU work remains, so do not claim entirely-NPU execution. Missing output needs diagnosis, not an assumed CPU fallback. Do not silently switch compute routes.

6. **Get approval before changes:** system/runtime installation or upgrades; model copies/downloads/imports/removal (`geniex pull/remove/clean`, `fetch_d1.py`); changing the d1 revision pin or user configuration (including network, account, and SSH settings); deleting user files; non-loopback server binding; or network cuts. This includes laptop serial-tool/driver installation. Review snapshot code before enabling `trust_remote_code`.

7. **Protect the board:** inspect resolved paths and symlinks before deletion, back up replaced board files, and preserve unrelated files. Do not stop a server you did not start without permission. Before a network cut, establish a tested local console or isolated USB-C control link and restoration plan.

## Choose the relevant skill

Read the corresponding `SKILL.md` **before doing that work**. Skills supply procedures and helper boundaries; `.claude/skills/` and `.agents/skills/` link here.

| Skill | Use it for |
|---|---|
| [iq9-getting-started](skills/iq9-getting-started/SKILL.md) | Guided onboarding: UART, setup internet, SSH, approved setup, first NPU response |
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
- Report only numbers measured for the team's own app, model, and runtime; never quote numbers from docs as measurements. No emoji markers.
