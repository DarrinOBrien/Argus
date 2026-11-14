# Argus

**An always-on eye and ear for the operating room. Everything runs on the board. No patient data leaves the room.**

Argus watches the instrument tray and the patient area, listens to the surgical team, and speaks up when something is wrong: an item missing at closing, a dose over the limit, a skipped step, a heart rate out of range. It runs entirely on a Qualcomm Dragonwing IQ-9075 with Liquid AI's LFM3-Omni-2B on the Hexagon NPU, built to keep working with Wi-Fi switched off.

Built in two hours at the **On-Device AI Hackathon: Cleared for Takeoff** (Liquid AI x Qualcomm), San Francisco, November 13, 2026.

> Hackathon prototype. Argus is not a medical device. The protocol, dose limits, and heart-rate range are demo values, not clinical guidance.

## The problem

Surgical teams count swabs and instruments by hand, out loud, at the start and end of every operation. The count happens at the busiest, most tired moment of the case, and sometimes it is wrong.

- About 1 in 5,500 to 7,000 operations leaves an item inside the patient. About two thirds are swabs.
- The Joint Commission reported 119 cases in 2024, the fourth year in a row of increase.
- Each case costs about $77,000 to over $500,000.

(Published figures gathered by the team, not Argus measurements.)

## What Argus does

| | |
|---|---|
| **Count in / count out** | A camera over the table counts tissues and instruments on the tray and in the patient area. At closing it compares count out with count in and raises a critical alarm: what is missing, how many, and where it was last seen. |
| **Voice log** | The team narrates as they work ("10 milligrams propofol", "starting incision"). Argus transcribes it on the board and logs drug, dose, unit, and time. |
| **Procedure tracking** | Loads a protocol (steps, time limits, drug table) and alerts on skipped steps, out-of-order steps, overdue steps, and doses above the single-dose limit. |
| **Heart rate** (optional) | Reads a Polar chest strap over Bluetooth LE and alerts when the rate leaves the protocol range or the signal drops. |
| **Alerts you can hear** | Alerts appear on a board-hosted dashboard and, with `--speak`, are spoken through the board's speaker by the model's speech output. |
| **A log that proves it** | Every observation, model call, decision, and alert is one flushed JSON line, with latency and NPU evidence per request. |

## Why it must run on the device

| Constraint | Why a cloud API fails it |
|---|---|
| Patient video and audio stay in the room | The inputs are a camera over an open patient and a microphone on the team. Nothing is sent off the board, so there is nothing upstream to breach (privacy, HIPAA). |
| The alarm cannot depend on a link | The closing alarm is decided by code on the board from local counts. It fires whether or not any network is up. |
| Operating-room networks are unreliable | Theatres are shielded and locked down. A counter that goes blind when Wi-Fi drops teaches the team to ignore it. |
| Flat cost | The microphone listens for the whole operation, every operation. Per-request billing grows with every minute; one board per room does not. |

## How it works

```text
 USB webcam (video + mic)        Polar H10 strap (optional, Bluetooth LE)
          |                                   |
          v                                   v
 +---------------- Dragonwing IQ-9075, Wi-Fi off -------------------+
 |                                                                   |
 |  camera.py   grayscale frames, tray / patient zone crops          |
 |  ear thread  6 s audio clips above a level threshold              |
 |       |                                                           |
 |       v                                                           |
 |  LFM3-Omni-2B on the Hexagon NPU (ZETIC Ixian SDK, v73 two-NSP)  |
 |  3 resident sessions: vision counts, speech to text, text parse   |
 |       |  proposals only (JSON counts, transcript, parsed event)   |
 |       v                                                           |
 |  argus.py: code decides                                           |
 |  validate -> inventory -> protocol -> dose -> heart rate -> alert |
 |       |                                                           |
 |       +--> run/argus-log.jsonl (flushed per record)               |
 |       +--> dashboard on 127.0.0.1:8000, spoken alerts             |
 +-------------------------------------------------------------------+
```

**The model proposes; code decides.** Every model answer is treated as untrusted. Standard-library Python validates it against the protocol (known item names, bounded integer counts, known drugs and units), keeps the inventory, and raises every alert. The model never writes to the inventory, never clears an alert, and never decides that a count is acceptable.

## Stack

- **Board:** Qualcomm Dragonwing IQ-9075 EVK, Ubuntu 24.04 aarch64
- **Model:** Liquid AI LFM3-Omni-2B (`ZETIC-ai/LFM3-Omni-2B-IQ9`, v73 two-NSP package), one model for vision, speech to text, text parsing, and speech output
- **Runtime:** ZETIC Ixian Hexagon SDK 0.2.1, model kept resident between requests
- **App:** Python 3.12 standard library only (no OpenCV, numpy, or web framework); `bleak` only for the optional heart-rate strap
- **Sensors:** Logitech C270 webcam (camera and microphone), optional Polar H10 chest strap

## Run it

On the **board**, from the repository root (needs the SDK and model staged locally, see the [app README](apps/argus/README.md#how-to-launch)):

```bash
apps/argus/run.sh                                              # spoken alerts on
~/.venvs/argus/bin/python apps/argus/argus.py --speak --polar 1C5EEF3E   # plus live heart rate (bleak in a venv)
```

On a **laptop**, with a fake camera and a fake model, to try the logic and the dashboard:

```bash
python3 apps/argus/argus.py --mock
# open http://127.0.0.1:8000
```

## Repository

| Path | What it is |
|---|---|
| [`apps/argus/README.md`](apps/argus/README.md) | Full technical write-up: architecture, flags, offline status, measurements, known limits |
| [`apps/argus/DEMO.md`](apps/argus/DEMO.md) | The two-minute demo script, including the Wi-Fi-off check |
| [`apps/argus/ARDUINO_PROJECT_HUB.md`](apps/argus/ARDUINO_PROJECT_HUB.md) | Arduino Project Hub write-up |
| `apps/argus/argus.py` | The app: worker queue, inventory, protocol, dose and heart-rate logic, alerts, JSONL log, web server |
| `apps/argus/camera.py` | Standard-library V4L2 capture and zone crops |
| `apps/argus/zetic_run.py` | Guarded wrapper around the ZETIC vendor CLI |
| `apps/argus/protocols/` | Demo protocol: items, steps, time limits, drug table, heart-rate range |
| `apps/argus/static/index.html` | The board-hosted dashboard |
| `procedures_step_by_step.txt` | Procedure library that `argus.py` loads (keep it at the repo root or in `apps/argus/`) |
| `AGENTS.md`, `CLAUDE.md`, `skills/`, `docs/` | Hackathon reference material and coding-agent skills for the IQ9 board |

## Offline and verification status

Argus makes no outbound network call: local model files, a local SDK binary, a page served by the board on loopback, no telemetry, no CDN assets. A static offline audit of `apps/argus` reports 0 errors and 0 warnings. What has and has not been measured on the board is listed honestly in the [app README](apps/argus/README.md#what-is-not-verified-yet).

## Team

Darrin O'Brien, Furkan Imamoglu, Hussein Hirani

## License

MIT, see [LICENSE](LICENSE). This repository started from the hackathon's [starter repo](https://github.com/heath0xFF/cleared-for-takeoff-hackathon). LFM3-Omni-2B is distributed under the LFM Open License v1.0; the ZETIC SDK carries its own licence. Neither the model weights nor the SDK binaries are in this repository.
