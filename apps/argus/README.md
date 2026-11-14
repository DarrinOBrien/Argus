# Argus

An always-on eye and ear for the operating room, running entirely on a Qualcomm Dragonwing IQ-9075 EVK.

A camera looks down at two zones, the instrument tray and the patient area. A local multimodal model counts what it sees and transcribes what the team says. Plain Python code keeps the inventory, follows the protocol, checks drug doses and step timing, and raises an alarm when the count at closing does not match the count at the start. Nothing leaves the board.

**Status: hackathon prototype.** Argus is not a medical device. The bundled protocol and dose limits are demo values, not clinical guidance. Read [what is not verified yet](#what-is-not-verified-yet) before relying on anything below.

Demo script: [DEMO.md](DEMO.md). Project Hub write-up: [ARDUINO_PROJECT_HUB.md](ARDUINO_PROJECT_HUB.md).

## The problem

Surgical teams count swabs and instruments by hand, out loud, at the start and end of an operation. The count is done by tired people at the busiest moment of the case, and sometimes it is wrong.

Background figures supplied by the team from published reports. They describe the problem; they are **not Argus measurements**:

- About 1 in 5,500 to 7,000 operations leaves an item inside the patient.
- About two thirds of retained items are swabs.
- The Joint Commission reported 119 cases in 2024.
- Cost per case is about $77,000 to over $500,000.

Argus is a second counter that does not get tired: it counts in, notes what it sees in the patient area, and refuses to stay quiet at closing if something is missing.

## Why it must be on-device

The judges' first question is "why is this not a cloud API call?" Four specific constraints:

| Constraint | Why a cloud call fails it |
|---|---|
| **Patient audio and video stay in the room** | The inputs are a camera over an open patient and a microphone on the surgical team. Argus sends no frame, clip, or transcript off the board; there is no upstream service to breach or misconfigure. |
| **The alarm cannot depend on a link** | The alert at "closing" is the whole product. The decision is made by code on the board from local counts, so it fires whether or not any network is up. |
| **Operating-room networks are unreliable** | Theatres are shielded, segmented, and locked down. A counter that goes blind when Wi-Fi drops teaches the team to ignore it. |
| **Flat cost** | The microphone listens for the whole operation, every operation. Always-on speech and vision billed per request grows with every minute of surgery; one board per room does not. |

## Architecture

```text
 Logitech C270 (USB)
   |-- video: /dev/video0, YUYV 1280x720, luma only (grayscale)
   |-- audio: built-in microphone, arecord, 6-second 16 kHz mono clips
   v
 camera.py                                   argus.py "ear" thread
   | 640x360 grayscale BMP preview             | keeps a clip only if its peak level
   | 512x512 PPM crop per zone                 | passes --mic-threshold
   v                                           v
 +---------------------------- zetic_run.py -----------------------------+
 | one capped request per call, one at a time                            |
 | -> zetic_lfm3_cli (Ixian Hexagon SDK 0.2.1)                           |
 | -> LFM3-Omni-2B, v73 two-NSP package, Hexagon NPU                     |
 | guards: token count, natural finish, non-empty text,                  |
 |         current-request Hexagon v73 / two-NSP evidence                |
 +-----------------------------------------------------------------------+
   | proposals: item counts per zone, transcript, parsed statement
   v
 argus.py: code decides
   | inventory (count in, zone counts, last sighting in the patient area)
   | protocol step list (order, skipped steps, time limits)
   | drug log (unit and single-dose limit)
   | alerts (medium / high / critical)
   |
   +--> run/argus-log.jsonl, flushed per record
   +--> static/index.html served from the board on 127.0.0.1:8000
        (camera, counts, steps, log, alerts, latency)
```

**The model only proposes; code decides.** LFM3-Omni-2B is used for these jobs, each as a separate capped request:

1. **Vision counts.** One 512x512 crop per zone. The model is asked for one JSON object of integer counts for the protocol's item list.
2. **Speech to text.** A short audio clip becomes a transcript.
3. **Text parsing, as a fallback.** Code rules read each transcript first (count in, closing, a dose with a unit and a drug name, step keywords). Only a statement the rules cannot read is sent to the model, which proposes one JSON event.
4. **Spoken alerts, optional.** With `--speak`, alert text is synthesized by the model's speech output and played on the board's speaker.

Every model answer is treated as an untrusted proposal. Standard-library Python then:

- **validates it.** Vision counts must be integers from 0 to 50 for item names in the protocol; anything else rejects the scan. A parsed step must be a step id in the protocol. A parsed drug must match the protocol's drug table, with a known unit and a bounded numeric dose.
- **keeps the inventory.** Count in records a baseline across both zones. Each scan updates the zone counts and the last time each item was seen in the patient area.
- **follows the protocol.** Starting a step marks earlier ones done or skipped, raises an alert for a skipped or out-of-order step, and a timer raises an alert when a step runs past its limit.
- **checks each dose.** A drug is logged with its dose and unit, then compared with the protocol's unit and single-dose maximum.
- **decides at closing.** Count out is compared with count in, item by item. Anything missing, extra, or still in the patient area raises a critical alert that says what, how many, and where it was last seen.
- **logs everything.** One flushed JSON line per event, with separate record kinds: `model` (raw text, errors, device evidence, timings), `proposal`, `observation`, `utterance`, `action`, `alert`, `error`, `note`, `system`. Errors in the loop are logged as data and the loop keeps running.

The model never writes to the inventory, never clears an alert, and never decides that a count is acceptable.

### What "always-on" means here

- The camera streams continuously for the preview.
- The microphone records continuously while listening is switched on in the page.
- **Counting is event-driven, not continuous:** both zones are counted at count in, on a scan request, and at closing. There is no periodic background count yet.

### Files

| File | Role |
|---|---|
| `argus.py` | The app: worker queue, inventory, protocol and dose logic, alerts, JSONL log, and the web server |
| `camera.py` | Standard-library V4L2 capture (no OpenCV, numpy, or PIL). Grabs YUYV 1280x720, keeps the luma plane, and produces the grayscale preview and the 512x512 zone crops |
| `zetic_run.py` | Wrapper around the vendor CLI `zetic_lfm3_cli`. One capped request per call, local files only, with output and device-evidence guards; errors are returned as data |
| `protocols/appendectomy.json` | Demo protocol: four item types with a shape hint for each, six steps with keywords and time limits, and a drug table with units and single-dose maximums |
| `static/index.html` | The board-hosted dashboard, one self-contained file (no external scripts, fonts, or images). Top row: case status, KPI tiles, and gauges for count match, step time, and heart rate (with `--polar`) or last model request time. Middle row: model request time per request, and items seen per zone against the count in. Bottom row: camera with controls, procedure steps, inventory, event log, drug log, and performance. Respects reduced-motion, reduced-transparency, and high-contrast settings |

Local endpoints served by `argus.py`: `GET /` (page), `GET /frame.bmp` (camera preview), `GET /api/state` (counts, steps, drugs, alerts, recent log, latency medians), and `POST /api/count_in`, `/api/scan`, `/api/closing`, `/api/say` (typed statement), `/api/listen` (microphone on or off).

### Design notes and known limits

- **Grayscale.** Camera frames are used in grayscale. Pure-Python colour conversion was too slow, so colour is dropped and counting relies on shape. Items that differ only by colour cannot be told apart.
- **A fresh model process per request.** The wrapper starts the vendor CLI for every request, so every request includes loading the model. Requests run one at a time through a single queue. A count of both zones is two requests.
- **Speech has a built-in delay.** Audio is recorded in 6-second clips (`--clip-seconds`), then transcribed, so a spoken command is acted on after the clip ends plus one model request.
- **Fixed zones.** The two zones are fixed 512x512 squares of the 1280x720 frame (left for the tray, right for the patient area). The camera and the mat must be lined up to match.
- **Not entirely NPU.** The vendor runtime offloads the model to the Hexagon NPU, with some work remaining on the CPU. We do not claim entirely-NPU execution.
- **Spoken alerts are best effort.** The `--speak` path calls the vendor CLI directly and does not go through the wrapper's output and device-evidence guards. A failure is logged and the on-screen alert stands.
- **Local working files.** `run/` holds the log (including transcripts), the last eight audio clips, and the latest crop of each zone. They stay on the board and the clips and crops are overwritten in place, but they are patient data: do not commit or copy them from a real room.
- **Demo protocol.** `appendectomy.json` is illustrative. Its steps, time limits, and dose limits were written for the demo and have not been reviewed by a clinician.

## How to launch

### What must be on the board first

- Dragonwing IQ-9075 EVK, Ubuntu 24.04 aarch64, Python 3.12. Standard library only; no pip packages.
- Ixian Hexagon SDK **0.2.1** (Linux ARM64 QCOM IQ9) in its original layout, at `~/zetic-demo/sdk` (or pass `--sdk`).
- The `ZETIC-ai/LFM3-Omni-2B-IQ9` package, `v73` (two-NSP) variant, at `~/zetic-demo/models/lfm3-omni-2b` (or pass `--model`). The directory must contain `v73/manifest.json`.
- Both on board storage, not on removable media. Staging steps: [examples/zetic-lfm](../../examples/zetic-lfm/README.md#stage-once-with-approval).
- A Logitech C270 on USB, visible as `/dev/video0`, with the `ubuntu` user in the `video` group.
- `arecord` for the microphone (ALSA device `plughw:CARD=WEBCAM,DEV=0` by default), and `aplay` if `--speak` is used.
- This repository on the board.

Nothing is downloaded or installed when Argus starts.

### Start it

On the **board** (UART console, or SSH), from the repository root:

```bash
python3 apps/argus/argus.py
```

It prints the listen address and the log path. The page is served on the board at `127.0.0.1:8000` and is not exposed on the network by default.

On the **laptop**, in a separate terminal, forward the port over SSH and open the page:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8000:127.0.0.1:8000 "$IQ9_HOST"
# then open http://127.0.0.1:8000 in the laptop browser
```

Watch the log on the **board**:

```bash
tail -f apps/argus/run/argus-log.jsonl
```

### Flags

| Flag | Default | Purpose |
|---|---|---|
| `--mock` | off | Laptop-only: fake camera and fake model, to test the logic and the page. The microphone and speech output are disabled |
| `--polar ID` | off | Live heart rate from a Polar strap over Bluetooth LE (for example `--polar 1C5EEF3E`). Needs `bleak`; see [Heart rate](#heart-rate-optional) |
| `--speak` | off | Speak alerts with the model's speech output on the board's speaker |
| `--parse {auto,rules}` | `auto` | `auto`: code rules first, the model for statements the rules cannot read. `rules`: code rules only, no model parsing |
| `--time-scale` | `1.0` | Scale step time limits (for example `0.02` so that overdue-step alerts appear in a short demo) |
| `--host`, `--port` | `127.0.0.1`, `8000` | Listen address. Keep loopback and use SSH port forwarding; a non-loopback address exposes the page to the network |
| `--sdk`, `--model` | `~/zetic-demo/sdk`, `~/zetic-demo/models/lfm3-omni-2b` | Local SDK and model package directories |
| `--protocol` | `protocols/appendectomy.json` | Protocol file |
| `--run-dir` | `apps/argus/run` | Log, audio clips, and zone crops |
| `--camera` | `/dev/video0` | V4L2 device |
| `--mic`, `--speaker` | `plughw:CARD=WEBCAM,DEV=0`, `plughw:CARD=LEMANSEVK,DEV=0` | ALSA capture and playback devices |
| `--clip-seconds`, `--mic-threshold` | `6`, `6000` | Clip length, and the peak level (0 to 32767) a clip must reach to be transcribed |
| `--timeout` | `120` | Seconds per model request, including model load |

`python3 apps/argus/argus.py --help` prints the same list.

### Heart rate (optional)

With `--polar ID`, a background thread finds the strap whose Bluetooth name contains `ID`, subscribes to the standard heart-rate characteristic (no Polar SDK), and shows the live rate on the page. Code raises a `high` alert when the rate leaves the protocol's `vitals` range (`hr_min`, `hr_max`), and when no valid reading arrives for 5 seconds (strap off or out of range). It logs a `vital` record every 30 seconds and on every range change. A lost strap is retried every 3 seconds; errors are logged and the rest of Argus keeps running.

This is the one non-standard-library dependency, and it is only imported with `--polar`. On the **board**, install it once while setup internet is up (needs approval; BlueZ must be running):

```bash
python3 -m venv --system-site-packages ~/.venvs/argus
~/.venvs/argus/bin/pip install bleak
~/.venvs/argus/bin/python apps/argus/argus.py --polar 1C5EEF3E
```

The strap only advertises while worn with wet electrodes, and a phone or other device holding it can block the connection. Checked so far on a laptop only (macOS, `--mock`): connected to a Polar H10, live rate on the page, out-of-range alert raised once. **Not yet run on the board.**

### Try it without a board

```bash
# laptop, from the repository root
python3 apps/argus/argus.py --mock
# open http://127.0.0.1:8000
```

In mock mode the "model" returns the counts in `run/mock_scene.json`, so editing that file moves items between zones. Create it with the protocol's item names before pressing Count in, for example:

```bash
mkdir -p apps/argus/run
echo '{"tray": {"swab": 3, "scalpel": 1, "forceps": 1, "probe": 1}, "patient": {}}' > apps/argus/run/mock_scene.json
```

Without that file the built-in mock tray uses item names that are not in the current protocol, so every count reads zero. Statements are typed into the page instead of spoken.

## Offline status

**Designed to run with no network. Not yet proven with the network off.**

By design:

- The model is loaded from a local package directory by a local SDK binary. There is no model download, package install, or hub lookup at startup or at runtime.
- The wrapper sets `HF_HUB_OFFLINE=1` and `HF_HUB_DISABLE_TELEMETRY=1` for the vendor process.
- The Python code uses the standard library only and makes no outbound network call. There is no telemetry and no cloud service.
- The page is served by the board. The server listens on loopback by default.

Checked so far:

- Static offline audit, run on a laptop on 2026-11-13 against `argus.py`, `camera.py`, `zetic_run.py`, the protocol file, and `static/index.html`:

  ```bash
  python3 skills/iq9-offline-rehearsal/scripts/offline_audit.py apps/argus
  # 0 error(s), 0 warning(s)
  ```

  The page loads no external script, stylesheet, font, or image; it only talks to the server that served it (`/api/*` and `/frame.bmp`). A static audit is a heuristic and is not proof of offline operation. Re-run it if the code changes.

For the demo, Wi-Fi is turned off from the UART console in front of the judge. The page then has to be reached over a path that does not use Wi-Fi; see [DEMO.md](DEMO.md#before-you-walk-up).

## Measurements

No numbers have been recorded yet. Every value below is a placeholder to be filled from this app's own runs on the board. Nothing here is copied from documentation.

Run context (fill in with the measurements):

| Item | Value |
|---|---|
| Board | Dragonwing IQ-9075 EVK, Ubuntu 24.04 aarch64 |
| Runtime | Ixian Hexagon SDK 0.2.1, `zetic_lfm3_cli`, target `v73` (two NSPs) |
| Model | `ZETIC-ai/LFM3-Omni-2B-IQ9`, package `lfm3-omni-2b` |
| Model package revision | TBD - measured on the board |
| Precision (`lm.quant` in the package manifest) | TBD - measured on the board |
| Date and workload | TBD - measured on the board |

Results. Report medians of successful requests with successful / attempted counts. The page's latency panel shows running medians per request kind; the source of truth is the `model` and `observation` records in `run/argus-log.jsonl`.

| Metric | Source | Value | n (ok / attempted) |
|---|---|---|---|
| Vision count, runtime time-to-first-token | `model` records, `request: vision:*`, `ttft_ms` | TBD - measured on the board | TBD |
| Vision count, decode tokens/s | same records, `tok_s` | TBD - measured on the board | TBD |
| Vision count, model load per request | same records, `load_ms` | TBD - measured on the board | TBD |
| Vision count, wall time per zone (includes load) | same records, `wall_s` | TBD - measured on the board | TBD |
| Two-zone scan, end to end | `observation` records, `loop_s` | TBD - measured on the board | TBD |
| Speech to text, wall time per clip | `model` records, `request: asr`, `wall_s` | TBD - measured on the board | TBD |
| Speech to text, runtime time-to-first-token | same records, `ttft_ms` | TBD - measured on the board | TBD |
| Text parse by the model (fallback), wall time | `model` records, `request: parse`, `wall_s` | TBD - measured on the board | TBD |
| "Closing" heard to critical alert logged | `utterance` and `alert` timestamps (1 s resolution) | TBD - measured on the board | TBD |
| Spoken alert synthesis time (`--speak`) | `action: spoken`, `tts_s` | TBD - measured on the board | TBD |
| Peak memory of the model process | `model` records, `peak_rss_mb` | TBD - measured on the board | TBD |
| Peak memory of the Argus process | `/usr/bin/time -v python3 apps/argus/argus.py` | TBD - measured on the board | TBD |
| Count accuracy on the demo tray | correct item counts / attempted | TBD - measured on the board | TBD |
| Network-off run | duration, scans, alerts, errors | TBD - measured on the board | TBD |

Notes for whoever fills this in:

- Runtime-reported time-to-first-token and decode rate exclude model loading; wall time includes it. Report them separately.
- The time taken by the code rules themselves (inventory, dose, protocol) is not instrumented as its own field.
- `peak_rss_mb` is the largest child process so far, as reported by the operating system; it is host memory, not NPU or device memory.

### Procedure log

The procedure library is `procedures_step_by_step.txt` at the repository root (or `--procedures`): a `=== #N | Name | Specialty ===` heading, then numbered steps. Choose a procedure in the page's procedure box (number or name), or say or type it ("we are doing demo 0", "starting laparoscopic gastric bypass"). Argus then counts in and keeps a timed, plain-sentence log in the Procedure log card and as `procedure_log` records in the JSONL log:

- **Taken and returned, numbered.** Camera changes to the tray count (seen in two scans in a row) and spoken or typed statements ("one tissue is taken", "taking two knives", "tissue one and tissue two returned") both write lines such as `Tissue 1 and tissue 2 taken`. Words are mapped to items through `item_aliases` in the protocol. A statement within 45 seconds of the same change seen by the camera is not counted twice, and a statement made first moves the count the camera compares against.
- **Procedure steps.** A statement that matches the next uncalled step of the chosen procedure ("the shirt is lifted") is logged as that step with its time.
- **Repeat doses.** A drug announced again after the doses the procedure plans (or after one dose, for a drug the procedure does not mention) is not recorded. Argus raises a critical alert and speaks "Don't do that! Someone already added <drug>." The spoken sentence carries no dose, so the microphone hearing it back is not read as another one. This applies to every drug, including the protocol's own.

`GET /api/procedures` lists the library for the page's picker; `POST /api/procedure` with `{"query": "0"}` starts one.

## What is not verified yet

Stated plainly, as of writing:

- **No measurement has been taken.** The table above is all placeholders.
- **No network-off rehearsal is recorded.** Argus has not been shown starting cold and running its core workflow with the board's Wi-Fi off.
- **NPU execution is not recorded for this app.** The wrapper rejects any request that lacks current-request Hexagon v73 / two-NSP evidence and logs the evidence line in each `model` record, but no such record from an Argus run on the board has been saved yet.
- **Count accuracy is unknown.** How reliably the model counts swabs, scalpels, forceps, and probes in grayscale 512x512 crops has not been evaluated.
- **Speech recognition is unverified** for operating-room speech, accents, masks, or background noise. The microphone threshold is a guess until tuned in the room.
- **Spoken alerts (`--speak`) are unverified** on the board.
- **The page's reachability after Wi-Fi goes off is unverified.** SSH port forwarding over Wi-Fi ends when Wi-Fi is turned off. An isolated USB-C link, or another path that does not use Wi-Fi, has to be set up and tested before the demo.
- **The protocol and dose table are not clinically reviewed.**
- **No endurance run.** Behaviour over a full-length operation (heat, memory, error rate) has not been observed.

What has been checked, on a laptop only:

- The demo flow in `--mock` mode through the local API (count in, "10 milligrams propofol", scan, "Closing"): the dose was logged, the protocol advanced, and a critical alert named one missing swab and where it was last seen. This exercises the code logic with a fake camera and a fake model. It says nothing about the board, the camera, the model, or the NPU.
- The procedure log in `--mock` mode through the local API, with typed statements for demo 0: numbered taken and returned lines with times, steps 2 to 7 matched, a camera change not counted twice when said afterwards, and the second "adding 5 mL of adrenaline" blocked with the spoken-alert job queued. Speech recognition of these phrases on the board is unverified.
- The static offline audit: 0 errors, 0 warnings. See [Offline status](#offline-status) for its scope.

## Licences

LFM3-Omni-2B is distributed under the LFM Open License v1.0. The Ixian Hexagon SDK carries its own licence files. This repository contains neither model weights nor SDK binaries.
