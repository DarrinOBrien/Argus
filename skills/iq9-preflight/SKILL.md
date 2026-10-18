---
name: iq9-preflight
description: Check that a Dragonwing IQ-9075 board is ready for the LiquidAI hackathon stack (GenieX v0.8.0, NPU device nodes, cached LFM models, the d1-3B venv and pinned snapshot, disk, memory, thermal sensors, network state). Use at the start of a session, before building or demoing, when something "suddenly stopped working", or when the user asks "is my board ready".
compatibility: Run on the IQ-9075 itself (bash, coreutils, curl, python3). From a laptop, run it over SSH.
metadata:
  version: "0.1"
---

# IQ-9075 preflight

Run this before anything else in a session. It only reads, never changes anything, and never downloads.

```bash
skills/iq9-preflight/scripts/preflight.sh          # report for a human
skills/iq9-preflight/scripts/preflight.sh --json   # {"ready": bool, "checks": [{status, check, detail, fix}]}
```

If the agent runs on a laptop, not on the board, use SSH. Both commands below are run from the repo root:

```bash
ssh "$IQ9_HOST" 'bash -s -- --json' < skills/iq9-preflight/scripts/preflight.sh
```

## Reading the result

- `FAIL` means the stack won't work until it's fixed. `WARN` means it will work, but read the detail. `ok` means fine.
- Each non-ok line comes with a `fix`. **Show the fix to the user. Don't run it yourself** if it needs `sudo`, the network, or more than a few hundred MB of disk. Those cases are installing driver packages, `usermod`, `geniex pull`, and `fetch_d1.py`.
- `network: online` is informational. During the event, anything that needs the network has to be done before the network is cut. Pass this along to the user.

| Check | What it means when it isn't ok |
|---|---|
| `npu-nodes`, `npu-access` | The NPU is unusable, and GenieX will quietly use the CPU instead (about 2.8 tok/s through the server, against about 23 on the NPU) |
| `geniex` WARN | The version differs from v0.8.0, so the numbers and workarounds in `docs/` may not hold. Don't upgrade during the event |
| `model:LiquidAI/LFM2.5-2.6B-GGUF` | The generator is missing. Pull it once, while the network is up |
| `model:LiquidAI/LFM2-1.2B-Tool-GGUF` WARN | Needed only for tool calling |
| `d1-venv`, `d1-snapshot` | The decision gate can't run. Follow `examples/system-one-decision/README.md` |
| `server` WARN | Normal if nothing has started it yet. See the `iq9-geniex-lfm` skill |
| `disk` WARN | Under 10 GB free. Run `geniex list` and ask the user before removing anything |

## Deeper checks (on request)

- **Full d1 check:** `~/.venvs/d1/bin/python examples/system-one-decision/check_env.py`, run from that directory.
- **End-to-end smoke test (about 75 s):** `./starter/run.sh`. It runs one d1 decision pass and one LFM generation.
- **Is the NPU really in use?** Start the server with `skills/iq9-geniex-lfm/scripts/serve.sh start`, send one request, then run `serve.sh status`. It should show `device: Using 1 device(s): HTP0`.
