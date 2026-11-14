#!/usr/bin/env python3
"""Show the board-hosted Argus page on a laptop over the micro-USB debug UART. No network involved.

The board's app listens on its own 127.0.0.1:8000. This laptop-side bridge logs into the board's serial
console, runs local curl requests there, and re-serves the results on the laptop's 127.0.0.1. All inference
and state stay on the board; the bridge only relays bytes over the serial cable, so it keeps working after
`nmcli radio wifi off`. It also offers /bridge, a small page to turn the board's Wi-Fi off and on.

  python3 serial_bridge.py --port /dev/cu.usbserial-XXXXB --password '<board password>'
"""
import argparse
import base64
import gzip
import json
import os
from pathlib import Path
import re
import select
import termios
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
PROMPT = re.compile(r"[\w-]+@[\w-]+:[^\n]*\$ ?$")
STATIC = Path(__file__).resolve().parent.parent / "static/index.html"


class Console:
    def __init__(self, port, user, password):
        self.user, self.password, self.lock = user, password, threading.Lock()
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        a = termios.tcgetattr(self.fd)
        a[4] = a[5] = termios.B115200
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[0] = a[1] = a[3] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, a)
        self._login()

    def _until(self, pred, timeout):
        buf, end = "", time.time() + timeout
        while time.time() < end:
            if select.select([self.fd], [], [], 0.1)[0]:
                buf += os.read(self.fd, 65536).replace(b"\x00", b"").decode(errors="replace")
                if pred(ANSI.sub("", buf).rstrip(" ")):
                    break
        return ANSI.sub("", buf)

    def _send(self, s):
        data = s.encode() + b"\n"
        for i in range(0, len(data), 512):
            os.write(self.fd, data[i:i + 512])
            time.sleep(0.03)

    def _login(self):
        self._send("")
        out = self._until(lambda b: b.endswith(("login:", "Password:")) or PROMPT.search(b), 8).rstrip(" ")
        if not PROMPT.search(out):
            if out.rstrip().endswith("Password:"):
                self._send("")
                self._until(lambda b: b.endswith("login:"), 10)
            self._send(self.user)
            self._until(lambda b: b.endswith("Password:"), 10)
            self._send(self.password)
            self._until(lambda b: PROMPT.search(b), 20)
        self._send("stty -echo; export TERM=dumb")
        self._until(lambda b: PROMPT.search(b), 5)

    def run(self, cmd, timeout=30):
        with self.lock:
            tag = "__E%d__" % int(time.time() * 1e6)
            self._send(f"{cmd}; echo {tag[:3]}''{tag[3:]} rc=$?")
            out = self._until(lambda b: re.search(tag + r" rc=\d+", b), timeout)
            return out.split(tag[:3] + "''" + tag[3:])[-1].split(tag + " rc=")[0].replace("\r", "")

    def fetch(self, path, timeout=30):
        """GET from the board's loopback server, gzip+base64 over the wire."""
        text = self.run(f"echo @@; curl -s --max-time 5 'http://127.0.0.1:{ARGS.board_port}{path}' | gzip -c | base64 -w0; echo; echo @@", timeout)
        m = re.search(r"@@\s*\n(.*?)\n@@", text, re.S)
        return gzip.decompress(base64.b64decode(re.sub(r"\s", "", m.group(1)))) if m and m.group(1).strip() else None

    def post(self, path, body):
        b64 = base64.b64encode(json.dumps(body).encode()).decode()
        return self.run(f"echo {b64} | base64 -d | curl -s --max-time 5 -X POST -H 'Content-Type: application/json' "
                        f"--data-binary @- 'http://127.0.0.1:{ARGS.board_port}{path}'")


