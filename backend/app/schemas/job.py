"""Validate the persisted analysis contract independently of model output."""

import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def media_path(job_dir: Path, filename: str) -> Path:
    if not isinstance(filename, str) or "\\" in filename or filename.startswith("/"):
        raise ValueError("Invalid media reference")
    candidate = (job_dir / filename).resolve()
    if not candidate.is_relative_to(job_dir.resolve()) or candidate == job_dir.resolve():
        raise ValueError("Invalid media reference")
    return candidate


def validate_result(result: dict, job: dict, settings) -> dict:
    duration = result.get("duration_sec")
    if isinstance(duration, bool) or not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid analysis duration")
    if duration > settings.max_video_seconds:
        raise ValueError("Video duration exceeds configuration")
    events = result.get("events")
    if not isinstance(events, list) or len(events) > settings.max_events:
        raise ValueError("Invalid event count")
    job_dir = settings.storage_dir / "jobs" / job["id"]
    known_rules = {rule["id"]: rule for rule in job["rules_snapshot"]}
    seen_ids = set()
    evidence_size = 0
    for event in events:
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id or event_id in seen_ids:
            raise ValueError("Invalid event identity")
        seen_ids.add(event_id)
        timestamp = event.get("timecode_sec")
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or not 0 <= timestamp <= duration:
            raise ValueError("Event timestamp outside source")
        for field in ("type", "observation", "interpretation"):
            if not isinstance(event.get(field), str) or not event[field].strip():
                raise ValueError("Missing event explanation")
        rule = event.get("rule")
        if event.get("kind") == "binary_candidate":
            if rule is not None or event["type"] != "Possible violation (unclassified)":
                raise ValueError("Binary findings must remain unclassified without an asserted legal rule")
        else:
            rule_id = rule.get("id") if isinstance(rule, dict) else None
            if rule_id not in known_rules or rule != known_rules[rule_id]:
                raise ValueError("Event rule is not the accepted rule snapshot")
        frames = event.get("evidence_frames")
        if not isinstance(frames, list) or not 1 <= len(frames) <= 3:
            raise ValueError("Events require one to three actual evidence frames")
        for frame in frames:
            timestamp = frame.get("timestamp_sec")
            if isinstance(timestamp, bool) or not isinstance(timestamp, (float, int)) or not math.isfinite(timestamp) or not 0 <= timestamp <= duration:
                raise ValueError("Evidence timestamp outside source")
            path = media_path(job_dir, frame.get("filename"))
            if path.suffix.lower() not in (".jpg", ".jpeg") or not path.is_file():
                raise ValueError("Evidence is unavailable")
            evidence_size += path.stat().st_size
            if evidence_size > settings.max_evidence_bytes:
                raise ValueError("Evidence response exceeds configured resource limit")
            with path.open("rb") as source:
                if source.read(2) != b"\xff\xd8":
                    raise ValueError("Evidence is not a JPEG")
                source.seek(-2, 2)
                if source.read(2) != b"\xff\xd9":
                    raise ValueError("Evidence JPEG is incomplete")
    result["events"] = sorted(events, key=lambda event: (event["timecode_sec"], event["id"]))
    result["verdict"] = "violation" if events else "no_violation"
    return result

class AcceptedJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str


class JudgeProcessing(AcceptedJob):
    status: Literal["processing"]


class SafeError(BaseModel):
    code: str
    message: str


class JudgeFailed(AcceptedJob):
    status: Literal["failed"]
    error: SafeError


class JudgeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp_sec: float = Field(ge=0)
    image_base64: str


class JudgeViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    timecode_sec: float = Field(ge=0)
    description: str
    evidence_frames: list[JudgeEvidence] = Field(min_length=1, max_length=3)


class JudgeDone(AcceptedJob):
    status: Literal["done"]
    verdict: Literal["no_violation", "violation"]
    violations: list[JudgeViolation]

    @model_validator(mode="after")
    def verdict_matches_findings(self):
        if bool(self.violations) != (self.verdict == "violation"):
            raise ValueError("The verdict must agree with the findings")
        return self
