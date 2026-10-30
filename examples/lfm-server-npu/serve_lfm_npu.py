#!/usr/bin/env python3
"""Start GenieX on the NPU for LFM3-1.7B and send one capped chat request.

Standard library only. The model must already be in the GenieX cache:
    geniex pull LiquidAI/LFM3-1.7B-GGUF:Q4_0
This script downloads nothing.

    python serve_lfm_npu.py
    python serve_lfm_npu.py --prompt "Say hello in five words." --max-tokens 64
    python serve_lfm_npu.py --keep-running    # leave geniex serve up afterwards
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

MODEL = "LiquidAI/LFM3-1.7B-GGUF:Q4_0"
HOST = "127.0.0.1"
PORT = 18181
BASE = f"http://{HOST}:{PORT}"


def server_up() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE}/v1/models", timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def model_cached(model: str) -> bool:
    """True if `geniex list` shows the repo with the requested precision."""
    repo, _, precision = model.partition(":")
    out = subprocess.run(["geniex", "list"], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        cells = [c.strip() for c in line.split("│")]
        if len(cells) >= 4 and cells[1] == repo and precision in cells[3].split(","):
            return True
    return False


def start_server(log_path: str, timeout: float) -> subprocess.Popen:
    log = open(log_path, "w")
    proc = subprocess.Popen(["geniex", "serve", "--compute", "npu"], stdout=log, stderr=subprocess.STDOUT)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            sys.exit(f"geniex serve exited with code {proc.returncode}; see {log_path}")
        if server_up():
            return proc
        time.sleep(1)
    proc.terminate()
    sys.exit(f"geniex serve did not answer on {BASE} within {timeout:.0f} s; see {log_path}")


def chat(prompt: str, max_tokens: int, timeout: float) -> tuple[dict, float]:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": max_tokens,  # retained for compatibility with the measured legacy runtimes
        "compute": "npu",
        "stream": False,  # one JSON reply per call; streaming is not the cause of zero-token replies (see README)
    }).encode()
    req = urllib.request.Request(f"{BASE}/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return data, time.perf_counter() - t0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", default="In one sentence, why does on-device inference help when the network is down?")
    ap.add_argument("--max-tokens", type=int, default=128,
                    help="cap on generated tokens, sent as max_completion_tokens")
    ap.add_argument("--startup-timeout", type=float, default=60.0, help="seconds to wait for geniex serve")
    ap.add_argument("--keep-running", action="store_true", help="do not stop geniex serve this script started")
    ap.add_argument("--log", default="geniex-serve.log", help="where geniex serve writes its log")
    args = ap.parse_args()

    if not model_cached(MODEL):
        sys.exit(f"{MODEL} is not in the GenieX cache. Run: geniex pull {MODEL}")

    proc = None
    if server_up():
        print(f"reusing geniex serve already listening on {BASE}")
    else:
        print("starting geniex serve --compute npu ...")
        proc = start_server(args.log, args.startup_timeout)

    try:
        data, wall = chat(args.prompt, args.max_tokens, timeout=180)
    finally:
        if proc is not None and not args.keep_running:
            proc.terminate()
            proc.wait(timeout=15)

    choice = data["choices"][0]
    usage = data.get("usage", {})
    n = usage.get("completion_tokens", 0)
    print(choice["message"]["content"].strip())
    print(f"\nfinish_reason={choice['finish_reason']} prompt_tokens={usage.get('prompt_tokens')} "
          f"completion_tokens={n}")
    print(f"end-to-end {wall:.2f} s ({n / wall:.1f} tok/s, includes prefill)")
    if n == 0:
        print("Zero-token reply. "
              "Restart geniex serve and vary the prompt (docs/runtimes.md).")
        sys.exit(2)
    if choice["finish_reason"] == "length":
        print("Hit the cap. LFM3-1.7B may include reasoning in the answer; "
              "raise --max-tokens or make the prompt narrower.")


if __name__ == "__main__":
    main()