CACHE = {"state": b"{}", "frame": None, "error": None}
WIFI = {"off": "sudo -S -p '' nmcli radio wifi off; sleep 1; nmcli -p device",
        "on": "sudo -S -p '' nmcli radio wifi on; sleep 6; nmcli -p device",
        "status": "nmcli radio wifi; nmcli -p device; ip -4 -br address; "
                  "curl -sI --max-time 4 https://example.com >/dev/null && echo 'internet: reachable' || echo 'internet: NOT reachable'"}


def poll(console):
    n = 0
    while True:
        try:
            state = console.fetch("/api/state")
            if state:
                CACHE["state"], CACHE["error"] = state, None
            if n % ARGS.frame_every == 0:
                frame = console.fetch(f"/frame.bmp?div={ARGS.div}", 60)
                if frame and frame[:2] == b"BM":
                    CACHE["frame"] = frame
            n += 1
        except Exception as exc:  # keep relaying; show the fault on the page's console
            CACHE["error"] = f"{type(exc).__name__}: {exc}"
            time.sleep(1)
        time.sleep(0.2)


BRIDGE_PAGE = """<!doctype html><meta charset=utf-8><title>Argus board console</title>
<body style="background:#111;color:#eee;font:16px system-ui;padding:24px"><h2>Board network (over the serial cable)</h2>
<button onclick="go('status')">Status</button> <button onclick="go('off')">Wi-Fi OFF</button>
<button onclick="go('on')">Wi-Fi on</button> <a href="/" style="color:#8cf;margin-left:16px">Back to Argus</a>
<pre id=o style="background:#000;padding:16px;white-space:pre-wrap"></pre>
<script>async function go(a){o.textContent='running '+a+' ...';
const r=await fetch('/bridge/wifi/'+a,{method:'POST'});o.textContent=await r.text()}</script>"""


def handler(console):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                self._send(200, STATIC.read_bytes(), "text/html; charset=utf-8")
            elif path == "/bridge":
                self._send(200, BRIDGE_PAGE.encode(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self._send(200, CACHE["state"], "application/json")
            elif path == "/frame.bmp" and CACHE["frame"]:
                self._send(200, CACHE["frame"], "image/bmp")
            else:
                self._send(503, (CACHE["error"] or "not ready").encode(), "text/plain")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if 0 < length <= 4096 else b"{}"
            if self.path.startswith("/bridge/wifi/"):
                action = self.path.rsplit("/", 1)[-1]
                if action not in WIFI:
                    return self._send(400, b"unknown", "text/plain")
                cmd = WIFI[action]
                if action != "status":
                    cmd = f"echo {base64.b64encode(console.password.encode()).decode()} | base64 -d | " + cmd
                return self._send(200, console.run(cmd, 40).encode(), "text/plain; charset=utf-8")
            if not re.fullmatch(r"/api/(count_in|scan|closing|say|listen)", self.path):
                return self._send(400, b'{"ok": false}', "application/json")
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {}
            console.post(self.path, body)
            self._send(200, b'{"ok": true}', "application/json")
    return H


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", required=True, help="laptop serial device of the board's Linux console")
    p.add_argument("--user", default="ubuntu")
    p.add_argument("--password", default=os.environ.get("IQ9_PASSWORD", ""), help="board login (or IQ9_PASSWORD)")
    p.add_argument("--board-port", type=int, default=8000)
    p.add_argument("--listen", type=int, default=8000, help="laptop port for the page")
    p.add_argument("--div", type=int, choices=(4, 8), default=8, help="camera preview downsample over serial")
    p.add_argument("--frame-every", type=int, default=2, help="fetch a camera frame every N state polls")
    ARGS = p.parse_args()
    con = Console(ARGS.port, ARGS.user, ARGS.password)
    threading.Thread(target=poll, args=(con,), daemon=True).start()
    print(f"Argus over serial: http://127.0.0.1:{ARGS.listen}   board network: http://127.0.0.1:{ARGS.listen}/bridge", flush=True)
    ThreadingHTTPServer(("127.0.0.1", ARGS.listen), handler(con)).serve_forever()
