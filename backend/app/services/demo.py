"""Opt-in synthetic UI fixtures. Never imported by the real analysis pipeline."""
from __future__ import annotations

import bisect
import json
import shutil
import time
import uuid
from pathlib import Path

from .media import create_preview, extract_frames, probe_video, run_media
from .rules import validate_rules

DEMO_NOTICE = "Demo — synthetic data; not a real compliance analysis"


def build_demo(kind: str, settings) -> dict:
    job_id = uuid.uuid4().hex
    jobs_root = (Path(settings.storage_dir) / "jobs").resolve()
    job_dir = (jobs_root / job_id).resolve()
    try:
        return _build_demo(kind, settings, job_id)
    except Exception:
        # Unaccepted demo fixtures have no DB row for the retention sweeper.
        if job_dir.parent == jobs_root and job_dir.is_dir():
            shutil.rmtree(job_dir)
        raise


def _build_demo(kind: str, settings, job_id: str) -> dict:
    if not getattr(settings, "enable_demo", False):
        raise ValueError("Synthetic demo is disabled")
    if kind not in {"positive", "negative", "failed"}:
        raise ValueError("Unknown synthetic fixture")
    created = time.time()
    result = {"job_id": job_id, "status": "failed" if kind == "failed" else "done", "stage": "completed",
              "created_at": created, "updated_at": created, "elapsed_sec": 0,
              "filename": f"synthetic-{kind}.mov", "size_bytes": 0, "demo": True, "demo_notice": DEMO_NOTICE}
    if kind == "failed":
        result.update(stage="failed", error={"code": "synthetic_failure", "message": "Synthetic failure example: the processing deadline was exceeded. No successful verdict was produced."})
        return result
    job_dir = Path(settings.storage_dir) / "jobs" / job_id
    job_dir.mkdir(parents=True)
    source = job_dir / "source.mov"
    deadline = created + 45
    y = 165 if kind == "positive" else 10
    graph = ("[0:v]drawbox=x=250:y=125:w=230:h=230:color=0x626574:thickness=4[bg];"
             f"[bg][1:v]overlay=x='40+65*t':y={y}:shortest=1[a];"
             f"[a][2:v]overlay=x='590-52*t':y={y+70}:shortest=1[out]")
    args = [settings.ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "color=c=0xF1F2F5:s=720x480:r=30:d=8",
            "-f", "lavfi", "-i", "color=c=0xA31551:s=48x48:r=30:d=8",
            "-f", "lavfi", "-i", "color=c=0x61CFFF:s=44x44:r=30:d=8",
            "-filter_complex", graph, "-map", "[out]", "-an", "-c:v", "mpeg4", "-q:v", "3", "-threads", "2", str(source)]
    run_media(args, deadline)
    metadata = probe_video(source, settings, deadline)
    create_preview(source, job_dir / "preview.mp4", settings, deadline)
    events = []
    if kind == "positive":
        example_path = Path(__file__).resolve().parents[3] / "examples" / "synthetic-rules.json"
        rules = validate_rules(json.loads(example_path.read_text(encoding="utf-8")), allow_synthetic=True)
        timestamps = metadata["frame_timestamps"]
        indices = [bisect.bisect_left(timestamps, second) for second in [4.0, 4.5, 5.0]]
        frames = extract_frames(source, job_dir / "evidence", indices, metadata, settings, deadline)
        evidence = [{"timestamp_sec": frame["timestamp_sec"], "filename": f"evidence/{Path(frame['path']).name}"} for frame in frames]
        for color in ["magenta", "sky-blue"]:
            events.append({"id": uuid.uuid4().hex, "type": "Synthetic shape in marked area", "timecode_sec": 4.0,
                           "observation": f"The generated {color} square is visible inside the outlined area.",
                           "interpretation": rules[0]["interpretation"], "rule": rules[0],
                           "limitations": rules[0]["limitations"], "evidence_frames": evidence})
    result.update(size_bytes=source.stat().st_size, updated_at=time.time(), elapsed_sec=time.time() - created,
                  result={"verdict": "violation" if events else "no_violation", "duration_sec": metadata["duration_sec"],
                          "events": events, "unmapped_observations": [], "preview_available": True,
                          "coverage": "Fixed synthetic fixture outcomes demonstrate the review interface only. No banking detection or model accuracy is being tested."})
    return result
