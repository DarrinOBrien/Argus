# Argus: Arduino Project Hub write-up

Paste-ready text for the Project Hub entry. The section headings below match the Project Hub editor's fields. Paste the code files listed under [Code](#code) into the entry's code section in full; the hackathon asks for the whole project on the Hub, not only a link.

Before publishing, replace every `TBD` with a number measured on the board, or delete the row. Do not publish a number that was not measured.

---

## Title

Argus: an always-on eye and ear for the operating room

## One-line summary

A camera and microphone over the instrument tray count swabs and instruments in and out, follow the surgical protocol, check spoken drug doses, and raise an alarm before closing if anything is missing. It runs entirely on a Qualcomm Dragonwing IQ-9075, with no network.

## Tags

on-device AI, edge AI, healthcare, surgical safety, computer vision, speech recognition, Qualcomm Dragonwing, LiquidAI LFM3, offline

---

## Components and supplies

| Item | Qty | Notes |
|---|---|---|
| Qualcomm Dragonwing IQ-9075 EVK | 1 | Ubuntu 24.04 aarch64, Hexagon NPU. Runs everything |
| Logitech C270 USB webcam | 1 | Looks straight down at the table. Its built-in microphone is the "ear" |
| Camera mount or arm | 1 | Holds the camera above the table, pointing down |
| Mat or sheet marked with two squares | 1 | Left square: instrument tray. Right square: patient area |
| Props: swabs, scalpel, forceps, probe | a few swabs, one of each tool | The four item types in the demo protocol |
| Laptop | 1 | Serial console, and a browser for the board-hosted page |
| Micro-USB cable | 1 | Board UART console. Needs no network |
| USB-C cable | 1 | Optional isolated link from laptop to board for SSH and the page |

No external sensor, no cloud account, and no Arduino-side firmware are needed.

## Apps and platforms

| Item | Notes |
|---|---|
| LiquidAI LFM3-Omni-2B (`ZETIC-ai/LFM3-Omni-2B-IQ9`, `v73` two-NSP package) | One multimodal model for image counts, speech to text, text parsing, and optional spoken alerts |
| ZETIC Ixian Hexagon SDK 0.2.1 | Vendor runtime and command-line tool that run the model on the Hexagon NPU |
| Python 3.12, standard library only | The whole app. No pip packages, no OpenCV, no numpy |
| ALSA `arecord` / `aplay` | Microphone capture, and playback for spoken alerts |

---

## Story

### The problem

At the start and end of an operation, the team counts every swab and instrument by hand, out loud. It is the last task of a long case, done by tired people, and sometimes the count is wrong. When it is, something stays inside the patient.

Published figures, quoted as background (these are not results from this project):

- About 1 in 5,500 to 7,000 operations leaves an item inside the patient.
- About two thirds of those items are swabs.
- The Joint Commission reported 119 cases in 2024.
- Each case costs about $77,000 to over $500,000.

### The idea

Argus is a second counter that does not get tired. A camera looks down at two zones, the instrument tray and the patient area. A microphone listens to the team. When the team counts in, Argus records what is on the table. As the case goes on, it notes what it sees in the patient area, logs each drug and dose it hears, and follows the steps of the procedure. When the surgeon says "closing", it counts again. If a swab that was counted in is on neither the tray nor in view, it says so, says where the swab was last seen, and says do not close.

Argus is named after the hundred-eyed watchman of Greek myth, who never closed all his eyes at once.

### Why it has to run on the device

This could not be a cloud API call, for four specific reasons:

1. **Patient audio and video stay in the room.** The inputs are a camera over an open patient and a microphone on the surgical team. Argus sends no frame, clip, or transcript anywhere. There is no upstream service to breach.
2. **The alarm cannot depend on a link.** The alert at closing is the whole product. It is decided by code on the board from local counts, so it fires whether or not any network is up.
3. **Operating-room networks are unreliable.** Theatres are shielded, segmented, and locked down. A counter that goes blind when Wi-Fi drops teaches the team to ignore it.
4. **Flat cost.** The microphone listens for the whole operation, every operation. Always-on vision and speech billed per request grows with every minute of surgery. One board per room does not.

