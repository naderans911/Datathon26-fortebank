"""Sample frames exactly like the live pipeline and cache per-frame features.

    python scripts/extract_features.py DATA_DIR [--fps 2]
Writes cache/features/<video>.json  (timestamps + embeddings + objects).
"""
import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.ml.dataset import SampleSettings, list_videos, sample_video  # noqa: E402
from backend.app.ml.features import extract  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    out_dir = ROOT / "cache" / "features"
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = SampleSettings(fps=args.fps)
    videos = list_videos(args.data)
    print(f"{len(videos)} videos")
    for number, video in enumerate(videos, 1):
        target = out_dir / f"{video.stem}.json"
        if target.exists() and not args.force:
            continue
        started = time.time()
        work = Path(tempfile.mkdtemp())
        try:
            frames = sample_video(video, work, settings)
            feats = extract([f["path"] for f in frames], ROOT / "models", args.device)
            target.write_text(json.dumps({"video": video.name, "timestamps": [f["timestamp_sec"] for f in frames],
                                          "features": feats}), encoding="utf-8")
        except Exception as exc:
            print(f"[{number}] {video.name}: FAILED {exc}")
            continue
        finally:
            shutil.rmtree(work, ignore_errors=True)
        print(f"[{number}/{len(videos)}] {video.name}: {len(frames)} frames, {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
