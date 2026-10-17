"""Contact sheets around labelled moments, to decide violation types by eye.

    python scripts/explore_dataset.py DATA_DIR LABELS_FILE
Writes reports/explore/<video>.jpg: frames at t-4..t+4 s around each label
(or 8 evenly spaced frames for clips without a violation) + summary.json.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.ml.dataset import list_videos, load_labels, norm_stem  # noqa: E402


def duration(video: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True).stdout
    return float(out.strip() or 0)


def grab(video: Path, t: float, width: int = 480) -> Image.Image | None:
    data = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.2f}", "-i", str(video), "-frames:v", "1",
                           "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                          capture_output=True).stdout
    if not data:
        return None
    from io import BytesIO
    return Image.open(BytesIO(data)).convert("RGB")


def sheet(images: list[tuple[str, Image.Image]], cols: int = 3) -> Image.Image:
    w, h = images[0][1].size
    rows = (len(images) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * w, rows * (h + 22)), "white")
    draw = ImageDraw.Draw(canvas)
    for i, (caption, img) in enumerate(images):
        x, y = (i % cols) * w, (i // cols) * (h + 22)
        canvas.paste(img, (x, y + 22))
        draw.text((x + 4, y + 4), caption, fill="black")
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("labels", type=Path)
    args = ap.parse_args()
    labels = load_labels(args.labels)
    out = ROOT / "reports" / "explore"
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for video in list_videos(args.data):
        stamps = labels.get(norm_stem(video.name))
        d = duration(video)
        summary.append({"video": video.name, "duration": round(d, 1), "labels": stamps})
        if stamps:
            times = [(f"t={t:.1f} ({o:+d}s)", t + o) for t in stamps for o in (-4, -2, 0, 2, 4, 6)]
        else:
            times = [(f"t={d * k / 9:.1f}", d * k / 9) for k in range(1, 9)]
        images = [(c, img) for c, t in times if (img := grab(video, t)) is not None]
        if images:
            sheet(images, cols=6 if stamps else 4).save(out / f"{video.stem}.jpg", quality=80)
        print(video.name, round(d, 1), stamps)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    unmatched = sorted(set(labels) - {norm_stem(v.name) for v in list_videos(args.data)})
    if unmatched:
        print("Labels without video:", unmatched[:20])


if __name__ == "__main__":
    main()
