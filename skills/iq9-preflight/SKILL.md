---
name: iq9-preflight
description: Check Dragonwing IQ-9075 readiness for the full reference stack, a chosen cached generator without d1, or hardware only. Profiles check GenieX v0.10.0, NPU access, selected cached model, optional d1 venv/pinned snapshot, disk, memory, thermal readings, and network state. Use at the start of a session, before building or demoing, when something "suddenly stopped working", or when the user asks "is my board ready".
compatibility: Run on the IQ-9075 itself (bash, coreutils, curl, python3). From a laptop, run it over SSH.
metadata:
  version: "0.2"
---

# IQ-9075 preflight

Run this at the start of **board work**. It only reads, never changes anything, and never downloads. For laptop-only documentation work without a supplied SSH host, report that board preflight was not run; do not test the laptop as if it were the board.

Choose the profile for the app. The default checks the full reference example stack, not competition eligibility: other LFM3-family models are welcome and d1 is optional.

```bash
skills/iq9-preflight/scripts/preflight.sh --json                         # full reference stack
skills/iq9-preflight/scripts/preflight.sh --profile generator --json     # generator, no d1
skills/iq9-preflight/scripts/preflight.sh --profile generator --model 'cached-name:precision' --json
skills/iq9-preflight/scripts/preflight.sh --profile board --json         # hardware checks only
```

If the agent runs on a laptop, not on the board, use SSH. Both commands below are run from the repo root:

```bash
ssh "$IQ9_HOST" 'bash -s -- --json --profile reference' < skills/iq9-preflight/scripts/preflight.sh
```

## Reading the result

- `FAIL` means a check required by the **selected profile** failed. `WARN` needs investigation; neither `ready: true` nor a WARN guarantees the app works end to end. The JSON records `profile`, `model`, and individual checks.
- Show suggested fixes. **Ask before** system changes, any `geniex pull` (including local imports), `fetch_d1.py`, model deletion, or runtime installation. Inspect `geniex list`, existing local weights/snapshots, and `df -h /` first. A missing cache registration does not prove the weights are absent.
- The external HTTPS probe is informational. A failed probe may mean an unreachable endpoint, not an offline board; neither result proves a physical network-off rehearsal.

| Check | What it means when it isn't ok |
|---|---|
| `display` WARN | Always emitted in every profile: monitor compatibility is not checked. This is the Adreno setup warning, not a detected display failure; see the display guidance below |
| `npu-nodes`, `npu-access` | Inspect current drivers/access and follow developer-guide section 3.2 with approval. Do not install/update Adreno as a generic NPU fix or infer CPU execution from this check alone |
| `geniex` WARN | The version differs from v0.10.0, so the LFM3 path may not hold. Don't change versions between rehearsal and demo |
| `model:<selected name>` | The selected model is not registered. Inspect local weights and cache before asking about an import/download |
| `d1-venv`, `d1-snapshot` | Required only by the reference profile. Follow `examples/system-one-decision/README.md` if this app uses d1 |
| `server` WARN | Normal if nothing has started it yet. See the `iq9-geniex-lfm` skill |
| `disk` WARN | Under 10 GB free. Run `geniex list` and ask the user before removing anything |

## Display and control path

Organizers report that the current Adreno APT update causes a GPU-driver issue with external monitors. For a monitor setup, **remove/roll back that update** using the organizers' board-specific procedure and owner approval; do not blindly purge packages or reinstall/update `qcom-adreno1`. See [Developer Notes](../../README.md#external-monitors-and-headless-setups). Every profile includes a `display` WARN in both text and JSON output, even when all required checks pass. This does not fail the run or mean a broken monitor was detected: the script does not test the display or identify affected package versions. `ready: true` is not proof of monitor compatibility or recovery.

The upstream `install_ppa_pkgs.sh` linked from the developer guide is **not adapted for this event's monitor issue**. Do not run it unchanged for a monitor setup until organizers confirm the graphics changes to omit or roll back. No event-specific patched installer is provided; see [driver setup](../../docs/developer-guide.md#32-driver-packages).

SSH is unaffected. An isolated, configured USB-C network link can carry SSH and a board-hosted app web UI during the network-off demo. Test it before cutting external uplinks, disable laptop internet sharing/forwarding, and keep the inference listener on loopback. See [display and USB-C access](../../docs/offline-readiness.md#display-and-usb-c-access).

## Deeper checks (on request)

- **Full d1 check:** from the repo root, run `~/.venvs/d1/bin/python examples/system-one-decision/check_env.py`.
- **Reference smoke test:** `./starter/run.sh`. It uses both reference models; measure elapsed time rather than promising a fixed duration.
- **Is the generator using the NPU?** In a separate terminal, run `skills/iq9-geniex-lfm/scripts/serve.sh run`, send a capped request, then inspect `serve.sh status` and the current server log. The dated reference run showed `Using 1 device(s): HTP0`; a missing line is a reason to investigate, not proof of CPU fallback. Do not silently switch to CPU.
- Latest dated reference checks: [README Developer Notes](../../README.md#developer-notes). They do not verify the board's current state or another model.
