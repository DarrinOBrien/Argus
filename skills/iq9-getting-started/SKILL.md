---
name: iq9-getting-started
description: Guide a participant from board access and setup internet to a useful local LFM response on the Dragonwing IQ-9075. Covers Ubuntu UART login, nmcli Wi-Fi setup, Ethernet, SSH, read-only inventory, approved USB-first model copying/imports, stale APT package-list recovery, and NPU verification. Use for getting started with this repo, preparing an IQ9, missing SSH or internet, or an unknown installed stack. d1 is optional.
compatibility: Laptop with a serial terminal/SSH client, or a shell directly on the IQ-9075 running Ubuntu 24.04 aarch64. Initial access and network steps may need participant interaction. GenieX is not required to begin.
metadata:
  version: "0.4"
---

# Get started on the IQ-9075

This is a guided workflow, **not an unattended installer**. Read [AGENTS.md](../../AGENTS.md) and the [developer guide](../../docs/developer-guide.md). Detailed access instructions and event login are in [section 0](../../docs/developer-guide.md#0-board-access-and-internet-for-setup), adapted from Qualcomm's **Ubuntu** [device setup page](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device). Do not substitute the separate Qualcomm Linux image's accounts, ADB requirements, or package recipes.

## 1. Establish access with the participant

Ask only what is not already known:

- Is the agent on the laptop or directly on the board? Which laptop OS?
- Is there already a working board shell or a known SSH host?
- If not, is a data-capable micro-USB UART cable available? What serial tools/ports are present?
- Which approved Wi-Fi network or Ethernet connection can the board use for setup?
- **Do you have the supplied USB model drive and your USB-C dongle/adapter?** Is the drive connected to the board or the laptop? Teams receive model media; ask before proposing model downloads. A storage dongle does not establish USB-C networking.

Reuse working access. Otherwise guide the participant through the [UART steps](../../docs/developer-guide.md#01-open-the-uart-console-if-needed): Main Domain/Converter B (second functional FTDI port), 115200 baud, and event `ubuntu` login. Identify the actual port; do not hardcode another board's device node. Keep the serial terminal separate from the agent's busy terminal. Never seize a port or kill another user's session.

If the agent cannot operate the serial terminal, provide short manual steps and ask for non-secret output. Do not claim a command was executed just because it was suggested. Ask before laptop tool/driver installations. If no control path is available, stop at access troubleshooting rather than running board checks on the laptop or assuming a failed flash.

**Checkpoint:** a confirmed shell on the intended board. Inspect architecture and OS; initial access does not require GenieX, model weights, or d1.

## 2. Inspect and establish setup internet

Follow [network setup](../../docs/developer-guide.md#02-inspect-and-connect-the-board) in the board shell. Inspect interfaces, addresses, and routes before changing anything. Use the existing connection if suitable.

If Wi-Fi is needed, ask for the chosen SSID and approval to configure it. Have the participant enter the Wi-Fi password privately using `sudo nmcli --ask dev wifi connect 'SSID'` in UART; do not request or record it in chat. The sudo password and Wi-Fi password are different. Ethernet is an alternative when available; neither a USB cable nor a laptop connection implies internet access.

Check [board-side DNS and bounded HTTPS](../../docs/developer-guide.md#03-check-internet-access-from-the-board) to the required setup sources. Report link/address, route, DNS, HTTP/TLS status, and missing diagnostic tools separately. A successful laptop request, one failed endpoint, or preflight's `ready` flag does not establish board online readiness. Do not bypass TLS or invent captive-portal/enterprise-network workarounds.

Ask before network changes. Preserve the current control connection; use a tested UART/local fallback and restoration plan before changing an interface carrying SSH. Do not enable laptop internet sharing/forwarding by default. Approved online staging is separate from the later isolated demo.

When possible, [test SSH](../../docs/developer-guide.md#04-move-to-ssh-and-setup) using the board address observed through UART and the event account. Keep host-key checks enabled; confirm why a key changed (a reflash changes it) before removing a known-hosts entry. If client isolation blocks SSH, ask organizers for a supported connection rather than scanning the network or weakening security.

**Checkpoint:** report the available control path and source-specific setup connectivity. If internet is unavailable but all needed assets are local, explain that setup may proceed locally; otherwise report staging as blocked.

## 3. Inventory, then propose a plan

Read the [preflight skill](../iq9-preflight/SKILL.md). Start with the hardware-only profile once access permits it:

```bash
# On the board, from the repo root:
bash skills/iq9-preflight/scripts/preflight.sh --profile board --json

# Or from the laptop's repo root, with the confirmed SSH host:
ssh "$IQ9_HOST" 'bash -s -- --profile board --json' < skills/iq9-preflight/scripts/preflight.sh
```

The SSH form does not require a board-side repo copy, and neither do the other one-shot helpers. Run them from the laptop as shown in [driving the board from the laptop](../../docs/developer-guide.md#05-drive-the-board-from-the-laptop-no-repo-copy), labelling every command as **laptop** or **board**. For the long-running server or importable helpers, copy only the needed files to a board work directory with approval; a full repo copy is optional and also needs approval, checking resolved destinations and preserving existing files. If using UART without the repo on the board, report preflight as unperformed until files are available; use the guide's basic board checks in the meantime.

Inspect existing package/runtime versions and permissions, local model directories, disk, memory, and running servers. Run `geniex version`, `geniex list`, and chipset configuration checks **if GenieX is available**; otherwise note it as missing and inspect local files first. Missing weights/GenieX are expected setup gaps, not proof that flashing failed. The always-emitted display warning is a reminder, not a detected monitor failure.

If the chosen model is missing from board storage, use the supplied USB drive before considering a download. Follow [USB model staging](../../docs/developer-guide.md#usb-model-drive-copy-never-move): find the mount, pick the one model directory, and get approval for the import. **Copy, never move.** If the drive is in the laptop, plan a copy over SSH; the board cannot see that mount.

Present a short plan listing:

- What works already and what can be reused.
- Required changes, the selected USB/local copy or cache import, source/destination paths, disk needs, and unresolved blockers. Downloads are a separately approved fallback only when suitable assets are unavailable locally or on the supplied drive.
- The reference generator path: LFM3-1.7B Q4_0, GenieX v0.10.0, NPU, loopback server.
- What is intentionally skipped: d1 unless requested/needed, broad multimedia installs, unneeded upgrades, and network-off rehearsal.

Wait for approval before installations/upgrades, model downloads/imports/removal, configuration changes, deletion, or non-loopback listeners. Do not run the upstream broad package installer unchanged; the [Adreno monitor warning](../../docs/developer-guide.md#32-driver-packages) still applies.

## 4. Apply only the approved setup

Use [developer guide sections 3–4](../../docs/developer-guide.md#3-setup) for missing base/NPU packages, GenieX, and the reference generator assets. Review installers before running them. Reuse compatible installations and local weights; inspect the cache again after installing GenieX and never re-pull registered models. Back up replaced board files and preserve unrelated files. Do not silently switch compute routes or upgrade to a different runtime version.

Run long setup, copy/import, and server jobs in a separate terminal. Retain logs and verify each exit status.

Before an APT install, refresh the **existing** sources, simulate the missing-package list, and review it. For `404 Not Found` package downloads, follow [stale APT recovery](../../docs/developer-guide.md#stale-apt-lists-and-package-file-404s); do not add a PPA, upgrade the system, use `--fix-missing`, or change Adreno. The participant runs sudo commands in their own board terminal.

Report the refreshed APT candidate, the installed package version, and GenieX's bundled runtime (`geniex version`) separately. They can differ and are not interchangeable; see the [stale APT note](../../docs/developer-guide.md#stale-apt-lists-and-package-file-404s).

After FastRPC is installed, check [NPU device access](../../docs/developer-guide.md#npu-device-access) for **read and write**, not just readable nodes. If the user must join `fastrpc`, the participant runs the `usermod` command privately; then reconnect SSH and re-check `id -nG`. A server started before that must be restarted, with permission, from the new login.

d1 is optional; do not create its venv or stage its snapshot to satisfy the generator milestone. If requested, hand off to the [d1 skill](../iq9-d1-decision-gate/SKILL.md) separately.

## 5. Verify the first generator milestone

Read the [generator skill](../iq9-geniex-lfm/SKILL.md). On the board, from the repo root:

```bash
bash skills/iq9-preflight/scripts/preflight.sh --profile generator --json
```

Reuse an appropriate existing server, or start `skills/iq9-geniex-lfm/scripts/serve.sh run` in an agreed separate terminal. Do not stop a server you did not start. Use the existing standard-library client for a bounded first response:

```bash
python3 skills/iq9-geniex-lfm/scripts/lfm_client.py --sentence 'Explain why local inference is useful when the internet is unavailable.'
skills/iq9-geniex-lfm/scripts/serve.sh status
```

Verify a non-empty, useful answer with positive completion usage, not just HTTP success, model availability, reasoning, or an `ok` flag. Inspect the **current server's** device/offload log for `HTP0` after the request. Diagnose missing output/device evidence without silently falling back to CPU. A preflight pass alone does not meet this milestone.

`starter/run.sh` is the full two-model reference check, **not** a generator-only onboarding requirement.

## 6. Hand back a clear status

Summarize observed facts, failed checks, and unperformed checks:

- Board/OS, control path, and setup connectivity.
- Runtime version, model/precision, usable response, and current-server NPU evidence.
- Installed/staged changes, unresolved blockers, and server/log location.
- d1 status (usually intentionally skipped).
- Next example: generator requests, guarded tool calling, or the always-on agent (`--gate rule` needs no d1).
- Offline status: local inference while connected is **not** a network-off rehearsal. Do not cut networking to complete onboarding; follow the [offline skill](../iq9-offline-rehearsal/SKILL.md) later with explicit approval and a tested fallback/restoration plan.
