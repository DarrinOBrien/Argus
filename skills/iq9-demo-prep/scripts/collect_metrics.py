#!/usr/bin/env python3
"""Collect capped, local GenieX metrics. Standard library only; no installs or model downloads.

TTFT includes reasoning; answer TTFT is separate. Decode rate is an SSE timing estimate,
not an exact tokenizer benchmark. Without server token usage, token rates remain null.
"""

import argparse
import json
import os
import statistics
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def sh(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def parse_stream(response, started):
    first = answer_first = last = None
    usage = None
    finish = None
    answer = []
    generated_chunks = 0
    for raw in response:
        line = raw.decode().strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        d = json.loads(data)
        if d.get("usage"):
            usage = d["usage"]
        for choice in d.get("choices", []):
            finish = choice.get("finish_reason") or finish
            delta = choice.get("delta") or {}
            content = delta.get("content") or ""
            reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
            if not content and not reasoning:
                continue
            now = time.perf_counter()
            first = now if first is None else first
            last = now
            generated_chunks += 1
            if content:
                answer.append(content)
                answer_first = now if answer_first is None else answer_first
    end = time.perf_counter()
    tokens = (usage or {}).get("completion_tokens")
    known = isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0
    text = "".join(answer).strip()
    error = None
    if not known:
        error = "missing/invalid server token usage; chunks are not tokens"
    elif tokens == 0:
        error = "zero completion tokens"
    elif not text:
        error = "empty answer (reasoning alone)"
    return {
        "ok": error is None, "error": error, "text": text,
        "tokens": tokens if known else None,
        "finish_reason": finish,
        "ttft_s": round(first - started, 4) if first is not None else None,
        "answer_ttft_s": round(answer_first - started, 4) if answer_first is not None else None,
        "e2e_s": round(end - started, 4),
        "generation_tok_s": round(tokens / (end - started), 3)
        if known and end > started else None,
        "decode_tok_s": round((tokens - 1) / (last - first), 3)
        if known and tokens > 1 and first is not None and last > first else None,
        "decode_is_estimate": True,
        "generated_chunks": generated_chunks,
    }


DEFAULT_PROMPT = "Describe one useful edge AI application in one sentence."


def stream_once(base, model, max_tokens, enable_think, prompt=DEFAULT_PROMPT, timeout=120):
    body = {"model": model, "stream": True, "max_completion_tokens": max_tokens,
            "compute": "npu", "enable_think": enable_think,
            "stream_options": {"include_usage": True},
            "messages": [{"role": "user", "content":
                          f"{prompt} Request {uuid.uuid4().hex}."}]}
    req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            sample = parse_stream(response, started)
        if sample["tokens"] is not None and sample["tokens"] > max_tokens:
            sample.update(ok=False, error="completion token cap exceeded")
        return sample
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:200], "tokens": None,
                "e2e_s": round(time.perf_counter() - started, 4)}


