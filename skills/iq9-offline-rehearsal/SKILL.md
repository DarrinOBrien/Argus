---
name: iq9-offline-rehearsal
description: Get a Dragonwing IQ-9075 app ready for the network-off demo and rehearse it. Covers a static audit for repo-ID loads, URLs, CDN assets, telemetry, and install-time fetches; USB-first model copying/imports and staging wheels/archives before the cut; the network-off run; and evidence for the judges. Use before the network is cut, at T-1, when the user says "offline", "network cut", "airplane mode", "rehearsal", or "will this work without internet".
compatibility: Audit script runs anywhere with Python 3. The rehearsal runs on the IQ-9075.
metadata:
  version: "0.3"
---

# Offline rehearsal

The event ends with the network removed. A project that only works online scores zero on the main constraint. The checklist and the common failures are in `docs/offline-readiness.md`. This skill is the procedure. Offline loading settings with the network still connected are **not** a network-off rehearsal.

## 1. Static audit (run on the app's code)

```bash
python3 skills/iq9-offline-rehearsal/scripts/offline_audit.py apps/my-agent
```

| Finding | Fix |
|---|---|
| `hub-id` (error) | Load from a local path: `~/models/d1-2B`, or the model name in the GenieX cache through `geniex serve` |
| `pull` (error) | Move `geniex pull`, `pip install`, `npm install`, and `apt install` into a setup step that runs before the cut. Never at runtime |
| `cdn` (error) | Vendor the JS and CSS into the app, and serve them locally |
| `url` (warn) | Check each non-localhost URL: remove external runtime dependencies or make them optional. An isolated USB-C board address may be local-only; verify its route and prefer SSH forwarding to localhost |
| `telemetry` (warn) | Disable it or remove it |
| `env` (info) | Add `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` to the launch script |

This is a heuristic static check, not proof of offline operation. Inspect runtime imports/dependencies and each warning. Finding an offline environment variable in text does not prove it is active; enforce `local_files_only=True` for Transformers and offline/telemetry settings before imports. Step 3 tests the whole app.

## 2. Stage everything before the network cut

Inspect `geniex list`, existing local model directories, and `df -h /` first. **Ask whether the participant has the supplied USB model drive and USB-C dongle/adapter.** Prefer compatible USB/local assets over network downloads; follow [USB model staging](../../docs/developer-guide.md#usb-model-drive-copy-never-move). Copy/import the selected full asset set onto board storage; **never move files, delete the USB source, or depend on that removable drive at runtime**. Verify the copy and registration, then test startup without the model drive attached after approved safe ejection.

**Ask before every model copy, `geniex pull` (including local imports), `fetch_d1.py`, installation/system change, mount/eject, or deletion**, regardless of size. Never re-pull cached models. Network access is needed only for separately approved missing software/assets, not for USB copies. Run long staging jobs in a separate terminal, retain logs, and verify exit status.

- [ ] Run `geniex list` and confirm every model the app uses is cached. Run `geniex version` and confirm v0.10.0.
- [ ] **If the app uses d1**, confirm `~/models/d1-2B/REVISION` reads `10e7671d44e4…`. Otherwise use `preflight.sh --profile generator --model <cached-name:precision>` (or `--profile board` without a generator). Reference defaults are not mandatory models.
- [ ] If needed, with approval, download wheels for an offline reinstall: `~/.venvs/d1/bin/python -m pip download -r <app>/requirements.txt -d ~/wheels`, then test `pip install --no-index --find-links ~/wheels -r <app>/requirements.txt` in a scratch venv.
- [ ] Keep the GenieX archive `geniex-cli-linux-arm64-v0.10.0.tar.gz` and `install.sh`.
- [ ] Put sample and recorded data for the demo on the board (in case a sensor fails).
- [ ] Stage this repo's docs and skills on the board. Back up files being replaced; do not use destructive sync to remove unrelated files.
- [ ] Stage only the app's needed models/assets. External sensors are optional and not supplied; keep local sample/recorded inputs for any hardware-dependent demo.
- [ ] Choose and test the display/control path. External monitors require removing/rolling back the current Adreno APT update with the organizers' procedure and owner approval; do not install/update `qcom-adreno1` as a generic NPU fix. SSH is unaffected. See [Developer Notes](../../README.md#external-monitors-and-headless-setups).
- [ ] For headless SSH/web UI, configure and test the isolated USB-C network link and port forwarding before the cut. Disable laptop internet sharing/bridging/forwarding, keep UI assets local and inference on the board, and leave GenieX on loopback. See [USB-C access](../../docs/offline-readiness.md#display-and-usb-c-access).

## 3. Network-off run (the real test)

**Get explicit permission before any network cut or reboot.** Cutting the uplink carrying SSH can cut your session. Use a tested local console or an isolated USB-C SSH link and a restoration plan. Inspect all external uplinks, including any USB route through a laptop; the isolated local control/UI link may remain, without internet sharing/forwarding.

1. The user unplugs Ethernet and turns off Wi-Fi. Inspect other external routes and laptop sharing/forwarding settings. Check: `curl -sS -m 5 https://huggingface.co` must fail; that alone is not proof of isolation.
2. Cold start: with approval, stop the owned generator and run `skills/iq9-geniex-lfm/scripts/serve.sh run` in a separate terminal, then start the app normally. A reboot is optional and needs approval. Do not silently switch a foreground server to a detached restart.
3. Run the core loop end to end for at least 10 minutes, including at least one alert or action. For a USB-C web UI, exercise the laptop browser with external uplinks cut and confirm local assets load and inference stays on the board.
4. Collect evidence: the app's JSONL log, `skills/iq9-demo-prep/scripts/collect_metrics.sh`, and a screen or phone recording.
5. Plug the network back in. Record anything that failed in the app's README, along with its fix.

Do not use a generic one-interface `ip link ... down` one-liner: it can leave another external uplink active, cut the isolated control link, or fail to restore connectivity. A scripted cut requires an approved, board-specific interface list, a tested local console or isolated USB-C control link, and a tested restoration plan. A failed external `curl` is supporting evidence, not proof that every external uplink is disconnected.

## 4. Recovery drill (T-1)

- If an already-cached, previously tested stack is useful, keep it as an optional rollback. Do not require participants to download another model or delete their chosen models.
- A recorded decision log and a recorded video, in case the live demo fails.
- Know where the log lives, and have a one-line command ready to show its last entries.
- Know how to safely stop and relaunch the owned foreground server. Keep the recovery step for persistent failures.