For the hackathon demo, the board's Wi-Fi is switched off in front of the judge and the whole workflow keeps running.

### The model proposes; code decides

A language model that miscounts must never be the thing that tells a surgeon it is safe to close. So the model is never asked that question. It is only asked small, checkable things: "how many of each item are in this picture", "what was said in this clip". Every answer is treated as an untrusted proposal. Ordinary Python code validates it, keeps the inventory, applies the rules, and raises the alarm. The model's raw answer and the code's decision are both written to a local log, so a wrong model answer is visible, not silent.

---

## How it works

```text
 Logitech C270 (USB)
   |-- video: YUYV 1280x720, luma only (grayscale)
   |-- audio: built-in microphone, 6-second 16 kHz mono clips
   v
 camera.py                                   argus.py "ear" thread
   | 640x360 grayscale preview                 | keeps a clip only if it is loud enough
   | 512x512 crop per zone                     |
   v                                           v
 +---------------------------- zetic_run.py -----------------------------+
 | one capped request per call, one at a time                            |
 | -> zetic_lfm3_cli (Ixian Hexagon SDK 0.2.1)                           |
 | -> LFM3-Omni-2B, v73 two-NSP package, Hexagon NPU                     |
 | checks: token count, natural finish, non-empty text,                  |
 |         Hexagon device evidence for this request                      |
 +-----------------------------------------------------------------------+
   | proposals: item counts per zone, transcript, parsed statement
   v
 argus.py: code decides
   | inventory, protocol steps, drug log, alerts
   +--> argus-log.jsonl (one flushed line per event)
   +--> web page served by the board (camera, counts, steps, log, alerts, latency)
```

### 1. Seeing

`camera.py` talks to the webcam directly through the Linux V4L2 interface using only the Python standard library. The board image has no OpenCV or numpy, and nothing is installed for this project. It captures 1280x720 frames, keeps only the brightness channel, and cuts two 512x512 squares: the left one is the tray, the right one is the patient area.

Frames are used in grayscale. Converting colour in pure Python was too slow, and the items are told apart by shape.

For each zone, the model receives the crop and a prompt asking for one JSON object of integer counts for the protocol's item list (swab, scalpel, forceps, probe), with a short description of each item's shape taken from the protocol file. Code then checks that every count is an integer from 0 to 50 for a known item. Anything else rejects the scan and is logged as an error.

### 2. Hearing

While listening is switched on, the app records 6-second clips from the webcam's microphone. Quiet clips are discarded. A clip with sound in it is sent to the same model for speech to text.

The transcript is read by code rules first: "count in", "closing", a dose with a unit and a drug name ("10 milligrams propofol"), and the protocol's step keywords. Number words and unit names are normalised, and drug names are matched against the protocol's drug table. Only a statement the rules cannot read is sent to the model, which proposes a single JSON event. That proposal is validated against the protocol before anything is recorded.

### 3. Deciding

All decisions are plain Python:

- **Count in** records a baseline for every item across both zones.
- **Scan** updates the zone counts and remembers when each item was last seen in the patient area.
- **Protocol.** Starting a step marks earlier steps done or skipped. A skipped step, an out-of-order step, or a step that runs past its time limit raises an alert.
- **Drugs.** Each dose is logged, then checked against the protocol's unit and single-dose maximum. A mismatch raises an alert asking the team to confirm.
- **Closing** counts both zones again and compares with the baseline, item by item. Anything missing, extra, or still in the patient area raises a critical alert.

An alert from a laptop test run with simulated camera and model input:

```text
critical  Count out does not match. 1 swab missing, last seen in the patient area at 19:17:14. Do not close.
```

### 4. Showing and logging

The board serves one web page from its own loopback address, reached from the laptop through SSH port forwarding. It shows the camera with both zones, the inventory, the procedure steps, the drug log, the event log, alerts, and per-request timing. The page loads nothing from the internet: no CDN script, stylesheet, or font.

