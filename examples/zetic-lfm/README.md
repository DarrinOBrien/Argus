# Example: ZETIC Ixian with LFM3 on IQ9

An **optional alternative to GenieX** on the Dragonwing IQ-9075. The wrapper accepts the four LFM3 generators in ZETIC's IQ9 collection, with text, one local image, or one WAV as supported by the selected package. The existing GenieX examples remain the reference server integration.

**Upstream resources:**

- **Model collection:** [LFM3 and d1 on Dragonwing IQ9](https://huggingface.co/collections/ZETIC-ai/lfm3-and-d1-on-dragonwing-iq9), now with one public repository per model.
- **SDK:** [Ixian Hexagon SDK](https://github.com/zetic-ai/IxianHexagon), release **0.2.1**. The collection's model cards require 0.2.1 or later; this recipe pins 0.2.1.
- **Fixtures:** [`zetic-ai/LFM3-zetic-apps`](https://github.com/zetic-ai/LFM3-zetic-apps). Its older IQ9 guide uses the previous SDK and gated monolithic model repository; use the staging instructions here for the current collection.

**Verification boundary:** the current SDK/package instructions were checked against upstream release metadata, headers, CLI flag/log strings, and package manifests on 2026-11-11. Local wrapper tests use mocks. **SDK 0.2.1 and the current package revisions have since been run on the IQ-9075.** The timings below were measured with SDK 0.1.0 and the older packages and have not been re-measured, so treat them as historical.

[`run.py`](run.py) is a standard-library Python wrapper around the **prebuilt vendor CLI**. No compiler, Python ML environment, camera, or microphone is needed. It makes one capped request, checks usage, answer content, natural completion, and current-request Hexagon evidence, then prints a JSONL result. It never downloads assets, starts a server, executes model-proposed actions, or changes GenieX.

## Why use it?

- **Text:** LFM3-1.7B provides another local deployment route to try alongside GenieX.
- **Multimodal:** Omni's text, image, and audio-input paths worked in our IQ9 checks. This is useful for hackathon projects that need local recordings or images, including where the selected GenieX build lacks the required audio/Omni projector support.
- **Keep it small:** use vendor packages and file inputs rather than adding a new server or runtime abstraction. GenieX remains the easiest starting point for the existing OpenAI-compatible Python examples.

The SDK also advertises other capabilities. **This wrapper does not cover video, speech generation, mixed image+audio turns, tool calling, or d1.** The reference d1 gate remains Transformers on CPU; the collection's separate NPU decision route is described below.

## Collection coverage

The following are vendor-advertised capabilities, not new board results from this repository. Each link pins the model repository revision inspected for this update; package manifests report version **0.2.0**. Use the full revision from the link with `hf download --revision` when selecting another model.

| Model repository (pinned) | Package directory | Inputs → outputs | Integration here |
|---|---|---|---|
| [LFM3-1.7B-IQ9](https://huggingface.co/ZETIC-ai/LFM3-1.7B-IQ9/tree/585c80f796fa599d8c6aeb7e7948ae9ddeeca0dd) | `lfm3-1.7b` | Text → text | Wrapper |
| [LFM3-VL-2B-IQ9](https://huggingface.co/ZETIC-ai/LFM3-VL-2B-IQ9/tree/4b97823becd3c17a050aef419924af48075eb199) | `lfm3-vl-2b` | Text/image/video → text | Wrapper: text or one image |
| [LFM3-Audio-2B-IQ9](https://huggingface.co/ZETIC-ai/LFM3-Audio-2B-IQ9/tree/5b4570b9de05bf511826b128d729b38ca29a5b79) | `lfm3-audio-2b` | Text/audio → text/speech | Wrapper: text or one WAV → text |
| [LFM3-Omni-2B-IQ9](https://huggingface.co/ZETIC-ai/LFM3-Omni-2B-IQ9/tree/01d43f16d72df24a2f4239914a3768abe3d4ef1e) | `lfm3-omni-2b` | Text/image/audio/video → text/speech | Wrapper: text, one image, or one WAV → text |
| [d1-2B-IQ9](https://huggingface.co/ZETIC-ai/d1-2B-IQ9/tree/c82c9736e92a3cafcfbac7625ead99ad99138a89) | `d1-2b` | Text/image → decisions | Vendor `Decision` API; no wrapper integration |
| [d1-Omni-2B-IQ9](https://huggingface.co/ZETIC-ai/d1-Omni-2B-IQ9/tree/3377c9a8c35c676f1ba5edc376c4eb7fd929d8f6) | `d1-omni-2b` | Text/image/audio → decisions | Vendor `Decision` API; no wrapper integration |

LFM3 packages offer `v73` (two NSPs) and `v73-1nsp`. **This wrapper selects and validates only `v73` with two NSPs.** The d1 packages have a `v73` directory but the vendor documents a one-NSP decision pass; do not apply the generator's two-NSP evidence check to d1.

### Optional ZETIC d1 route

ZETIC supplies `zetic_d1_cli` and the C++ `Decision::systemOne` API in `zetic_decision.h` (namespace `zetic::ixian`). They accept typed yes/no, choice, and score questions, up to 16 per pass, with a documented 1,024-token pass budget including state, media, and questions. These are native ZETIC packages, not the pinned Transformers snapshot or GenieX decision endpoints. See the [vendor SDK guide](https://github.com/zetic-ai/IxianHexagon#d1-decisions) for integration.

This repo's Python agents and calibration `--score` path still use CPU Transformers. A ZETIC integration must validate typed results and current-request device logs, return errors as data, enforce action policy in code, log flushed JSONL, and calibrate/evaluate the selected quantized package on task-representative held-out data. Do not reuse CPU thresholds or change the CPU snapshot pin. Keep models sequential until the chosen scheduling has been measured. ZETIC d1 has not been board-verified here.

## Prerequisites and asset layout

- IQ-9075, Ubuntu 24.04 aarch64, Python 3.12, and working FastRPC read/write access. Start with [board access/preflight](../../docs/developer-guide.md#31-confirm-the-board) and [NPU access](../../docs/developer-guide.md#npu-device-access). Use `--profile board`; the GenieX-specific generator profile does not validate ZETIC.
- Ixian Hexagon SDK **0.2.1, Linux ARM64 QCOM IQ9**, with `bin/zetic_lfm3_cli`, `lib/libzetic_ixian_hexagon.so`, and `lib/libhexrt_v73_skel.so` together in its original layout.
- A selected **ZETIC v73 generator package**, not a GenieX GGUF:

  | Package | Inputs covered here | Approximate package size |
  |---|---|---:|
  | `lfm3-1.7b` | Text | 2.73 GB |
  | `lfm3-vl-2b` | Text, image → text | 3.10 GB |
  | `lfm3-audio-2b` | Text, audio → text | 3.20 GB |
  | `lfm3-omni-2b` | Text, image, audio → text | 3.58 GB |

Sizes describe assets, not RAM requirements. Budget for any laptop/board staging copies. A model's parent directory must contain `v73/manifest.json`; the wrapper reads that manifest and rejects unsupported models/targets.

Example board layout (use your actual staged directory):

```text
~/zetic-demo/
  run.py
  sdk/bin/zetic_lfm3_cli
  sdk/lib/libhexrt_v73_skel.so
  models/lfm3-1.7b/v73/...
  models/lfm3-omni-2b/v73/...
  samples/image_count/count.ppm
  samples/asr/jfk.wav
```

### Stage once, with approval

**Inspect local assets and disk first. Ask whether you have the supplied USB model drive and a suitable adapter.** Prefer existing board assets, then compatible local/USB packages. Follow [copy, never move](../../docs/developer-guide.md#usb-model-drive-copy-never-move): inspect resolved paths/symlinks, preserve unrelated files, obtain approval for explicit source/destination paths, and leave every source file intact. Keep SDKs, models, and fixtures on board storage, not removable media at launch.

Use the [Ixian 0.2.1 release archive](https://github.com/zetic-ai/IxianHexagon/releases/tag/0.2.1) for the SDK and the [pinned apps repository](https://github.com/zetic-ai/LFM3-zetic-apps/tree/35acef15824f4df435c36faf6439b2204a89c029) only for fixtures. **We use the prebuilt CLI**, so do not install `g++`, `make`, Git, or `hf` on the board just for this example. Reuse working FastRPC packages; do not upgrade graphics drivers or interrupt a shared NPU server to follow this recipe.

The six IQ9 model repositories were public and ungated at the time of this review. The older `ZETIC-ai/LFM3` repository is a separate, legacy source. SDK availability and model access are separate from redistribution permission; inspect the SDK `PROVENANCE.json`/`LICENSES` and each model's LFM Open License v1.0 before distributing assets on event media. This repo includes neither SDK binaries nor weights.

**Only if compatible local/USB assets are unavailable and downloads are approved**, stage on the **laptop**, from this repo's root:

```bash
set -euo pipefail
STAGE="$PWD/.iq9-onboarding/zetic-assets"  # use a new staging directory
mkdir -p "$(dirname "$STAGE")"
mkdir "$STAGE"                          # fail rather than overwrite existing staging
GH_REV=35acef15824f4df435c36faf6439b2204a89c029
ARCHIVE=ixian-hexagon-0.2.1-linux-arm64-qcom-iq9.tar.gz
RELEASE=https://github.com/zetic-ai/IxianHexagon/releases/download/0.2.1
BASE="https://raw.githubusercontent.com/zetic-ai/LFM3-zetic-apps/$GH_REV"
curl -fSL --connect-timeout 5 --max-time 120 "$RELEASE/$ARCHIVE" -o "$STAGE/$ARCHIVE"
curl -fSL --connect-timeout 5 --max-time 30 "$RELEASE/$ARCHIVE.sha256" -o "$STAGE/$ARCHIVE.sha256"
(cd "$STAGE" && shasum -a 256 -c "$ARCHIVE.sha256")  # Linux: sha256sum -c

tar -tvzf "$STAGE/$ARCHIVE"  # review paths/types before extracting
mkdir "$STAGE/sdk"         # must be new/empty, not a symlink or existing install
tar -xzf "$STAGE/$ARCHIVE" --strip-components=1 -C "$STAGE/sdk"

# Choose only a missing model; repeat for the other model only if needed/approved.
MODEL=lfm3-1.7b
MODEL_REPO=ZETIC-ai/LFM3-1.7B-IQ9
HF_REV=585c80f796fa599d8c6aeb7e7948ae9ddeeca0dd
# For another model, change all three values using the collection table above.
# Requires hf on the laptop; install it only with approval if missing.
hf download "$MODEL_REPO" --revision "$HF_REV" \
  --include 'v73/*' LICENSE README.md --local-dir "$STAGE/models/$MODEL"

# Optional known fixtures. The images are synthetic; JFK audio is public domain.
for FILE in samples/README.md samples/image_count/count.ppm samples/asr/jfk.wav; do
  mkdir -p "$STAGE/$(dirname "$FILE")"
  curl -fSL --connect-timeout 5 --max-time 30 "$BASE/$FILE" -o "$STAGE/$FILE"
done
```

Do not extract archive entries with absolute/`..` paths or links. Keep the archive and checksum for recovery; checksums establish integrity against the pinned source, not a publisher signature. The inspected 0.2.1 archive SHA-256 is `afb426755bb793efd929fc1a8e37fb7a5bd2ff3133576d5f3e22de8bb7fe8b0b`.

After approval to copy to a **new board directory**, from the **laptop** with your confirmed `IQ9_HOST`:

```bash
set -euo pipefail
ssh "$IQ9_HOST" 'set -eu; mkdir "$HOME/zetic-demo"'
scp -r "$STAGE/sdk" "$STAGE/models" "$IQ9_HOST":zetic-demo/
# Only if the optional fixtures were staged:
scp -r "$STAGE/samples" "$IQ9_HOST":zetic-demo/
scp examples/zetic-lfm/run.py "$IQ9_HOST":zetic-demo/
```

Use a separate terminal for long downloads/copies and check exit statuses. If a destination already exists, stop and inspect it; do not merge or replace it blindly. If the assets are already staged, skip these copies and point `--sdk`/`--model` at them instead. No HF token needs to be copied to the board.

On the **board**, verify each selected package before its first request:

```bash
set -euo pipefail
cd ~/zetic-demo
MODEL=lfm3-1.7b             # select the model you actually staged
(cd "models/$MODEL/v73" && sha256sum -c SHA256SUMS)
export LD_LIBRARY_PATH="$PWD/sdk/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
timeout 180s sdk/bin/zetic_lfm3_cli info --model "models/$MODEL" --target v73 --verify --verbose
```

## Run on the board

From the staged directory (`~/zetic-demo` in this example):

```bash
SDK="$PWD/sdk"
TEXT="$PWD/models/lfm3-1.7b"
OMNI="$PWD/models/lfm3-omni-2b"

# Text model: a short first check, then a reasonable longer answer.
python3 run.py --sdk "$SDK" --model "$TEXT" --max-tokens 64 \
  --prompt 'What is the capital of France? Answer in one short sentence.'
python3 run.py --sdk "$SDK" --model "$TEXT" --max-tokens 512 \
  --prompt 'Why is the sky blue? Explain Rayleigh scattering as well, including why sunsets look red. Use about 150 words and answer directly.'

# Omni: text, a known image, then speech recognition from a local recording.
python3 run.py --sdk "$SDK" --model "$OMNI" --max-tokens 64 \
  --prompt 'What is the capital of France? Answer in one short sentence.'
python3 run.py --sdk "$SDK" --model "$OMNI" --max-tokens 64 \
  --image samples/image_count/count.ppm --prompt 'How many black circles are in the image?'
python3 run.py --sdk "$SDK" --model "$OMNI" --max-tokens 128 \
  --audio samples/asr/jfk.wav --prompt 'Transcribe the audio.' --log zetic-results.jsonl
```

Use only commands for models you staged. For VL, use its local model directory with the text/image commands; for Audio, use its directory with the text/WAV commands. Images must be exactly **512×512 RGB**; the vendor SDK decodes PPM/PNG/JPEG/BMP but does not resize. Audio is WAV, **up to 30 seconds**; supply a short clip rather than relying on truncation. Only English speech recognition was checked with the older Omni stack. Sensors, recording, playback, resizing, video, and speech output are outside this wrapper.

Each invocation prints one JSON object containing `ok`, `text`, completion usage, `finish_reason`, `timings`, device evidence, raw CLI output, and separate proposals/actions/errors. Exit **0** means the guards passed; **2** means an unusable/truncated answer, input/runtime error, missing device evidence, timeout, or log-write failure. Non-empty text is not proof of factual correctness. There is no automatic retry or restart; diagnose errors, then retry at most once if appropriate.

`--max-tokens` defaults to 256 (allowed 1–1024); `--timeout` defaults to 120 seconds **including model loading**. `--log` appends a flushed JSONL record. `--help` is available without a board/runtime. For a Python app, import `run.py` and call `run(sdk, model, prompt, ...)`; errors are returned as data.

**Device check:** current CLI logs must show `hexrt open ... v73 ... HEXRT_NSP2=1` and the selected model loaded as v73. ZETIC uses its own Hexagon runtime, so do not look for GenieX's `HTP0` label here. Logs also show CPU head work; this is not entirely-NPU execution. Missing evidence is a failure to diagnose, not permission to switch compute routes. Keep inference sequential with other models and do not stop shared servers without approval.

## Measurements and verified scope

**Historical evidence, before the Ixian 0.2.1 update.** On **2026-11-10**, IQ-9075, Ubuntu 24.04 aarch64, SDK **0.1.0/runtime `61ba260`**, v73 packages with **`w4lpbq` language-model weights**:

- The earlier wrapper was checked on this board with four bounded requests: text on LFM3-1.7B and Omni, then Omni image and audio. All returned positive usage, natural completion, and current-request Hexagon evidence. SDK 0.2.1 and the current package revisions have since been run on the board; these timings were not re-measured.
- Omni: one text, one synthetic-image, and one 11-second WAV request returned useful answers (Paris, three circles, recognizable JFK transcription), within caps of 64/64/128 tokens. This is a smoke check, not a quality evaluation.
- Text-model comparison: the longer prompt shown above (sky blue, Rayleigh scattering, red sunsets, about 150 words), temperature zero, 512-token cap, one excluded warm-up per runtime. Medians of **three successful answers**:

  | Runtime/package | Generation TTFT | Decode tok/s | Output tokens | Successful / attempted |
  |---|---:|---:|---:|---:|
  | GenieX v0.10.0, LFM3-1.7B GGUF Q4_0 | 93.6 ms | 40.4 | 135 | 3 / 4 |
  | ZETIC SDK 0.1.0, LFM3-1.7B `w4lpbq` | 53.7 ms | 45.7 | 174 | 3 / 3 |

These are **runtime-reported** TTFT/decode values, excluding model loading, with potentially different instrumentation. One GenieX request exhausted its cap on reasoning with no answer; it was excluded from successful-run medians and an additional request succeeded. ZETIC decode samples ranged from 44.84 to 58.47 tok/s. Different quantizations, templates, repetition defaults, output lengths, and offload paths mean this is not a runtime-only comparison or a general performance claim.

GenieX used a resident server (112.3 ms median client time to first answer). ZETIC used fresh CLI processes: **3.299 seconds median model loading** before generation. This wrapper also reloads per invocation. For a frequent monitor, the vendor C++ SDK can keep a model loaded; a resident integration is not implemented or measured here. The existing GenieX HTTP metrics collector does not measure ZETIC; use the wrapper's JSONL `timings`, exclude failed/cap-hit samples, distinguish loading from generation, and report sample counts and medians for your own workload.

Pinned sources: apps repo `35acef15824f4df435c36faf6439b2204a89c029`; HF packages `24a56588cb8a84e25c821217a02ddc437ed7a30c`. Model source revisions: LFM3-1.7B `40ebe0aa6662c9d40389c2f5d565b6a2c6aebacd`; Omni `ce2458cbce4ad970f92032ed94e3d18d30b04f9c`. Re-test other SDK builds/packages rather than transferring these results.

## Offline status

The wrapper launches only local files and has no downloads, installs, cloud calls, or UI dependencies. The older SDK 0.1.0/model startup and the above IQ9 requests were tested **while connected**. The current 0.2.1 route has since been run on the board. **A network-off cold-start rehearsal is not recorded here.** Follow [offline readiness](../../docs/offline-readiness.md) with explicit approval and a tested UART/isolated USB-C control path before claiming an offline demo. Offline environment variables or local paths alone are not that proof.

## Local checks

```bash
# From this repo's root; mocks only, no weights or SDK required.
python3 -m unittest discover -s examples/zetic-lfm -p 'test_*.py' -v
python3 skills/iq9-offline-rehearsal/scripts/offline_audit.py examples/zetic-lfm/run.py
```
