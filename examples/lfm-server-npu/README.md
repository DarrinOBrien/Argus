# Example: GenieX on the NPU with LFM3-1.7B

Starts `geniex serve --compute npu`, sends one capped chat request to LFM3-1.7B, prints the reply and token counts, and stops the server it started. Standard library only, so no venv is needed.

Script: [`serve_lfm_npu.py`](serve_lfm_npu.py)

## Prerequisites

- GenieX CLI v0.10.0 on the PATH. Install it below.
- The model in the GenieX cache. The script checks this and does not download:

  ```bash
  geniex list                                  # look for LiquidAI/LFM3-1.7B-GGUF  Q4_0
  geniex pull LiquidAI/LFM3-1.7B-GGUF:Q4_0     # only if it is missing
  ```

- Python 3.

## Install GenieX

**External monitor warning:** organizers report a GPU-driver issue after the current Adreno APT update. Monitor setups must **remove/roll back that update** with the organizers' procedure and board-owner approval. SSH is unaffected; a headless SSH/web UI setup over an isolated USB-C link is allowed. See [Developer Notes](../../README.md#external-monitors-and-headless-setups) and [USB-C access](../../docs/offline-readiness.md#display-and-usb-c-access).

Needs outbound HTTPS during setup to `qaihub-public-assets.s3.us-west-2.amazonaws.com`, `curl` or `wget`, and the NPU driver packages. Inspect the existing installation first and obtain approval before installing only missing libraries; do not install/update `qcom-adreno1` as part of this NPU setup:

```bash
sudo apt-get install -y libatomic1 libglib2.0-0 ocl-icd-libopencl1
sudo apt-get install -y qcom-fastrpc1 libqnn1
```

Install the version this example was tested on:

```bash
curl -fsSL https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-geniex/install.sh | sh -s -- --version v0.10.0
```

- As a regular user, the install goes to `~/.local/share/geniex`, and the launcher goes to `~/.local/bin/geniex`. If the installer says `~/.local/bin` is not on your PATH, add it (`export PATH="$HOME/.local/bin:$PATH"` in your shell profile). As root, it goes to `/usr/local/lib/geniex` and `/usr/local/bin`.
- Leave out `--version` to get the newest stable release instead. That may not match the version this example was tested on.
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

1. Checks `geniex list` for the model and precision. Exits with the `geniex pull` command if the model is missing.
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

The output below is the historical LFM2.5-2.6B result on GenieX v0.8.0. It is retained as a regression baseline and is not an LFM3 measurement:

```
starting geniex serve --compute npu ...
The user wants a one-sentence explanation of why on-device inference is beneficial when the network is down.
...

finish_reason=length prompt_tokens=27 completion_tokens=128
end-to-end 11.04 s (11.6 tok/s, includes prefill)
Hit the cap. LFM2.5-2.6B includes reasoning in the answer; raise --max-tokens or make the prompt narrower.
```

The reply is the legacy model's reasoning, not just the answer.

## Things to know

- **Use `max_completion_tokens`.** v0.4.0 ignored `max_tokens`. v0.8.0 honours both, and `max_completion_tokens` wins if both are set. The script sends `max_completion_tokens`, which works on both versions. ✅ (measured)
- **Inspect LFM3 output on the board.** Keep the cap low and check `finish_reason` before raising it.
- **Zero-token replies.** After several identical requests, GenieX v0.8.0 can return a reply with no tokens (`completion_tokens: 0`). Streaming is not the cause. The script detects this, prints a warning, and exits with code 2. Restart `geniex serve` to clear it. See [`docs/runtimes.md`](../../docs/runtimes.md#known-gap-zero-token-responses-on-v080).
- **Cold start.** The script starts the server, so its first request includes the model load. To see warm timing, run it with `--keep-running`, then run it again. The second run reuses the server. The server unloads the model after 300 s idle by default. See [`docs/runtimes.md`](../../docs/runtimes.md#server-lifecycle-model-loading-and-idle-unloading).
- **`geniex serve` runs on loopback only** (`127.0.0.1:18181`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `... is not in the GenieX cache` | `geniex pull LiquidAI/LFM3-1.7B-GGUF:Q4_0` |
| `geniex serve exited with code ...` | Read the log (default `geniex-serve.log`) |
| `did not answer ... within 60 s` | Raise `--startup-timeout`; the first load can take a while |
| Reply is empty or cut off | Raise `--max-tokens`; check `finish_reason` |
| `geniex: command not found` | Put `~/.local/bin` on the PATH |
