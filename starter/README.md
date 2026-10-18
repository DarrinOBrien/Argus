# Starter: the five-minute check

One command confirms the board, the decision layer, and the generator are ready. It also leaves a decision log you can show. Run it first, before you build anything.

```bash
./starter/run.sh              # board checks, one d1-3B decision pass, one LFM2.5-2.6B generation
./starter/run.sh --skip-lfm   # same, without the generator
```

It downloads nothing. If something is missing, it stops and prints the command that fixes it.

## Before you run it

One-time setup, done while the network is up:

| Needed | Set up with |
|---|---|
| GenieX v0.8.0 and the NPU driver packages | [`docs/developer-guide.md` §3](../docs/developer-guide.md#3-setup) |
| `LiquidAI/LFM2.5-2.6B-GGUF:Q4_0` in the GenieX cache | `geniex list`. If it is missing: `geniex pull LiquidAI/LFM2.5-2.6B-GGUF:Q4_0`. Don't re-pull a model you already have ([why](../docs/runtimes.md#pitfalls)). |
| The d1 venv `~/.venvs/d1` and the snapshot `~/models/d1-3B` | [`examples/system-one-decision`](../examples/system-one-decision/README.md#install) |

d1-3B is not a GenieX model. It runs through transformers from a local snapshot, so it never shows up in `geniex list`.

Override the defaults with `D1_PYTHON=/path/to/python` and `D1_MODEL_DIR=/path/to/d1-3B`.

## What it does

| Step | What runs | Expected |
|---|---|---|
| 1. Board | `uname -m`, `geniex version`, `geniex config get chipset`, `/dev/fastrpc-cdsp*`, `df -h /` | `aarch64`, v0.8.0, `Dragonwing IQ-9075 EVK` |
| 2. Decision layer | `examples/system-one-decision/check_env.py` in the d1 venv | `All checks passed.` |
| 3. Decision pass | `system_one_example.py`: three sensor states, one image, one batch | `p_alert` 0.698 / 0.069 / 0.600, about 4 s per state. Each decision is appended to `starter/demo_log.jsonl`. |
| 4. Generation | `examples/lfm-server-npu/serve_lfm_npu.py --max-tokens 48`. It reuses a running `geniex serve`, or starts one and stops it when done. | 48 tokens with `finish_reason=length`. The reply is the model's reasoning, which is normal for this model ([why](../examples/always-on-agent/README.md#explanations-why-a-raw-completion)). |

Measured on the IQ-9075: the whole script took 75 s with a warm server already running. If the script starts the server itself, the first request adds about 5 s.

## Next

| Build | Start from |
|---|---|
| An agent that watches local signals and acts | [`examples/always-on-agent`](../examples/always-on-agent/README.md) |
| A model that calls your functions | [`examples/tool-calling`](../examples/tool-calling/README.md) |
| Your own LFM requests | [`examples/lfm-server-npu`](../examples/lfm-server-npu/README.md) and [`docs/runtimes.md`](../docs/runtimes.md) |
| The offline proof for the demo | [`docs/offline-readiness.md`](../docs/offline-readiness.md) |
