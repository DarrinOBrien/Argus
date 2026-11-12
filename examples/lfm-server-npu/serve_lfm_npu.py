#!/usr/bin/env python3
"""Send a capped, validated LFM3-1.7B request to an existing GenieX NPU server.

Start skills/iq9-geniex-lfm/scripts/serve.sh run in a separate board terminal first.
This example never starts/stops servers, installs software, or downloads models.
"""

import argparse
import json
import math
from pathlib import Path
import sys
import time

CLIENT_DIR = Path(__file__).resolve().parents[2] / "skills/iq9-geniex-lfm/scripts"
sys.path.insert(0, str(CLIENT_DIR))
from lfm_client import LFM, DEFAULT_MODEL  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default="In one sentence, why does on-device inference help when the network is down?")
    parser.add_argument("--max-tokens", type=int, default=128,
                        help="positive safety cap, sent as max_completion_tokens")
    parser.add_argument("--timeout", type=float, default=180, help="seconds per request, including model loading")
    args = parser.parse_args()
    if args.max_tokens <= 0:
        parser.error("--max-tokens must be positive")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if not args.prompt.strip():
        parser.error("--prompt must not be empty")

    lfm = LFM(model=DEFAULT_MODEL, compute="npu", timeout=args.timeout)
    if not lfm.ready():
        print("No GenieX server at 127.0.0.1:18181. In a separate board terminal, run "
              "bash skills/iq9-geniex-lfm/scripts/serve.sh run from the repo root.", file=sys.stderr)
        return 2
    try:
        if DEFAULT_MODEL not in lfm.models():
            print(f"{DEFAULT_MODEL} is not registered. Follow docs/developer-guide.md section 4 "
                  "(inspect local/USB assets first; copies/imports/downloads need approval).", file=sys.stderr)
            return 2
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Could not inspect server models: {exc}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    result = lfm.chat([{"role": "user", "content": args.prompt}],
                      max_tokens=args.max_tokens, enable_think=False)
    result["wall_s"] = time.perf_counter() - started
    if result["ok"] and result["finish"] != "stop":
        result.update(ok=False, error=f"generation did not finish naturally: {result['finish']}")
    print(json.dumps(result), flush=True)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
