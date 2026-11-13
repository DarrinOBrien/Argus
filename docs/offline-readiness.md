# Offline Readiness

The final demo runs with the network removed. Stage everything the app needs on the board and rehearse its normal startup and core workflow offline.

## Disk first

Before downloading or importing assets:

```bash
df -h /
if command -v geniex >/dev/null; then geniex list; fi  # not required for ZETIC
```

Check local model directories as well as the cache: a missing cache entry does not mean the weights are absent. Use the supplied USB model drive before downloading, following [USB model staging](developer-guide.md#usb-model-drive-copy-never-move). Reuse registered models without re-importing.

For planning, the LFM3-1.7B QAD-Q4_0 weights use about **1.05 GB**; the optional d1-2B Transformers snapshot uses about **3.84 GB**. For another model or precision, use its exact artifact's file list and inspect the local files rather than carrying over these estimates.

For ZETIC, inspect the local SDK and selected package directories instead of GenieX registration. Follow the [Ixian SDK and IQ9 package recipe](../examples/zetic-lfm/README.md#stage-once-with-approval), with matching runtime libraries, complete package assets, checksums, and fixtures. Its `v73` generator packages are larger than the reference GGUF; do not use the GGUF size as their disk estimate.

Budget for the full set of matching weights, model code, tokenizer, prompt template, and any modality assets (such as vision projectors or audio tokenizer/vocoder files). Also allow for environments, recovery wheels, runtime archives, UI assets, sample data, and extra copies made during local imports. Stage only what the app needs.

Weight-file size is not runtime RAM usage: host RAM and device buffers are separate budgets. See [Measuring performance](developer-guide.md#10-measuring-performance) for app-level timing and memory checks.

Ask before deleting files or running `geniex remove` or `geniex clean`. Do not edit cache metadata to free space.

## Before the network goes down

### Software

- [ ] The chosen runtime is installed; the reference GenieX version is v0.10.0.
- [ ] NPU driver packages and device permissions are set up for the generator.
- [ ] The app's Python environment and other dependencies are installed.
- [ ] Runtime installers, matching archives, and any recovery wheels are available locally if needed.
- [ ] UI JavaScript, CSS, fonts, and other assets are served locally rather than from a CDN.
- [ ] No installation or model download happens when the app starts.

For an offline Python reinstall, stage wheels for the app's requirements and try `pip install --no-index --find-links <wheel-directory>` in a scratch environment before relying on it. Some packages need additional runtime assets; stage those too. Do not replace a working environment unnecessarily.

### Models

- [ ] Every generator model used by the app is on board storage: registered in the GenieX cache for that runtime, or a complete verified local SDK/package directory for ZETIC.
- [ ] USB-sourced files have been copied and checked against source sizes/checksums; no runtime path/symlink points back to removable media. After approved safe ejection, startup works without the model drive attached. A storage dongle is not a USB-C network/control link.
- [ ] Its matching tokenizer, prompt template, projector, and any other required modality assets are present.
- [ ] If using reference CPU d1, the full pinned snapshot is at `~/models/d1-2B`; its `REVISION` matches `10e7671d44e4`. A ZETIC d1 app uses its separate native package and records that package/SDK revision instead.
- [ ] Model code has been reviewed before `trust_remote_code=True` is used.
- [ ] Model licenses have been read.

Stage only what this app needs. LFM3-1.7B and d1-2B are reference defaults, not mandatory models.

### Data and docs

- [ ] The repo's docs, examples, and skills are available on the board.
- [ ] Local sample inputs cover the demo workflow.
- [ ] If using a decision threshold, calibration and held-out data are available locally.
- [ ] Any brought sensors have local drivers and a sample-data fallback. External sensors are optional and not provided.

Back up board files being replaced when copying updates. Avoid destructive sync that removes unrelated files.

## Code rules

- **Local model loads:** Transformers loads a snapshot directory with `local_files_only=True`; GenieX requests use already-registered cached IDs; ZETIC opens local model package directories with a staged SDK.
- **Offline settings:** set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and `HF_HUB_DISABLE_TELEMETRY=1` before local Transformers imports.
- **No external runtime dependencies:** no downloads, package installs, telemetry, cloud services, or remote UI assets in the core workflow. Loopback calls to the local inference server are allowed.
- **Bounded calls:** cap LFM requests, validate output, and log errors without crashing the monitor loop.

The [static audit](../skills/iq9-offline-rehearsal/scripts/offline_audit.py) helps locate likely network dependencies:

```bash
python3 skills/iq9-offline-rehearsal/scripts/offline_audit.py apps/my-agent
```

Review each finding and the dependencies it cannot inspect. A static scan is not a substitute for running the app with its external uplinks disconnected.

## Display and USB-C access

- **At the event:** you turn the board's Wi-Fi off in front of the judge with `sudo nmcli radio wifi off` ([demo format](judging.md#demo-format)), and organizers review submitted code for calls that leave the board. They may also switch off the venue Wi-Fi. When Wi-Fi goes off, SSH over it goes too, so set up and test your control path while Wi-Fi is still on: the USB-C link below, or the micro-USB UART console you used for setup, which needs no network.
- **External monitor:** read the [monitor issue](../README.md#external-monitors-and-headless-setups) first, and test the display before the cut.
- **Headless SSH/web UI:** SSH is not affected by the monitor issue. A configured **USB-C network link** between a laptop and the board is allowed for local control and an app web UI during the network-off demo. A USB-C cable alone does not establish networking; stage and test the link and SSH while the external network is still available.
- **Keep it isolated:** disable laptop internet sharing, bridging, and forwarding to external networks; disconnect/disable external uplinks and verify that neither the app nor the board can reach internet services through the laptop. The browser must use local UI assets, not CDNs or cloud APIs. All inference stays on the board.

Prefer SSH port forwarding over exposing the inference server or app listener. For an existing app web server listening on the board's `127.0.0.1:8000`, run this in a separate laptop terminal (replace `8000` with the app's actual port and set `IQ9_HOST` to the board's USB-link SSH host):

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8000:127.0.0.1:8000 "$IQ9_HOST"
```

Open `http://127.0.0.1:8000` in the laptop browser. This command forwards an existing server; it does not configure USB networking or start the web app. Keep GenieX bound to `127.0.0.1:18181`, and have the app call it locally on the board. Test the browser workflow after the external network is cut, including cold startup and local asset loading.

## Rehearsal: network-off test

Get explicit approval before a network cut or reboot. Use a tested local console or an isolated USB-C SSH session; disconnecting the uplink carrying SSH can also disconnect your control session. Have a tested restoration plan, including after a reboot if one is planned.

1. Disconnect Ethernet, disable Wi-Fi, and inspect other possible external uplinks, including USB networking. An isolated USB-C control/UI link may remain, but must not provide internet access via the laptop. Inspect routes and laptop sharing/forwarding settings; an external `curl` failure alone does not establish isolation.
2. Start the generator from a stopped state in a separate terminal, then launch the app using its normal command. For the one-shot ZETIC wrapper, launch the CLI through the wrapper normally; there is no server to restart. A reboot is optional, not required.
3. Send a capped request and verify usable output and current-request device evidence: the current GenieX server's `HTP0` log, or the ZETIC wrapper's Hexagon v73/two-NSP evidence. ZETIC d1 needs its own Decision API/device checks; the generator wrapper does not validate it. Investigate missing device output rather than assuming CPU fallback.
4. Run the core workflow for as long as the schedule allows (10 minutes is a good target; a few minutes is realistic during the event), including an event that triggers an explanation or allowlisted action. Exercise local UI assets and input handling too.
5. Inspect the app's flushed JSONL for decisions, executed actions, usable explanations, and errors. Check responsiveness and memory for the intended workload.
6. Restore external networking through the tested local console or isolated USB-C control session when the rehearsal is complete.

Do not use a generic one-interface network-cut script. A scripted cut needs an approved interface list and a restoration plan.

## Recovery drill

- Keep local sample data, a recorded demo, and a copy of the decision log.
- Know the normal launch command and where errors are logged.
- Know how to stop and relaunch your foreground server.
- An already-cached alternative model can be an optional fallback; do not download a second stack just for this checklist.

## Common failures

| Failure | What to inspect | Next step |
|---|---|---|
| Online startup works but offline startup fails | Model paths, install steps, remote assets, dependency network calls | Stage missing assets and remove runtime fetches |
| Offline reinstall fails | Missing wheels or package-specific runtime files | Stage and exercise recovery before the cut |
| Generator is slow or device output is missing | Current log, compute configuration, drivers, permissions | Diagnose NPU access; do not silently switch to CPU |
| No space left on device | Cache, local snapshots, archives, duplicate copies | Ask before removing unused files |
| Server request fails | Listener, model ID, response body, current server log | Correct configuration or safely relaunch the owned server |
| Empty LFM answer or zero completion tokens | Answer/reasoning fields, cap, prompt uniqueness | Retry once with a fresh tag; log persistent failure |
