# Example: GenieX on the NPU with LFM3-1.7B

Sends a capped chat request to LFM3-1.7B through an existing GenieX NPU server. It uses the shared validated LFM client and prints a JSON result. Standard library only, so no venv is needed. Server lifecycle stays in a separate terminal; this example never starts or stops a server.

Script: [`serve_lfm_npu.py`](serve_lfm_npu.py)

## Prerequisites

- GenieX CLI v0.10.0 on the PATH, with NPU device access. See [Setup](#setup) below.
- The model in the GenieX cache. The script checks this and does not download:

  ```bash
  geniex list                                  # look for LiquidAI/LFM3-1.7B-GGUF  Q4_0
  ```

  If it is missing, follow [Stage your model](../../docs/developer-guide.md#4-stage-your-model). Copy/import it from the supplied USB model drive first (copy, never move); download only with approval if no local copy exists.
- Python 3.

<a id="install-geniex"></a>

## Setup

This example has no setup recipe of its own. Follow the [developer guide](../../docs/developer-guide.md#3-setup), which is the single maintained procedure:

1. **Inventory first.** Run the hardware [preflight](../../docs/developer-guide.md#31-confirm-the-board) and check what is already installed. Reuse working packages and an existing GenieX.
2. **Driver packages** ([section 3.2](../../docs/developer-guide.md#32-driver-packages)). With approval: refresh the existing APT sources, **simulate** the install of only the missing packages, review the plan, then install interactively. Do not use `-y`. For package-file 404s, see [stale APT lists](../../docs/developer-guide.md#stale-apt-lists-and-package-file-404s).
3. **NPU access.** Check read **and** write on the CDSP nodes; see [NPU device access](../../docs/developer-guide.md#npu-device-access).
4. **GenieX v0.10.0** ([section 3.3](../../docs/developer-guide.md#33-geniex-cli)). Download the installer, read it, then run it with `--version v0.10.0`. Do not pipe it straight into `sh`.

Out of scope here: Adreno/graphics packages, broad `apt upgrade`, and new package sources. **External monitor warning:** organizers report a GPU-driver issue after the current Adreno APT update; see [Developer Notes](../../README.md#external-monitors-and-headless-setups). SSH is unaffected, and a headless SSH/web UI setup over an isolated USB-C link is allowed ([USB-C access](../../docs/offline-readiness.md#display-and-usb-c-access)).

Notes on the GenieX installer:

- As a regular user, the install goes to `~/.local/share/geniex`, and the launcher goes to `~/.local/bin/geniex`. If the installer says `~/.local/bin` is not on your PATH, add it (`export PATH="$HOME/.local/bin:$PATH"` in your shell profile). As root, it goes to `/usr/local/lib/geniex` and `/usr/local/bin`.
- Leave out `--version` to get the newest stable release instead. This repo targets v0.10.0.
- Installing over an existing GenieX replaces it. The installer moves the old install aside and deletes it after the new one is in place. Back up the old install first if you need it.
- `geniex update` does not install anything. It only prints the install command.
- Keep the downloaded `geniex-cli-linux-arm64-v0.10.0.tar.gz` archive if the board will be offline later.

Check the install:

```bash
geniex version              # expect GenieX CLI Version: v0.10.0
geniex config get chipset   # Dragonwing IQ-9075 EVK
```


## Run

On the board, from the repo root, start the foreground server in a separate terminal (or reuse an appropriate existing server):

```bash
bash skills/iq9-geniex-lfm/scripts/serve.sh run
```

In another board terminal, from the repo root:

```bash
python3 examples/lfm-server-npu/serve_lfm_npu.py
python3 examples/lfm-server-npu/serve_lfm_npu.py --prompt "Say hello in five words." --max-tokens 64
skills/iq9-geniex-lfm/scripts/serve.sh status
```

Check the answer and confirm `HTP0` in the current server's log after the request. A token count or HTTP success alone does not verify useful output or NPU execution.

| Option | Default | Meaning |
|---|---|---|
| `--prompt` | a one-sentence question about on-device inference | nonempty user message |
| `--max-tokens` | 128 | positive cap sent as `max_completion_tokens` |
| `--timeout` | 180 | seconds per request, including any model loading |

## What it checks

The script checks server readiness and exact model registration, then calls the shared [LFM client](../../skills/iq9-geniex-lfm/scripts/lfm_client.py) with `compute: npu`, `stream: false`, and `enable_think: false`. The client rejects missing/zero usage and empty answers, and retries unusable output at most once with a fresh tag. Reasoning in a separate field does not count as an answer. The sample also rejects a response that did not finish naturally (`finish_reason != stop`).

Exit **0** means the output guards passed; **2** means a readiness, registration, request, or output failure. Invalid arguments also exit 2 before any request. The JSON includes `ok`, `text`, `tokens`, `finish`, `retried`, `error`, and timing. `ms` describes the final attempt; `wall_s` includes both attempts when retried. Neither is pure decode speed or an answer-quality evaluation.

The old `--keep-running`, `--startup-timeout`, and server `--log` options were removed. Start/stop the owned server explicitly with `serve.sh`; the GenieX launcher PID is not a reliable server PID. Do not interrupt a shared server. No install, import, or download happens here.

## Timing and offline status

The first request after a model unload includes loading. Repeat the command while the model remains resident to observe warm requests; `serve.sh run` defaults to a 1,800-second keepalive. See [server lifecycle](../../docs/runtimes.md#server-lifecycle-model-loading-and-idle-unloading).

This revised sample has local mocked validation only; a bounded IQ9 check and network-off rehearsal remain unperformed for this revision. Record actual board/runtime/model/precision, workload, sample counts, successful/failed runs, and medians before reporting performance. See [offline readiness](../../docs/offline-readiness.md).

## Troubleshooting

| Symptom | Next step |
|---|---|
| No server | Start the foreground server in a separate board terminal; inspect its log |
| Model is not registered | Inspect board/local/USB assets, then obtain approval for needed staging |
| Empty or reasoning-only answer after retry | Inspect the returned error and current log; narrow the prompt or adjust the cap before another bounded attempt |
| `finish=length` | The cap was hit; inspect reasoning/output, then choose a suitable cap for the workload |
| Missing `HTP0` | Diagnose device access and current-server logs; do not assume CPU fallback |

## Local checks

```bash
python3 -m unittest discover -s examples/lfm-server-npu -p 'test_*.py' -v
```
