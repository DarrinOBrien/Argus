# Hardware - Qualcomm Dragonwing IQ-9075 EVK

The hackathon uses the **Dragonwing IQ-9075 EVK.**

## Board

| Item | Value |
| --- | --- |
| Board | Qualcomm Dragonwing IQ-9075 EVK |
| SoC | QCS9075 |
| NPU | Hexagon v73 (HTP) |
| Memory | 36 GB LPDDR5 |
| CPU | 8 cores |
| OS | Ubuntu 24.04, aarch64 |

External sensors are **optional and not provided**. Participants may bring their own camera, microphone, or other sensors. Projects can also use simulated inputs, local files/events, or the board's internal thermal readings.

## Display and headless access

Organizers report a GPU-driver issue with external monitors after the current Adreno APT update. Read [Developer Notes](../README.md#external-monitors-and-headless-setups) before using a monitor, and do not install or update `qcom-adreno1` for the NPU.

SSH is not affected. A configured, isolated USB-C network link can carry SSH and a board-hosted app web UI during the network-off demo, without laptop internet sharing/forwarding. See [offline access and rehearsal](offline-readiness.md#display-and-usb-c-access).

## Requirements

- Plan disk and memory for the selected models, their runtime, and the app. Weight-file size is not the same as runtime memory use.
- Use outbound HTTPS during setup to stage packages, model files, documentation, and sample data. The final demo must run without the network.
- Keep a local copy of any UI assets; do not depend on a CDN.

Common setup sources:

- `qaihub-public-assets.s3.us-west-2.amazonaws.com`: GenieX installer and archives
- `huggingface.co`: model files and model cards
- PyPI: Python dependencies

## Software this guide expects

| Component | Reference configuration | Set up in |
|---|---|---|
| GenieX CLI | v0.10.0 | [Developer guide section 3.3](developer-guide.md#33-geniex-cli) |
| NPU driver packages | `qcom-fastrpc1`, `libqnn1`, plus base libraries; see Adreno monitor warning above | [Section 3.2](developer-guide.md#32-driver-packages) |
| Python | 3.12 | [Section 3.4](developer-guide.md#34-python-environment-for-the-decision-layer) |
| Optional d1 environment | Transformers 5.19+, torch, torchvision, Pillow | [Section 3.4](developer-guide.md#34-python-environment-for-the-decision-layer) |

Reuse the board's existing torch installation when creating the d1 environment. Match torchvision to that torch version rather than replacing torch unnecessarily. d1 runs on the CPU in fp32; the reference LFM generator runs on the NPU.

## First-time setup

Start with [board access and internet for setup](developer-guide.md#0-board-access-and-internet-for-setup): use the micro-USB debug UART when SSH is not yet available, configure Wi-Fi with `nmcli` or use Ethernet, and verify setup connectivity from the board. Event UART/SSH login is `ubuntu` / `liquidxqualcomm`; the upstream initial password differs.

These steps adapt the [Qualcomm Ubuntu IQ-9075 setup guide](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device). Flashing, camera pipelines, and model conversion are outside this repository's scope.

Inspect the current setup before installing or changing system software.

## Quick checks

Run on the board:

```bash
uname -m                    # aarch64
df -h /                     # available disk space
free -h                     # available memory
ls /dev/fastrpc-cdsp*        # CDSP device nodes
geniex version
geniex list                 # registered cached models
```

The read-only [preflight script](../skills/iq9-preflight/SKILL.md) groups these checks by app configuration. Choose `reference` for the full example stack, `generator` for a cached generator without d1, or `board` for hardware checks.

For NPU execution, send a capped request and inspect the current server's device/offload log for `HTP0`. A missing log line calls for investigation; do not assume CPU fallback or change compute routes silently.
