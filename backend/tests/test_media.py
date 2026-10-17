"""Only locally generated shapes; no competition footage enters these tests."""
import base64
import os
import shutil
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.app.detectors.base import DetectionError
from backend.app.services.demo import build_demo
from backend.app.services.media import MediaError, create_preview, extract_frames, probe_video, run_media, sample_indices
from backend.app.services.pipeline import process_job


def _tool(name):
    configured = os.environ.get(f"{name.upper()}_BINARY")
    binary = configured or shutil.which(name)
    if not binary:
        root = Path(__file__).resolve().parents[2]
        binary = next(root.glob(f".tools/**/{name}.exe"), None)
    if not binary:
        pytest.skip(f"{name} is required for real generated-media integration tests")
    return str(binary)


@pytest.fixture
def media_settings(tmp_path):
    return SimpleNamespace(ffmpeg_binary=_tool("ffmpeg"), ffprobe_binary=_tool("ffprobe"),
                           max_video_seconds=300, sampling_fps=2, max_sample_frames=80, sample_width=640,
                           window_seconds=16, max_events=24, max_evidence_bytes=12 * 1024 * 1024,
                           storage_dir=tmp_path, enable_demo=True)


@pytest.fixture
def rule():
    return {"id": "TEST-ONLY", "title": "Test fixture", "event_type": "Visible fixture action",
            "jurisdiction": "Test environment", "source_type": "internal_procedure", "document_title": "Test-only procedure",
            "source_url": None, "section_or_paragraph": None, "relevant_excerpt": "A generated shape is visible.",
            "observed_condition": "A generated shape is visible.", "required_context": ["Test fixture"],
            "interpretation": "Test-only interpretation; no banking claim.", "limitations": ["Test fixture only"],
            "verification_status": "verified", "verified_at": "2026-01-01", "enabled": True, "version": "1"}


