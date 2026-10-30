"""Check the Path A stack before running the System One example.

Exit code 0 means every check passed. Run it after the install steps in README.md.
"""

import pathlib
import sys

from packaging.version import Version

from fetch_d1 import REVISION

MODEL_DIR = pathlib.Path("~/models/d1-2B").expanduser()
MIN_TRANSFORMERS = Version("5.19")

failures: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {detail}")
    if not ok:
        failures.append(name)


check("python", sys.version_info >= (3, 10), sys.version.split()[0])

try:
    import torch
    check("torch", True, f"{torch.__version__} (cuda available: {torch.cuda.is_available()}, CPU path is used)")
except ImportError as e:
    check("torch", False, str(e))

try:
    import torchvision
    check("torchvision", True, torchvision.__version__)
except ImportError as e:
    check("torchvision", False, str(e))

try:
    import PIL
    check("pillow", True, PIL.__version__)
except ImportError as e:
    check("pillow", False, str(e))

try:
    import transformers
    tv = Version(transformers.__version__)
    check("transformers", tv >= MIN_TRANSFORMERS, f"{transformers.__version__} (need >= {MIN_TRANSFORMERS})")
except ImportError as e:
    check("transformers", False, str(e))

for f in ["config.json", "model.safetensors", "modeling_d1.py", "tokenizer.json"]:
    check(f"model file {f}", (MODEL_DIR / f).is_file(), str(MODEL_DIR / f))

rev_file = MODEL_DIR / "REVISION"
rev = rev_file.read_text().strip() if rev_file.is_file() else "missing"
check("pinned revision", rev == REVISION, f"{rev[:12]} (expected {REVISION[:12]})")

print("\nAll checks passed." if not failures else f"\nFailed: {', '.join(failures)}")
sys.exit(1 if failures else 0)
