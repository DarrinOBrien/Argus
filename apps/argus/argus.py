#!/usr/bin/env python3
"""Argus: an always-on eye and ear for the operating room, running entirely on the IQ-9075.

observe (camera zones, microphone) -> model proposes (LFM3-Omni on the Hexagon NPU via ZETIC)
-> code decides (inventory, protocol, dose and timing rules) -> alert (screen, optional speech) -> JSONL log.

Standard library only, except the optional --polar heart-rate strap, which needs the bleak package.
No network calls: local model files, local web page, loopback by default.
"""
import argparse
import array
import collections
import datetime
import difflib
import json
import os
from pathlib import Path
import pty
import queue
import re
import resource
import select
import shutil
import signal
import statistics
import subprocess
import termios
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import camera as cam
import zetic_run

HERE = Path(__file__).resolve().parent
HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"  # standard Bluetooth LE heart-rate characteristic
NUM_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
NUM_WORDS.update({"thirty": 30, "forty": 40, "fifty": 50, "hundred": 100})
UNITS = {"milligram": "mg", "milligrams": "mg", "mg": "mg", "microgram": "mcg", "micrograms": "mcg", "mcg": "mcg",
         "milliliter": "ml", "milliliters": "ml", "ml": "ml", "unit": "units", "units": "units",
         "gram": "g", "grams": "g", "g": "g"}
NUM = r"(\d+(?:\.\d+)?|" + "|".join(NUM_WORDS) + r")"
UNIT = r"(" + "|".join(sorted(UNITS, key=len, reverse=True)) + r")"
DOSE_THEN_DRUG = re.compile(NUM + r"\s*" + UNIT + r"\b\s+(?:of\s+)?([a-z]{4,})", re.I)
DRUG_THEN_DOSE = re.compile(r"([a-z]{4,})[\s,]+" + NUM + r"\s*" + UNIT + r"\b", re.I)
TAKE = re.compile(r"\b(take|takes|taken|taking|took|grab|grabs|grabbed|grabbing|pick(?:s|ed|ing)? up)\b")
RETURN = re.compile(r"\b(return|returns|returned|returning|put back|putting back|back on the tray)\b")
STOP = set("the a an is are was were be been of on to in and with into for at by it its this that one".split())


def stem(word):
    for end in ("ing", "ed", "en", "es", "s"):
        if word.endswith(end) and len(word) - len(end) >= 3:
            return word[:-len(end)]
    return word


def content_words(text):
    return {stem(w) for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP}


def now():
    return datetime.datetime.now().astimezone()


def clock(ts=None):
    return (ts or now()).strftime("%H:%M:%S")


def load_procedures(path):
    """Read the procedure library: a '=== #N | Name | Specialty ===' heading, then numbered steps."""
    procedures = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                head = re.match(r"=== #(\d+) \| (.+) \| (.+?) ===\s*$", line)
                step = re.match(r"\d+\.\s+(.*\S)", line)
                if head:
                    procedures.append({"id": int(head.group(1)), "name": head.group(2).strip(),
                                       "specialty": head.group(3).strip(), "steps": []})
                elif step and procedures:
                    procedures[-1]["steps"].append(step.group(1))
    except OSError:
        pass
    return procedures


class CliSession:
    """One vendor CLI process in interactive mode: the model stays loaded on the NPU between requests.

    `chat -i --media FILE` re-reads FILE for the first turn after every /reset, so each request is:
    overwrite FILE, send /reset, send the prompt, read the answer and the runtime's stats line.
    """
    STATS = re.compile(r"\[(\w+)\] finish (\w+) \| prompt (\d+) rows \(cached (\d+)\) -> (\d+) tokens"
                       r"(?:.*?ttft ([\d.]+) ms)?(?:.*?decode \d+ steps ([\d.]+) t/s)?")
    ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

    def __init__(self, sdk, model, media=None, system=None, max_tokens=96):
        lib = str(Path(sdk) / "lib")
        cmd = [str(Path(sdk) / "bin/zetic_lfm3_cli"), "chat", "-i", "--model", str(model), "--target", "v73",
               "--lib-dir", lib, "--temp", "0", "--max-tokens", str(max_tokens)]
        if media:
            cmd += ["--media", str(media)]
        if system:
            cmd += ["--system", system]
        self.master, slave = pty.openpty()
        attrs = termios.tcgetattr(slave)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        self.proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave, cwd=sdk, close_fds=True,
                                     env=dict(os.environ, LD_LIBRARY_PATH=lib))
        os.close(slave)
        banner = self._read(lambda b: re.search(r"\| load \d+ ms", b) and b.rstrip().endswith(">"), 90)
        load = re.search(r"\| load (\d+) ms", banner)
        if not load or "loaded " not in banner:
            raise OSError("model session did not start: " + banner[-300:])
        self.load_ms = int(load.group(1))
        self.device = next((l.strip() for l in banner.splitlines() if "hexrt open" in l and "v73" in l and "nsp2=1" in l), None)

    def _read(self, done, timeout):
        buf, end = "", time.time() + timeout
        while time.time() < end:
            if select.select([self.master], [], [], 0.05)[0]:
                try:
                    buf += os.read(self.master, 65536).decode(errors="replace")
                except OSError:
                    break
                if done(self.ANSI.sub("", buf)):
                    break
        return self.ANSI.sub("", buf).replace("\r", "")

    def ask(self, prompt, timeout=60):
        os.write(self.master, b"/reset\n" + " ".join(prompt.split()).encode() + b"\n")
        out = self._read(lambda b: self.STATS.search(b) and b.rstrip().endswith(">"), timeout)
        stats = self.STATS.search(out)
        if not stats:
            raise OSError("no completion stats from the model session: " + out[-200:])
        status, finish, _, _, tokens, ttft, tps = stats.groups()
        text = re.sub(r"^(\s*>\s*)+", "", out[:stats.start()]).strip()
        return (status.lower() == "ok", int(tokens), float(ttft) if ttft else None, float(tps) if tps else None,
                finish, text)


