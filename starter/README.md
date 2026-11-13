# Starter: the full two-model reference check

This optional check exercises the board, d1 decision layer, and LFM generator after **both models** have been set up. It also leaves a decision log. It is not a fresh-board installer or the first onboarding step, and no fixed run time is promised.

For board access, setup internet, and a first **generator-only** response, start with the [getting-started skill](../skills/iq9-getting-started/SKILL.md) and [developer guide](../docs/developer-guide.md#0-board-access-and-internet-for-setup). d1 is optional for projects but required by this particular script, including with `--skip-lfm`. Without d1, skip it and run the [always-on example](../examples/always-on-agent/README.md) with `--gate rule`.

```bash
./starter/run.sh              # board checks, one d1-2B decision pass, one LFM3-1.7B generation
./starter/run.sh --skip-lfm   # same, without the generator
```

It downloads nothing. If something is missing, it stops and prints what to do next.

## Before you run it

One-time setup, done while the network is up:

| Needed | Set up with |
|---|---|
| GenieX v0.10.0 and the NPU driver packages | [`docs/developer-guide.md` §3](../docs/developer-guide.md#3-setup) |
| `LiquidAI/LFM3-1.7B-GGUF:Q4_0` in the GenieX cache | If absent, import it from the supplied USB model drive; see [model staging](../docs/developer-guide.md#4-stage-your-model). |
| The d1 venv `~/.venvs/d1` and the snapshot `~/models/d1-2B` | [`examples/system-one-decision`](../examples/system-one-decision/README.md#install); copy the snapshot from the USB drive when it is there |

d1-2B runs through transformers from a local snapshot in this repo, so it does not need to appear in `geniex list`.

Unless using `--skip-lfm`, reuse an appropriate running server or start this in a separate board terminal from the repo root before running the starter:

```bash
bash skills/iq9-geniex-lfm/scripts/serve.sh run
```

The starter leaves that server running. Stop it when you are done, using the [generator skill](../skills/iq9-geniex-lfm/SKILL.md#1-server).

Override the defaults with `D1_PYTHON=/path/to/python` and `D1_MODEL_DIR=/path/to/d1-2B`.

## What it does

| Step | What runs | Expected |
|---|---|---|
| 1. Board | `uname -m`, `geniex version`, `geniex config get chipset`, `/dev/fastrpc-cdsp*`, `df -h /` | `aarch64`, v0.10.0, `Dragonwing IQ-9075 EVK` |
| 2. Decision layer | `examples/system-one-decision/check_env.py` in the d1 venv | `All checks passed.` |
| 3. Decision pass | `system_one_example.py`: three sensor states, one image, one batch | Typed answers with zero output tokens; each decision is appended to `starter/demo_log.jsonl`. |
| 4. Generation | `examples/lfm-server-npu/serve_lfm_npu.py --max-tokens 48`. Requires `serve.sh run` in a separate board terminal; never starts/stops a server. | A non-empty capped response with natural completion. Record latency and token counts on the board, and inspect current-server `HTP0`. |

## Next

| Build | Start from |
|---|---|
| An agent that watches local signals and acts | [`examples/always-on-agent`](../examples/always-on-agent/README.md) |
| A model that calls your functions | [`examples/tool-calling`](../examples/tool-calling/README.md) |
| Your own LFM requests | [`examples/lfm-server-npu`](../examples/lfm-server-npu/README.md) and [`docs/runtimes.md`](../docs/runtimes.md) |
| The offline proof for the demo | [`docs/offline-readiness.md`](../docs/offline-readiness.md) |