def make_source(path, settings, *, vfr=False, offset=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [settings.ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
               "testsrc2=size=160x96:rate=30:duration=2"]
    if vfr:
        command.extend(["-vf", "select='not(mod(n,3))+not(mod(n,7))'", "-fps_mode", "vfr"])
    command.extend(["-c:v", "mpeg4", "-q:v", "3", "-an"])
    if offset:
        command.extend(["-output_ts_offset", "5"])
    run_media([*command, str(path)], time.time() + 30)


class FixtureDetector:
    def __init__(self, positive=True):
        self.positive = positive

    def analyze_windows(self, windows, rules, deadline):
        if not self.positive:
            return []
        frame = windows[0]["frames"][1]["id"]
        first = {"rule_id": rules[0]["id"], "frame_ids": [frame], "observation": "A generated rectangle is visible.", "event_key": "rectangle-a"}
        return [first, {**first, "observation": "The same generated rectangle remains visible."}, {**first, "event_key": "rectangle-b", "observation": "A second generated rectangle is visible."},
                {**first, "rule_id": None, "event_key": "unmapped", "observation": "An unmapped generated shape is visible."}]


def new_job(settings, rule):
    job_id = uuid.uuid4().hex
    source = Path(settings.storage_dir) / "jobs" / job_id / "source.mov"
    make_source(source, settings)
    return {"id": job_id, "source_path": str(source.resolve()), "rules_snapshot": [rule],
            "accepted_at": time.time(), "deadline_at": time.time() + 60}


def test_real_mov_pipeline_simultaneous_events_and_jpegs(media_settings, rule):
    job = new_job(media_settings, rule)
    stages = []
    result = process_job(job, media_settings, FixtureDetector(), stages.append)
    assert stages == ["validating_video", "preparing_frames", "analyzing_activity", "checking_rule_mappings", "preparing_evidence"]
    assert len(result["events"]) == 2
    assert result["events"][0]["id"] != result["events"][1]["id"]
    assert result["events"][0]["timecode_sec"] == result["events"][1]["timecode_sec"]
    assert len(result["unmapped_observations"]) == 1
    directory = Path(job["source_path"]).parent
    for event in result["events"]:
        for evidence in event["evidence_frames"]:
            assert 0 <= evidence["timestamp_sec"] <= result["duration_sec"]
            raw = (directory / evidence["filename"]).read_bytes()
            assert base64.b64decode(base64.b64encode(raw)) == raw
            with Image.open(directory / evidence["filename"]) as image:
                assert image.format == "JPEG"
                image.verify()
    assert (directory / "preview.mp4").is_file()


def test_negative_is_real_empty_result(media_settings, rule):
    result = process_job(new_job(media_settings, rule), media_settings, FixtureDetector(False), lambda _: None)
    assert result["events"] == []
    assert "not proof" in result["coverage"]


@pytest.mark.parametrize("vfr,offset", [(False, True), (True, False), (True, True)])
def test_actual_pts_sampling_and_preview_alignment(media_settings, tmp_path, vfr, offset):
    source = tmp_path / "aligned.mov"
    make_source(source, media_settings, vfr=vfr, offset=offset)
    metadata = probe_video(source, media_settings, time.time() + 30)
    assert metadata["frame_timestamps"][0] == 0
    if offset:
        assert metadata["source_start_pts"] == pytest.approx(5, abs=0.04)
    if vfr:
        gaps = {round(b - a, 4) for a, b in zip(metadata["frame_timestamps"], metadata["frame_timestamps"][1:])}
        assert len(gaps) > 1
    indices = sample_indices(metadata, media_settings)
    frames = extract_frames(source, tmp_path / "frames", indices, metadata, media_settings, time.time() + 30)
    assert [frame["timestamp_sec"] for frame in frames] == [metadata["frame_timestamps"][index] for index in indices]
    assert indices[0] == 0 and indices[-1] == metadata["frame_count"] - 1
    preview = tmp_path / "preview.mp4"
    create_preview(source, preview, media_settings, time.time() + 30)
    preview_data = probe_video(preview, media_settings, time.time() + 30)
    assert preview_data["frame_timestamps"] == pytest.approx(metadata["frame_timestamps"], abs=0.04)


def test_rotated_source_orientation(media_settings, tmp_path):
    original, rotated = tmp_path / "original.mov", tmp_path / "rotated.mov"
    make_source(original, media_settings)
    run_media([media_settings.ffmpeg_binary, "-v", "error", "-y", "-display_rotation", "90", "-i", str(original), "-c", "copy", str(rotated)], time.time() + 30)
    metadata = probe_video(rotated, media_settings, time.time() + 30)
    assert abs(metadata["rotation"]) == 90
    frames = extract_frames(rotated, tmp_path / "rotated-frames", [0], metadata, media_settings, time.time() + 30)
    with Image.open(frames[0]["path"]) as image:
        assert image.size == (96, 160)


def test_corrupt_media_is_failure(media_settings, tmp_path):
    path = tmp_path / "corrupt.mov"
    path.write_bytes(b"this is not a video")
    with pytest.raises(MediaError):
        probe_video(path, media_settings, time.time() + 10)


def test_expired_deadline_and_missing_rules_fail(media_settings, rule):
    job = new_job(media_settings, rule)
    job["deadline_at"] = time.time() - 1
    with pytest.raises(MediaError, match="deadline"):
        process_job(job, media_settings, FixtureDetector(), lambda _: None)
    job["deadline_at"] = time.time() + 30
    job["rules_snapshot"] = []
    with pytest.raises(DetectionError, match="verified"):
        process_job(job, media_settings, FixtureDetector(), lambda _: None)


def test_demo_isolated_and_generates_valid_media(media_settings, rule):
    positive = build_demo("positive", media_settings)
    assert positive["demo"] and positive["result"]["verdict"] == "violation"
    assert len(positive["result"]["events"]) == 2
    demo_rule = positive["result"]["events"][0]["rule"]
    job = new_job(media_settings, rule)
    job["rules_snapshot"] = [demo_rule]
    with pytest.raises(ValueError, match="Synthetic"):
        process_job(job, media_settings, FixtureDetector(), lambda _: None)
    negative = build_demo("negative", media_settings)
    assert negative["result"]["verdict"] == "no_violation" and not negative["result"]["events"]
    failed = build_demo("failed", media_settings)
    assert failed["status"] == "failed" and "result" not in failed
    media_settings.enable_demo = False
    with pytest.raises(ValueError, match="disabled"):
        build_demo("positive", media_settings)


def test_failed_demo_removes_unaccepted_artifacts(media_settings, monkeypatch):
    from backend.app.services import demo

    def fail(*args, **kwargs):
        raise MediaError("Synthetic test failure")

    monkeypatch.setattr(demo, "run_media", fail)
    with pytest.raises(MediaError):
        demo.build_demo("positive", media_settings)
    assert list((media_settings.storage_dir / "jobs").iterdir()) == []


def test_evidence_limit_fails_without_truncated_verdict(media_settings, rule):
    job = new_job(media_settings, rule)
    media_settings.max_evidence_bytes = 1
    with pytest.raises(MediaError, match="size limit"):
        process_job(job, media_settings, FixtureDetector(), lambda _: None)
