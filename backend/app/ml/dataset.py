"""Training-only metadata compatibility and source-aligned frame sampling.

No production/jury inference module should import organizer label helpers.
"""
from __future__ import annotations

from pathlib import Path
import time

from backend.app.services.media import extract_frames, probe_video, sample_indices
from backend.app.training.labels import LabelDataError, import_labels, matching_key, parse_timestamp
from backend.app.training.resolver import list_videos as _list_videos


def list_videos(directory: Path) -> list[Path]:
    return _list_videos(directory)


def norm_stem(name) -> str:
    """Known leading Cyrillic Х/Latin X lookup hint only; preserve all other text."""
    return matching_key(str(name))


def parse_time(value) -> float | None:
    """Strict whole-input Russian units or numeric seconds; missing stays null."""
    return parse_timestamp(value)


def load_labels(path: Path) -> dict[str, list[float]]:
    """Compatibility view of strict actual-format labels.

    Only an explicitly negative source label becomes an empty list. Missing,
    unsupported, inconsistent and duplicate labels raise before training. Prefer
    import_labels + the local resolver for richer metadata and verified matches.
    """
    imported = import_labels(path)
    if not imported.valid:
        raise LabelDataError("Label import failed validation; run the local label validator and review its report.")
    output = {}
    for record in imported.records:
        key = norm_stem(record["filename_raw"])
        if key in output:
            raise LabelDataError("Alias lookup keys collide; resolve actual files and review the mapping before training.")
        if record["has_violation"] is False:
            output[key] = []
        elif record["has_violation"] is True and record["timestamp_sec"] is not None:
            output[key] = [record["timestamp_sec"]]
        else:
            raise LabelDataError("An unknown label or missing positive timestamp cannot become a negative example.")
    return output


class SampleSettings:
    """Sampling settings for local feature preparation, separate from inference."""

    def __init__(self, fps: float = 2.0, max_frames: int = 400, width: int = 640):
        from backend.app.core.config import Settings
        configured = Settings()
        self.ffmpeg_binary, self.ffprobe_binary = configured.ffmpeg_binary, configured.ffprobe_binary
        self.sampling_fps, self.max_sample_frames, self.sample_width = fps, max_frames, width
        self.max_video_seconds = 3600


def sample_video(video: Path, workdir: Path, settings: SampleSettings) -> list[dict]:
    deadline = time.time() + 600
    meta = probe_video(video, settings, deadline)
    indices = sample_indices(meta, settings)
    return extract_frames(video, workdir, indices, meta, settings, deadline)