class Resident:
    """Three always-loaded sessions of the same ZETIC package: vision, speech-to-text, text."""
    tts = False  # speech output still uses a one-shot CLI call

    def __init__(self, sdk, model, run_dir):
        self.image_path, self.audio_path = run_dir / "live.ppm", run_dir / "live.wav"
        if not self.image_path.exists():
            self.image_path.write_bytes(b"P6\n512 512\n255\n" + bytes(512 * 512 * 3))
        if not self.audio_path.exists():
            with wave.open(str(self.audio_path), "wb") as w:
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000), w.writeframes(bytes(32000))
        self.sessions = {"image": CliSession(sdk, model, media=self.image_path, max_tokens=64),
                         "audio": CliSession(sdk, model, media=self.audio_path, system="Perform ASR in English.", max_tokens=96),
                         "text": CliSession(sdk, model, max_tokens=64)}
        self.load_ms = sum(x.load_ms for x in self.sessions.values())
        self.device = self.sessions["image"].device
        self.info = ["LFM3-Omni-2B", "v73 two-NSP", "3 resident sessions"]

    def close(self):
        """Exit each session cleanly. Killing them leaves their NPU memory mappings stuck until a reboot."""
        for session in self.sessions.values():
            try:
                os.write(session.master, b"/exit\n")
                session.proc.wait(timeout=15)
            except (OSError, subprocess.SubprocessError):
                pass

    def request(self, mode, prompt, path="-", system="-", max_tokens=96):
        if mode == "image" and Path(path) != self.image_path:
            shutil.copyfile(path, self.image_path)
        if mode == "audio" and Path(path) != self.audio_path:
            shutil.copyfile(path, self.audio_path)
        return self.sessions[mode].ask(prompt)


def heart_rate(data):
    """bpm from one heart-rate notification, or None when the strap reports no skin contact or no reading."""
    if len(data) < 2 or data[0] & 0x06 == 0x04:
        return None
    bpm = int.from_bytes(data[1:3], "little") if data[0] & 1 else data[1]
    return bpm if 0 < bpm < 300 else None


