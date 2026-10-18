---
name: iq9-offline-rehearsal
description: Get a Dragonwing IQ-9075 app ready for the network-off demo and rehearse it. Covers a static audit for repo-ID loads, URLs, CDN assets, telemetry, and install-time fetches; staging models, wheels, and archives while the network is up; the network-off run; and evidence for the judges. Use before the network is cut, at T-1, when the user says "offline", "network cut", "airplane mode", "rehearsal", or "will this work without internet".
compatibility: Audit script runs anywhere with Python 3. The rehearsal runs on the IQ-9075.
metadata:
  version: "0.1"
---

# Offline rehearsal

The event ends with the network removed. A project that only works online scores zero on the main constraint. The checklist and the common failures are in `docs/offline-readiness.md`. This skill is the procedure.

## 1. Static audit (run on the app's code)

```bash
python3 skills/iq9-offline-rehearsal/scripts/offline_audit.py apps/<name>
```

| Finding | Fix |
|---|---|
| `hub-id` (error) | Load from a local path: `~/models/d1-3B`, or the model name in the GenieX cache through `geniex serve` |
| `pull` (error) | Move `geniex pull`, `pip install`, `npm install`, and `apt install` into a setup step that runs before the cut. Never at runtime |
| `cdn` (error) | Vendor the JS and CSS into the app, and serve them locally |
| `url` (warn) | Every non-localhost URL has to be optional, or gone. Check each one |
| `telemetry` (warn) | Disable it or remove it |
| `env` (info) | Add `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` to the launch script |

It's a static check, so it misses dependencies that phone home on their own. Step 3 catches those.

## 2. Stage everything while the network is up

Check `df -h /` first. Pull only what is missing, and ask before pulling anything over 1 GB.

- [ ] Run `geniex list` and confirm every model the app uses is cached. Run `geniex version` and confirm v0.8.0.
- [ ] Confirm `~/models/d1-3B/REVISION` reads `051bcc464b01…` (run `skills/iq9-preflight/scripts/preflight.sh`).
- [ ] Download wheels for an offline reinstall: `~/.venvs/d1/bin/python -m pip download -r <app>/requirements.txt -d ~/wheels`, then test `pip install --no-index --find-links ~/wheels -r <app>/requirements.txt` in a scratch venv.
- [ ] Keep the GenieX archive `geniex-cli-linux-arm64-v0.8.0.tar.gz` and `install.sh`.
- [ ] Put sample and recorded data for the demo on the board (in case a sensor fails).
- [ ] Clone this repo onto the board, so the docs and skills are there offline.

## 3. Network-off run (the real test)

The agent can't unplug the cable for the user, and over SSH it would cut its own connection. Have the user do this step on the board, or run a script that leaves the network down for a set time:

1. The user unplugs Ethernet and turns off Wi-Fi. Check: `curl -sS -m 5 https://huggingface.co` must fail.
2. Cold start: reboot, or `skills/iq9-geniex-lfm/scripts/serve.sh restart`, then start the app with its normal launch command.
3. Run the core loop end to end for at least 10 minutes, including at least one alert or action.
4. Collect evidence: the app's JSONL log, `skills/iq9-demo-prep/scripts/collect_metrics.sh`, and a screen or phone recording.
5. Plug the network back in. Record anything that failed in the app's README, along with its fix.

If the user wants a scripted cut on the board, give them this and have them run it locally, not over SSH:

```bash
IF=$(ip route | awk '/default/ {print $5; exit}'); sudo ip link set "$IF" down; sleep 900; sudo ip link set "$IF" up
```

## 4. Recovery drill (T-1)

- A second generator you can switch to with one flag (for example `--llm LiquidAI/LFM2-1.2B-Tool-GGUF:Q4_0`).
- A recorded decision log and a recorded video, in case the live demo fails.
- Know where the log lives, and have a one-line command ready to show its last entries.
- `serve.sh restart` memorised, for the zero-token state.
