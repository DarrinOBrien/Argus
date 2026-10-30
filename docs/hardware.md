# Hardware — Qualcomm Dragonwing IQ-9075 EVK

The event uses the **IQ-9075 EVK only**. Markers: ✅ confirmed in Qualcomm docs · 🧪 checked on a reference board · ⚠️ verify.

## Board

| Item | Value | Source |
|---|---|---|
| Board | Qualcomm Dragonwing IQ-9075 EVK | ✅ |
| SoC | QCS9075 | ✅ |
| NPU | Hexagon **v73** (HTP), two CDSP nodes | ✅ Dragonwing tutorial · 🧪 |
| Memory | 36 GB LPDDR5 (the OS reports 34 GiB) | ✅ spec · 🧪 reading |
| CPU | 8 cores | 🧪 |
| OS | Ubuntu 24.04.4 LTS (`aarch64`) | 🧪 · ✅ (Dragonwing tutorials use 24.04) |
| Compute claim | 100 dense INT8 TOPS; "13B-parameter LLM / GenAI models" | ✅ Qualcomm highlights (marketing figure, not tested) |

## Requirements

- At least **12 GB free storage** and **12 GB RAM** for GenieX. ✅
- Outbound HTTPS for installation and model pulls:
  - `qaihub-public-assets.s3.us-west-2.amazonaws.com` (GenieX installer and benchmark archives) ✅
  - `huggingface.co` (model downloads) ✅
  - PyPI (`transformers`, `geniex`) ✅

## Software this guide expects

| Component | Version | Set up in |
|---|---|---|
| GenieX CLI | v0.10.0 migration target | [developer guide §3.3](developer-guide.md#33-geniex-cli) |
| NPU driver packages | `qcom-adreno1`, `qcom-fastrpc1`, `libqnn1`, plus base APT packages | [§3.2](developer-guide.md#32-driver-packages) |
| Python 3.12 venv with transformers | transformers 5.19.0 observed | [§3.4](developer-guide.md#34-python-environment-for-the-decision-layer) |
| torch, torchvision | CPU builds (2.11.0, 0.26.0 observed). No CUDA device, so Path A runs on the CPU. | §3.4 |

## First-time setup

Follow the Qualcomm guide: https://dragonwingdocs.qualcomm.com/Ubuntu/devices/iq9075-evk/set-up-the-device ✅

The event provides a numbered, powered, networked kit per team, with a camera, mic, or sensor bundle attached. ✅ (event brief). The exact peripheral list is ⚠️ **TBD: confirm with the event lead.**

## Quick checks

```bash
uname -m                    # aarch64
df -h /                     # disk: plan before pulling
free -h                     # RAM
ls /dev/fastrpc-cdsp*       # two CDSP nodes on IQ-9075 ✅
geniex version              # expect v0.10.0 for the LFM3 migration
geniex list                 # what is already in the GenieX cache
```

## Known gaps

- We don't plan to use external sensors. The always-on agent reads the board's own thermal zones (see `examples/always-on-agent`). The event's camera, microphone, or sensor bundle is still TBD with the event lead and is optional for us.
- ⚠️ The server's CPU path decodes far slower than the bench's CPU path (2.8 vs 27.1 tok/s). See [`runtimes.md`](runtimes.md#known-gap-server-cpu-decode).
