# Example: System One decisions with d1-2B (Transformers, CPU)

Calls `LiquidAI/d1-2B` through transformers and `trust_remote_code=True`, the path the model card documents. The example asks named questions over a sensor state and gets typed answers back from one forward pass, with zero output tokens.

It shows the three question types: `noul` (yes/no probability), `choice` (one of named options, with probabilities), and `score` (median level on an ordered scale). It also covers an image question and a packed batch.

This uses the model card's `system_one()` API through Transformers, run in-process on the CPU. It remains the board's decision route until GenieX decision serving is verified with d1-2B.

## Check what is already on the board

Reuse what is installed rather than adding a second copy. On the board:

```bash
python3 --version
python3 -c "import venv" && echo venv-ok
python3 -c "import torch, torchvision; print(torch.__version__, torchvision.__version__, torch.cuda.is_available())" 2>/dev/null || echo "torch/torchvision not installed"
python3 -c "import PIL, numpy; print(PIL.__version__, numpy.__version__)" 2>/dev/null || echo "pillow/numpy not installed"
```

The IQ-9075 has no CUDA device, so `torch.cuda.is_available()` is `False` even for a `+cu` torch build; this example runs on the CPU. GenieX is not used by this path.

## What this example adds

| Piece                                                                         | Version                   | Notes                                                                              |
| ----------------------------------------------------------------------------- | ------------------------- | ---------------------------------------------------------------------------------- |
| venv `~/.venvs/d1`                                                            | —                         | created with `--system-site-packages` so it reuses the torch and torchvision above |
| transformers                                                                  | 5.19.0 or newer           | requirement is `>=5.19`                                                            |
| huggingface_hub                                                               | 1.33.0                    | pulled in by transformers; used by `fetch_d1.py`                                   |
| tokenizers, safetensors, regex, typer, rich, shellingham, annotated-doc, idna | pulled in by transformers | —                                                                                  |
| `~/models/d1-2B`                                                              | commit `10e7671d44e4`     | 3.8 GB weights plus tokenizer and code.                                            |

A dry run confirmed pip would only add transformers and its dependencies. It would not replace torch, torchvision, or pillow.

## Install

Run on the IQ-9075. Each step is idempotent.

```bash
# 1. venv that reuses the system torch and torchvision
python3 -m venv --system-site-packages ~/.venvs/d1
source ~/.venvs/d1/bin/activate
python -m pip install -U pip

# 2. the example's requirements (transformers, pillow, packaging; torchvision if missing)
cd examples/system-one-decision          # from the repo root
python -m pip install -r requirements.txt

# 3. the pinned d1-2B snapshot (about 3.8 GB, Hub needed once)
python fetch_d1.py --dest ~/models/d1-2B

# 4. confirm the stack
python check_env.py
```

`fetch_d1.py` pins the commit in one place (`REVISION`). It writes a `REVISION` file into the model directory, and `check_env.py` compares it against the pin.

Before you change the pin, review the remote code. `trust_remote_code=True` runs it. This review covered every shipped Python file in revision `10e7671d44e4`, including the d1 API/runner, LFM3/VL model code, processors, parsing, calibration, and media helpers. Nothing starts subprocesses or uses shell execution, `eval`, `exec`, or pickle. The only Hub helpers are Transformers loaders; with the local model directory and offline environment variables, they resolve local files.

## Run

```bash
python system_one_example.py --model-dir ~/models/d1-2B --log decisions.jsonl
python system_one_example.py --dtype bfloat16 --log decisions_bf16.jsonl   # slower, see below
```

Each decision is appended as one JSON line to `--log`. The alert threshold (`ALERT_THRESHOLD = 0.5`) is an example value. Tune it on states you have labeled yourself.

### Notes for the CPU path

* **Use fp32.** bf16 uses less memory but is several times slower on this CPU; treat it only as a memory option and measure it first.
* **Batching does not help on the CPU.** The model card's batch speedup is for GPUs; here a batch of N states costs about N single decisions.
* **Plan the loop around d1's latency.** A CPU decision takes seconds, not milliseconds: fine for a slow monitoring loop, too slow for a fast one. The card's millisecond latencies are for other hardware and do not apply here.
* **The example states are plausibility checks, not validation.** A state near the threshold can flip with a small input change.

Measure load time, decision and image latency, batch time, and peak RSS for your own task before setting an interval.

## Troubleshooting

| Symptom                                   | Cause                                              | Fix                                                                                         |
| ----------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `check_env.py` fails on `pinned revision` | Weights were downloaded without `fetch_d1.py`      | Run `python fetch_d1.py` again. It reuses the local files and writes the `REVISION` marker. |
| `ModuleNotFoundError` for transformers    | Venv not activated                                 | `source ~/.venvs/d1/bin/activate`                                                           |
| torch and torchvision mismatch            | torchvision version does not match the torch build | Keep the system torch and install the matching torchvision (0.26.0 for torch 2.11.0)        |
| Out of memory with fp32                   | Other large models resident                        | Stop other servers, or measure `--dtype bfloat16` before relying on it                      |
| Slow first call                           | Setup cost on first use                            | The example makes a warm-up call before timing                                              |
