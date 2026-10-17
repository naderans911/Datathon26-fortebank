"""Bounded local FFmpeg pathway using source presentation timestamps."""
from __future__ import annotations

import bisect
import json
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path


class MediaError(RuntimeError):
    """Safe media failure (no uploaded content or sensitive paths in text)."""

    @property
    def code(self) -> str:
        return "deadline_exceeded" if "deadline" in str(self).lower() else "invalid_media"

    @property
    def public_message(self) -> str:
        return str(self)


def run_media(args: list[str], deadline: float, *, output_limit: int = 20 * 1024 * 1024) -> bytes:
    """Disk-backed output prevents unbounded PIPE accumulation; kill on deadline."""
    if time.time() >= deadline:
        raise MediaError("The analysis deadline was exceeded")
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except OSError as exc:
            raise MediaError("FFmpeg or ffprobe is not available; install the configured local media tools") from exc
        try:
            while process.poll() is None:
                if time.time() >= deadline:
                    raise MediaError("The analysis deadline was exceeded")
                if os.fstat(output.fileno()).st_size > output_limit or os.fstat(errors.fileno()).st_size > 2 * 1024 * 1024:
                    raise MediaError("Media metadata or diagnostic output exceeded the configured limit")
                time.sleep(0.025)
            if process.returncode or os.fstat(errors.fileno()).st_size:
                raise MediaError("The video could not be decoded or prepared with the local media tools")
            if os.fstat(output.fileno()).st_size > output_limit:
                raise MediaError("Media metadata exceeded the configured limit")
            output.seek(0)
            return output.read(output_limit + 1)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


