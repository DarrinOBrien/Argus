# Starter: the five-minute check

One command confirms the board, the decision layer, and the generator are ready. It also leaves a decision log you can show. Run it first, before you build anything.

```bash
./starter/run.sh              # board checks, one d1-2B decision pass, one LFM3-1.7B generation
./starter/run.sh --skip-lfm   # same, without the generator
```

It downloads nothing. If something is missing, it stops and prints the command that fixes it.

## Before you run it

One-time setup, done while the network is up:

| Needed | Set up with |
|---|---|
| GenieX v0.10.0 and the NPU driver packages | [`docs/developer-guide.md` §3](../docs/developer-guide.md#3-setup) |
| `LiquidAI/LFM3-1.7B-GGUF:Q4_0` in the GenieX cache | `geniex list`. If it is missing: `geniex pull LiquidAI/LFM3-1.7B-GGUF:Q4_0`. Don't re-pull a model you already have. |
| The d1 venv `~/.venvs/d1` and the snapshot `~/models/d1-2B` | [`examples/system-one-decision`](../examples/system-one-decision/README.md#install) |

d1-2B runs through transformers from a local snapshot in this repo, so it does not need to appear in `geniex list`.

Override the defaults with `D1_PYTHON=/path/to/python` and `D1_MODEL_DIR=/path/to/d1-2B`.

## What it does

| Step | What runs | Expected |
|---|---|---|
| 1. Board | `uname -m`, `geniex version`, `geniex config get chipset`, `/dev/fastrpc-cdsp*`, `df -h /` | `aarch64`, v0.10.0, `Dragonwing IQ-9075 EVK` |
| 2. Decision layer | `examples/system-one-decision/check_env.py` in the d1 venv | `All checks passed.` |
| 3. Decision pass | `system_one_example.py`: three sensor states, one image, one batch | Typed answers with zero output tokens; each decision is appended to `starter/demo_log.jsonl`. |
| 4. Generation | `examples/lfm-server-npu/serve_lfm_npu.py --max-tokens 48`. It reuses a running `geniex serve`, or starts one and stops it when done. | A non-empty capped response. Record latency and token counts on the board. |

The previous stack took 75 s on the reference IQ-9075. Re-measure this LFM3/d1-2B stack before quoting a result.

## Next

| Build | Start from |
|---|---|
| An agent that watches local signals and acts | [`examples/always-on-agent`](../examples/always-on-agent/README.md) |
| A model that calls your functions | [`examples/tool-calling`](../examples/tool-calling/README.md) |
| Your own LFM requests | [`examples/lfm-server-npu`](../examples/lfm-server-npu/README.md) and [`docs/runtimes.md`](../docs/runtimes.md) |
| The offline proof for the demo | [`docs/offline-readiness.md`](../docs/offline-readiness.md) |
