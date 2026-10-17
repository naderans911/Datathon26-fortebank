"""Training-time helpers: same frame sampling as the live pipeline + label loading."""
from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path

from backend.app.services.media import extract_frames, probe_video, sample_indices

VIDEO_EXT = {".mov", ".mp4", ".avi", ".mkv", ".m4v"}


def list_videos(directory: Path) -> list[Path]:
    return sorted(p for p in Path(directory).rglob("*") if p.suffix.lower() in VIDEO_EXT and p.is_file())


def norm_stem(name) -> str:
    """'Х-3.mov' (Cyrillic Х) and 'x-3' both -> 'X-3'."""
    stem = Path(str(name).strip()).stem.upper()
    return stem.translate(str.maketrans("ХАВСЕКМНОРТУ", "XABCEKMHOPTY"))


def parse_time(value) -> float | None:
    """Accept 11, 11.5, '11', '0:11', '00:00:11', '11s', '11 сек'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace(",", ".")
    if not text or text in {"-", "nan", "none", "нет"}:
        return None
    minutes = re.search(r"(\d+(?:\.\d+)?)\s*(?:мин|min|м\b)", text)
    seconds = re.search(r"(\d+(?:\.\d+)?)\s*(?:сек|sec|s\b|с\b)", text)
    if minutes:
        return float(minutes.group(1)) * 60 + (float(seconds.group(1)) if seconds else 0.0)
    if ":" in text:
        parts = [float(p) for p in re.findall(r"\d+(?:\.\d+)?", text)]
        seconds = 0.0
        for part in parts:
            seconds = seconds * 60 + part
        return seconds
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def load_labels(path: Path) -> dict[str, list[float]]:
    """Return {video_stem: [timestamps]}; an empty list means 'no violation'.

    Supports JSON ({"clip.mov": [11, 40]} or a list of records) and CSV/TSV/XLSX
    with columns resembling video/file/name, time/timecode/sec, label/violation.
    """
    path = Path(path)
    records: list[dict] = []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            out = {}
            for name, value in data.items():
                values = value if isinstance(value, list) else [value]
                out[norm_stem(name)] = [t for t in (parse_time(v) for v in values) if t is not None]
            return out
        records = list(data)
    elif path.suffix.lower() in {".xlsx", ".xls"}:
        import openpyxl
        sheet = openpyxl.load_workbook(path, read_only=True).active
        rows = list(sheet.iter_rows(values_only=True))
        header = [str(h or "").strip().lower() for h in rows[0]]
        records = [dict(zip(header, row)) for row in rows[1:]]
    else:
        text = path.read_text(encoding="utf-8-sig")
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
        records = [{(k or "").strip().lower(): v for k, v in row.items()} for row in csv.DictReader(text.splitlines(), dialect=dialect)]

    def pick(row: dict, *keys):
        for key in row:
            if any(k in key for k in keys):
                return row[key]
        return None

    out: dict[str, list[float]] = {}
    for row in records:
        name = pick(row, "video", "file", "name", "видео", "файл", "clip")
        if not name:
            continue
        stem = norm_stem(name)
        out.setdefault(stem, [])
        label = pick(row, "label", "violation", "наруш", "метк", "class")
        is_negative = label is not None and str(label).strip().lower() in {"0", "false", "no", "нет", "норма", "no_violation", "без нарушения"}
        t = parse_time(pick(row, "time", "timecode", "sec", "врем", "секунд", "тайм", "ts"))
        if t is not None and not is_negative:
            out[stem].append(t)
    return out


class SampleSettings:
    """Mirror of the live sampling settings (keep in sync with .env)."""

    def __init__(self, fps: float = 2.0, max_frames: int = 400, width: int = 640):
        self.ffmpeg_binary, self.ffprobe_binary = "ffmpeg", "ffprobe"
        self.sampling_fps, self.max_sample_frames, self.sample_width = fps, max_frames, width
        self.max_video_seconds = 3600


def sample_video(video: Path, workdir: Path, settings: SampleSettings) -> list[dict]:
    deadline = time.time() + 600
    meta = probe_video(video, settings, deadline)
    indices = sample_indices(meta, settings)
    return extract_frames(video, workdir, indices, meta, settings, deadline)
