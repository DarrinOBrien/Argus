# Example: GenieX on the NPU with LFM3-1.7B

Starts `geniex serve --compute npu`, sends one capped chat request to LFM3-1.7B, prints the reply and token counts, and stops the server it started. Standard library only, so no venv is needed.

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

```bash
python3 serve_lfm_npu.py
python3 serve_lfm_npu.py --prompt "Say hello in five words." --max-tokens 64
python3 serve_lfm_npu.py --keep-running             # leave geniex serve up afterwards
```

| Option | Default | Meaning |
|---|---|---|
| `--prompt` | a one-sentence question about on-device inference | user message |
| `--max-tokens` | 128 | cap on generated tokens, sent as `max_completion_tokens` |
| `--startup-timeout` | 60 | seconds to wait for `geniex serve` to answer |
| `--keep-running` | off | do not stop a server this script started |
| `--log` | `geniex-serve.log` | where `geniex serve` writes its log (in the current directory) |

## What it does

1. Checks `geniex list` for the model and precision. If the model is missing, exits and points to [Stage your model](../../docs/developer-guide.md#4-stage-your-model).
2. Checks whether `127.0.0.1:18181` already answers. If it does, reuses that server. If not, starts `geniex serve --compute npu` and polls `/v1/models` until it answers, up to `--startup-timeout` seconds.
3. Sends one non-streamed `POST /v1/chat/completions` with `compute: npu`, `max_completion_tokens` set from `--max-tokens`, and `stream: false`.
4. Prints the reply, `finish_reason`, prompt and completion token counts, and end-to-end tokens per second. Warns when the reply hit the cap.
5. Stops the server it started, including when the request fails, unless `--keep-running` is set. It never stops a server it reused.

## Why a Python script

One request is one HTTP call, so a shell version works for a quick check:

```bash
geniex serve --compute npu > serve.log 2>&1 &
for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:18181/v1/models && break; sleep 1; done
curl -s http://127.0.0.1:18181/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"LiquidAI/LFM3-1.7B-GGUF:Q4_0","messages":[{"role":"user","content":"Say hi."}],"max_completion_tokens":32,"compute":"npu","stream":false}'
# stop the process that holds the port; kill $! does not reach the server
kill "$(ss -ltnp | sed -n 's/.*127.0.0.1:18181.*pid=\([0-9]*\).*/\1/p')"
```

The script exists for the parts that shell gets wrong or leaves out:

- **Cleanup.** `$!` is the launcher, not the server. In our test, `kill $!` left the server running and answering on the port. The script stops the process it started in a `finally` block. We tested the normal path, which left no server running. We have not tested a failed request.
- **Readiness with a timeout.** It polls until the server answers, fails with the log path if the server exits or doesn't answer in time, and never waits forever.
- **Reuse.** If a server is already on the port, it uses that server and doesn't start a second one.
- **Request fields that are easy to get wrong.** Use `max_completion_tokens`, `stream: false` for one JSON reply, and `compute: npu` on every request.
- **Output that matches this model.** The reply usually contains reasoning, so the script prints token counts and warns when the cap is hit.

Use the shell version for a one-off check. Use the script for runs you repeat or that have to clean up after themselves.

## Expected output

The script prints the reply, then a summary line:

```
finish_reason=<stop|length> prompt_tokens=<n> completion_tokens=<n>
end-to-end <s> s (<tok/s> tok/s, includes prefill)
```

`finish_reason=length` means the cap was hit; the script warns, because LFM3-1.7B may spend the budget on reasoning. A zero-token reply prints a warning and exits with code 2.

## Things to know

- **Use `max_completion_tokens` on chat.** It takes precedence over `max_tokens` if both are set.
- **Inspect LFM3 output on the board.** Keep the cap low and check `finish_reason` before raising it.
- **Unusable replies.** A reply can be empty or report zero tokens. The script detects zero tokens, prints a warning, and exits with code 2; if it persists, restart `geniex serve`. See [`docs/runtimes.md`](../../docs/runtimes.md#handling-unusable-output).
- **Cold start.** The script starts the server, so its first request includes the model load. To see warm timing, run it with `--keep-running`, then run it again. The second run reuses the server. The server unloads the model after 300 s idle by default. See [`docs/runtimes.md`](../../docs/runtimes.md#server-lifecycle-model-loading-and-idle-unloading).
- **`geniex serve` runs on loopback only** (`127.0.0.1:18181`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `... is not in the GenieX cache` | [Stage the model](../../docs/developer-guide.md#4-stage-your-model): USB copy/import first, approved download only as a fallback |
| `geniex serve exited with code ...` | Read the log (default `geniex-serve.log`) |
| `did not answer ... within 60 s` | Raise `--startup-timeout`; the first load can take a while |
| Reply is empty or cut off | Raise `--max-tokens`; check `finish_reason` |
| `geniex: command not found` | Put `~/.local/bin` on the PATH |