Every event is appended to `argus-log.jsonl` and flushed immediately. Record kinds are kept separate: `model` (the raw answer, errors, device evidence, timings), `proposal`, `observation`, `utterance`, `action`, `alert`, `error`. An error in the loop becomes a log record; the loop keeps running.

With `--speak`, alert text is also synthesized by the model's speech output and played on the board's speaker.

### What "always-on" means in this version

The camera streams continuously and the microphone records continuously while listening is on. Counting is event-driven: at count in, on a scan request, and at closing. A continuous background count is the next step.

---

## Code

Paste each of these files, in full, into the Project Hub code section. They are in `apps/argus/` in the repository.

| File | What it does |
|---|---|
| `argus.py` | The app. Worker queue, inventory, protocol and dose rules, alerts, JSONL log, and the web server |
| `camera.py` | Standard-library V4L2 capture. Produces the grayscale preview and the two 512x512 zone crops |
| `zetic_run.py` | Wrapper around the vendor command-line tool. One capped request per call from local files, with checks on the output and on Hexagon device evidence. Errors are returned as data |
| `protocols/appendectomy.json` | The demo protocol: items, steps with keywords and time limits, and the drug table |
| `static/index.html` | The page served by the board. Self-contained |

Repository: https://github.com/DarrinOBrien/Argus (app in `apps/argus/`).

### The closing check

This is the decision that matters, and it is ordinary code. From `argus.py`:

```python
def closing(self):
    if self.baseline is None:
        self.alert("high", "Closing called but no count in was recorded.")
        return
    zones = self.scan("count_out")
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
```

### Validating what the model says

The vision answer is only accepted if it is exactly what was asked for. From `argus.py`:

```python
raw = json.loads(match.group(0))
counts = {}
for item in self.items:  # allowlisted keys, bounded integers; anything else is rejected
    value = raw.get(item, 0)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 50:
        raise ValueError(f"vision count for {item} is invalid: {value!r}")
    counts[item] = value
```

### The protocol file

A procedure is data, not code. `protocols/appendectomy.json`:

```json
{
  "name": "Laparoscopic appendectomy (demo protocol)",
  "items": ["swab", "scalpel", "forceps", "probe"],
  "item_hints": {
    "swab": "flat rectangular cloth or paper pad",
    "scalpel": "knife-shaped tool",
    "forceps": "fork-shaped tool",
    "probe": "thin metal rod"
  },
  "steps": [
    {"id": "timeout", "name": "Team time-out and count in", "keywords": ["time out", "timeout", "count in"], "max_minutes": 5},
    {"id": "anesthesia", "name": "Induction of anesthesia", "keywords": ["induction", "anesthesia", "propofol"], "max_minutes": 10},
    {"id": "incision", "name": "Incision and port placement", "keywords": ["incision", "port"], "max_minutes": 10},
    {"id": "dissection", "name": "Dissect and ligate appendix", "keywords": ["dissect", "ligat", "dividing"], "max_minutes": 25},
    {"id": "removal", "name": "Remove appendix", "keywords": ["removing the appendix", "appendix out", "specimen"], "max_minutes": 10},
    {"id": "closing", "name": "Count out and closing", "keywords": ["closing", "count out", "closure"], "max_minutes": 15}
  ],
  "drugs": {
    "propofol": {"max_single_dose": 200, "unit": "mg"},
    "fentanyl": {"max_single_dose": 100, "unit": "mcg"},
    "cefazolin": {"max_single_dose": 2000, "unit": "mg"},
    "rocuronium": {"max_single_dose": 100, "unit": "mg"}
  }
}
```

These steps, time limits, and dose limits are demo values. They have not been reviewed by a clinician.

---

## How to run it

### Set up the board once