class Argus:
    def __init__(self, args):
        self.args = args
        self.protocol = json.loads(Path(args.protocol).read_text())
        self.items = self.protocol["items"]
        self.run_dir = Path(args.run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.run_dir / "argus-log.jsonl"
        self.log_file = self.log_path.open("a")
        self.lock = threading.RLock()
        self.infer_lock = threading.Lock()
        self.jobs = queue.Queue()
        self.busy = None
        self.events = collections.deque(maxlen=200)
        self.alerts = []
        self.metrics = []
        self.zones = {"tray": None, "patient": None}
        self.zones_time = None
        self.baseline = None
        self.baseline_time = None
        self.last_seen = {}  # item -> {"zone", "time"} for the last sighting in the patient area
        self.steps = [dict(s, status="pending", started=None, done=None, overdue=False) for s in self.protocol["steps"]]
        self.current = -1
        self.drugs = []
        self.procedures = load_procedures(args.procedures)
        self.procedure = None  # the procedure the team said they are doing
        self.proc_log = []     # what has been done since then, one plain sentence per line
        self.proc_drugs = {}   # drug -> doses planned in the procedure's own steps
        self.out = {}          # item -> instance numbers currently away from the tray
        self.stable = None     # tray counts the procedure log currently believes
        self.pending = {}      # item -> a new tray count seen once, waiting for a second scan
        self.proc_steps = []   # per step of the chosen procedure: time it was called out, or None
        self.seen_moves = []   # camera-logged taken/returned, so a spoken one right after is not counted twice
        self.said = collections.deque(maxlen=4)  # alerts spoken aloud, so the microphone can ignore them
        self.listening = False
        self.hr = None
        self.hr_logged = 0.0
        self.camera = cam.Camera(args.camera, mock=args.mock)
        self.resident = None
        if not args.mock and args.runner != "cli":
            try:
                self.resident = Resident(args.sdk, args.model, self.run_dir)
            except OSError as exc:
                print(f"resident model sessions unavailable ({exc}); using one CLI process per request", flush=True)
        if self.resident:
            self.log("system", message="model loaded once and kept resident", load_ms=self.resident.load_ms,
                     info=self.resident.info, device=self.resident.device)
        self.log("system", message="Argus started", mock=args.mock, runner="resident" if self.resident else "cli", model=str(args.model), protocol=self.protocol["name"])
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._ticker, daemon=True).start()
        if args.scan_every > 0:
            threading.Thread(target=self._watch, daemon=True).start()
        threading.Thread(target=self._ear, daemon=True).start()
        if args.polar:
            threading.Thread(target=self._pulse, daemon=True).start()

    # ---------- heart rate (Polar strap, Bluetooth LE) ----------
    def _pulse(self):
        import asyncio
        while True:
            try:
                asyncio.run(self._pulse_session())
            except Exception as exc:  # loop errors are data, not crashes
                self.log("error", where="pulse", error=f"{type(exc).__name__}: {exc}")
            with self.lock:
                had, self.hr = self.hr, None
            if had:
                self.alert("high", "Heart rate signal lost. Check the strap.")
            time.sleep(3)

    async def _pulse_session(self):
        import asyncio
        from bleak import BleakClient, BleakScanner
        dev = await BleakScanner.find_device_by_filter(lambda d, adv: self.args.polar in (d.name or ""), timeout=15)
        if dev is None:
            raise RuntimeError(f"strap {self.args.polar} not found (worn, electrodes wet, not held by a phone?)")
        packets = asyncio.Queue()
        async with BleakClient(dev) as client:
            self.log("system", message=f"heart-rate strap connected: {dev.name}")
            await client.start_notify(HR_MEASUREMENT, lambda _, data: packets.put_nowait(bytes(data)))
            last = time.monotonic()
            while time.monotonic() - last < 5:
                try:
                    data = await asyncio.wait_for(packets.get(), 1)
                except asyncio.TimeoutError:
                    continue
                bpm = heart_rate(data)
                if bpm is not None:
                    last = time.monotonic()
                    self.on_heart_rate(bpm)
        raise RuntimeError("no heart-rate reading for 5 s")

    def on_heart_rate(self, bpm):
        limits = self.protocol.get("vitals", {})
        low, high = limits.get("hr_min", 40), limits.get("hr_max", 140)
        out = not low <= bpm <= high
        with self.lock:
            was_out = bool(self.hr and self.hr["out"])
            self.hr = {"bpm": bpm, "time": clock(), "out": out, "min": low, "max": high}
        if out and not was_out:
            self.alert("high", f"Heart rate {bpm} bpm, outside {low}-{high}.")
        if out != was_out or time.monotonic() - self.hr_logged >= 30:
            self.hr_logged = time.monotonic()
            self.log("vital", hr_bpm=bpm, out_of_range=out)

    # ---------- log ----------
    def log(self, kind, **fields):
        record = {"time": now().isoformat(timespec="seconds"), "kind": kind, **fields}
        with self.lock:
            self.events.append(record)
            self.log_file.write(json.dumps(record) + "\n")
            self.log_file.flush()
        return record

    def alert(self, severity, message, speak=False):
        record = self.log("alert", severity=severity, message=message)
        with self.lock:
            self.alerts.append(record)
        if self.args.speak or speak:
            self.said.append(message)
            self.jobs.put(("speak", message))

    # ---------- procedure ----------
    def note(self, text):
        """One plain sentence in the procedure log, with the time it happened."""
        self.log("procedure_log", text=text)
        with self.lock:
            self.proc_log.append({"time": clock(), "text": text})

    def find_procedure(self, text):
        """The procedure a statement names: by number ('procedure 0', 'demo zero') or by its title."""
        low = " ".join(text.lower().split())
        m = re.search(r"\b(?:procedure|operation|demo)\s+(?:number\s+)?" + NUM + r"\b", low)
        if m:
            number = NUM_WORDS[m.group(1)] if m.group(1) in NUM_WORDS else float(m.group(1))
            return next((p for p in self.procedures if p["id"] == number), None)
        if not re.search(r"\b(procedure|operation|start|starting|begin|beginning|doing|performing)\b", low):
            return None
        named = [p for p in self.procedures if p["name"].lower() in low]
        return max(named, key=lambda p: len(p["name"]), default=None)

    def choose_procedure(self, query):
        """From the page: a number, or all or part of a title."""
        low = query.lower().strip().lstrip("#")
        if low.isdigit() or low in NUM_WORDS:
            return self.start_procedure(NUM_WORDS[low] if low in NUM_WORDS else int(low))
        named = sorted((p for p in self.procedures if low in p["name"].lower()), key=lambda p: len(p["name"]))
        if not named:
            close = difflib.get_close_matches(low, [p["name"].lower() for p in self.procedures], n=1, cutoff=0.6)
            named = [p for p in self.procedures if close and p["name"].lower() == close[0]]
        if not named:
            self.log("error", where="procedure", error=f"no procedure matches '{query}'")
            return
        self.start_procedure(named[0]["id"])

    def start_procedure(self, number):
        procedure = next((p for p in self.procedures if p["id"] == number), None)
        if procedure is None:
            self.log("error", where="procedure", error=f"no procedure #{number} in {self.args.procedures}")
            return
        planned = collections.defaultdict(list)
        for step in procedure["steps"]:
            for m in DOSE_THEN_DRUG.finditer(step.lower()):
                amount = float(NUM_WORDS[m.group(1)]) if m.group(1) in NUM_WORDS else float(m.group(1))
                planned[m.group(3)].append({"dose": amount, "unit": UNITS[m.group(2)]})
        with self.lock:
            self.procedure = dict(procedure, started=clock())
            self.proc_drugs, self.proc_log, self.drugs = dict(planned), [], []
            self.proc_steps = [None] * len(procedure["steps"])
        self.log("action", action="procedure_started", procedure=procedure["id"], name=procedure["name"],
                 specialty=procedure["specialty"], steps=len(procedure["steps"]))
        self.note(f"Procedure #{procedure['id']} {procedure['name']} started")
        self.count_in()  # the reference count that 'taken' and 'returned' are measured against

    def track(self, zones, confirmed=False):
        """Turn tray-count changes into numbered 'taken' and 'returned' lines.

        A change has to be seen in two scans in a row (or in a confirmed scan) before it is written,
        so one miscount by the model does not become history."""
        if self.stable is None:
            return
        taken, returned = [], []
        with self.lock:
            for item in self.items:
                n = zones["tray"][item]
                if n == self.stable[item]:
                    self.pending.pop(item, None)
                elif not confirmed and self.pending.get(item) != n:
                    self.pending[item] = n
                else:
                    out = self.out.setdefault(item, [])
                    for _ in range(self.stable[item] - n):  # fewer on the tray: taken, lowest free number
                        out.append(next(k for k in range(1, 1000) if k not in out))
                        taken.append(f"{item} {out[-1]}")
                    for _ in range(n - self.stable[item]):  # more on the tray: returned, oldest first
                        returned.append(f"{item} {out.pop(0)}" if out else f"an extra {item}")
                    verb = "taken" if n < self.stable[item] else "returned"
                    for _ in range(abs(n - self.stable[item])):
                        self.seen_moves.append({"item": item, "verb": verb, "at": time.monotonic()})
                    self.stable[item] = n
                    self.pending.pop(item, None)
            self.seen_moves = [m for m in self.seen_moves if m["at"] > time.monotonic() - 45]
        for names, verb in ((taken, "taken"), (returned, "returned")):
            if names:
                self.note((" and ".join(names) + " " + verb).capitalize() + " (camera)")

    def _item_name(self, word):
        """Map a spoken word (knife, swab, kinfe) to a protocol item, or None."""
        aliases = self.protocol.get("item_aliases", {})
        word = word.lower()
        forms = {word, word[:-1] if word.endswith("s") else word, word[:-2] if word.endswith("es") else word}
        for item in self.items:
            if forms & set([item] + aliases.get(item, [])):
                return item
        return None

    def parse_moves(self, low):
        """'one tissue taken', 'taking two knives', 'tissue one and tissue two returned' -> move events."""
        take, back = bool(TAKE.search(low)), bool(RETURN.search(low))
        if take == back:  # neither, or both in one sentence: too ambiguous to log
            return []
        verb, events = ("taken" if take else "returned"), []
        words = re.findall(r"[a-z]+|\d+", low)
        i = 0
        while i < len(words):
            item = self._item_name(words[i])
            if item:
                before = words[i - 1] if i else ""
                after = words[i + 2] if i + 2 < len(words) and words[i + 1] == "number" else (words[i + 1] if i + 1 < len(words) else "")
                as_num = lambda w: NUM_WORDS.get(w, int(w) if w.isdigit() else None)
                count = as_num(before) if before not in ("", "and") else None
                if before in ("a", "an"):
                    count = 1
                ident = as_num(after)
                events.append({"item": item, "id": ident,
                               "count": 1 if ident is not None else max(1, min(count or 1, 20))})
            i += 1
        return [{"type": "move", "verb": verb, "parts": events}] if events else []

    def apply_move(self, event, source):
        """A spoken or typed 'taken'/'returned'. It moves the tray count the camera compares against,
        so the camera seeing the same change afterwards does not log it a second time."""
        verb, names, deduped = event["verb"], [], []
        with self.lock:
            for part in event["parts"]:
                item = part["item"]
                out = self.out.setdefault(item, [])
                for _ in range(part["count"]):
                    cutoff = time.monotonic() - 45
                    seen = next((m for m in self.seen_moves
                                 if m["item"] == item and m["verb"] == verb and m["at"] > cutoff), None)
                    if seen:  # the camera already logged this one a moment ago
                        self.seen_moves.remove(seen)
                        deduped.append(item)
                        continue
                    if verb == "taken":
                        k = part["id"] if part["id"] and part["id"] not in out else next(
                            k for k in range(1, 1000) if k not in out)
                        out.append(k)
                        names.append(f"{item} {k}")
                        if self.stable is not None:
                            self.stable[item] = max(0, self.stable[item] - 1)
                    else:
                        k = part["id"] if part["id"] in out else (out[0] if out else None)
                        if k is not None:
                            out.remove(k)
                        names.append(f"{item} {k}" if k is not None else f"an extra {item}")
                        if self.stable is not None:
                            self.stable[item] += 1
                    self.pending.pop(item, None)
        if names:
            self.log("action", action="item_" + verb, items=names, source=source)
            self.note((" and ".join(names) + " " + verb).capitalize())
        if deduped:
            self.log("note", text=f"{' and '.join(deduped)} {verb} ({source}): already logged from the camera")

    def match_step(self, text):
        """Index of the chosen procedure's next step that this statement describes, or None."""
        if not self.procedure:
            return None
        said = content_words(text)
        best, best_score = None, 0.0
        for i, step in enumerate(self.procedure["steps"]):
            if self.proc_steps[i] is not None:
                continue
            want = content_words(step)
            if not want:
                continue
            hits = sum(1 for w in want if w in said or difflib.get_close_matches(w, said, n=1, cutoff=0.75))
            score = hits / len(want)
            if (hits >= 2 or len(want) == 1) and score >= 0.5 and score > best_score:
                best, best_score = i, score
        return best

    def mark_step(self, index, quiet=False):
        with self.lock:
            self.proc_steps[index] = clock()
        step = self.procedure["steps"][index]
        self.log("action", action="procedure_step", step=index + 1, text=step)
        if not quiet:
            self.note(f"Step {index + 1}: {step}")

    # ---------- model ----------
    def infer(self, kind, prompt, image=None, audio=None, max_tokens=96):
        """One capped, sequential request to the local model. Errors come back as data."""
        with self.infer_lock:
            started = time.perf_counter()
            if self.args.mock:
                result = self._mock(kind, prompt)
            elif self.resident:
                result = self._resident(prompt, image, audio, max_tokens)
            else:
                result = zetic_run.run(self.args.sdk, self.args.model, prompt, image=image, audio=audio,
                                       max_tokens=max_tokens, timeout=self.args.timeout)
            wall = time.perf_counter() - started
        t = result.get("timings", {})
        metric = {"kind": kind, "ok": result["ok"], "wall_s": round(wall, 3), "load_ms": t.get("model_load_ms"),
                  "ttft_ms": t.get("runtime_ttft_ms"), "tok_s": t.get("runtime_decode_tok_s"),
                  "tokens": result.get("completion_tokens"),
                  "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1)}
        with self.lock:
            self.metrics.append(metric)
        self.log("model", request=kind, text=result.get("text", "")[:400], errors=result.get("errors", []),
                 device=result.get("device_evidence"), **{k: v for k, v in metric.items() if k != "kind"})
        return result

    def _resident(self, prompt, image, audio, max_tokens):
        """Same guards as the CLI wrapper: positive usage, natural stop, non-empty answer, NPU evidence."""
        errors = []
        try:
            mode = "image" if image else "audio" if audio else "text"
            ok, tokens, ttft, tps, finish, text = self.resident.request(
                mode, prompt, path=image or audio or "-", system="Perform ASR in English." if audio else "-",
                max_tokens=max_tokens)
            text = re.sub(r"<think>.*?(?:</think>|$)", "", text, flags=re.S | re.I).strip()
            if not ok:
                errors.append(text)
            if not 0 < tokens <= max_tokens:
                errors.append("zero completion tokens or token cap exceeded")
            if finish.lower() != "stop":
                errors.append(f"generation did not finish naturally: {finish}")
            if not text:
                errors.append("empty answer")
            if not self.resident.device:
                errors.append("missing Hexagon v73/two-NSP evidence in the session log")
        except (OSError, ValueError) as exc:
            ok, tokens, ttft, tps, text = False, None, None, None, ""
            errors.append(f"{type(exc).__name__}: {exc}")
        return {"ok": not errors, "text": text, "errors": errors, "completion_tokens": tokens,
                "device_evidence": self.resident.device,
                "timings": {"model_load_ms": 0.0, "runtime_ttft_ms": ttft, "runtime_decode_tok_s": tps}}

    def _mock(self, kind, prompt):
        """Laptop-only stand-in so the logic and UI can be exercised without the board."""
        text = "{}"
        if kind.startswith("vision"):
            scene_file = self.run_dir / "mock_scene.json"
            scene = json.loads(scene_file.read_text()) if scene_file.exists() else {
                "tray": {item: 2 for item in self.items}, "patient": {}}
            text = json.dumps(scene.get(kind.split(":")[1], {}))
        elif kind == "parse":
            text = '{"type": "note"}'
        return {"ok": True, "text": text, "errors": [], "completion_tokens": len(text) // 4, "device_evidence": "mock",
                "timings": {"model_load_ms": 0.0, "runtime_ttft_ms": 1.0, "runtime_decode_tok_s": 0.0}}

    # ---------- eye ----------
    def _count_zone(self, zone):
        path = self.camera.zone_ppm(zone, str(self.run_dir / f"zone-{zone}.ppm"))
        keys = ", ".join(f'"{i}": 0' for i in self.items)
        hints = self.protocol.get("item_hints", {})
        prompt = ("Count the objects on the table. "
                  + "; ".join(f"{i} = {hints.get(i, i)}" for i in self.items)
                  + f". Reply with only one JSON object of integers, like {{{keys}}}.")
        result = self.infer(f"vision:{zone}", prompt, image=path, max_tokens=64)
        match = re.search(r"\{[^{}]*\}", result.get("text", ""))
        if not result["ok"] or not match:
            raise ValueError(f"vision request for {zone} was unusable: {result.get('errors')}")
        raw = json.loads(match.group(0))
        counts = {}
        for item in self.items:  # allowlisted keys, bounded integers; anything else is rejected
            value = raw.get(item, 0)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 50:
                raise ValueError(f"vision count for {item} is invalid: {value!r}")
            counts[item] = value
        return counts

    def scan(self, reason="scan", confirm=False):
        """Count both zones. With confirm, count again and use a third pass as tie-breaker (per-item median)."""
        started = time.perf_counter()
        zones = {zone: self._count_zone(zone) for zone in ("tray", "patient")}
        if confirm:
            second = {zone: self._count_zone(zone) for zone in ("tray", "patient")}
            if second != zones:
                third = {zone: self._count_zone(zone) for zone in ("tray", "patient")}
                self.log("observation", reason=reason + "_disagreement", passes=[zones, second, third])
                zones = {zone: {i: sorted((zones[zone][i], second[zone][i], third[zone][i]))[1] for i in self.items}
                         for zone in ("tray", "patient")}
        stamp = now()
        with self.lock:
            self.zones, self.zones_time = zones, clock(stamp)
            for item, n in zones["patient"].items():
                if n > 0:
                    self.last_seen[item] = {"zone": "patient area", "time": clock(stamp)}
        self.log("observation", reason=reason, zones=zones, loop_s=round(time.perf_counter() - started, 2))
        if reason != "count_in":
            self.track(zones, confirmed=confirm)
        return zones

    def count_in(self):
        zones = self.scan("count_in", confirm=True)
        baseline = {i: zones["tray"][i] + zones["patient"][i] for i in self.items}
        with self.lock:
            self.baseline, self.baseline_time = baseline, clock()
            self.stable, self.pending, self.out = dict(zones["tray"]), {}, {}
        self.log("action", action="count_in", baseline=baseline)
        self.note("Count in: " + ", ".join(f"{n} {item}" for item, n in zones["tray"].items()) + " on the tray")
        self._start_step("timeout")

    def closing(self):
        if self.baseline is None:
            self.alert("high", "Closing called but no count in was recorded.")
            return
        zones = self.scan("count_out", confirm=True)
        problems = []
        for item in self.items:
            expected, on_tray, in_patient = self.baseline[item], zones["tray"][item], zones["patient"][item]
            if in_patient > 0:
                problems.append(f"{in_patient} {item} still in the patient area")
            missing = expected - on_tray - in_patient
            if missing > 0:
                seen = self.last_seen.get(item)
                where = f", last seen in the {seen['zone']} at {seen['time']}" if seen else ", never seen leaving the tray"
                problems.append(f"{missing} {item} missing{where}")
            elif missing < 0:
                problems.append(f"{-missing} more {item} than at count in")
        self.log("action", action="count_out", baseline=self.baseline, zones=zones, problems=problems)
        if problems:
            self.alert("critical", "Count out does not match. " + "; ".join(problems) + ". Do not close.")
        else:
            self.log("action", action="count_out_ok", message="Count out matches count in. Safe to close.")

    # ---------- ear ----------
    def _ear(self):
        """Record short clips; transcribe only the ones that contain sound."""
        n = 0
        while True:
            if not self.listening or self.args.mock:
                time.sleep(0.3)
                continue
            n = (n + 1) % 8
            path = self.run_dir / f"clip-{n}.wav"
            try:
                subprocess.run(["arecord", "-q", "-D", self.args.mic, "-f", "S16_LE", "-r", "16000", "-c", "1",
                                "-d", str(self.args.clip_seconds), str(path)], check=True, timeout=self.args.clip_seconds + 10,
                               capture_output=True)
                with wave.open(str(path)) as w:
                    samples = array.array("h", w.readframes(w.getnframes()))
                peak = max(max(samples, default=0), -min(samples, default=0))
                if peak >= self.args.mic_threshold:
                    self.jobs.put(("audio", str(path)))
            except (OSError, subprocess.SubprocessError, wave.Error, EOFError) as exc:
                self.log("error", where="microphone", error=str(exc))
                time.sleep(3)

    def transcribe(self, path):
        result = self.infer("asr", "Transcribe the audio.", audio=path, max_tokens=96)
        text = result.get("text", "").strip()
        if result["ok"] and text:
            self.handle_utterance(text, "microphone")

    def handle_utterance(self, text, source):
        self.log("utterance", source=source, text=text)
        if source == "microphone" and any(
                difflib.SequenceMatcher(None, text.lower(), said.lower()).ratio() > 0.6 for said in self.said):
            self.log("note", text=text, ignored="this is Argus's own spoken alert")
            return
        events = self.parse_rules(text)
        # A line of the chosen procedure ('the shirt is lifted') is logged as that step, before asking the model.
        step = self.match_step(text) if not any(e["type"] == "procedure" for e in events) else None
        if not events and step is None and self.args.parse != "rules":
            events = self.parse_llm(text)
        for event in events:
            self.apply(event, text, source)
        if step is not None:
            self.mark_step(step, quiet=bool(events))
        if not events and step is None:
            self.log("note", text=text)

    def _drug_name(self, word):
        known = list(self.protocol["drugs"]) + list(self.proc_drugs)
        match = difflib.get_close_matches(word.lower(), known, n=1, cutoff=0.7)
        return match[0] if match else None

    def parse_rules(self, text):
        procedure = self.find_procedure(text)
        if procedure:
            return [{"type": "procedure", "id": procedure["id"]}]
        low, events = text.lower(), []
        if re.search(r"\bcount(ing)?\s+in\b", low):
            events.append({"type": "command", "command": "count_in"})
        if re.search(r"\b(closing|count(ing)?\s+out|closure)\b", low):
            events.append({"type": "command", "command": "closing"})
        for pattern, order in ((DOSE_THEN_DRUG, (0, 1, 2)), (DRUG_THEN_DOSE, (1, 2, 0))):
            for m in pattern.finditer(low):
                amount, unit, word = (m.group(i + 1) for i in order)
                name = self._drug_name(word)
                if name and not any(e.get("drug") == name for e in events):
                    dose = float(NUM_WORDS[amount]) if amount in NUM_WORDS else float(amount)
                    events.append({"type": "drug", "drug": name, "dose": dose, "unit": UNITS[unit]})
        has_drug = any(e["type"] == "drug" for e in events)
        if not has_drug:
            events += self.parse_moves(low)
        for step in self.protocol["steps"]:
            if step["id"] in ("timeout", "closing") or not any(k in low for k in step["keywords"]):
                continue
            # A dose given later in the case must not drag the procedure back to induction.
            if not (step["id"] == "anesthesia" and has_drug and self.current >= 1):
                events.append({"type": "step", "step_id": step["id"]})
            break
        return events

    def parse_llm(self, text):
        steps = "; ".join(f'{s["id"]} = {s["name"]}' for s in self.protocol["steps"])
        prompt = ("You keep the log in an operating room. Turn the statement into exactly one JSON object and nothing else. "
                  'Use {"type":"drug","drug":"name","dose":number,"unit":"mg"} for a medication, '
                  '{"type":"step","step_id":"id"} when a procedure step starts, or {"type":"note"} otherwise. '
                  f"Step ids: {steps}. Statement: \"{text}\"")
        result = self.infer("parse", prompt, max_tokens=64)
        match = re.search(r"\{[^{}]*\}", result.get("text", ""))
        if not result["ok"] or not match:
            return []
        try:
            event = json.loads(match.group(0))
        except ValueError:
            return []
        self.log("proposal", source="lfm", event=event)
        # The model only proposes. Code validates against the protocol before anything is recorded.
        if event.get("type") == "step" and event.get("step_id") in {s["id"] for s in self.protocol["steps"]}:
            return [{"type": "step", "step_id": event["step_id"]}]
        if event.get("type") == "drug" and isinstance(event.get("drug"), str):
            name, dose = self._drug_name(event["drug"]), event.get("dose")
            unit = UNITS.get(str(event.get("unit", "")).lower())
            if name and unit and isinstance(dose, (int, float)) and not isinstance(dose, bool) and 0 < dose < 100000:
                return [{"type": "drug", "drug": name, "dose": float(dose), "unit": unit}]
        return []

    def apply(self, event, text, source="typed"):
        if event["type"] == "move":
            self.apply_move(event, source)
        elif event["type"] == "command":
            if event["command"] == "count_in":
                self.count_in()
            else:
                self._start_step("closing")
                self.closing()
        elif event["type"] == "procedure":
            self.start_procedure(event["id"])
        elif event["type"] == "step":
            self._start_step(event["step_id"])
        elif event["type"] == "drug":
            name, planned = event["drug"], self.proc_drugs.get(event["drug"], [])
            with self.lock:
                given = [d for d in self.drugs if d["drug"] == name]
            if len(given) >= max(1, len(planned)):
                # Announced again after it was already given: say so out loud and do not record a second dose.
                # The spoken sentence carries no dose, so hearing it back cannot be read as another one.
                self.log("action", action="drug_repeat_blocked", drug=name, dose=event["dose"], unit=event["unit"],
                         first_given=given[0]["time"])
                self.note(f"{name.capitalize()} announced again; already added at {given[0]['time']}. "
                          "Warned, not recorded as given")
                self.alert("critical", f"Don't do that! Someone already added {name}.", speak=True)
                return
            spec = self.protocol["drugs"].get(name) or {"unit": planned[0]["unit"], "max_single_dose": planned[0]["dose"]}
            record = {"time": clock(), "drug": event["drug"], "dose": event["dose"], "unit": event["unit"]}
            with self.lock:
                self.drugs.append(record)
            self.log("action", action="drug_logged", **record)
            self.note(f"{event['dose']:g} {event['unit']} of {name} added")
            if event["unit"] != spec["unit"]:
                self.alert("high", f"{event['drug']} was given in {event['unit']}, protocol expects {spec['unit']}. Please confirm.")
            elif event["dose"] > spec["max_single_dose"]:
                self.alert("high", f"{event['dose']:g} {event['unit']} of {event['drug']} is above the protocol limit "
                                   f"of {spec['max_single_dose']:g} {spec['unit']}. Please confirm.")

    def _start_step(self, step_id):
        with self.lock:
            index = next(i for i, s in enumerate(self.steps) if s["id"] == step_id)
            if index == self.current:
                return
            stamp = clock()
            skipped = [s["name"] for s in self.steps[:index] if s["status"] == "pending"]
            out_of_order = index < self.current
            previous = self.steps[self.current]["name"] if self.current >= 0 else None
            for s in self.steps[:index]:
                if s["status"] == "active":
                    s["status"], s["done"] = "done", stamp
                elif s["status"] == "pending":
                    s["status"] = "skipped"
            step = self.steps[index]
            step.update(status="active", started=stamp, started_at=time.time(), overdue=False)
            self.current = index
        self.log("action", action="step_started", step=step_id, name=step["name"])
        if out_of_order:
            self.alert("medium", f"Step out of order: '{step['name']}' called after '{previous}'.")
        if skipped:
            self.alert("high", "Step skipped: " + ", ".join(skipped) + ".")

    def _watch(self):
        """Always-on eye: after count in, rescan whenever the worker is idle."""
        while True:
            time.sleep(self.args.scan_every)
            if self.args.scan_every > 0 and self.baseline is not None and self.busy is None and self.jobs.empty():
                self.jobs.put(("scan", None))

    def _ticker(self):
        while True:
            time.sleep(5)
            with self.lock:
                step = self.steps[self.current] if self.current >= 0 else None
                late = bool(step and step["status"] == "active" and not step["overdue"]
                            and time.time() - step["started_at"] > step["max_minutes"] * 60 * self.args.time_scale)
                if late:
                    step["overdue"] = True
            if late:
                self.alert("medium", f"'{step['name']}' is running longer than the expected {step['max_minutes']} minutes.")

    # ---------- voice ----------
    def speak(self, message):
        """Best effort: synthesize with the local model and play on the board speaker."""
        if self.args.mock:
            return
        wav = self.run_dir / "alert.wav"
        lib = str(Path(self.args.sdk) / "lib")
        try:
            if self.resident and self.resident.tts:
                with self.infer_lock:
                    started = time.perf_counter()
                    ok, _, first_audio, rtf, _, text = self.resident.request(
                        "tts", message, path=str(wav), system="Perform TTS in American English using a female voice.")
                    wall = time.perf_counter() - started
                if not ok:
                    raise OSError(text)
                subprocess.run(["aplay", "-q", "-D", self.args.speaker, str(wav)], check=True, capture_output=True, timeout=60)
                self.log("action", action="spoken", message=message, tts_s=round(wall, 2), first_audio_ms=first_audio)
                return
            with self.infer_lock:
                started = time.perf_counter()
                subprocess.run([str(Path(self.args.sdk) / "bin/zetic_lfm3_cli"), "chat", "--model", str(self.args.model),
                                "--target", "v73", "--lib-dir", lib, "--tts", "--out", str(wav),
                                "--system", "Perform TTS in American English using a female voice.", message],
                               env=dict(os.environ, LD_LIBRARY_PATH=lib), cwd=self.args.sdk, check=True,
                               capture_output=True, timeout=self.args.timeout)
                wall = time.perf_counter() - started
            subprocess.run(["aplay", "-q", "-D", self.args.speaker, str(wav)], check=True, capture_output=True, timeout=60)
            self.log("action", action="spoken", message=message, tts_s=round(wall, 2))
        except (OSError, subprocess.SubprocessError) as exc:
            detail = getattr(exc, "stderr", b"") or b""
            self.log("error", where="speech", error=str(exc)[:200], detail=detail.decode(errors="replace")[-300:])

    # ---------- worker ----------
    def _worker(self):
        while True:
            name, payload = self.jobs.get()
            self.busy = name
            try:
                if name == "count_in":
                    self.count_in()
                elif name == "scan":
                    self.scan()
                elif name == "closing":
                    self._start_step("closing")
                    self.closing()
                elif name == "procedure":
                    self.choose_procedure(payload)
                elif name == "say":
                    self.handle_utterance(payload, "typed")
                elif name == "audio":
                    self.transcribe(payload)
                elif name == "speak":
                    self.speak(payload)
            except Exception as exc:  # loop errors are data, not crashes
                self.log("error", where=name, error=f"{type(exc).__name__}: {exc}")
            finally:
                self.busy = None

    def state(self):
        with self.lock:
            by_kind = collections.defaultdict(list)
            for m in self.metrics:
                if m["ok"]:
                    by_kind[m["kind"].split(":")[0]].append(m)
            medians = {}
            for kind, rows in by_kind.items():
                medians[kind] = {"n": len(rows)}
                for key in ("wall_s", "load_ms", "ttft_ms", "tok_s"):
                    values = [r[key] for r in rows if r[key] is not None]
                    medians[kind][key] = round(statistics.median(values), 2) if values else None
            return {"time": clock(), "protocol": self.protocol["name"], "items": self.items, "mock": self.args.mock,
                    "busy": self.busy, "queued": self.jobs.qsize(), "listening": self.listening,
                    "camera_error": self.camera.error, "zones": self.zones, "zones_time": self.zones_time,
                    "baseline": self.baseline, "baseline_time": self.baseline_time, "last_seen": self.last_seen,
                    "steps": [{k: s[k] for k in ("id", "name", "status", "started", "done", "max_minutes", "overdue")}
                              for s in self.steps],
                    "drugs": self.drugs, "polar": self.args.polar, "hr": self.hr, "alerts": self.alerts[-8:],
                    # Kept small: the page may be polling over a slow serial link.
                    "procedure": self.procedure and {
                        "id": self.procedure["id"], "name": self.procedure["name"], "started": self.procedure["started"],
                        "step_count": len(self.procedure["steps"]),
                        "steps": [{"text": s[:90], "done": d} for s, d in
                                  list(zip(self.procedure["steps"], self.proc_steps))[:40]]},
                    "procedure_log": self.proc_log[-40:], "procedures": len(self.procedures), "out": self.out,
                    "events": [{k: v for k, v in e.items() if k != "device"} for e in self.events
                               if e["kind"] not in ("model", "observation")][-30:],
                    "last_metric": self.metrics[-1] if self.metrics else None, "medians": medians,
                    "peak_rss_mb": max((m["peak_rss_mb"] for m in self.metrics), default=None),
                    "runner": "resident" if self.resident else "cli",
                    "model_load_ms": self.resident.load_ms if self.resident else None,
                    "log_path": str(self.log_path)}


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
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
            try:
                if path == "/":
                    self._send(200, (HERE / "static/index.html").read_bytes(), "text/html; charset=utf-8")
                elif path == "/frame.bmp":
                    step = 8 if "div=8" in self.path else 4 if "div=4" in self.path else 2
                    self._send(200, app.camera.preview_bmp(step), "image/bmp")
                elif path == "/api/state":
                    self._send(200, json.dumps(app.state()).encode(), "application/json")
                elif path == "/api/procedures":
                    names = [{"id": p["id"], "name": p["name"], "specialty": p["specialty"]} for p in app.procedures]
                    self._send(200, json.dumps(names).encode(), "application/json")
                else:
                    self._send(404, b"not found", "text/plain")
            except OSError as exc:
                self._send(503, str(exc).encode(), "text/plain")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}") if length <= 4096 else {}
            except ValueError:
                body = {}
            action = self.path.rsplit("/", 1)[-1]
            if action in ("count_in", "scan", "closing"):
                app.jobs.put((action, None))
            elif action == "procedure" and str(body.get("query", "")).strip():
                app.jobs.put(("procedure", str(body["query"]).strip()[:120]))
            elif action == "say" and isinstance(body.get("text"), str) and body["text"].strip():
                app.jobs.put(("say", body["text"].strip()[:300]))
            elif action == "listen":
                app.listening = bool(body.get("on"))
                app.log("system", message=f"listening {'on' if app.listening else 'off'}")
            else:
                return self._send(400, b'{"ok": false}', "application/json")
            self._send(200, b'{"ok": true}', "application/json")
    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sdk", default="~/zetic-demo/sdk", help="local Ixian Hexagon SDK directory")
    p.add_argument("--model", default="~/zetic-demo/models/lfm3-omni-2b", help="local LFM3-Omni package directory")
    p.add_argument("--protocol", default=str(HERE / "protocols/appendectomy.json"))
    library = next((d / "procedures_step_by_step.txt" for d in (HERE, HERE.parent.parent)
                    if (d / "procedures_step_by_step.txt").exists()), HERE / "procedures_step_by_step.txt")
    p.add_argument("--procedures", default=str(library), help="step-by-step procedure library (text file)")
    p.add_argument("--run-dir", default=str(HERE / "run"), help="log, clips and zone snapshots")
    p.add_argument("--camera", default="auto", help="V4L2 device, or auto for the first USB camera")
    p.add_argument("--mic", default="plughw:CARD=WEBCAM,DEV=0", help="ALSA capture device")
    p.add_argument("--speaker", default="plughw:CARD=LEMANSEVK,DEV=0", help="ALSA playback device")
    p.add_argument("--clip-seconds", type=int, default=6)
    p.add_argument("--mic-threshold", type=int, default=6000, help="peak level (0-32767) that counts as speech")
    p.add_argument("--parse", choices=("auto", "rules"), default="auto",
                   help="auto: code rules first, the LFM for statements the rules cannot read")
    p.add_argument("--scan-every", type=float, default=3.0, help="seconds between automatic scans after count in; 0 = off")
    p.add_argument("--runner", choices=("auto", "cli"), default="auto",
                   help="auto: keep the model loaded in interactive CLI sessions; cli: one CLI process per request")
    p.add_argument("--speak", action="store_true", help="speak alerts with the model's speech output")
    p.add_argument("--time-scale", type=float, default=1.0, help="scale step time limits (0.02 for a fast demo)")
    p.add_argument("--timeout", type=float, default=120, help="seconds per model request, including load")
    p.add_argument("--host", default="127.0.0.1", help="keep loopback; reach it through SSH port forwarding")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--mock", action="store_true", help="laptop-only: fake camera and model, to test logic and UI")
    p.add_argument("--polar", metavar="ID", help="Polar strap device ID (e.g. 1C5EEF3E) for live heart rate; needs bleak")
    args = p.parse_args()
    args.sdk, args.model = os.path.expanduser(args.sdk), os.path.expanduser(args.model)
    app = Argus(args)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"Argus on http://{args.host}:{args.port}  log: {app.log_path}", flush=True)
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if app.resident:
            with app.infer_lock:
                app.resident.close()


if __name__ == "__main__":
    main()
