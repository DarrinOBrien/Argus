"""Download LiquidAI/d1-2B at a pinned commit into a local directory.

The Hub is only needed for this step. After it runs, the example loads from disk.
"""

import argparse
import pathlib

from huggingface_hub import snapshot_download

REPO = "LiquidAI/d1-2B"
# Pinned commit. Review the shipped Python code before moving this pin because
# trust_remote_code runs it. See README.md for the reviewed file set.
REVISION = "10e7671d44e4b37700020b1eed3f594c5f2af0b4"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", default="~/models/d1-2B", help="local directory for the snapshot")
    args = ap.parse_args()

    dest = pathlib.Path(args.dest).expanduser()
    snapshot_download(REPO, revision=REVISION, local_dir=dest)
    (dest / "REVISION").write_text(REVISION + "\n")
    print(f"{REPO}@{REVISION[:12]} -> {dest}")


if __name__ == "__main__":
    main()
