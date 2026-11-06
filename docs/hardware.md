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
| NPU driver packages | `qcom-adreno1`, `qcom-fastrpc1`, `libqnn1`, plus base libraries | [Section 3.2](developer-guide.md#32-driver-packages) |
| Python | 3.12 | [Section 3.4](developer-guide.md#34-python-environment-for-the-decision-layer) |
| Optional d1 environment | Transformers 5.19+, torch, torchvision, Pillow | [Section 3.4](developer-guide.md#34-python-environment-for-the-decision-layer) |

Reuse the board's existing torch installation when creating the d1 environment. Match torchvision to that torch version rather than replacing torch unnecessarily. d1 runs on the CPU in fp32; the reference LFM generator runs on the NPU.

## First-time setup

Follow the [Qualcomm IQ-9075 setup guide](https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device) for board setup. Flashing, camera pipelines, and model conversion are outside this repository's scope.

Before installing or changing system software, inspect the current setup and obtain approval from the board owner.

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
