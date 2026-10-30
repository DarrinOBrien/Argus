# Offline Readiness

The event ends with **network isolation**. Everything a demo needs must already be on the board. The brief requires that all packages, docs, model files, and sample data be mirrored locally, and that the isolation be rehearsed. ✅ (event brief)

Markers: ✅ confirmed · 🧪 measured on the reference board · ⚠️ verify.

## Disk first

Check free space before every pull:

```bash
df -h /
geniex list
```

Staging budget for the models this event uses (see [`models.md`](models.md)):

| Item | Approx. size | Needed for |
|---|---:|---|
| LFM3-1.7B Q4_0 | ~1.05 GB | generator and tools |
| d1-2B safetensors | 3.84 GB | Path A |
| Python venv and wheels | small, plus torchvision | Path A |

Remove unused cached models only after checking them with `geniex list`. ✅ (`geniex remove <model>[:<precision>]`)

## Before the network goes down

### Software

- [ ] GenieX CLI installed, and `geniex version` shows **v0.10.0**. ⚠️ Complete the board rehearsal before treating it as verified. Don't swap versions between rehearsal and event.
- [ ] Keep a copy of the GenieX installer and its binary archive for a reinstall (`install.sh` and `geniex-cli-linux-arm64-v0.10.0.tar.gz`).
- [ ] Driver packages installed: `qcom-adreno1`, `qcom-fastrpc1`, `libqnn1`, plus the base APT packages. ✅
- [ ] Keep an offline copy of the `geniex` wheel if you use the Python SDK: `python -m pip download geniex -d ~/wheels`. ⚠️ The wheel fetches SDK libraries when installed, so test an offline install before relying on it. The Python SDK is not used by the verified routes.
- [ ] Keep wheels for the decision-layer packages: `python -m pip download -r examples/system-one-decision/requirements.txt -d ~/wheels`. ⚠️ (not yet tested offline)
- [ ] Keep the benchmark archive (`geniex-bench-linux-arm64-v0.10.0.tar.gz`) if you plan to measure on the board.

### Models

- [ ] LFM3-1.7B Q4_0 in the cache, confirmed by `geniex list`. ⚠️
- [ ] d1-2B snapshot at `~/models/d1-2B`, with `REVISION` matching `10e7671d44e4`. Run `python examples/system-one-decision/check_env.py`.
- [ ] Review the code the d1 repo ships before running it, because `trust_remote_code=True` executes it. We reviewed revision `10e7671d44e4`. ✅
- [ ] Check the license on every model you show. ✅

### Data and docs

- [ ] Labeled states for tuning the d1 threshold, in a folder of your choice. Board telemetry logs from `examples/always-on-agent` or your own. ⚠️
- [ ] Clone this repo onto the board, including `docs/` and `examples/`. ✅

## Code rules

- **Load from local paths.** A Hugging Face repo ID downloads on first use, which fails with the network off. ✅ (Python SDK docs)
- **Path A uses local files only.** It loads `~/models/d1-2B` from disk and needs no server. The Hub is used only by `fetch_d1.py`, once, before the network goes down. ✅
- **No runtime network calls.** No telemetry, no model-check calls, no CDN assets in any UI. ⚠️ (check your dependencies)

## Rehearsal: network-off test

Run the whole loop at least once with the network removed:

1. Unplug the Ethernet or disable Wi-Fi on the board. Confirm with `ping -c 1 huggingface.co`, which should fail.
2. Start `geniex serve`, then the app, from a cold boot.
3. Run the core loop end to end. The local log should show every decision, and the explanations where triggered.
4. Confirm the NPU is in use with `GGML_HEX_VERBOSE=1`. ✅
5. Record time to first token, decode speed, and memory for the judges, then add them to [`models.md`](models.md).

## Recovery drill

Rehearse at T-1, per the brief, and keep a spare path:

- [ ] A second generator you can switch to in one command. ⚠️
- [ ] A recorded run of the decision log, in case a sensor or camera fails. ✅
- [ ] Know where the local log lives, so you can show it if the live demo breaks. ✅

## Common failures

| Failure | Cause | Fix |
|---|---|---|
| Works online, fails offline | Model fetched by repo ID | Use the local `.gguf` in the cache or the local snapshot at `~/models/d1-2B` |
| Install fails offline | Install-time fetch | Install before the network drops; keep the wheels and archives |
| Generator runs slow, no Hexagon lines | Silent CPU fallback | Fix the driver packages and recheck with `GGML_HEX_VERBOSE=1` ✅ |
| Extra `…-QAD-Q4_0.gguf` in the cache | Re-pull on v0.4.0 | Remove it as described in [`runtimes.md`](runtimes.md#pitfalls) ✅ |
| `No space left on device` | Staged models exceed free disk | `geniex list`, then remove unused models ✅ |
| Server answers nothing | Model not pulled, or `geniex serve` not running | `geniex list`, then `geniex serve` ✅ |
| Replies with `completion_tokens: 0` after several identical requests (v0.8.0) | Server state; restarting clears it | Restart `geniex serve`; vary the prompt. See [`runtimes.md`](runtimes.md#known-gap-zero-token-responses-on-v080) ⚠️ |
