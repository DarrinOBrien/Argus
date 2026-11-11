# Example: ZETIC with LFM3-1.7B and LFM3-Omni-2B

An **optional alternative to GenieX**, not a replacement for the reference stack. Run text generation with LFM3-1.7B, or turn a local image/WAV into text with LFM3-Omni-2B, on the Dragonwing IQ-9075.

**Upstream resources:**

- **Model collection:** [LFM3 and d1 on Dragonwing IQ9](https://huggingface.co/collections/ZETIC-ai/lfm3-and-d1-on-dragonwing-iq9). This example uses the LFM3 packages from [`ZETIC-ai/LFM3`](https://huggingface.co/ZETIC-ai/LFM3), not the collection's d1 route.
- **SDK and sample apps:** [`zetic-ai/LFM3-zetic-apps`](https://github.com/zetic-ai/LFM3-zetic-apps). The staging recipe below pins the SDK/apps and model revisions used in our IQ9 checks.

[`run.py`](run.py) is a standard-library Python wrapper around the **prebuilt vendor CLI**. No compiler, Python ML environment, camera, or microphone is needed. It makes one capped request, checks usage, answer content, natural completion, and current-request Hexagon evidence, then prints a JSONL result. It never downloads assets, starts a server, executes model-proposed actions, or changes GenieX.

## Why use it?

- **Text:** LFM3-1.7B provides another local deployment route to try alongside GenieX.
- **Multimodal:** Omni's text, image, and audio-input paths worked in our IQ9 checks. This is useful for hackathon projects that need local recordings or images, including where the selected GenieX build lacks the required audio/Omni projector support.
- **Keep it small:** use vendor packages and file inputs rather than adding a new server or runtime abstraction. GenieX remains the easiest starting point for the existing OpenAI-compatible Python examples.

The SDK also advertises other capabilities. **This example does not cover video, speech generation, mixed image+audio turns, tool calling, or d1.** The reference d1 gate remains Transformers on CPU.

## Prerequisites and asset layout

- IQ-9075, Ubuntu 24.04 aarch64, Python 3.12, and working FastRPC read/write access. Start with [board access/preflight](../../docs/developer-guide.md#31-confirm-the-board) and [NPU access](../../docs/developer-guide.md#npu-device-access). Use `--profile board`; the GenieX-specific generator profile does not validate ZETIC.
- ZeticMLange Hexagon SDK **0.1.0, Linux ARM64 QCOM**, with `bin/zetic_lfm3_cli` and `lib/libhexrt_v73_skel.so` together in its original layout.
- One or both **ZETIC v73 packages**, not GenieX GGUFs:

  | Package | Inputs covered here | Approximate package size |
  |---|---|---:|
  | `lfm3-1.7b` | Text | 2.73 GB |
  | `lfm3-omni-2b` | Text, image, audio → text | 3.58 GB |

Sizes describe assets, not RAM requirements. Budget for any laptop/board staging copies. A model's parent directory must contain `v73/manifest.json`; the wrapper reads that manifest and rejects unsupported models/targets.

Example board layout (use your actual staged directory):

```text
~/zetic-demo/
  run.py
  sdk/bin/zetic_lfm3_cli
  sdk/lib/libhexrt_v73_skel.so
  models/qualcomm/lfm3-1.7b/v73/...
  models/qualcomm/lfm3-omni-2b/v73/...
  samples/image_count/count.ppm
  samples/asr/jfk.wav
```

### Stage once, with approval

**Inspect local assets and disk first. Ask whether you have the supplied USB model drive and a suitable adapter.** Prefer existing board assets, then compatible local/USB packages. Follow [copy, never move](../../docs/developer-guide.md#usb-model-drive-copy-never-move): inspect resolved paths/symlinks, preserve unrelated files, obtain approval for explicit source/destination paths, and leave every source file intact. Keep SDKs, models, and fixtures on board storage, not removable media at launch.

The [tested apps repository revision](https://github.com/zetic-ai/LFM3-zetic-apps/tree/35acef15824f4df435c36faf6439b2204a89c029) contains the SDK archive and fixtures. Its [IQ9 guide](https://github.com/zetic-ai/LFM3-zetic-apps/blob/35acef15824f4df435c36faf6439b2204a89c029/iq9/README.md) describes building the demo CLI; **we use the archive's prebuilt CLI instead**, so do not install `g++`, `make`, Git, or `hf` on the board just for this example. Reuse working FastRPC packages; do not upgrade graphics drivers or interrupt a shared NPU server to follow this recipe.

The [model repository](https://huggingface.co/ZETIC-ai/LFM3) is manually gated at the time of our check. Arrange participant access before the event. SDK availability and model access are separate from redistribution permission; inspect the SDK `PROVENANCE.json`/`LICENSES` and the model's LFM Open License v1.0 before distributing assets on event media. This repo includes neither SDK binaries nor weights.

**Only if compatible local/USB assets are unavailable and downloads are approved**, stage on the **laptop**, from this repo's root:

```bash
set -euo pipefail
STAGE="$PWD/.iq9-onboarding/zetic-assets"  # use a new staging directory
mkdir -p "$(dirname "$STAGE")"
mkdir "$STAGE"                          # fail rather than overwrite existing staging
GH_REV=35acef15824f4df435c36faf6439b2204a89c029
HF_REV=24a56588cb8a84e25c821217a02ddc437ed7a30c
ARCHIVE=zetic-mlange-hexagon-0.1.0-linux-arm64-qcom.tar.gz
BASE="https://raw.githubusercontent.com/zetic-ai/LFM3-zetic-apps/$GH_REV"
curl -fSL --connect-timeout 5 --max-time 120 "$BASE/sdk/$ARCHIVE" -o "$STAGE/$ARCHIVE"
curl -fSL --connect-timeout 5 --max-time 30 "$BASE/sdk/$ARCHIVE.sha256" -o "$STAGE/$ARCHIVE.sha256"
(cd "$STAGE" && shasum -a 256 -c "$ARCHIVE.sha256")  # Linux: sha256sum -c

tar -tvzf "$STAGE/$ARCHIVE"  # review paths/types before extracting
mkdir "$STAGE/sdk"         # must be new/empty, not a symlink or existing install
tar -xzf "$STAGE/$ARCHIVE" --strip-components=1 -C "$STAGE/sdk"

# Choose only a missing model; repeat for the other model only if needed/approved.
MODEL=lfm3-omni-2b           # or lfm3-1.7b
hf auth whoami             # if needed, log in interactively with hf auth login
hf download ZETIC-ai/LFM3 --revision "$HF_REV" \
  --include "qualcomm/$MODEL/v73/*" --local-dir "$STAGE/models"

# Optional known fixtures. The images are synthetic; JFK audio is public domain.
for FILE in samples/README.md samples/image_count/count.ppm samples/asr/jfk.wav; do
  mkdir -p "$STAGE/$(dirname "$FILE")"
  curl -fSL --connect-timeout 5 --max-time 30 "$BASE/$FILE" -o "$STAGE/$FILE"
done
```

Do not extract archive entries with absolute/`..` paths or links. The verified SDK archive contained regular files/directories. Keep the archive and checksum for recovery; checksums establish integrity against the pinned source, not a publisher signature.

After approval to copy to a **new board directory**, from the **laptop** with your confirmed `IQ9_HOST`:

```bash
set -euo pipefail
ssh "$IQ9_HOST" 'set -eu; mkdir "$HOME/zetic-demo"; mkdir "$HOME/zetic-demo/models"'
scp -r "$STAGE/sdk" "$STAGE/samples" "$IQ9_HOST":zetic-demo/
scp -r "$STAGE/models/qualcomm" "$IQ9_HOST":zetic-demo/models/
scp examples/zetic-lfm/run.py "$IQ9_HOST":zetic-demo/
```

Use a separate terminal for long downloads/copies and check exit statuses. If a destination already exists, stop and inspect it; do not merge or replace it blindly. If the assets are already staged, skip these copies and point `--sdk`/`--model` at them instead. No HF token needs to be copied to the board.

On the **board**, verify each selected package before its first request:

```bash
set -euo pipefail
cd ~/zetic-demo
MODEL=lfm3-omni-2b           # repeat for lfm3-1.7b if staged
(cd "models/qualcomm/$MODEL/v73" && sha256sum -c SHA256SUMS)
export LD_LIBRARY_PATH="$PWD/sdk/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
timeout 180s sdk/bin/zetic_lfm3_cli info --model "models/qualcomm/$MODEL" --verify --verbose
```

## Run on the board

From the staged directory (`~/zetic-demo` in this example):

```bash
SDK="$PWD/sdk"
TEXT="$PWD/models/qualcomm/lfm3-1.7b"
OMNI="$PWD/models/qualcomm/lfm3-omni-2b"

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

Use only commands for models you staged. Images must be exactly **512×512 RGB**; the vendor SDK decodes PPM/PNG/JPEG but does not resize. Audio is WAV, **up to 30 seconds**; supply a short clip rather than relying on truncation. Only English speech recognition was checked here. Sensors, recording, playback, resizing, video, and speech output are outside this example.

Each invocation prints one JSON object containing `ok`, `text`, completion usage, `finish_reason`, `timings`, device evidence, raw CLI output, and separate proposals/actions/errors. Exit **0** means the guards passed; **2** means an unusable/truncated answer, input/runtime error, missing device evidence, timeout, or log-write failure. Non-empty text is not proof of factual correctness. There is no automatic retry or restart; diagnose errors, then retry at most once if appropriate.

`--max-tokens` defaults to 256 (allowed 1–1024); `--timeout` defaults to 120 seconds **including model loading**. `--log` appends a flushed JSONL record. `--help` is available without a board/runtime. For a Python app, import `run.py` and call `run(sdk, model, prompt, ...)`; errors are returned as data.

**Device check:** current CLI logs must show `hexrt open ... v73 ... HEXRT_NSP2=1` and the selected model loaded as v73. ZETIC uses its own Hexagon runtime, so do not look for GenieX's `HTP0` label here. Logs also show CPU head work; this is not entirely-NPU execution. Missing evidence is a failure to diagnose, not permission to switch compute routes. Keep inference sequential with other models and do not stop shared servers without approval.

## Measurements and verified scope

On **2026-11-10**, IQ-9075, Ubuntu 24.04 aarch64, SDK **0.1.0/runtime `61ba260`**, v73 packages with **`w4lpbq` language-model weights**:

- The published wrapper was checked on this board with four bounded requests: text on each model, then Omni image and audio. All returned positive usage, natural completion, and current-request Hexagon evidence.
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

The wrapper launches only local files and has no downloads, installs, cloud calls, or UI dependencies. Native SDK/model startup and the above IQ9 requests were tested **while connected**. **A network-off cold-start rehearsal has not been performed.** Follow [offline readiness](../../docs/offline-readiness.md) with explicit approval and a tested UART/isolated USB-C control path before claiming an offline demo. Offline environment variables or local paths alone are not that proof.

## Local checks

```bash
# From this repo's root; mocks only, no weights or SDK required.
python3 -m unittest discover -s examples/zetic-lfm -p 'test_*.py' -v
python3 skills/iq9-offline-rehearsal/scripts/offline_audit.py examples/zetic-lfm/run.py
```
