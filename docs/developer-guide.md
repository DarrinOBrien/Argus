# Developer Guide - LiquidAI on Qualcomm Dragonwing IQ-9075

Reference for developers at the On-Device AI Hackathon: Cleared for Takeoff. Schedule, venue, and logistics are on the [event page](https://luma.com/0nsdnkoa).

* **Hardware:** Dragonwing IQ-9075 EVK, Ubuntu 24.04 aarch64.
* **Generator and tools:** any LFM3-family model that fits the project. The examples default to LFM3-1.7B GGUF through GenieX v0.10.0 on the NPU.
* **Optional ZETIC route:** LFM3 text and local image/audio → text through ZETIC's Hexagon SDK. See [section 2.5](#25-optional-zetic-route).
* **Optional decision layer:** d1-2B through Transformers on the CPU, or a rule in code.
* **Inputs:** external sensors are optional and not supplied. Use brought sensors, board readings, local files, or simulated inputs.
* **Deployment:** the final demo runs without the network.

**The shortest path to a first response:** get a board shell ([0](#0-board-access-and-internet-for-setup)) → install the NPU packages and join `fastrpc` ([3.2](#32-driver-packages)) → install GenieX ([3.3](#33-geniex-cli)) → import the model from the USB drive ([4](#4-stage-your-model)) → start the server and send a request ([5](#5-local-server-openai-compatible)). d1 is not needed for that.

## Ground rules

These apply to every section and are not repeated in each one.

1. **Inspect first, then ask before changing anything.** Reuse what already works. Installs and upgrades, model copies/imports/downloads/removals, network, account, and SSH changes, and file deletions need the participant's approval. Coding agents follow the full list in [AGENTS.md](../AGENTS.md#non-negotiable-rules).
2. **Passwords stay with the participant.** They type sudo, Wi-Fi, and login passwords in their own terminal. Never put them in chat, commands, or logs. An agent's non-interactive SSH session cannot answer a sudo prompt: it prints the exact command, the participant runs it and pastes back the non-secret output.
3. **Every command runs on the laptop or on the board, and says which.** The laptop has no GenieX, NPU, or models. Board commands run from the repo root unless stated otherwise.
4. **Setup may use the internet; the app may not.** Nothing is installed or downloaded when the app starts.

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

Find out what is available first: an existing SSH session, a micro-USB UART cable, Wi-Fi, or Ethernet, and which laptop OS is in use. Do not guess a board address, and do not assume the laptop's internet connection gives the board internet access.

These steps adapt Qualcomm's **Ubuntu** [IQ-9075 device setup guide](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device) ([debug UART](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device#set-up-the-debug-uart), [network](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device#connect-to-the-network), [SSH](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device#connect-over-ssh)), not the separate Qualcomm Linux image.

### 0.1 Open the UART console if needed

Power the board with its supplied adapter and connect a **data-capable micro-USB cable** from the board's debug UART port to the laptop. This is not the USB-C port. Open the **Main Domain** UART at **115200 baud**: the onboard FTDI adapter exposes several serial ports, and the second functional one (Converter B) is the Linux login console.

- **Linux laptop:** list ports with `ls /dev/ttyUSB*`, then `sudo screen /dev/ttyUSB1 115200`. Qualcomm's example uses `ttyUSB1`; confirm this board's port when other adapters are attached.
- **macOS laptop:** list ports with `ls /dev/cu.*`, then `screen /dev/cu.<observed-node> 115200`.
- **Windows laptop:** find Converter B's COM port in Device Manager, then open PuTTY in Serial mode at 115200. The upstream UART section covers the FTDI driver.

Only one application can own the port; do not open a second session or kill someone else's terminal. Press **Enter** for the login prompt.

**Event login (UART and SSH):**

| Field | Event value |
| --- | --- |
| Username | `ubuntu` |
| Password | `liquidxqualcomm` |

These are shared event credentials. The upstream guide's `ubuntu` / `ubuntu` login is **not** the event login. If the event login fails or a password-change prompt appears, ask the organizers; do not reset accounts or reflash. Do not expose the board to the public internet.

### 0.2 Inspect and connect the board

On the **board** (UART shell or an existing session):

```bash
uname -m                         # expect aarch64; GenieX need not exist yet
cat /etc/os-release              # expect Ubuntu 24.04
nmcli -p device                  # network interfaces and state
ip -br address
ip route
```

If a suitable connection already works, leave it alone. A different patch or kernel version is not a reason to reflash.

For **Wi-Fi**, with approval to change the board's network configuration:

```bash
nmcli dev wifi list
sudo nmcli --ask dev wifi connect 'YOUR_WIFI_SSID'
nmcli -p device
ip -br address
```

Keep the quotes for names with spaces. `--ask` prompts for the Wi-Fi password instead of putting it in shell history. The `sudo` prompt wants the **board account** password, not the Wi-Fi password.

For **Ethernet**, connect the RJ45 port to a network with internet access, then check `nmcli -p device` and `ip -br address`. Use the interface names the board reports (upstream examples: `wlp1s0`, `end0`). A laptop-to-board cable or an IP address alone is not internet access.

Do not reconfigure the interface carrying an active SSH session without a fallback such as UART. For a captive portal or enterprise Wi-Fi, ask the organizers for the supported way to connect.

### 0.3 Check internet access from the board

On the **board**, check the route, DNS, clock, and the two setup sources. These fetch headers only:

```bash
ip route
getent ahosts qaihub-public-assets.s3.us-west-2.amazonaws.com
getent ahosts huggingface.co
date -Is                         # a wrong clock can cause TLS failures
curl -I --connect-timeout 5 --max-time 15 \
  https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-geniex/install.sh
curl -I --connect-timeout 5 --max-time 15 https://huggingface.co
```

Diagnose link, route, DNS, and HTTPS separately; one failed endpoint does not mean there is no internet. Do not disable TLS verification to work around a bad clock or certificate error.

Preflight's network probe is informational: `ready: true` proves neither online setup readiness nor a network-off rehearsal.

### 0.4 Move to SSH and setup

On the **laptop**, on a network that can reach the board, using the address the board reported:

```bash
export IQ9_HOST='ubuntu@BOARD_IP'
ssh "$IQ9_HOST"
```

Keep SSH host-key verification on. A reflash changes the board's key; confirm that is the cause before removing a stale `known_hosts` entry. If the connection is refused, check the SSH service from UART. Some event networks isolate clients from each other; ask the organizers if SSH is blocked.

Next, run the [hardware-only preflight](#31-confirm-the-board), take stock of the installed software, weights, and disk, and plan the setup. Missing GenieX and weights are normal on a fresh board, not a bad flash. The repo can stay on the laptop ([next section](#05-drive-the-board-from-the-laptop-no-repo-copy)).

The first milestone is a **useful local LFM response with the current server's `HTP0` line**, from [sections 3–5](#3-setup). That is separate from an [offline rehearsal](offline-readiness.md), which comes later.

### 0.5 Drive the board from the laptop (no repo copy)

One-shot helpers read their script from SSH stdin, so nothing is copied to the board. On the **laptop**, from the repo root, with `IQ9_HOST` set (an `~/.ssh/config` alias also works):

```bash
# Non-interactive SSH may not put ~/.local/bin (GenieX's user install) on PATH.
B='export PATH="$HOME/.local/bin:$PATH"'

# Preflight: hardware first, then the generator profile after setup
ssh "$IQ9_HOST" 'bash -s -- --profile board --json' < skills/iq9-preflight/scripts/preflight.sh
ssh "$IQ9_HOST" "$B; bash -s -- --profile generator --json" < skills/iq9-preflight/scripts/preflight.sh

# One capped, validated request to the board's loopback server
ssh "$IQ9_HOST" "python3 - --sentence 'Explain why local inference is useful when the internet is unavailable.'" \
  < skills/iq9-geniex-lfm/scripts/lfm_client.py

# Server status plus the HTP0 line from the board's ~/geniex-serve.log
ssh "$IQ9_HOST" "$B; bash -s -- status" < skills/iq9-geniex-lfm/scripts/serve.sh
```

Paths in these commands are on the **board**: `~/.local/bin/geniex`, the GenieX cache `~/.cache/geniex/models`, and the server log `~/geniex-serve.log`.

Streaming suits one-shot helpers: preflight, `lfm_client.py --check/--sentence/--chat`, and `serve.sh status`. For the long-running server, or app code that imports `lfm_client`, copy just those files to a board work directory (for example `scp skills/iq9-geniex-lfm/scripts/{serve.sh,lfm_client.py} "$IQ9_HOST":iq9-work/`) and run the server in its own board terminal.

## 1. Pre-work

**Event boards arrive with freshly flashed Ubuntu images.** Do not assume the image includes GenieX, torch, or model weights; install and stage what your project needs while internet access is available.

* [IQ-9075 EVK setup](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device)
* [IQ-9075: Install Required Software Packages](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/Install_required_software_packages) (covers many AI, camera, and multimedia cases; read the [monitor caveat](#32-driver-packages) before running its script)
* [GenieX quickstart](https://geniex.aihub.qualcomm.com/en/get-started/quickstart) and [platforms and runtimes](https://geniex.aihub.qualcomm.com/en/get-started/platforms)
* [LFM3-1.7B GGUF model card](https://huggingface.co/LiquidAI/LFM3-1.7B-GGUF) and [d1-2B model card](https://huggingface.co/LiquidAI/d1-2B)

## 2. Architecture

### 2.1 Two models, two jobs

**This is an example, not a prescribed architecture.** Teams do not need d1, a two-model design, or a monitor to compete or win. Choose the design that serves your project and the [judging criteria](judging.md).

The reference monitor separates a decision from its explanation:

```text
Local observation
    |
    v
A rule or d1-2B: decide whether anything needs attention
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

The model may propose actions, but code validates and authorizes them. If you use both d1 and the LFM, keep their inference sequential.

### 2.2 Runtimes and routes

| Work | Route |
| --- | --- |
| Reference LFM generation and tools | GenieX `llama_cpp`, cached GGUF, NPU |
| Optional LFM text/image/audio → text | ZETIC Hexagon SDK, local v73 packages |
| Optional d1 gate | Transformers `system_one()`, local snapshot, fp32 CPU |

### 2.3 Compute units

These `--compute` options are GenieX's, not ZETIC's.

| `--compute` | Route | Guidance |
| --- | --- | --- |
| `npu` | Hexagon HTP | Reference generator route |
| `hybrid` | HTP and CPU | Evaluate on your model and workload before choosing |
| `cpu` | CPU | Explicit alternative for compatible models |
| `gpu` | Adreno/OpenCL | Requires a compatible model/runtime configuration |

After a capped generator request, look for `HTP0` in the current server's log. A missing line calls for diagnosis, not an assumption that the CPU was used.

### 2.4 Hardware budget

Budget disk, host RAM, and device buffers separately. Check `df -h /` and `free -h` before staging models. See [Offline readiness: disk first](offline-readiness.md#disk-first).

### 2.5 Optional ZETIC route

**GenieX remains the reference Python/server path.** ZETIC is an option for projects that need a different model or input route, particularly audio or Omni input that the selected GenieX build does not support.

The [ZETIC example](../examples/zetic-lfm/README.md) wraps the prebuilt **Ixian Hexagon SDK 0.2.1** CLI with a capped Python wrapper for LFM3 text/image/WAV → text. It uses separate two-NSP **v73 packages**, not GGUFs, and they are never imported into the GenieX cache. The example pins the SDK release and model revisions and records its verified scope: SDK 0.2.1 and the current packages have been run on the board, while its timing table is from the earlier SDK 0.1.0.

Trade-offs: the one-shot CLI reloads the model on every call, while GenieX keeps it resident. ZETIC's logs show **Hexagon v73 / two NSPs** rather than `HTP0`, and some work stays on the CPU, so do not describe it as entirely on the NPU. Keep output caps, answer checks, and code-side action policy on either runtime. The collection's d1 packages use a separate native API; see [decision routes](decision-models.md#optional-zetic-npu-decisions).

Upstream: [ZETIC's LFM3 and d1 on Dragonwing IQ9 collection](https://huggingface.co/collections/ZETIC-ai/lfm3-and-d1-on-dragonwing-iq9), [Ixian Hexagon SDK releases](https://github.com/zetic-ai/IxianHexagon/releases), and [ZETIC sample apps](https://github.com/zetic-ai/LFM3-zetic-apps).

## 3. Setup

### 3.1 Confirm the board

Start with the hardware-only [preflight](../skills/iq9-preflight/SKILL.md). It is read-only and expects no GenieX, weights, or d1. On the **board**:

```bash
bash skills/iq9-preflight/scripts/preflight.sh --profile board --json
```

Or from the **laptop**, with no repo on the board:

```bash
ssh "$IQ9_HOST" 'bash -s -- --profile board --json' < skills/iq9-preflight/scripts/preflight.sh
```

A failed driver check usually means the packages below are not installed yet, not that flashing failed. Every profile prints a `display` warning: it is a reminder about the [monitor issue](#32-driver-packages), not a detected fault.

After setup and model staging, use `--profile generator` (add `--model 'cached-name:precision'` for another model), or `--profile reference` for the full stack with d1.

### 3.2 Driver packages

**External monitors:** organizers report that the current Adreno APT update causes a GPU-driver issue with external monitors. SSH is not affected. See [Developer Notes](../README.md#external-monitors-and-headless-setups) before using a monitor. Because of that:

- Do not install or update `qcom-adreno1` as part of NPU setup.
- Do not run Qualcomm's `install_ppa_pkgs.sh` unchanged. It installs Adreno packages (its Desktop path also adds a Mesa PPA), runs a broad upgrade, and reboots. No event-specific version of that script is provided here.

The NPU needs only a few packages. On the **board**, refresh the existing APT sources and simulate the install first:

```bash
sudo apt-get update &&
apt-get -s install --no-install-recommends libatomic1 qcom-fastrpc1 libqnn1
```

Add `libglib2.0-0t64` and `ocl-icd-libopencl1` to both commands if GLib or the OpenCL loader is missing. Read the plan: stop if it adds graphics packages, upgrades, or removals you did not expect. Then install interactively, without `-y`:

```bash
sudo apt-get install --no-install-recommends libatomic1 qcom-fastrpc1 libqnn1
```

Do not add package sources.

#### NPU device access

GenieX needs **read and write** access to `/dev/fastrpc-cdsp` and `/dev/fastrpc-cdsp1`. Nodes can exist and be readable while still unusable. On the **board**:

```bash
ls -l /dev/fastrpc-cdsp*
id -nG
getent group fastrpc || echo 'no fastrpc group'
for n in /dev/fastrpc-cdsp /dev/fastrpc-cdsp1; do
  if [ -r "$n" ] && [ -w "$n" ]; then echo "rw ok: $n"; else echo "NO rw: $n"; fi
done
```

1. **Root-only nodes and no `fastrpc` group:** `qcom-fastrpc1` is missing. It installs the udev rules that give the nodes to the `fastrpc` group. Install it as above, then check again.
2. **Group-owned nodes, user not in the group:** run `sudo usermod -aG fastrpc "$USER"`. Group changes apply only to **new** logins: reconnect SSH and re-check `id -nG`. Shells and servers that were already running keep the old groups.
3. **In the group but still no access:** inspect the node's group and mode and the installed udev rules. Do not `chmod` device nodes.

On a freshly flashed image, expect both steps 1 and 2. Preflight's `npu-access` check tests read and write, but passing it is not NPU verification: finish with a capped request and the **current** server's `HTP0` line ([section 5](#5-local-server-openai-compatible)). Restart a server that was started before the group change.

#### Stale APT lists and package-file 404s

A freshly flashed image carries APT indexes from the day it was built. A package download that returns `404 Not Found` usually means the cached index points to a file the source no longer serves, typically for the older QAIRT packages (`qairt-dsp-binaries`, `qairt-libs`, `libqnn1`). It does not mean the board is offline or needs a new PPA.

Recover during online setup:

1. Check what is installed and what APT would install: `dpkg-query -W` and `apt-cache policy`.
2. Run `sudo apt-get update` against the existing sources, then simulate the install again. If the update reports failed sources, diagnose those first.
3. Review the refreshed plan. "N not upgraded" does not call for a broad upgrade. Do not run `apt upgrade`/`dist-upgrade`, add a PPA, change Adreno, use `--fix-missing`, or disable signature or TLS checks.
4. If 404s persist after a clean refresh, report the exact URL and source instead of switching runtime or repository.

**System packages and GenieX's runtime are separate.** GenieX ships its own QAIRT runtime (`geniex version` shows it), which can differ from the QAIRT packages APT installs. Record both versions; neither replaces the other, so install the full package list above.

### 3.3 GenieX CLI

Check `geniex version` and `geniex config get chipset` first. The reference version is v0.10.0; do not replace a working install.

If GenieX is missing, on the **board**:

```bash
curl -fSLo install.sh https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-geniex/install.sh
# Read install.sh before running it.
sh install.sh --version v0.10.0
```

Keep the installer and its archive on the board for recovery.

### 3.4 Python environment for the decision layer

Skip this if the app does not use d1. Check whether the board's Python already has torch:

```bash
python3 -c 'import torch; print(torch.__version__)'
```

Create the environment and install the example's requirements:

```bash
python3 -m venv --system-site-packages ~/.venvs/d1
source ~/.venvs/d1/bin/activate
python -m pip install --dry-run -r examples/system-one-decision/requirements.txt   # review the plan
python -m pip install -r examples/system-one-decision/requirements.txt
```

The requirements pin torchvision to the reference pairing (torch 2.11.0 / torchvision 0.26.0) and leave torch out, so an existing torch is reused. On a fresh image without torch, pip resolves the matching torch as a dependency of torchvision; the dry run shows what it would add and how large the download is. If the board has a different torch, change the torchvision pin to match it instead of replacing torch.

The [System One example](../examples/system-one-decision/README.md) covers the pinned snapshot, the remote-code review, and `check_env.py`.

## 4. Stage your model

Teams receive **USB drives with model assets** and were asked to bring **USB-C adapters**. Use what is already on the board first, then the USB drive. A download is the fallback, not the default.

These commands are for the GenieX route. ZETIC has its [own staging recipe](../examples/zetic-lfm/README.md#stage-once-with-approval).

Check the cache and disk first, on the **board**:

```bash
geniex --skip-update list
df -h /
```

### USB model drive: copy, never move

The drive is the event's supplied media: **copy from it, never move, edit, or delete anything on it.** That means no `mv`, no `rsync --remove-source-files`, no `--delete` sync, and no formatting.

1. **Find the drive.** On the board: `lsblk -o NAME,TRAN,SIZE,FSTYPE,LABEL,MOUNTPOINTS` and `findmnt`. Use the mount path you observe, mounted read-only if you mount it yourself. If the drive is in the laptop instead, copy over SSH; laptop and board paths differ.
2. **Pick one model, not the whole drive.** For the reference generator that is the LFM3-1.7B **QAD-Q4_0 GGUF** directory, with its tokenizer and template files. Check that the board has room for the import.
3. **Import it into the GenieX cache** when `geniex list` does not already show the model. Replace the path with the model directory you found, not the drive root:

   ```bash
   MODEL_USB_DIR='/actual/mounted/path/to/LFM3-model-directory'
   geniex --skip-update pull LiquidAI/LFM3-1.7B-GGUF:Q4_0 \
     --model-hub localfs --local-path "$MODEL_USB_DIR"
   geniex --skip-update list
   ```

   `--local-path` copies into the cache (`~/.cache/geniex/models`) without downloading ([CLI reference](https://geniex.aihub.qualcomm.com/en/run/cli/reference#geniex-pull)). Do not edit the cache by hand, and never re-import a model that is already registered.
4. **If using d1,** copy the **entire pinned Transformers snapshot** to `~/models/d1-2B`: weights, configs, tokenizer, model code, and `REVISION`. A GGUF is not a substitute. Copy real files, not symlinks back to the drive, and do not change the revision pin to match the drive. See the [d1 skill](../skills/iq9-d1-decision-gate/SKILL.md).
5. **Verify.** Compare file sizes or checksums with the source, confirm `geniex list` (or the d1 `REVISION`), then eject the drive and confirm the app starts without it. For the generator, send a capped request and check the current server's `HTP0` line.

If the model is not in the cache, on the board, or on the drive, download it during setup:

```bash
geniex --skip-update pull LiquidAI/LFM3-1.7B-GGUF:Q4_0
```

Never pull or import weights when the app starts.

## 5. Local server (OpenAI-compatible)

On the **board**, run the server in its own terminal:

```bash
bash skills/iq9-geniex-lfm/scripts/serve.sh run
```

It listens on `127.0.0.1:18181`, uses the NPU with a long keepalive, serves cached models only, and logs to `~/geniex-serve.log`. From another board terminal:

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
bash skills/iq9-geniex-lfm/scripts/serve.sh status    # prints the HTP0 device line
```

* Cap every chat call with `max_completion_tokens`; use `max_tokens` on raw completions.
* Check the answer content. A reply can report tokens and still be empty or reasoning-only.
* For direct LFM3-1.7B answers, try `enable_think: false` or the client's `sentence()` template.
* Tag raw prompts so they are unique, retry unusable output once, and return persistent errors as data.
* The model unloads when idle. Warm it up with a capped request before the demo; see [server lifecycle](runtimes.md#server-lifecycle-model-loading-and-idle-unloading).
* Keep the server on loopback.

The standard-library [LFM client](../skills/iq9-geniex-lfm/scripts/lfm_client.py) implements these guards; copy it into your app. [Runtime reference](runtimes.md) lists endpoints and fields. ZETIC does not use this server; its [wrapper](../examples/zetic-lfm/run.py) applies the same guards to the vendor CLI.

## 6. The decision layer

A rule in code is the simplest gate, and the [always-on example](../examples/always-on-agent/README.md) runs with one (`--gate rule`).

If you use d1-2B, run the pinned local snapshot through Transformers in fp32 on the CPU. Load it once and reuse it. Set the offline settings before the imports and pass `local_files_only=True`. Do not route it through GenieX's decision endpoints, and a d1 GGUF does not replace the snapshot. d1 returns zero output tokens by design, unlike an empty LFM reply.

The [decision-layer reference](decision-models.md) covers loading, typed questions, and calibration. The [System One example](../examples/system-one-decision/README.md) shows state, image, and batch calls.

## 7. Choosing a model

Choose on task, format, precision, runtime/NPU support, and memory. Any LFM3-family model is welcome and other LFM models are options; LFM3-1.7B is the examples' default, not an eligibility rule.

For vision or audio, stage the matching assets and use that modality's API. Browse [LiquidAI's published models](../README.md#platform-and-models), check [format, precision, and runtime compatibility](runtimes.md#model-format-and-precision), and test your model on the board; the reference results do not carry over.

## 8. Building an always-on agent

The reference loop is **observe -> decide -> act -> explain -> log**.

1. **Generate only when needed.** A rule or decision gate runs before the LFM is asked for an explanation.
2. **Calibrate on the app's task.** Fit thresholds on labeled states and evaluate on held-out data.
3. **Constrain actions.** Schemas, allowlists, and write-action policy belong in code.
4. **Log each iteration.** Flush JSONL with the observation, decision, executed action, explanation, timing, and errors.
5. **Cap and validate output.** Empty answers, reasoning alone, and zero LFM tokens are failures even when the HTTP request succeeds.
6. **Keep the loop alive.** Input, decision, and explanation failures become logged data, not crashes.
7. **Keep inference sequential.** Do not overlap d1 and the generator without measuring the change.

Start from [Always-on agent](../examples/always-on-agent/README.md), or create an app with the [scaffold](../skills/iq9-always-on-agent/SKILL.md). Use bounded iterations and simulated inputs while adapting it.

## 9. Tool calling

Send OpenAI-style function schemas in `tools` to `/v1/chat/completions`. Validate the returned call envelopes, IDs, names, and arguments before executing anything.

The model proposes; code decides. Apply a policy before every write or real-world action, and report executed actions from the app's own records, not the model's prose. Keep the tool list short and the number of turns bounded.

The [tool-calling example](../examples/tool-calling/README.md) includes the schema, allowlist, policy, execution, and local guard checks.

## 10. Measuring performance

Measure your own workload: cold startup, warm requests, decision latency, loop time, memory, and error rate.

For server requests, use the [metrics collector](../skills/iq9-demo-prep/scripts/collect_metrics.sh). It separates first generated output from first answer content and labels streamed decode timing as an estimate. Do not count SSE chunks as tokens.

The collector's default prompt asks for **one sentence**, so its numbers describe short answers, which are dominated by prefill and understate sustained decode speed. Pass `--prompt` with a representative request. For long answers, set `--max-tokens` as a generous safety cap and check that `finish_reason` is `stop`, not `length`: a capped run measures the cap. Report decode tok/s and end-to-end tok/s separately. See the [demo-prep skill](../skills/iq9-demo-prep/SKILL.md#2-numbers-measure-them-never-quote-the-docs-as-your-own).

For ZETIC, use the [example's JSONL timing records](../examples/zetic-lfm/README.md#measurements-and-verified-scope), and keep model loading separate from generation.

For a local GGUF benchmark, stage the `geniex-bench` that matches the runtime and point it at the file:

```bash
D="$HOME/geniex-bench-linux-arm64-v0.10.0"
export LD_LIBRARY_PATH="$D/lib:$D/lib/llama_cpp:$D/lib/qairt"
"$D/bin/geniex-bench" --plugin llama_cpp --device npu \
  -m /absolute/path/to/model.gguf -r 5 -p 512 -n 128
```

That is five runs, a 512-token prefill, and 128 generated tokens. It does not time d1; time `system_one()` separately with the app's own questions. Process RSS, peak RSS, and device memory are different resources.

Put results in the app's README with the board, runtime, model/precision, workload, sample count, and medians.

## 11. Running offline

Stage models, packages, UI assets, docs, and sample data before the cut. At runtime, load local snapshots and cache entries only.

Rehearse cold startup and the core workflow with every external uplink disconnected. An isolated USB-C link may stay up for SSH and an app web UI, with no internet sharing from the laptop. Before cutting the network, have a control path that does not depend on it: UART or the USB-C link, not SSH over the uplink being cut.

Full checklist: [Offline readiness](offline-readiness.md).

## 12. Troubleshooting

| Symptom | What to inspect | Next step |
| --- | --- | --- |
| `geniex: command not found` | Installed CLI path and shell `PATH` | Add `~/.local/bin` to `PATH`, or install per section 3.3 |
| External monitor stops working after an APT update | Installed Adreno package versions | See [Developer Notes](../README.md#external-monitors-and-headless-setups); SSH and a USB-C web UI still work |
| Missing NPU libraries | Driver packages and the loader error | Install only the missing packages (section 3.2); leave Adreno alone |
| CDSP permission denied | Read **and** write on each node; `fastrpc` group | Follow [NPU device access](#npu-device-access); reconnect SSH and restart the server |
| Package download returns 404 | APT index age | Follow [stale APT lists](#stale-apt-lists-and-package-file-404s) |
| Slow generator or no `HTP0` line | Current server log, compute route, drivers, permissions | Diagnose NPU access; do not silently change compute |
| `serve.sh status` shows no device line | Whether a capped request has run; the log path | Send a capped request; check `~/geniex-serve.log` or `GENIEX_SERVE_LOG` |
| Long or reasoning-only answer | Token cap, prompt template, answer/reasoning fields | Keep the cap, try direct-answer controls, validate the content |
| Empty answer or zero LFM tokens | Response body, prompt uniqueness, cap | Retry once with a fresh tag; log persistent failures, then restart your server |
| d1 request sent to a server endpoint | Integration route | Call `model.system_one()` locally through Transformers |
| Slower first or post-idle request | Weight loading and keepalive | Plan for cold starts and raise the keepalive |
| Benchmark cannot find libraries | Archive layout and `LD_LIBRARY_PATH` | Point the paths at the matching benchmark libraries |
| No space left on device | Cache, snapshots, archives, duplicate copies | Ask before removing files; never delete from the USB drive |
| Python import fails | Interpreter, venv, package versions | Inspect the environment before recreating it |
| d1 loader requests code approval | Snapshot revision and loader options | Review the local model code before `trust_remote_code=True` |
