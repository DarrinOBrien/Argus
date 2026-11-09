# Developer Guide - LiquidAI on Qualcomm Dragonwing IQ-9075

Reference documentation for developers at the On-Device AI Hackathon: Cleared for Takeoff.

* **Hardware:** Dragonwing IQ-9075 EVK, Ubuntu 24.04 aarch64.
* **Generator and tools:** choose an LFM3-family model that fits the project. The examples default to LFM3-1.7B GGUF through GenieX v0.10.0 on the NPU.
* **Optional decision layer:** d1-2B through Transformers on the CPU, or a rule/another decision design.
* **Inputs:** external sensors are optional and not supplied. Use brought sensors, internal readings, local files/events, or simulated inputs.
* **Deployment:** the final demo runs without the network.

## Table of contents

0. [Board access and internet for setup](#0-board-access-and-internet-for-setup)
1. [Pre-work](#1-pre-work)
2. [Architecture](#2-architecture)
3. [Setup](#3-setup)
4. [Stage your model](#4-stage-your-model)
5. [Local server (OpenAI-compatible)](#5-local-server-openai-compatible)
6. [The decision layer](#6-the-decision-layer)
7. [Choosing a model](#7-choosing-a-model)
8. [Building an always-on agent](#8-building-an-always-on-agent)
9. [Tool calling](#9-tool-calling)
10. [Measuring performance](#10-measuring-performance)
11. [Running offline](#11-running-offline)
12. [Troubleshooting](#12-troubleshooting)

## 0. Board access and internet for setup

Start here if you do not yet have a board shell or working internet on the board. If both already work, reuse them and continue to [setup](#3-setup). Coding agents should follow the [getting-started skill](../skills/iq9-getting-started/SKILL.md).

**First establish access, then inspect, propose a plan, and make approved changes.** Ask whether the agent is running on the laptop or the board, which host OS is in use, and what is available: an existing SSH session, a micro-USB UART cable, Wi-Fi, or Ethernet. Do not guess a board address or assume the laptop's internet connection gives the board internet access. A working local console is also an option; external monitors have the [Adreno caveat](#32-driver-packages).

The steps below adapt Qualcomm's **Ubuntu** [IQ-9075 device setup guide](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device), specifically [debug UART](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device#set-up-the-debug-uart), [network setup](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device#connect-to-the-network), and [SSH](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device#connect-over-ssh). They are not instructions for the separate Qualcomm Linux image.

### 0.1 Open the UART console if needed

Power the board with its supplied adapter and connect a **data-capable micro-USB cable** from the board's debug UART port to the laptop. This is not the USB-C flashing/network port. Open the **Main Domain** UART at **115200 baud**; the onboard FTDI adapter exposes multiple serial ports, and its second functional port (Converter B) is the Linux login console.

- **Ubuntu/Linux laptop:** list ports with `ls /dev/ttyUSB*`. Qualcomm's example uses `/dev/ttyUSB1`; identify this board's port rather than assuming that number when other adapters are attached. With the port confirmed, open `sudo screen /dev/ttyUSB1 115200` in a separate terminal. If `screen` is missing, ask before installing it on the **laptop**.
- **macOS laptop:** list ports with `ls /dev/cu.*`, identify this board's Main Domain port, then use `screen /dev/cu.<actual-device-node> 115200` in a separate terminal. Substitute the observed node, not an upstream example's serial number.
- **Windows laptop:** use Device Manager to identify Converter B's COM port, then open PuTTY in Serial mode at 115200. See the upstream UART section for port identification and FTDI driver instructions; ask before any laptop installation.

Only one application should own the UART port. Inspect a busy port rather than opening a second session or killing another user's terminal. If the agent cannot interact with a serial terminal, guide the participant through these steps and ask for non-secret output. Press **Enter** for the login prompt.

**Organizer-provided event login (UART and SSH):**

| Field | Event value |
| --- | --- |
| Username | `ubuntu` |
| Password | `liquidxqualcomm` |

These are shared event credentials, not production credentials. The upstream Ubuntu guide's initial `ubuntu` / `ubuntu` login is **not** the event login. If the event credentials fail or a password-change prompt appears, confirm the image/account state with the owner or organizers; do not reset accounts or reflash automatically. Enter passwords interactively, not in logged commands. Do not expose these boards to the public internet; ask before changing passwords or SSH configuration.

### 0.2 Inspect and connect the board

Run these in the **board's UART shell** (or reuse an already working board shell):

```bash
uname -m                         # expect aarch64; GenieX need not exist yet
nmcli -p device                  # observed network interfaces and state
ip -br address
ip route
```

Inspect `/etc/os-release` to confirm Ubuntu 24.04. A different patch/kernel version is not by itself a reason to reflash. If a suitable network connection already works, leave it alone.

For **Wi-Fi**, ask which SSID to use and have the participant enter its password privately in the UART terminal. After approval to change the board's network configuration:

```bash
nmcli dev wifi list
sudo nmcli --ask dev wifi connect 'YOUR_WIFI_SSID'
nmcli -p device
ip -br address
```

Replace `YOUR_WIFI_SSID` with the selected SSID, preserving quotes for names containing spaces. `--ask` prompts for the Wi-Fi password instead of putting it in shell history or agent logs; this adapts upstream's `sudo nmcli dev wifi connect <WiFi-SSID> password <WiFi-password>`. A `sudo` password prompt uses the **board account** password, not the Wi-Fi password. Do not request private Wi-Fi passwords in chat or store them in this repo.

For **Ethernet**, connect the EVK's RJ45 port to an approved network/router, then inspect `nmcli -p device` and `ip -br address` in the UART shell. Upstream's example interface names are `wlp1s0` for Wi-Fi and `end0` for Ethernet; use the names actually reported by this board. A laptop-to-board cable or an IP address alone does not establish internet access.

Do not disable/reconfigure the interface carrying an active SSH session without an approved fallback control path and restoration plan. If Wi-Fi requires a captive portal or enterprise authentication, get the network's supported connection instructions from organizers rather than inventing credentials or bypassing access controls.

### 0.3 Check internet access from the board

Internet is used **during setup** to stage software and model assets, not during app inference or the final demo. On the board, inspect the default route and DNS, then use bounded HTTPS checks for the actual setup sources:

```bash
ip route
getent ahosts qaihub-public-assets.s3.us-west-2.amazonaws.com
getent ahosts huggingface.co
date -Is                         # a wrong clock can cause TLS failures
curl -I --connect-timeout 5 --max-time 15 \
  https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-geniex/install.sh
curl -I --connect-timeout 5 --max-time 15 https://huggingface.co
```

These fetch headers, not installers or model weights. If a command is unavailable, report the missing tool and ask before installing it. Diagnose link/address, route, DNS, and HTTPS/TLS separately. An HTTP error, captive-portal redirect, or one unreachable endpoint does not prove general internet access works or fails. Do not disable TLS verification to work around a bad clock or certificate error. Check package sources separately when installations are needed.

Preflight's external HTTPS probe is informational and does not fail a profile when offline; `ready: true` is **not** proof of online setup readiness or of a network-off rehearsal.

### 0.4 Move to SSH and setup

Once the board has a known reachable address, connect from the **laptop** on the same reachable network. Replace `BOARD_IP` with the address observed in the board shell:

```bash
export IQ9_HOST='ubuntu@BOARD_IP'
ssh "$IQ9_HOST"
```

Enter the event password when prompted. Keep SSH host-key verification enabled. Verify an unfamiliar or changed key against the board/owner before accepting it or approving removal of a stale entry; a reflash can change the key, but a mismatch is not permission to bypass verification. For a refused connection, inspect the SSH service from UART before proposing service or firewall changes. Some event networks isolate clients even when both have internet access; ask organizers for a supported control link if SSH is blocked.

Next run the [hardware-only preflight](#31-confirm-the-board), inventory existing software/weights/disk, and present a setup plan. Missing GenieX and weights are setup work, not proof of a bad flash. You do not need the whole repo on the board: see [driving the board from the laptop](#05-drive-the-board-from-the-laptop-no-repo-copy). If a full copy is wanted, arrange an approved, non-destructive copy, preserving unrelated board files.

The first milestone is a **useful local LFM response with current-server `HTP0` evidence**, following [sections 3–5](#3-setup) and the [generator skill](../skills/iq9-geniex-lfm/SKILL.md). Leave d1 optional. Report this milestone separately from an actual [offline rehearsal](offline-readiness.md), which requires explicit approval before a network cut.

### 0.5 Drive the board from the laptop (no repo copy)

The repo can stay on the laptop. One-shot helpers read their script from SSH stdin, so nothing is copied to the board. These run on the **laptop**, from the repo root, with `IQ9_HOST` set as above (an `~/.ssh/config` alias also works):

```bash
# Laptop. Non-interactive SSH may not put ~/.local/bin (GenieX's user install) on PATH.
B='export PATH="$HOME/.local/bin:$PATH"'

# Preflight: hardware first, then the generator profile after setup
ssh "$IQ9_HOST" 'bash -s -- --profile board --json' < skills/iq9-preflight/scripts/preflight.sh
ssh "$IQ9_HOST" "$B; bash -s -- --profile generator --json" < skills/iq9-preflight/scripts/preflight.sh

# One capped, validated request to the board's loopback server
ssh "$IQ9_HOST" "python3 - --sentence 'Explain why local inference is useful when the internet is unavailable.'" \
  < skills/iq9-geniex-lfm/scripts/lfm_client.py

# Server status plus the HTP0 line; point GENIEX_SERVE_LOG at the board-side server log
ssh "$IQ9_HOST" "$B; GENIEX_SERVE_LOG=\$HOME/iq9-work/geniex-serve.log bash -s -- status" \
  < skills/iq9-geniex-lfm/scripts/serve.sh
```

The paths in these commands are on the **board**: `~/.local/bin/geniex`, the GenieX cache `~/.cache/geniex/models`, and a work/log directory such as `~/iq9-work/`. The laptop has no GenieX, NPU, or models.

Streaming suits one-shot CLI helpers: preflight, `lfm_client.py --check/--sentence/--chat`, and `serve.sh status`. For the long-running server, or app code that imports `lfm_client`, copy just the needed files to a board work directory with approval (for example `scp skills/iq9-geniex-lfm/scripts/{serve.sh,lfm_client.py} "$IQ9_HOST":iq9-work/`). Then run the server in a separate board SSH terminal from that directory, so its log stays on the board.

**sudo stays with the participant.** The agent's SSH session is non-interactive and cannot answer a sudo prompt. The agent prints the exact command; the participant runs it in their own `ssh "$IQ9_HOST"` terminal, enters the password there, and pastes back the non-secret output. Never put passwords in commands, chat, or logs.

## 1. Pre-work

**Event boards will arrive with freshly flashed Ubuntu images.** Use Qualcomm's required-software guide for post-flash setup, then install and stage your project's runtimes, dependencies, and models while internet access is available. Do not assume the image already includes GenieX, torch, or model weights.

* [IQ-9075 EVK setup](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device)
* [IQ-9075: Install Required Software Packages](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/Install_required_software_packages)
* [GenieX quickstart](https://geniex.aihub.qualcomm.com/en/get-started/quickstart)
* [GenieX platforms and runtimes](https://geniex.aihub.qualcomm.com/en/get-started/platforms)
* [LFM3-1.7B GGUF model card](https://huggingface.co/LiquidAI/LFM3-1.7B-GGUF)
* [d1-2B model card](https://huggingface.co/LiquidAI/d1-2B)

The required-software page covers a broad set of AI, camera, and multimedia use cases; not every package is needed by every project. Read the [monitor caveat in section 3.2](#32-driver-packages) before running its installation script.

Run commands below on the board from the repo root unless a different directory is specified. From a laptop, use the board host supplied by the owner; do not assume the laptop has GenieX, the NPU, or the models.

## 2. Architecture

### 2.1 Two models, two jobs

**This is an example implementation, not a prescribed architecture or a recipe for the hackathon.** It shows one way you *could* combine a decision gate, guarded actions, and an explanation model. Teams do not need to follow this pattern, use d1, or build a two-model monitor to compete or win. Choose the design that best serves your project's purpose and the [judging criteria](judging.md).

In this example, the reference monitor separates a decision from its explanation:

```text
Local observation
    |
    v
d1-2B or a rule: decide whether anything needs attention
    |
    +-- no action --> log and continue
    |
    +-- action --> code policy --> allowlisted action
                                      |
                                      v
                               LFM explanation
                                      |
                                      v
                                local JSONL log
```

A rule can replace d1 when the decision is simple. If you use both d1 and LFM in the reference stack, keep their inference sequential. The model may propose actions, but code validates and authorizes them.

### 2.2 Runtimes and routes

| Work                     | Reference route                                       |
| ------------------------ | ----------------------------------------------------- |
| LFM generation and tools | GenieX `llama_cpp`, cached GGUF, NPU                  |
| Optional d1 gate         | Transformers `system_one()`, local snapshot, fp32 CPU |

### 2.3 Compute units

| `--compute` | Route         | Guidance                                                                               |
| ----------- | ------------- | -------------------------------------------------------------------------------------- |
| `npu`       | Hexagon HTP   | Reference generator route                                                              |
| `hybrid`    | HTP and CPU   | Evaluate on the selected model and workload before choosing                            |
| `cpu`       | CPU           | Explicit alternative for compatible models; d1 uses Transformers on the CPU separately |
| `gpu`       | Adreno/OpenCL | Requires a compatible model/runtime configuration                                      |

After a capped generator request, inspect the current device/offload log for `HTP0`. Missing device output calls for diagnosis, not an automatic CPU-fallback conclusion.

### 2.4 Hardware budget

Budget disk, host RAM, and device buffers separately. Inspect `df -h /` and `free -h` before staging models. See [Offline readiness: disk first](offline-readiness.md#disk-first) for asset and staging budgets.

## 3. Setup

### 3.1 Confirm the board

After establishing [board access](#0-board-access-and-internet-for-setup), start with the hardware-only [preflight](../skills/iq9-preflight/SKILL.md) when the installed stack is not yet known. On the board, from the repo root:

```bash
bash skills/iq9-preflight/scripts/preflight.sh --profile board --json
```

Or from the laptop's repo root, using the confirmed SSH host (the repo need not yet be on the board):

```bash
ssh "$IQ9_HOST" 'bash -s -- --profile board --json' < skills/iq9-preflight/scripts/preflight.sh
```

This inspects hardware/driver readiness without expecting GenieX, model weights, or a d1 environment. Missing driver checks may still need the package setup below; they are not by themselves proof that flashing failed.

Every profile also emits a `display` warning about the Adreno monitor issue. It is a setup reminder, not a detected display failure: preflight does not test monitor compatibility or identify affected graphics-package versions. A passing run does not establish that a monitor setup works.

After setup and model staging, choose the app's profile: `--profile generator --model 'cached-name:precision'` without d1, or `--profile reference` for the full example stack. Missing runtimes/models are expected before they have been installed or staged.

### 3.2 Driver packages

For post-flash setup, refer to Qualcomm's [Install Required Software Packages](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/Install_required_software_packages) guide.

**External monitor warning:** organizers report that the current Adreno APT update causes a GPU-driver issue with an external monitor. Teams using a monitor must **remove/roll back that update**; SSH is unaffected. See [Developer Notes](../README.md#external-monitors-and-headless-setups). Confirm installed versions and the board-specific removal/rollback procedure with the organizers and board owner; do not blindly purge GPU packages.

**The linked upstream `install_ppa_pkgs.sh` is not adapted for this event's monitor issue.** Do not run it unchanged for a monitor setup until organizers confirm which graphics changes to omit or roll back.

Its Server path installs `qcom-adreno1`; its Desktop path installs `qcom-adreno-cl-dev`, adds a Mesa PPA, and upgrades `libegl-mesa0`. It also performs a broad package upgrade and reboots. These are the script's graphics changes, not confirmed causes of the monitor issue; excluding `qcom-adreno1` alone is not a verified Desktop workaround.

No event-specific patched installer is provided here. The affected packages/versions and approved installation or rollback procedure need confirmation before one can be supplied.

Inspect the current drivers and permissions before making changes. With the board owner's approval, refresh the **existing** APT sources and simulate only missing base and NPU libraries before installation. Do not install/update `qcom-adreno1` as part of this NPU setup. For example, when GLib and the OpenCL loader are already installed:

```bash
sudo apt-get update &&
apt-get -s install --no-install-recommends libatomic1 qcom-fastrpc1 libqnn1
```

If GLib or the OpenCL loader is missing, include the appropriate Ubuntu 24.04 packages (`libglib2.0-0t64`, `ocl-icd-libopencl1`) in the simulation and installation lists. Review the resulting dependencies, candidate versions, upgrades, and removals. Stop if the plan adds graphics changes or other changes outside the owner's approval. Only after a successful source refresh and an acceptable simulation, run the matching install interactively (no automatic `-y`):

```bash
sudo apt-get install --no-install-recommends libatomic1 qcom-fastrpc1 libqnn1
```

If sudo requires a password, have the participant enter it privately in their board terminal, not in chat or logged commands.

Follow the board setup guide rather than adding duplicate package sources.

#### NPU device access

GenieX needs **read and write** access to `/dev/fastrpc-cdsp` and `/dev/fastrpc-cdsp1`. Nodes can exist and be readable while still unusable. Check, on the board:

```bash
ls -l /dev/fastrpc-cdsp*
id -nG
getent group fastrpc || echo 'no fastrpc group'
for n in /dev/fastrpc-cdsp /dev/fastrpc-cdsp1; do
  if [ -r "$n" ] && [ -w "$n" ]; then echo "rw ok: $n"; else echo "NO rw: $n"; fi
done
```

1. **Root-only nodes and no `fastrpc` group:** the FastRPC package is missing. `qcom-fastrpc1` installs the udev rules that give the nodes to the `fastrpc` group. Install it with the approved package step above, then re-inspect.
2. **Group-owned nodes, user not in the group:** with approval, the participant runs `sudo usermod -aG fastrpc "$USER"` (use the observed group name). Group changes apply only to **new** logins. Exit and reconnect SSH, and re-check `id -nG`; already-open shells and servers keep the old groups.
3. **User in the group but still no access:** inspect the node's group and mode, and the installed udev rules, before changing anything. Do not `chmod` device nodes as a workaround.

The preflight `npu-access` check tests read and write on each node, but passing it is not NPU verification. Finish with a capped useful request and the **current** server's `HTP0` log line ([section 5](#5-local-server-openai-compatible)). A server started before the group change must be restarted (with permission) from a new login.

On a freshly flashed image, expect to need both steps: installing `qcom-fastrpc1`, then adding the user to `fastrpc` and reconnecting.

#### Stale APT lists and package-file 404s

Freshly flashed images can contain old APT indexes. A package-file `404 Not Found` does not by itself mean the board has no internet or needs a new PPA: the cached candidate may reference a file the configured source no longer serves.

Typical symptom: the image's Qualcomm PPA lists date from the flash, so downloads for older QAIRT packages (`qairt-dsp-binaries`, `qairt-libs`, `libqnn1`) return 404 and nothing installs. Refreshing the existing sources normally selects newer package versions; re-simulate and confirm there are no upgrades or removals before installing. Package versions change over time and are not pins.

**System packages and GenieX's runtime are separate.** GenieX ships its own QAIRT runtime (`geniex version` shows it), which can differ from the system QAIRT packages APT installs. Record the APT candidate, the installed package version (`dpkg-query -W`), and the GenieX runtime version separately; they are not interchangeable. Install the packages listed above; do not trim the list on the assumption that the bundled runtime makes them unnecessary.

Recovery, during approved online setup only:

1. Check installed package state and cached candidates (`dpkg-query -W`, `apt-cache policy`). If useful, inspect list timestamps under `/var/lib/apt/lists`; a failed fetch is not evidence that installation completed.
2. Run `sudo apt-get update` against the existing sources, then re-simulate the actual missing-package list as above. If update reports failed sources or retained old indexes, stop and diagnose those errors rather than trusting its exit status alone.
3. Review the refreshed install plan before accepting it. An “N not upgraded” message does not require a broad upgrade. Do not run `apt upgrade`/`dist-upgrade`, add a PPA, change Adreno, disable signature/TLS verification, or use `--fix-missing` as a stale-index workaround.
4. If package-file 404s persist after a successful refresh, inspect the exact URL and source metadata; report the remaining source problem instead of guessing a different runtime or repository. After installation, record actual versions, rerun preflight, and verify a capped useful LFM response with current-server `HTP0` evidence.

### 3.3 GenieX CLI

First inspect `geniex version`, `geniex --help`, and `geniex config get chipset`. The reference version is v0.10.0. Do not replace an existing install unnecessarily.

If installation is needed, obtain approval and stage the installer while networking is available:

```bash
curl -fSLo install.sh https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-geniex/install.sh
# Read install.sh before executing it; back up an install being replaced.
sh install.sh --version v0.10.0
```

Keep the installer and matching archive locally for recovery. No runtime installation is part of the app's launch path.

### 3.4 Python environment for the decision layer

Skip this step if the app does not use d1. Reuse a compatible existing d1 environment if available. Before creating a venv that inherits system packages, check whether the board's Python already has torch:

```bash
python3 -c 'import torch; print(torch.__version__)'
```

A fresh image may not include torch. If it is missing, arrange a compatible aarch64 CPU torch installation and matching torchvision with approval before continuing. The example requirements deliberately omit torch and pin torchvision to the reference pairing (torch 2.11.0 / torchvision 0.26.0); do not assume these are preinstalled or replace a working installation blindly.

Create the environment only if needed, with approval, and stage dependencies while networking is available:

```bash
python3 -m venv --system-site-packages ~/.venvs/d1
source ~/.venvs/d1/bin/activate
python -m pip install -r examples/system-one-decision/requirements.txt
```

If torch is already present, reuse it and match torchvision to that build, adjusting the dependency selection as needed before installation. The [System One example](../examples/system-one-decision/README.md) covers the pinned snapshot, remote-code review, and environment checks, including how to see which packages are already installed.

<a id="4-first-model-in-five-minutes"></a>

## 4. Stage your model

Teams receive **USB drives with model assets** and have been asked to bring **USB-C dongles/adapters**. Ask: **“Do you have your supplied USB model drive and a suitable USB-C adapter? Is it connected to the board or your laptop?”** Prefer existing board assets first, then compatible USB assets; model downloads are a separately approved fallback, not the default.

Inspect the cache, disk, and existing local model directories before copying/importing or downloading anything:

```bash
geniex --skip-update list
df -h /
```

### USB model drive: copy, never move

1. **Discover, do not guess.** On the board, inspect existing block devices/mounts with `lsblk -o NAME,TRAN,SIZE,FSTYPE,LABEL,MOUNTPOINTS` and `findmnt`. Have the participant identify their drive and use the observed mount path. Ask before mounting an unmounted drive or changing configuration; prefer read-only source access. If it is attached to the laptop, inspect it there and plan an approved copy over the confirmed SSH link—laptop and board mount paths are different. Do not format the drive or repurpose a cable carrying the active control session. A storage dongle does not establish USB-C networking or internet access.
2. **Select and budget.** Inspect the chosen model's directory, manifest/file list, format, precision, license, and runtime/NPU compatibility; do not copy the entire drive just because it contains all models. Resolve source/destination paths and inspect symlinks. Include matching tokenizer, template, model code, and modality assets. For the reference generator, select LFM3-1.7B **QAD-Q4_0 GGUF**, not an arbitrary d1 GGUF or a different precision. Check board free space for the full import and any intermediate copy.
3. **Get approval for explicit source and destination paths. Copy, never move.** Leave all USB source files intact: no `mv`, source deletion after import, `rsync --remove-source-files`, destructive `--delete` sync, or edits to the supplied drive. Preserve unrelated board files and back up any approved replacements. Do not manually populate/edit GenieX cache metadata.
4. **Import a missing generator from the selected local directory.** With approval and the matching cached model absent, use the installed CLI's local import. Replace the path below with the **observed** model directory, not the drive root:

   ```bash
   MODEL_USB_DIR='/actual/mounted/path/to/LFM3-model-directory'
   geniex --skip-update pull LiquidAI/LFM3-1.7B-GGUF:Q4_0 \
     --model-hub localfs --local-path "$MODEL_USB_DIR"
   geniex --skip-update list
   ```

   `--local-path` copies into the GenieX cache (default `~/.cache/geniex/models`) without downloading weights; `--model-hub localfs` makes the source explicit. The [GenieX CLI reference](https://geniex.aihub.qualcomm.com/en/run/cli/reference#geniex-pull) documents this copy behavior. **Do not delete the USB source**, even though general upstream guidance permits removing a source after import. If a laptop-side source must be copied to a new board staging directory first, budget for both that copy and the cache import. Never re-import an already-registered model.
5. **If using optional d1**, copy the **entire pinned Transformers snapshot** to `~/models/d1-2B`, including weights, configs, tokenizer, model code, and `REVISION`; a GGUF is not a substitute. Inspect any cache-style symlinks and copy their verified targets into board-local files, without retaining links to removable media. Do not merge into an existing snapshot blindly or change the revision pin to match the drive. Follow the [d1 skill](../skills/iq9-d1-decision-gate/SKILL.md).
6. **Verify, then run locally.** Retain the copy/import log and exit status, verify expected files and sizes/checksums against the source or supplied manifest, and confirm cache registration or the d1 revision. Run long copies/imports in a separate terminal. Stage everything on board storage, not on the drive: after approved safe ejection, verify startup without it. For the generator, send a capped useful request and inspect the current server's `HTP0` evidence. **USB staging is not yet board-rehearsed in this repo; documentation and CLI checks do not prove a successful media import.**

If suitable assets are absent from the cache, board/laptop local files, and the supplied USB drive (or the drive is unavailable), explain the gap and obtain approval before downloading during setup:

```bash
geniex --skip-update pull LiquidAI/LFM3-1.7B-GGUF:Q4_0
```

Never re-pull cached models or fetch/import weights on application startup.

## 5. Local server (OpenAI-compatible)

Run the foreground server in a separate terminal:

```bash
bash skills/iq9-geniex-lfm/scripts/serve.sh run
```

The reference server uses `127.0.0.1:18181`, NPU compute, and a long keepalive. It serves cached models without downloading them. Send a capped request from another terminal on the board:

```bash
curl -sS --max-time 60 http://127.0.0.1:18181/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "LiquidAI/LFM3-1.7B-GGUF:Q4_0",
    "messages": [{"role": "user", "content": "Say hello in five words."}],
    "max_completion_tokens": 64,
    "compute": "npu",
    "enable_think": false,
    "stream": false
  }'
```

* Cap every chat call with `max_completion_tokens`; use `max_tokens` on raw completions.
* Inspect answer content and reasoning separately. Positive token usage does not make an empty answer usable.
* For direct LFM3-1.7B answers, try `enable_think: false` or the helper's closed-reasoning raw template. Keep output validation either way.
* Tag raw prompts before the first call and retry unusable output once. Return persistent errors as data.
* Plan for idle unloading and warm up with a capped request before the demo. See [Server lifecycle](runtimes.md#server-lifecycle-model-loading-and-idle-unloading).
* Do not bind to non-loopback addresses or interrupt shared servers without approval.

The standard-library [LFM client](../skills/iq9-geniex-lfm/scripts/lfm_client.py) provides these request guards. [Runtime reference](runtimes.md) describes endpoints and fields.

## 6. The decision layer

If using d1-2B, run a pinned local snapshot through Transformers in fp32 on the CPU. Load once and reuse it. Set offline/telemetry settings before imports and pass `local_files_only=True` to the loader.

The [decision-layer reference](decision-models.md) includes loading, typed questions, and calibration. The runnable [System One example](../examples/system-one-decision/README.md) shows state, image, and batch calls.

Do not route this reference d1 integration through GenieX decision endpoints. A d1 GGUF does not replace the Transformers snapshot. Zero generated output tokens are expected for d1, unlike an empty LFM-generation response.

## 7. Choosing a model

Choose based on task, format, precision, runtime/NPU support, and available memory. Any LFM3-family model is welcome; other LFM models are options too. LFM3-1.7B is the examples' default, not an eligibility rule.

Use a rule instead of d1 when a local threshold is enough. For vision or audio, stage the matching assets and use the modality's API. External sensors are optional; local images, recordings, or simulated events can serve as inputs.

Browse [LiquidAI's published models](../README.md#platform-and-models), then check [format, precision, and runtime compatibility](runtimes.md#model-format-and-precision). The example READMEs explain their reference choices; re-test your selected model on the board rather than transferring their results.

## 8. Building an always-on agent

The reference loop is **observe -> decide -> act -> explain -> log**.

1. **Generate only when needed.** Use a decision gate or rule before invoking the LFM for an explanation.
2. **Calibrate on the app's task.** Fit thresholds on labeled states and evaluate separately on held-out data.
3. **Constrain actions.** Schemas, allowlists, and write-action policy belong in code.
4. **Log each iteration.** Flush JSONL with the observation, decision, executed action, explanation, timing, and errors.
5. **Cap and validate output.** Empty answers, reasoning alone, and zero LFM tokens are failures even when the HTTP request succeeds.
6. **Keep the loop alive.** Input and explanation failures become logged data; avoid unhandled exceptions inside a monitor.
7. **Keep inference sequential.** Do not overlap d1 and the generator without evaluating a changed scheduling design on the app's workload.

Start from [Always-on agent](../examples/always-on-agent/README.md), or create an app using the [scaffold](../skills/iq9-always-on-agent/SKILL.md). Use bounded iterations and simulated inputs while adapting it.

## 9. Tool calling

Send OpenAI-style function schemas in `tools` to `/v1/chat/completions`. Validate returned call envelopes, IDs, names, and arguments before executing anything.

The model proposes; code decides. Apply a policy before every write or real-world action, and report executed actions from the app's own records rather than the model's prose. Keep the tool list short and the number of turns bounded. A token budget is not a guarantee that the model chooses a valid tool.

The [tool-calling example](../examples/tool-calling/README.md) includes schema, allowlist, policy, execution, and local guard checks.

## 10. Measuring performance

Choose an observation interval and token budget based on the app's workload. Include cold startup, warm requests, decision latency, loop time, memory, and error rate.

For server requests, use the [metrics collector](../skills/iq9-demo-prep/scripts/collect_metrics.sh). It separates generated-output TTFT from answer TTFT and labels streamed decode timing as an estimate. Do not count SSE chunks as tokens.

The collector's default prompt asks for **one sentence**, so its numbers describe short answers. Short-answer runs are dominated by prefill and TTFT, so they understate sustained decode speed. For your app's workload, pass `--prompt` with a representative request. For long answers, set `--max-tokens` as a generous **safety cap** and check that `finish_reason` is `stop` rather than `length`; a capped run measures the cap, not the answer. Report decode tok/s and end-to-end tok/s separately, and keep the warm-up out of the medians (the collector already does). See the [demo-prep skill](../skills/iq9-demo-prep/SKILL.md#2-numbers-measure-them-never-quote-the-docs-as-your-own).

For a local GGUF benchmark, stage `geniex-bench` matching the runtime, then point it at the actual file:

```bash
D="$HOME/geniex-bench-linux-arm64-v0.10.0"
export LD_LIBRARY_PATH="$D/lib:$D/lib/llama_cpp:$D/lib/qairt"
"$D/bin/geniex-bench" --plugin llama_cpp --device npu \
  -m /absolute/path/to/model.gguf -r 5 -p 512 -n 128
```

This command selects five runs, a 512-token prefill, and 128 generated tokens. It does not time d1; time `system_one()` separately for the app's exact questions. Process RSS, peak process RSS, and device memory are different resources.

Put app results in the app's README with the board, runtime, model/precision, workload, sample count, and medians. Keep this shared reference focused on setup and APIs.

## 11. Running offline

Stage the chosen models, packages, UI assets, docs, and sample data before the cut. At runtime, load local snapshots/cache entries only; do not install packages, pull models, send telemetry, or fetch remote assets.

Rehearse cold startup and the core workflow with all external uplinks disconnected. A configured, isolated USB-C link may remain for SSH and an app web UI, with no laptop internet sharing/forwarding. Get approval before cutting the network; use a working local console or a tested isolated USB-C SSH session, not SSH over the uplink being cut. See [display and USB-C access](offline-readiness.md#display-and-usb-c-access).

Full checklist: [Offline readiness](offline-readiness.md).

## 12. Troubleshooting

| Symptom                                                      | What to inspect                                         | Next step                                                                                                                                      |
| ------------------------------------------------------------ | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `geniex: command not found`                                  | Installed CLI path and shell `PATH`                     | Use the existing install or follow approved setup; do not reinstall blindly                                                                    |
| External monitor/GPU-driver issue after an Adreno APT update | Installed Adreno package versions and update history    | With approval, remove/roll back the update using the organizers' board-specific procedure; SSH/USB-C web UI is an alternative. See section 3.2 |
| Missing NPU libraries                                        | Driver packages and loader error                        | Install only missing packages with approval; do not reinstall/update Adreno as a generic NPU fix. See section 3.2                              |
| CDSP permission denied                                       | Read **and** write on each node; `fastrpc` group        | Follow [NPU device access](#npu-device-access) with approval; reconnect SSH and restart the server from the new login                          |
| Slow generator or no HTP0 output                             | Current server log, compute route, drivers, permissions | Diagnose NPU access without silently changing compute                                                                                          |
| Long or reasoning-only answer                                | Token cap, prompt template, answer/reasoning fields     | Keep the cap, try direct-answer controls, and validate usable content                                                                          |
| Empty answer or zero LFM tokens                              | Response body, prompt uniqueness, cap                   | Retry once with a fresh tag; log persistent failure before safely relaunching the owned server                                                 |
| d1 request sent to a server endpoint                         | Integration route                                       | Call `model.system_one()` locally through Transformers on the CPU                                                                              |
| Slower first or post-idle request                            | Weight loading and keepalive                            | Plan cold/warm startup and adjust keepalive for quiet gaps                                                                                     |
| Benchmark cannot find libraries                              | Archive layout and `LD_LIBRARY_PATH`                    | Set paths to the matching local benchmark libraries                                                                                            |
| No space left on device                                      | Cache, snapshots, archives, duplicate copies            | Ask the owner before removing unused files                                                                                                     |
| Python import fails                                          | Selected interpreter, venv, package versions            | Inspect the environment before changing or recreating it                                                                                       |
| d1 loader requests code approval                             | Snapshot revision and loader options                    | Review local model code before enabling `trust_remote_code=True`                                                                               |
