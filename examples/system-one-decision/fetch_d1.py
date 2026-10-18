"""Download LiquidAI/d1-3B at a pinned commit into a local directory.

The Hub is only needed for this step. After it runs, the example loads from disk.
"""

import argparse
import pathlib

from huggingface_hub import snapshot_download

REPO = "LiquidAI/d1-3B"
# Pinned commit. Review the shipped Python code (modeling_d1.py, api.py, runner.py,
# hybrid.py, prompt.py, lfm2_vl.py) before moving this pin, because trust_remote_code runs it.
REVISION = "051bcc464b01b9f92942b364d9586b0ef5912432"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", default="~/models/d1-3B", help="local directory for the snapshot")
    args = ap.parse_args()

    dest = pathlib.Path(args.dest).expanduser()
    snapshot_download(REPO, revision=REVISION, local_dir=dest)
    (dest / "REVISION").write_text(REVISION + "\n")
    print(f"{REPO}@{REVISION[:12]} -> {dest}")


if __name__ == "__main__":
    main()