def summarize(samples):
    ok = [s for s in samples if s["ok"]]
    def median(key):
        values = [s[key] for s in ok if s.get(key) is not None]
        return round(statistics.median(values), 4) if values else None
    return {"runs": len(samples), "successful_runs": len(ok), "failed_runs": len(samples) - len(ok),
            "zero_token_runs": sum(s.get("tokens") == 0 for s in samples),
            "cap_hit_runs": sum(s.get("finish_reason") == "length" for s in samples),
            "ttft_s_median": median("ttft_s"), "answer_ttft_s_median": median("answer_ttft_s"),
            "decode_tok_s_median": median("decode_tok_s"),
            "generation_tok_s_median": median("generation_tok_s"),
            "e2e_s_median": median("e2e_s"), "samples": samples}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="LiquidAI/LFM3-1.7B-GGUF:Q4_0", help="already-cached model name")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--max-tokens", type=int, default=128,
                    help="cap per request; for long answers use a generous safety cap and check cap_hit_runs")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT,
                    help="user message (a unique request tag is appended); default asks for one sentence")
    ap.add_argument("--timeout", type=float, default=120, help="per-request timeout in seconds")
    ap.add_argument("--enable-think", action="store_true", help="include reasoning (default: thinking disabled)")
    ap.add_argument("--log", default="", help="optional app JSONL log")
    ap.add_argument("--out", default="", help="write JSON evidence here")
    args = ap.parse_args()
    if args.runs < 1 or args.max_tokens < 1 or args.timeout <= 0:
        ap.error("--runs, --max-tokens, and --timeout must be positive")
    if not args.prompt.strip():
        ap.error("--prompt must not be empty")
    try:
        port = int(os.environ.get("GENIEX_PORT", "18181"))
    except ValueError:
        ap.error("GENIEX_PORT must be an integer")
    if not 1 <= port <= 65535:
        ap.error("GENIEX_PORT must be between 1 and 65535")
    base = f"http://127.0.0.1:{port}"
    run = lambda: stream_once(base, args.model, args.max_tokens, args.enable_think, args.prompt, args.timeout)
    warmup = run()
    samples = [run() for _ in range(args.runs)]
    llm = summarize(samples)
    llm.update(max_completion_tokens=args.max_tokens, enable_think=args.enable_think, prompt=args.prompt,
               prompt_is_default=args.prompt == DEFAULT_PROMPT,
               decode_method="estimate: (server completion tokens - 1) / first-to-last generated SSE interval; chunks may bundle tokens",
               generation_method="server completion tokens / full request time (includes prefill and transport)")
    server_pid = None
    for line in sh("ss", "-ltnp").splitlines():
        if f"127.0.0.1:{port} " in line and "pid=" in line:
            server_pid = line.split("pid=", 1)[1].split(",", 1)[0]
            break
    rss = sh("ps", "-o", "rss=", "-p", server_pid) if server_pid else ""
    log_path = Path(os.environ.get("GENIEX_SERVE_LOG", str(Path.cwd() / "geniex-serve.log")))
    device_line = None
    try:
        if log_path.is_file():
            device_line = next((line for line in reversed(log_path.read_text(errors="replace").splitlines())
                                if " device(s):" in line), None)
    except OSError:
        pass  # Missing device evidence remains unknown, not CPU fallback.
    temps = []
    for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            temps.append(int(path.read_text()) / 1000)
        except (OSError, ValueError):
            pass
    out = {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "board": sh("geniex", "config", "get", "chipset"), "geniex": sh("geniex", "version"),
           "model": args.model, "precision_label": args.model.rsplit(":", 1)[-1] if ":" in args.model else None,
           "device_log_excerpt": device_line, "device_log_path": str(log_path),
           "device_note": "verify this log belongs to the current server/request; absence is not proof of CPU fallback",
           "warmup": warmup, "llm": llm,
           "server_rss_mb": round(int(rss) / 1024, 1) if rss.strip().isdigit() else None,
           "rss_note": "instantaneous process RSS, not peak app RSS or NPU/device memory",
           "mem": sh("free", "-m"), "disk_free": sh("df", "-h", "/"),
           "hottest_zone_c": max(temps) if temps else None}
    if args.log:
        with open(args.log) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        decisions = [r for r in rows if "decision" in r]
        def med(values):
            values = [v for v in values if v is not None]
            return round(statistics.median(values), 3) if values else None
        explanations = [r["explanation"] for r in rows if r.get("explanation")]
        out["app"] = {"log": args.log, "iterations": len(rows),
                      "error_iterations": sum(bool(r.get("error")) for r in rows),
                      "alerts": sum(r.get("action") == "log_alert" for r in rows),
                      "gate_ms_median": med([r["decision"].get("gate_ms") for r in decisions]),
                      "loop_ms_median": med([r.get("loop_ms") for r in rows]),
                      "explanations_ok": sum(bool(e.get("ok") and e.get("text")) for e in explanations),
                      "explanations": len(explanations),
                      "first_t": rows[0].get("t") if rows else None, "last_t": rows[-1].get("t") if rows else None}
    text = json.dumps(out, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0 if llm["successful_runs"] == args.runs else 2


if __name__ == "__main__":
    raise SystemExit(main())