1. Dragonwing IQ-9075 EVK with Ubuntu 24.04 and Python 3.12.
2. Put the Ixian Hexagon SDK 0.2.1 (Linux ARM64 QCOM IQ9) at `~/zetic-demo/sdk`, in its original layout.
3. Put the `ZETIC-ai/LFM3-Omni-2B-IQ9` package, `v73` variant, at `~/zetic-demo/models/lfm3-omni-2b`. The directory must contain `v73/manifest.json`.
4. Keep both on the board's own storage, not on a USB drive.
5. Plug in the Logitech C270. It should appear as `/dev/video0`.
6. Copy the repository to the board.

Nothing is downloaded or installed when the app starts.

### Lay out the table

Mount the camera looking straight down. Put the tray under the left half of the picture and the patient area under the right half. Use the page's camera view to line both up inside their squares. Even lighting helps.

### Start Argus

On the board, from the repository root:

```bash
python3 apps/argus/argus.py
```

On the laptop, forward the page and open it:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8000:127.0.0.1:8000 <board-ssh-host>
# open http://127.0.0.1:8000
```

### Use it

1. Lay out the items on the tray and press **Count in**.
2. Press **Listen** to switch the microphone on.
3. Say "10 milligrams propofol". The drug log records it and the procedure moves to induction.
4. Move items into the patient area and press **Scan**.
5. Take a swab out of view.
6. Say "Closing". Argus counts again and raises the alarm.

"Count in" and "Closing" can be spoken, typed, or pressed. There is a text box for typing any statement instead of saying it.

### Useful options

| Option | Purpose |
|---|---|
| `--mock` | Run on a laptop with a fake camera and a fake model, to try the page and the logic |
| `--speak` | Speak alerts through the board's speaker using the model's speech output |
| `--parse rules` | Read statements with code rules only; never ask the model to parse text |
| `--time-scale 0.02` | Shrink the step time limits so overdue-step alerts appear in a short demo |
| `--host`, `--port` | Listen address, `127.0.0.1:8000` by default |

`python3 apps/argus/argus.py --help` lists the rest (model and SDK paths, camera, microphone, clip length).

### Try it with no board at all

```bash
python3 apps/argus/argus.py --mock
# open http://127.0.0.1:8000
```

---

## Measurements

Measured on the Dragonwing IQ-9075 EVK with this app, this model, and this runtime. Medians of successful requests.

| Metric | Value | n (ok / attempted) |
|---|---|---|
| Vision count, wall time per zone (includes model load) | TBD - measured on the board | TBD |
| Vision count, runtime time-to-first-token | TBD - measured on the board | TBD |
| Vision count, decode tokens/s | TBD - measured on the board | TBD |
| Two-zone scan, end to end | TBD - measured on the board | TBD |
| Speech to text, wall time per clip | TBD - measured on the board | TBD |
| "Closing" heard to critical alert | TBD - measured on the board | TBD |
| Peak memory of the model process | TBD - measured on the board | TBD |
| Network-off run (duration, scans, alerts, errors) | TBD - measured on the board | TBD |

## Limits, stated plainly

- Argus is a hackathon prototype, not a medical device. It has not been tested in an operating room.
- Counting accuracy has not been evaluated. The demo is one staged scenario with four item types on a clean tray.
- Frames are grayscale, so items that differ only by colour cannot be told apart.
- The model is started fresh for every request, so each request includes loading it. Requests run one at a time.
- Speech is taken in 6-second clips, so a spoken command is acted on a few seconds after it is said.
- Counting happens at count in, on request, and at closing, not continuously.
- The model runs on the Hexagon NPU through the vendor runtime; some work remains on the CPU.
- The demo protocol and dose limits are illustrative and not clinical guidance.

## What comes next

- Keep the model loaded between requests, so a count is limited by inference and not by loading.
- Count continuously in the background and track each item between zones.
- Use colour, and more than one camera angle.
- A library of clinician-reviewed protocols, one file per procedure.
- A study of counting accuracy against a manual count, before anyone relies on it.

## Credits

Built at the On-Device AI Hackathon: Cleared for Takeoff (LiquidAI x Qualcomm Dragonwing), November 2026. Model: LiquidAI LFM3-Omni-2B, LFM Open License v1.0. Runtime: ZETIC Ixian Hexagon SDK 0.2.1.
