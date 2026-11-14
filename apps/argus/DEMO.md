# Argus: two-minute demo

Format from [docs/judging.md](../../docs/judging.md#demo-format): two minutes, one judge question, Wi-Fi turned off in front of the judge, then the core workflow running offline with the log as proof.

Every command says where it runs. **Board** means the board's shell. **Laptop** means the laptop's own terminal.

## Pick the path before you walk up

When Wi-Fi goes off, anything carried over Wi-Fi dies with it: an SSH session, the port forward, and an Argus process that was started from that SSH session.

- **Path A, page on the laptop.** Needs an isolated USB-C network link between laptop and board (no laptop internet sharing, bridging, or forwarding), set up and tested with Wi-Fi off. The judge sees the page.
- **Path B, serial console only.** Needs nothing but the micro-USB UART console. The judge sees the live log on the console. Use this if the USB-C link is not working and tested.

Decide now. Do not find out at the table.

## Before you walk up

Do these while Wi-Fi is still on.

- [ ] **Serial console open and logged in** as `ubuntu` on the board's Linux UART console. Run `sudo -v` once so the password prompt does not eat demo time.
- [ ] **Ethernet unplugged** from the board.
- [ ] **Argus started from a session that survives**, from the repository root. On the serial console, start it in the background so the console stays free for the Wi-Fi commands:

  ```bash
  # board, serial console
  python3 apps/argus/argus.py &
  ```

  Leave `--time-scale` at its default. A small value makes "step is running long" alerts fire within seconds and clutters the demo.
- [ ] **Path A only: page open** on the laptop at `http://127.0.0.1:8000`, forwarded over the isolated USB-C link:

  ```bash
  # laptop, separate terminal; IQ9_HOST is the board's address on the USB-C link
  ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8000:127.0.0.1:8000 "$IQ9_HOST"
  ```

- [ ] **Listening on.** Path A: press **Listen** on the page so it reads "on". Path B: use the command in [Path B](#path-b-serial-console-only).
- [ ] **Camera framed.** Tray in the left zone, patient area in the right zone, both fully inside their squares. Even lighting, no glare.
- [ ] **Props on the tray:** the item types in `protocols/appendectomy.json`, currently swabs, a scalpel, forceps, and a probe. Patient area empty.
- [ ] **One full dry run with a stopwatch**, with these props, Wi-Fi off, including the alarm. Every model request reloads the model, and the flow below makes six vision requests and two speech requests. If the dry run does not fit in two minutes, apply the [cuts](#if-the-dry-run-is-too-long).
- [ ] **Timer visible** (phone stopwatch on the table).
- [ ] **Backups on the laptop:** a screen recording of a good run, and a copy of that run's `argus-log.jsonl`.
- [ ] **Roles agreed:** one person speaks and drives the console and page, one person moves the items.

## The script (Path A)

| Time | Say | Do |
|---|---|---|
| 0:00-0:20 | "Roughly one operation in every 5,500 to 7,000 ends with something left inside the patient, and about two thirds of the time it is a swab. The count is done by hand, out loud, at the end of a long case. Argus is a second counter. It watches the tray and the patient, listens to the team, and runs entirely on this board, because an operating room's audio and video cannot leave the room and the alarm cannot depend on a network." | Point at the camera, the tray, the board. Start the timer. |
| 0:20-0:35 | "So let me turn the network off." | **Board, serial console:** type the two commands below. Point at the Wi-Fi row in the output. |
| 0:35-0:50 | "Count in." | Press **Count in**. Both zones are counted; the Inventory panel shows the baseline and the first protocol step starts. |
| 0:50-1:05 | "10 milligrams propofol." | Say it toward the camera's microphone and wait: audio is taken in 6-second clips. The Drug log shows propofol, 10 mg, and the step list moves to induction of anesthesia. |
| 1:05-1:20 | "The model only proposes counts. Code keeps the inventory." | Move one swab and the forceps into the patient area. Press **Scan**; counts change in both zones. Then put the forceps back on the tray and **hide the swab** (palm it, out of both zones). |
| 1:20-1:40 | "Closing." | Say it clearly. Argus counts out and compares with count in. Two alerts appear: the skipped steps, then the critical one: one swab missing, last seen in the patient area, do not close. Let it sit for a second. "It also caught that we skipped three steps." |
| 1:40-1:55 | "Every proposal, decision, and error is in a local log, with timing for each model request." | Tick **show model rows** in the Event log; point at a model row and at the Performance panel. Only quote numbers that are in the README's Measurements table. |
| 1:55-2:00 | "Next: keep the model loaded between requests, count continuously, add colour, and a clinician-reviewed protocol library. The alarm stays in code." | Stop the timer. |

Wi-Fi off, in front of the judge:

```bash
# board, from the serial (UART) console - never from SSH over Wi-Fi
sudo nmcli radio wifi off
nmcli -p device              # show the judge that Wi-Fi is no longer connected
```

What the alarm should read (seen in a laptop `--mock` run; not yet seen on the board):

```text
high      Step skipped: Incision and port placement, Dissect and ligate appendix, Remove appendix.
critical  Count out does not match. 1 swab missing, last seen in the patient area at HH:MM:SS. Do not close.
```

Variations you may see, all correct behaviour:

- No **Scan** between count in and closing: the alert says the swab was "never seen leaving the tray".
- Items still in the patient area at closing: the alert also lists each as "still in the patient area".

Keep these true while speaking:

- Do not quote a latency, accuracy, or memory number that is not in the README's Measurements table. If it is still empty, say the numbers are on the Performance panel as single runs and medians are still being collected.
- Do not say "runs entirely on the NPU". Say "the model runs on the Hexagon NPU through the vendor runtime". Some work stays on the CPU.
- If a count on screen is wrong, say so. The log shows what the model proposed and what code decided; that is the point.

### If the dry run is too long

Cut in this order:

1. Press **Closing** instead of saying it (saves a 6-second clip and a speech request). Keep "10 milligrams propofol" as the one spoken line.
2. Drop the mid-case **Scan** (saves two vision requests). The alarm then says "never seen leaving the tray".
3. Type "10 milligrams propofol" into the text box and press **Send** instead of saying it.

## Path B: serial console only

Same story, same timings, with the page replaced by commands on the board and the log on the console. Argus is already running in the background from the checklist.

```bash
# board, serial console - before the judge arrives
curl -s -X POST -H 'Content-Type: application/json' -d '{"on": true}' http://127.0.0.1:8000/api/listen
tail -f apps/argus/run/argus-log.jsonl | grep --line-buffered -v '"kind": "model"' &
```

```bash
# board, serial console - during the demo
sudo nmcli radio wifi off
nmcli -p device
curl -s -X POST http://127.0.0.1:8000/api/count_in       # "Count in"
# say "10 milligrams propofol"; move items
curl -s -X POST http://127.0.0.1:8000/api/scan           # after moving items into the patient area
# hide the swab; say "Closing", or:
curl -s -X POST http://127.0.0.1:8000/api/closing
# latency: the last model requests, with timings and device evidence
grep '"kind": "model"' apps/argus/run/argus-log.jsonl | tail -n 3
```

If speech is not picked up, type the statement instead:

```bash
# board
curl -s -X POST -H 'Content-Type: application/json' -d '{"text": "10 milligrams propofol"}' http://127.0.0.1:8000/api/say
```

These calls go to the board's own loopback address. Rehearse Path B once; it has only been exercised against the laptop mock.

## The first question: "Why is this not a cloud API call?"

Short answer, two sentences:

> The inputs are a camera over an open patient and a microphone on the surgical team, and that audio and video cannot leave the room. The alarm at closing is the whole product, so it has to fire whether or not the hospital network is up, and it does, because the count, the rules, and the log are all on this one board.

If they push:

- **Privacy.** No frame, clip, or transcript is sent anywhere. There is no upstream service to breach or misconfigure.
- **Reliability.** Theatres are shielded and their networks are segmented and locked down. A counter that goes blind when the link drops trains the team to ignore it.
- **Reaction.** The decision to alarm is code on the board working from local counts. It never waits on a link. Be straight about speed: each model request currently reloads the model, and that is the first thing to fix.
- **Cost.** The microphone listens for the whole operation, every operation. Per-request cloud billing grows with every minute of surgery; one board per room is a flat cost.
- **Trust.** The model proposes counts and transcripts. Code validates them and decides, and the log shows both, so a wrong model answer is visible instead of silent.

## Backup plan

In order. Move down the list as soon as something is not working; do not debug in front of the judge.

1. **Speech is not recognised.** Do not repeat it more than once. Type the line into the text box and press **Send**, or press **Closing**. The same code path handles typed and spoken statements, and the log marks which was used.
2. **The page is unreachable after Wi-Fi goes off.** Switch to [Path B](#path-b-serial-console-only) on the serial console. Argus is still running on the board. Say: "the page was forwarded over a link that is now down; this is the same log, straight from the board."
3. **A count is slow or wrong.** Keep going and narrate it. Rejected proposals and errors are logged as data and the closing check still runs. Do not restart mid-demo.
4. **Camera or model will not start.** Run the simulated path and label it as simulated:

   ```bash
   # board or laptop
   python3 apps/argus/argus.py --mock
   ```

   Say: "this is simulated camera and model input; the inventory, protocol, dose, and alarm logic is the real code."
5. **Nothing runs.** Play the screen recording of a good run and open the saved `argus-log.jsonl` from that run. Say that it is a recording.

After judging, restore Wi-Fi:

```bash
# board, serial console
sudo nmcli radio wifi on
```

## What this demo does not prove

- It is one staged scenario with four item types on a clean tray, not an evaluation of counting accuracy.
- The protocol and dose limits are demo values, not clinical guidance.
- Numbers on the Performance panel during the demo are from a handful of requests. Medians and sample counts belong in the README's Measurements table.
