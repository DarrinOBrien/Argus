#!/usr/bin/env python3
"""Tool calling with LFM3-1.7B on GenieX (OpenAI `tools` schema).

The model picks a tool and fills its arguments. Code does everything else:
  1. validate   the call against the tool's JSON schema
  2. allowlist  only tools in TOOLS can run; anything else is refused
  3. policy     write actions are checked against a rule in code, not the model's judgement
  4. execute    run the tool, send its result back to the model
  5. log        every step is one JSON line; the summary lists only actions that actually ran

Standard library only. Needs `geniex serve` on --server with the model cached:
    geniex pull LiquidAI/LFM3-1.7B-GGUF:Q4_0
    geniex serve --compute npu

    python3 tool_calling.py
    python3 tool_calling.py --prompt "Is the board too hot? If so, log a note for the operator."
    python3 tool_calling.py --self-test        # validator and allowlist checks, no server needed
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
THERMAL_ROOT = "/sys/class/thermal"
REQUEST_TIMEOUT_S = 60
NOTE_MIN_TEMP_C = 70.0  # policy for log_note: an example value, set your own


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# --- Tools: what the model sees ---------------------------------------------------------------------

TOOLS = {
    "read_thermal": {
        "description": "Read the board's SoC thermal zones. Returns the hottest zone and its temperature in Celsius.",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    "read_system": {
        "description": "Read CPU load averages and free memory on the board.",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    "log_note": {
        "description": "Write a note for the operator to the local log. Use only when the board is too hot.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "one sentence for the operator"},
                "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
            },
            "required": ["text", "severity"],
            "additionalProperties": False,
        },
    },
}

READ_ONLY = {"read_thermal", "read_system"}


def openai_tools():
    return [{"type": "function", "function": {"name": n, **spec}} for n, spec in TOOLS.items()]


# --- Tools: what actually runs ----------------------------------------------------------------------

def read_thermal():
    zones = []
    if os.path.isdir(THERMAL_ROOT):
        for name in sorted(os.listdir(THERMAL_ROOT)):
            if not name.startswith("thermal_zone"):
                continue
            base = os.path.join(THERMAL_ROOT, name)
            try:
                with open(os.path.join(base, "type")) as f:
                    typ = f.read().strip()
                with open(os.path.join(base, "temp")) as f:
                    zones.append((int(f.read().strip()) / 1000.0, typ))
            except (OSError, ValueError):
                continue
    if not zones:
        return {"error": "no readable thermal zones (not running on the board?)"}
    temp, zone = max(zones)
    return {"hottest_zone": zone, "temp_c": round(temp, 1), "zones_read": len(zones)}


def read_system():
    load1, load5, _ = os.getloadavg()
    mem = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                key, val = line.split(":", 1)
                if key in ("MemTotal", "MemAvailable"):
                    mem[key] = round(int(val.split()[0]) / 1024 / 1024, 1)  # GiB
    except OSError:
        pass
    return {"cpu_load_1min": round(load1, 2), "cpu_load_5min": round(load5, 2), "cpus": os.cpu_count(),
            "mem_total_gib": mem.get("MemTotal"), "mem_available_gib": mem.get("MemAvailable")}


class Notes:
    def __init__(self, path):
        self.path = path

    def log_note(self, text, severity):
        entry = {"t": now_iso(), "type": "note", "severity": severity, "text": text}
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"logged": True, "path": os.path.basename(self.path)}


# --- Validation, allowlist, policy -------------------------------------------------------------------

_TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "object": dict, "array": list}


def validate(args, schema):
    """Small JSON-schema subset: type, required, enum, additionalProperties. Returns a list of errors."""
    if not isinstance(args, dict):
        return ["arguments must be a JSON object"]
    props = schema.get("properties", {})
    errors = [f"missing required argument '{k}'" for k in schema.get("required", []) if k not in args]
    for k, v in args.items():
        if k not in props:
            if schema.get("additionalProperties", True) is False:
                errors.append(f"unexpected argument '{k}'")
            continue
        p = props[k]
        want = _TYPES.get(p.get("type"))
        if want and (not isinstance(v, want) or (p.get("type") in ("number", "integer") and isinstance(v, bool))):
            errors.append(f"'{k}' must be {p['type']}")
        elif "enum" in p and v not in p["enum"]:
            errors.append(f"'{k}' must be one of {p['enum']}")
    return errors


def check_policy(name, state):
    """Write actions are allowed only when a rule in code says so. The model's own judgement is not enough:
    on the IQ-9075, LFM2-1.2B-Tool asked to alert on 12 of 12 readings, including 39 C (measured)."""
    if name in READ_ONLY:
        return None
    if name == "log_note":
        t = state.get("last_temp_c")
        if t is None:
            return "read_thermal first: log_note needs a measured temperature"
        if t < NOTE_MIN_TEMP_C:
            return f"refused by policy: {t} C is below {NOTE_MIN_TEMP_C} C"
        return None
    return "no policy for this tool"


def run_tool(name, raw_args, state, notes):
    """Returns (result, executed). Refusals and errors come back as results so the model can see them."""
    if name not in TOOLS:
        return {"error": f"unknown tool '{name}'. Allowed: {sorted(TOOLS)}"}, False
    try:
        args = json.loads(raw_args) if raw_args else {}
    except json.JSONDecodeError as e:
        return {"error": f"arguments are not valid JSON: {e}"}, False
    errors = validate(args, TOOLS[name]["parameters"])
    if errors:
        return {"error": "; ".join(errors)}, False
    refusal = check_policy(name, state)
    if refusal:
        return {"error": refusal}, False
    if name == "read_thermal":
        result = read_thermal()
        if "temp_c" in result:
            state["last_temp_c"] = result["temp_c"]
    elif name == "read_system":
        result = read_system()
    else:
        result = notes.log_note(**args)
    return result, True


# --- Server -------------------------------------------------------------------------------------------

def chat(server, model, messages, max_tokens):
    body = json.dumps({
        "model": model,
        "messages": messages,
        "tools": openai_tools(),
        "max_completion_tokens": max_tokens,
        "compute": "npu",
        "stream": False,
    }).encode()
    req = urllib.request.Request(server.rstrip("/") + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
        d = json.load(r)
    return d, round((time.perf_counter() - t0) * 1000, 1)


def is_empty(d):
    """Zero-token reply (GenieX v0.8.0 after repeated identical requests)."""
    m = d["choices"][0]["message"]
    return d.get("usage", {}).get("completion_tokens", 0) == 0 and not m.get("tool_calls") and not m.get("content")


def server_ready(server):
    try:
        with urllib.request.urlopen(server.rstrip("/") + "/v1/models", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


SYSTEM_PROMPT = ("You are an assistant on an edge board. You can only learn about the board or act by calling tools. "
                 "Call one tool at a time. Use the numbers the tools return; do not invent readings. "
                 "Never say you logged or did something unless a tool result confirms it.")


def run(args):
    if not server_ready(args.server):
        sys.exit(f"no GenieX server at {args.server}. Start it with: geniex serve --compute npu")
    log = open(args.log, "a")
    notes = Notes(args.notes)
    state = {}
    executed = []

    def write(entry):
        log.write(json.dumps({"t": now_iso(), **entry}) + "\n")
        log.flush()

    # The request tag keeps prompts unique, which avoids the v0.8.0 zero-token state (see docs/runtimes.md).
    messages = [{"role": "system", "content": f"{SYSTEM_PROMPT} Request {uuid.uuid4().hex[:6]}."},
                {"role": "user", "content": args.prompt}]
    print(f"user: {args.prompt}")
    final = None
    for step in range(args.max_steps):
        d, ms = chat(args.server, args.model, messages, args.max_tokens)
        retried = False
        if is_empty(d):
            retried = True
            messages[0]["content"] = f"{SYSTEM_PROMPT} Request {uuid.uuid4().hex[:6]}."
            d, ms = chat(args.server, args.model, messages, args.max_tokens)
        choice = d["choices"][0]
        msg = choice["message"]
        calls = msg.get("tool_calls") or []
        write({"step": step, "ms": ms, "retried": retried, "finish": choice["finish_reason"],
               "tokens": d.get("usage", {}).get("completion_tokens"), "content": msg.get("content") or None,
               "tool_calls": [{"name": c["function"]["name"], "arguments": c["function"]["arguments"]} for c in calls]})
        if not calls:
            final = (msg.get("content") or "").strip()
            break
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            name, raw = c["function"]["name"], c["function"]["arguments"]
            result, ok = run_tool(name, raw, state, notes)
            print(f"  step {step}: {name}({raw}) -> {'ran' if ok else 'refused'} {json.dumps(result)}  [{ms:.0f} ms]")
            write({"step": step, "tool": name, "arguments": raw, "executed": ok, "result": result})
            if ok:
                executed.append(name)
            messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": json.dumps(result)})
    else:
        print(f"  stopped after --max-steps {args.max_steps} without a final answer")

    print(f"model: {final if final else '(no final answer)'}")
    # Report what ran from our own record, not from the model's text. The model can claim actions it never took.
    print(f"actions that ran: {executed or 'none'}")
    write({"summary": True, "prompt": args.prompt, "final": final, "executed": executed})
    log.close()


# --- Self-test ----------------------------------------------------------------------------------------

def self_test():
    notes = Notes(os.devnull)
    s = {}
    assert validate({}, TOOLS["read_thermal"]["parameters"]) == []
    assert validate({"x": 1}, TOOLS["read_thermal"]["parameters"]) == ["unexpected argument 'x'"]
    assert validate({"text": "hi"}, TOOLS["log_note"]["parameters"]) == ["missing required argument 'severity'"]
    assert validate({"text": "hi", "severity": "panic"}, TOOLS["log_note"]["parameters"])[0].startswith("'severity' must be one of")
    assert validate({"text": 3, "severity": "info"}, TOOLS["log_note"]["parameters"]) == ["'text' must be string"]
    assert run_tool("rm_rf", "{}", s, notes) == ({"error": "unknown tool 'rm_rf'. Allowed: " + str(sorted(TOOLS))}, False)
    assert run_tool("read_system", "{not json", s, notes)[1] is False
    ok_args = json.dumps({"text": "hot", "severity": "warning"})
    assert "read_thermal first" in run_tool("log_note", ok_args, s, notes)[0]["error"]
    s["last_temp_c"] = 39.0
    assert "refused by policy" in run_tool("log_note", ok_args, s, notes)[0]["error"]
    s["last_temp_c"] = 75.0
    assert run_tool("log_note", ok_args, s, notes) == ({"logged": True, "path": os.path.basename(os.devnull)}, True)
    assert run_tool("read_system", "", s, notes)[1] is True
    print("self-test passed")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", default="How hot is the board right now, and how busy is the CPU?")
    ap.add_argument("--model", default="LiquidAI/LFM3-1.7B-GGUF:Q4_0")
    ap.add_argument("--server", default="http://127.0.0.1:18181")
    ap.add_argument("--max-steps", type=int, default=4, help="model turns before giving up")
    ap.add_argument("--max-tokens", type=int, default=128, help="cap per model turn (max_completion_tokens)")
    ap.add_argument("--log", default="tool_calls.jsonl", help="every step, appended")
    ap.add_argument("--notes", default="operator_notes.jsonl", help="where log_note writes")
    ap.add_argument("--self-test", action="store_true", help="check the validator and allowlist; no server needed")
    args = ap.parse_args()
    if args.self_test:
        self_test()
    else:
        run(args)


if __name__ == "__main__":
    main()
