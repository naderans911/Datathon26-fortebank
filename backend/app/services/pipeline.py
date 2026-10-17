"""Shared real analysis pipeline, independent of judge/UI routes and demo fixtures."""
from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path

from ..detectors.base import DetectionError, validate_observations
from .media import MediaError, create_preview, extract_frames, group_windows, probe_video, sample_indices
from .rules import active_rules, validate_rules


def process_job(job: dict, settings, detector, progress) -> dict:
    deadline = float(job["deadline_at"])
    if time.time() >= deadline:
        raise MediaError("The analysis deadline was exceeded, including queue time")
    # Revalidate persisted snapshots; synthetic fixtures can never enter this path.
    rules = active_rules(validate_rules(job["rules_snapshot"]))
    if not rules:
        raise DetectionError("No applicable enabled verified rules are available")
    job_dir = Path(settings.storage_dir).resolve() / "jobs" / job["id"]
    source = Path(job["source_path"]).resolve()
    if source.parent != job_dir.resolve() or source.name != "source.mov":
        raise MediaError("The job source is outside controlled storage")
    progress("validating_video")
    metadata = probe_video(source, settings, deadline)
    progress("preparing_frames")
    selected = sample_indices(metadata, settings)
    frames = extract_frames(source, job_dir / "samples", selected, metadata, settings, deadline)
    windows = group_windows(frames, getattr(settings, "window_seconds", 16))
    progress("analyzing_activity")
    raw = detector.analyze_windows(windows, rules, deadline)
    if time.time() >= deadline:
        raise MediaError("The analysis deadline was exceeded")
    progress("checking_rule_mappings")
    binary_detector = getattr(detector, "supports_binary_candidates", False)
    observations = validate_observations(raw, frames, rules, getattr(settings, "max_events", 24),
                                        allow_binary_candidates=binary_detector)
    frame_map = {frame["id"]: frame for frame in frames}
    rule_map = {rule["id"]: rule for rule in rules}
    observations.sort(key=lambda item: frame_map[item["frame_ids"][0]]["timestamp_sec"])
    # Shared evidence + the same rule/action key links overlapping window reports.
    # Different rule/action keys sharing a timestamp remain independent events.
    unique = []
    for observation in observations:
        existing = next((item for item in unique
                         if item["rule_id"] == observation["rule_id"]
                         and item["kind"] == observation["kind"]
                         and item["event_key"] == observation["event_key"]
                         and set(item["frame_ids"]) & set(observation["frame_ids"])), None)
        if existing is None:
            unique.append({**observation, "frame_ids": list(observation["frame_ids"])})
        else:
            combined = sorted(set(existing["frame_ids"]) | set(observation["frame_ids"]),
                              key=lambda frame_id: frame_map[frame_id]["timestamp_sec"])
            # The judge contract permits at most three representative frames.
            # Keep the first, middle, and last when overlapping windows add context.
            anchor = existing["anchor_frame_id"] or combined[len(combined) // 2]
            existing["frame_ids"] = combined if len(combined) <= 3 else sorted(
                {combined[0], anchor, combined[-1]}, key=lambda frame_id: frame_map[frame_id]["timestamp_sec"])
    events, unmapped = [], []
    progress("preparing_evidence")
    evidence_dir = job_dir / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    evidence_bytes = 0
    for observation in unique:
        if observation["rule_id"] is None and observation["kind"] != "binary_candidate":
            unmapped.append({"observation": observation["observation"],
                            "timecode_sec": frame_map[observation["frame_ids"][0]]["timestamp_sec"],
                            "limitations": ["No verified rule mapping; this observation is not counted as a violation."]})
            continue
        event_id = uuid.uuid4().hex
        evidence = []
        for number, frame_id in enumerate(observation["frame_ids"]):
            frame = frame_map[frame_id]
            timestamp = frame["timestamp_sec"]
            if not 0 <= timestamp <= metadata["duration_sec"]:
                raise MediaError("An evidence timestamp is outside the original source timeline")
            relative = f"evidence/{event_id}-{number}.jpg"
            shutil.copyfile(frame["path"], job_dir / relative)
            evidence_bytes += (job_dir / relative).stat().st_size
            if evidence_bytes > getattr(settings, "max_evidence_bytes", 12 * 1024 * 1024):
                raise MediaError("Evidence exceeds the response size limit; no partial verdict was saved")
            evidence.append({"timestamp_sec": timestamp, "filename": relative})
        if observation["kind"] == "binary_candidate":
            anchor = observation["anchor_frame_id"] or observation["frame_ids"][0]
            events.append({"id": event_id, "kind": "binary_candidate", "type": "Possible violation (unclassified)",
                           "timecode_sec": frame_map[anchor]["timestamp_sec"], "observation": observation["observation"],
                           "interpretation": "Binary visual scoring suggests a moment to review. The event category and applicable legal basis have not been established.",
                           "rule": None, "limitations": ["A binary label and point timestamp do not establish an event type or its start/end boundaries.",
                               "The model score is uncalibrated; banking detection quality remains unvalidated.",
                               "Sparse sampling, occlusion and changed viewpoints can miss indicators. Human review is required."],
                           "evidence_frames": evidence})
            continue
        rule = rule_map[observation["rule_id"]]
        limitations = [*rule["limitations"], "Sparse sampled frames can miss brief actions or required context.",
                       "Unfamiliar camera angles and occlusion can reduce detection coverage. A human must assess each finding."]
        if not rule["section_or_paragraph"]:
            limitations.append("The source is verified at document level; a pinpoint section has not been established.")
        events.append({"id": event_id, "type": rule["event_type"], "timecode_sec": evidence[0]["timestamp_sec"],
                       "observation": observation["observation"], "interpretation": rule["interpretation"],
                       "rule": rule, "limitations": limitations, "evidence_frames": evidence})
    create_preview(source, job_dir / "preview.mp4", settings, deadline)
    if time.time() >= deadline:
        raise MediaError("The analysis deadline was exceeded")
    gaps = [b["timestamp_sec"] - a["timestamp_sec"] for a, b in zip(frames, frames[1:])]
    coverage = (f"{len(frames)} actual source frames sampled across {metadata['duration_sec']:.2f} seconds; "
                f"largest sampling gap {max(gaps, default=0):.2f} seconds. " +
                ("Local binary visual scoring was used; it does not classify events or establish legal mappings. " if binary_detector
                 else f"{len(rules)} enabled verified rules were evaluated. ") +
                "No violation detected means no indicators under the configured detector and this sampling coverage, not proof of complete compliance.")
    return {"duration_sec": metadata["duration_sec"], "events": events, "unmapped_observations": unmapped,
            "preview_available": True, "coverage": coverage,
            "detector": getattr(detector, "provenance", {"name": type(detector).__name__, "adapter_version": "1"}),
            "media": {key: value for key, value in metadata.items() if key != "frame_timestamps"}}
