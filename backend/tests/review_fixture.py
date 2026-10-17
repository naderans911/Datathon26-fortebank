"""Synthetic-only loopback fixture server for Playwright. Never loads organizer data."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import uvicorn

from backend.app.review.app import ReviewSettings, create_app


def main():
    workspace = Path(__file__).resolve().parents[2]
    fixture_root = workspace / ".local" / "review-e2e"
    fixture_root.mkdir(parents=True, exist_ok=True)
    fixture = Path(tempfile.mkdtemp(prefix="synthetic-", dir=fixture_root))
    videos = fixture / "videos"
    videos.mkdir()
    ffmpeg = os.getenv("FFMPEG_BINARY") or shutil.which("ffmpeg")
    if not ffmpeg:
        portable = next(workspace.glob(".tools/**/ffmpeg.exe"), None)
        ffmpeg = str(portable) if portable else "ffmpeg"
    source = videos / "synthetic-review-e2e.mp4"
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                    "color=c=0xf1f2f5:s=640x360:r=24:d=12", "-vf",
                    "drawbox=x=250:y=120:w=70:h=70:color=0xA31551:t=fill,drawbox=x=350:y=170:w=50:h=50:color=0x61CFFF:t=fill",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(source)],
                   check=True, timeout=30, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    labels = fixture / "synthetic-validation.json"
    records = [{"filename_raw": source.name, "resolved_video_path": str(source), "source_sheet": "Synthetic",
                "source_row": 2, "timestamp_sec": 4.0, "timestamp_raw": "00:04", "has_violation": True,
                "label_raw": "1", "duration_sec": 12.0, "validation_status": "valid"}]
    labels.write_text(json.dumps({"records": records, "issues": [], "source_fingerprint": {
        "sha256": hashlib.sha256(b"Synthetic Playwright fixture only").hexdigest(),
        "source_name": "synthetic", "format": "json", "size_bytes": 0}}), encoding="utf-8")
    app = create_app(ReviewSettings(enabled=True, labels=labels, video_root=videos,
                                   data_dir=fixture / "annotations", frontend_dist=workspace / "frontend" / "dist",
                                   ffmpeg_binary=ffmpeg))
    uvicorn.run(app, host="127.0.0.1", port=8001, proxy_headers=False, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
