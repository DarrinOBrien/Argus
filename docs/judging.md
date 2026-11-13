# Judging and Demos

Use this rubric to plan the project and its demo. If the organizers' brief differs, follow the brief. The date, schedule, and venue are on the [event page](https://luma.com/0nsdnkoa).

## How to submit

Submit between **8:00 and 8:30 p.m. Pacific on November 13, 2026** through the [event submission form](https://submissions.loggia.sh/events/cleared-for-takeoff). Building ends and judging starts at 8:15 p.m.

Your submission must include **both**:

- A link to your project's **GitHub repository**. Fork this repo and build under [`apps/`](../apps/README.md), or use a repository of your own; either works. Make it **public**: judges open it, and organizers review the code for anything that calls a service outside the board.
- A link to your project on the **[Arduino Project Hub](https://projecthub.arduino.cc/)**. Post your entire project there, the write-up and the code, not only a link back to GitHub. Posting needs an Arduino account, so sign in before the window opens.

Have both links ready before 8:00 p.m.

## Scoring

| Weight | Criterion | What judges look for |
|---|---|---|
| 25% | **Edge-native value** | Why is this better, or only possible, on-device? |
| 20% | **Technical execution** | Reliability, integration quality, local operation |
| 20% | **Originality** | A distinct insight, not another generic chatbot |
| 15% | **Real-world usefulness** | A clear user, a real need, a plausible next step |
| 10% | **Performance / efficiency** | Latency, memory, endurance, resource awareness |
| 10% | **Demo quality** | A concise, clear offline demonstration |

## The first question

Expect this question: **"Why should this not simply be a cloud API call?"**

Prepare an answer that names a specific constraint. Examples: the network is unavailable, the data is sensitive, the reaction must happen in under a second, or the marginal cost has to stay flat at scale. Being on-device is not an answer by itself.

## Demo format

- Two minutes per team, plus one judge question.
- **Turn the board's Wi-Fi off in front of the judge**, unplug any Ethernet cable, then run the core workflow:

  ```bash
  # board shell, from the UART console or a USB-C link
  sudo nmcli radio wifi off
  nmcli -p device              # show the judge that Wi-Fi is no longer connected
  ```

  Run it from a session that does not depend on Wi-Fi. Over SSH on Wi-Fi, the command ends your own session; the micro-USB UART console you used for setup needs no network. `sudo nmcli radio wifi on` restores Wi-Fi afterwards. Rehearse this once before judging.
- The core workflow must keep running offline. An isolated USB-C link for SSH and a board-hosted app web UI is allowed, with no laptop internet sharing/forwarding; see [display and USB-C access](offline-readiness.md#display-and-usb-c-access). Organizers may also switch off the venue Wi-Fi.
- Show local inputs, decisions, executed actions, and errors from the app's log.
- Prepare a visible timer, local sample data, and a backup recording.

## What to measure and show

| Metric | How | Why it matters |
|---|---|---|
| Time-to-first-token | Benchmark or timed stream; distinguish generated reasoning from answer content | Responsiveness |
| Decode tokens/s | Benchmark or usage-based streamed estimate; do not count chunks as tokens | Generation efficiency |
| Peak process memory | `/usr/bin/time -v`; track system/device memory separately | Footprint |
| Decision-gate latency | Time the app's actual rule or optional d1 questions on the board | Fits the observation interval |
| End-to-end loop time | Timing in the app's flushed JSONL | Includes decision, action, and explanation work |
| Network-off run | Disconnect all external uplinks and demonstrate the core workflow; any USB-C control/UI link must remain isolated | Offline operation |
| Decision log | Local timestamps, decisions, executed actions, and errors | Explains what the app did |

For timing and footprint guidance, see [`runtimes.md`](runtimes.md) for `geniex-bench` and [`developer-guide.md` §10](developer-guide.md#10-measuring-performance).

Use the app's own workload and selected model/precision when collecting numbers. Keep the shared documentation as a reference; put project-specific results in the app's README.
