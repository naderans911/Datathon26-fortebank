"""Check that this machine analyses the longest dataset clip (142 s, 287 frames) within the job deadline.

    python scripts/benchmark.py
Times feature extraction on synthetic 640px frames and, if needed, writes a sparser
object-detector stride (CV_DET_STRIDE) into .env; run_windows.ps1 / run_mac.sh pick it up.
"""
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

FRAMES = 287          # X-14, the longest clip, at SAMPLING_FPS=2
OVERHEAD = 25.0       # probe + frame extraction + scoring + evidence, seconds
BUDGET = 200.0        # keep a margin under the 285 s job deadline


def main():
    import numpy as np
    from PIL import Image

    from backend.app.ml.features import extract

    work = Path(tempfile.mkdtemp())
    rng = np.random.default_rng(0)
    paths = []
    for i in range(24):
        path = work / f"f{i}.jpg"
        Image.fromarray(rng.integers(0, 255, (360, 640, 3), dtype=np.uint8)).save(path)
        paths.append(str(path))
    extract(paths[:8], ROOT / "models", "auto", det_stride=2)  # warm-up / model load
    estimates = {}
    for stride in (2, 4, 8):
        started = time.time()
        extract(paths, ROOT / "models", "auto", det_stride=stride)
        estimates[stride] = (time.time() - started) / len(paths) * FRAMES + OVERHEAD
        print(f"CV_DET_STRIDE={stride}: longest clip ~ {estimates[stride]:.0f} s")
    chosen = next((s for s in (2, 4, 8) if estimates[s] <= BUDGET), None)
    env = ROOT / ".env"
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    if chosen is None:
        print("TOO SLOW: even CV_DET_STRIDE=8 exceeds the budget; use a faster machine.")
        chosen = 8
    line = f"CV_DET_STRIDE={chosen}"
    text = re.sub(r"(?m)^CV_DET_STRIDE=.*$", line, text) if "CV_DET_STRIDE=" in text else text.rstrip("\n") + "\n" + line + "\n"
    env.write_text(text, encoding="utf-8")
    print(f"OK: wrote {line} to .env (restart the run script to apply).")


if __name__ == "__main__":
    main()