def _finite_number(value, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def probe_video(source: Path, settings, deadline: float) -> dict:
    command = [settings.ffprobe_binary, "-v", "error", "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,avi",
               "-select_streams", "v:0", "-show_streams", "-show_format",
               "-show_entries", "stream=codec_name,codec_type,width,height,avg_frame_rate,r_frame_rate,time_base,start_time,duration:stream_tags=rotate:stream_side_data=rotation:format=duration,format_name,start_time",
               "-of", "json", str(source)]
    try:
        data = json.loads(run_media(command, deadline))
        streams = data.get("streams", [])
        if len(streams) != 1 or streams[0].get("codec_type") != "video":
            raise ValueError
        stream = streams[0]
        width, height = int(stream["width"]), int(stream["height"])
        if not 1 <= width <= 7680 or not 1 <= height <= 4320 or width * height > 33_177_600:
            raise MediaError("Video dimensions exceed the supported decoding limit")
        if _finite_number(stream.get("duration")) > settings.max_video_seconds:
            raise MediaError("Video duration exceeds the configured limit")
        # Decode only after inexpensive header dimension/duration validation.
        frame_command = [settings.ffprobe_binary, "-v", "error", "-protocol_whitelist", "file,pipe",
                         "-format_whitelist", "mov,matroska,avi", "-select_streams", "v:0", "-show_frames",
                         "-show_entries", "frame=best_effort_timestamp_time,pkt_duration_time,duration_time", "-of", "json", str(source)]
        frames = json.loads(run_media(frame_command, deadline)).get("frames", [])
        if not frames or len(frames) > 180_000:
            raise MediaError("Video has no decodable frames or exceeds the frame-count limit")
        pts = [_finite_number(frame.get("best_effort_timestamp_time"), math.nan) for frame in frames]
        if any(not math.isfinite(value) for value in pts) or pts != sorted(pts):
            raise MediaError("Video presentation timestamps are missing or not chronological")
        start = pts[0]
        container_start = _finite_number(data.get("format", {}).get("start_time"), start)
        if abs(start - container_start) > 0.1:
            raise MediaError("The video stream has a delayed start that cannot be aligned safely to the original clip")
        times = [value - start for value in pts]
        tail = _finite_number(frames[-1].get("duration_time") or frames[-1].get("pkt_duration_time"))
        if tail <= 0:
            tail = times[-1] - times[-2] if len(times) > 1 else 1 / 30
        duration = max(times[-1] + tail, _finite_number(stream.get("duration")))
        if duration <= 0 or duration > settings.max_video_seconds:
            raise MediaError("Video duration is invalid or exceeds the configured limit")
        # Reject broken timestamps and empty tails rather than hide partial decode.
        if duration - times[-1] > max(2.0, tail * 2):
            raise MediaError("The decoded timeline does not cover the reported video duration")
        rotation = next((item["rotation"] for item in stream.get("side_data_list", []) if "rotation" in item),
                        stream.get("tags", {}).get("rotate", 0))
        return {"duration_sec": duration, "width": width, "height": height,
                "frame_rate": stream.get("avg_frame_rate", "0/0"), "time_base": stream.get("time_base"),
                "rotation": _finite_number(rotation), "source_start_pts": start,
                "frame_timestamps": times, "frame_count": len(frames), "codec": stream.get("codec_name")}
    except MediaError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise MediaError("The uploaded file is not a supported decodable video") from exc


def sample_indices(metadata: dict, settings) -> list[int]:
    timestamps = metadata["frame_timestamps"]
    fps = float(getattr(settings, "sampling_fps", 0.25))
    maximum = int(getattr(settings, "max_sample_frames", 80))
    if fps <= 0 or maximum < 2:
        raise MediaError("Sampling settings are invalid")
    desired = max(2, math.ceil(metadata["duration_sec"] * fps) + 1)
    count = min(maximum, desired, len(timestamps))
    targets = [timestamps[-1] * index / max(count - 1, 1) for index in range(count)]
    return sorted({min(bisect.bisect_left(timestamps, target), len(timestamps) - 1) for target in targets})


def extract_frames(source: Path, destination: Path, indices: list[int], metadata: dict, settings, deadline: float) -> list[dict]:
    destination.mkdir(parents=True, exist_ok=True)
    if not indices:
        raise MediaError("No frames were selected for analysis")
    selection = "+".join(f"eq(n\\,{index})" for index in indices)
    width = max(160, min(int(getattr(settings, "sample_width", 640)), 1280))
    filters = (f"select='{selection}',scale=w='min({width},iw)':h='min({width},ih)':"
               "force_original_aspect_ratio=decrease:force_divisible_by=2")
    command = [settings.ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-xerror",
               "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,avi", "-threads", "2", "-i", str(source), "-map", "0:v:0",
               "-an", "-sn", "-dn", "-vf", filters, "-fps_mode", "passthrough", "-frames:v", str(len(indices)),
               "-q:v", "3", "-threads", "2", str(destination / "frame-%04d.jpg")]
    run_media(command, deadline)
    files = sorted(destination.glob("frame-*.jpg"))
    if len(files) != len(indices):
        raise MediaError("Frame extraction did not cover the selected source timestamps")
    frames = []
    for sequence, (index, path) in enumerate(zip(indices, files, strict=True)):
        if path.stat().st_size > 512 * 1024:
            raise MediaError("A sampled JPEG exceeds the size limit")
        with path.open("rb") as file:
            if file.read(2) != b"\xff\xd8":
                raise MediaError("Evidence extraction did not produce a valid JPEG")
        frames.append({"id": f"frame-{sequence:04d}", "source_index": index,
                       "timestamp_sec": metadata["frame_timestamps"][index], "path": str(path)})
    return frames


def group_windows(frames: list[dict], seconds: float) -> list[dict]:
    if not frames or seconds <= 0:
        raise MediaError("Temporal window configuration is invalid")
    windows = []
    current = []
    for frame in frames:
        if current and (frame["timestamp_sec"] - current[0]["timestamp_sec"] >= seconds or len(current) >= 8):
            windows.append({"frames": current})
            # One shared chronological frame gives adjacent windows minimal continuity.
            current = current[-1:]
        current.append(frame)
    if current:
        windows.append({"frames": current})
    return windows


def create_preview(source: Path, target: Path, settings, deadline: float) -> None:
    maximum_bytes = int(getattr(settings, "max_preview_bytes", 80 * 1024 * 1024))
    command = [settings.ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-xerror",
               "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,avi", "-threads", "2", "-i", str(source), "-map", "0:v:0", "-an", "-sn", "-dn",
               "-vf", "setpts=PTS-STARTPTS,scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2", "-fps_mode", "vfr",
               "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "25", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", "-map_metadata", "-1", "-metadata:s:v:0", "rotate=0", "-fs", str(maximum_bytes), str(target)]
    run_media(command, deadline)
    if not target.is_file() or target.stat().st_size == 0:
        raise MediaError("Browser preview generation did not produce a playable file")
    if target.stat().st_size >= maximum_bytes:
        raise MediaError("The browser preview exceeds the configured size limit")
