# Example: System One decisions with d1-2B (Transformers, CPU)

Calls `LiquidAI/d1-2B` through transformers and `trust_remote_code=True`, the path the model card documents. The example asks named questions over a sensor state and gets typed answers back from one forward pass, with zero output tokens.

It shows the three question types: `noul` (yes/no probability), `choice` (one of named options, with probabilities), and `score` (median level on an ordered scale). It also covers an image question and a packed batch.

The code path is statically tested, but d1-2B still needs an IQ-9075 run. The checked-in [`sample-output-fp32.txt`](sample-output-fp32.txt) is the historical d1-3B baseline, not an LFM3 result.

This uses the model card's `system_one()` API through Transformers, run in-process on the CPU. It remains the board's decision route until GenieX decision serving is verified with d1-2B.

## What is already on the board

Checked on the IQ-9075 (Ubuntu 24.04.4 LTS, aarch64). These were installed before this example and were not changed:

| Piece        | Version           | Where                                                                                    |
| ------------ | ----------------- | ---------------------------------------------------------------------------------------- |
| Python       | 3.12.3            | system                                                                                   |
| pip          | 24.0              | system                                                                                   |
| python3-venv | 3.12.3-0ubuntu2.1 | apt, already installed                                                                   |
| torch        | 2.11.0+cu130      | `~/.local` (user site). `torch.cuda.is_available()` is `False`, so this runs on the CPU. |
| torchvision  | 0.26.0+cu130      | `~/.local` (user site)                                                                   |
| pillow       | 10.2.0            | system                                                                                   |
| numpy        | 2.4.4             | user site                                                                                |
| GenieX CLI   | installed         | `/usr/local/bin/geniex`. Not used by this path.                                          |

The torch build is tagged `+cu130`, but this board has no CUDA device, so CPU is the only path. The example runs fine on CPU.

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

### Historical d1-3B output

```
loaded /home/ubuntu/models/d1-3B as float32 in 3.0 s, threads=8

== 1. sensor states
{"obs": {"temp_c": 71.5, "temp_c_1min_ago": 58.0, "motion": "none"}, "p_alert": 0.6983, "alert_fired": true,  "category": "thermal", "severity_expected_level": 1.0,   "output_tokens": 0, "ms": 4555.9}
{"obs": {"temp_c": 36.8, "temp_c_1min_ago": 36.6, "motion": "none"}, "p_alert": 0.0686, "alert_fired": false, "category": "normal",  "severity_expected_level": 0.264, "output_tokens": 0, "ms": 4268.9}
{"obs": {"temp_c": 37.0, "temp_c_1min_ago": 36.9, "motion": "sudden 2.1 g spike"}, "p_alert": 0.5998, "alert_fired": true, "category": "motion", "severity_expected_level": 1.031, "output_tokens": 0, "ms": 4464.4}

== 2. image (state=None)
{"p_red_object": 0.9865, "ms": 7638.5, "input_tokens": 91}

== 3. batch of 3
batch of 3 in 13724.1 ms total
```

Read these as plausibility checks, not validation. The three states are the examples in the script. The third state sits just above the threshold, so a small change in input flips the alert.

## Historical d1-3B measurements on the IQ-9075

|                                                          | fp32 (default) |   bf16 |
| -------------------------------------------------------- | -------------: | -----: |
| Model load                                               |          3.0 s |  1.7 s |
| One sensor decision (3 questions, one pass), median of 3 |         4.46 s | 23.9 s |
| Image decision (`noul`, 256×256)                         |          7.6 s | 26.6 s |
| Batch of 3 states                                        |         13.7 s | 73.2 s |
| Peak RSS                                                 |        19.4 GB | 7.2 GB |
| Full run, wall clock                                     |           50 s |  206 s |

These numbers do not describe d1-2B. Re-run the example and record the d1-2B result before the demo.

Notes from the previous stack:

* **Use fp32 on this board.** bf16 is about 5× slower on this CPU, so it is kept only as a memory option.
* **Batching does not help on CPU.** The card's batch speedup is for GPUs. Here three states cost about three times one state.
* **Decisions are about 4.5 s each.** That is fine for a slow monitoring loop and too slow for anything faster. Plan the loop around it.
* bf16 changes the probabilities a little (`p_alert` 0.7058 vs 0.6983 for the same state).
* These numbers are for the CPU path. The card's latencies (26–50 ms) are for Jetson and Apple hardware and do not apply here.

## Troubleshooting

| Symptom                                   | Cause                                              | Fix                                                                                         |
| ----------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `check_env.py` fails on `pinned revision` | Weights were downloaded without `fetch_d1.py`      | Run `python fetch_d1.py` again. It reuses the local files and writes the `REVISION` marker. |
| `ModuleNotFoundError` for transformers    | Venv not activated                                 | `source ~/.venvs/d1/bin/activate`                                                           |
| torch and torchvision mismatch            | torchvision version does not match the torch build | Keep the system torch and install the matching torchvision (0.26.0 for torch 2.11.0)        |
| Out of memory with fp32                   | Other large models resident                        | Stop other servers, or measure `--dtype bfloat16` before relying on it                      |
| Slow first call                           | Setup cost on first use                            | The example makes a warm-up call before timing                                              |
