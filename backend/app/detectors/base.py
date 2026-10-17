from __future__ import annotations

import time
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class DetectionError(RuntimeError):
    """Safe failure text; never include model content, frames, or transport URLs."""

    @property
    def code(self) -> str:
        return "deadline_exceeded" if "deadline" in str(self).lower() else "detector_failed"

    @property
    def public_message(self) -> str:
        return str(self)


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    rule_id: str | None
    frame_ids: list[str] = Field(min_length=1, max_length=3)
    observation: str = Field(min_length=1, max_length=1200)
    # A visible-object/action discriminator permits distinct simultaneous events.
    event_key: str = Field(min_length=1, max_length=100)


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    observations: list[Observation] = Field(max_length=24)


class Detector(Protocol):
    def readiness(self) -> dict: ...
    def analyze_windows(self, windows: list[dict], rules: list[dict], deadline: float) -> list[dict]: ...


def remaining(deadline: float, maximum: float = 60.0) -> float:
    seconds = deadline - time.time()
    if seconds <= 0:
        raise DetectionError("The analysis deadline was exceeded")
    return min(seconds, maximum)


def validate_observations(values: list[dict], frames: list[dict], rules: list[dict], max_events: int = 24) -> list[dict]:
    if not isinstance(values, list) or len(values) > max_events:
        raise DetectionError("Detector output exceeded the configured event limit; no partial verdict was saved")
    frame_map = {frame["id"]: frame for frame in frames}
    rule_ids = {rule["id"] for rule in rules}
    validated = []
    for value in values:
        try:
            observation = Observation.model_validate(value).model_dump()
        except (ValueError, TypeError) as exc:
            raise DetectionError("The detector returned invalid structured observations") from exc
        if observation["rule_id"] is not None and observation["rule_id"] not in rule_ids:
            raise DetectionError("The detector referenced an unknown or inactive rule")
        ids = observation["frame_ids"]
        if len(ids) != len(set(ids)) or any(frame_id not in frame_map for frame_id in ids):
            raise DetectionError("The detector referenced unknown or duplicate frames")
        timestamps = [frame_map[frame_id]["timestamp_sec"] for frame_id in ids]
        if timestamps != sorted(timestamps):
            raise DetectionError("The detector returned frames in invalid temporal order")
        validated.append(observation)
    return validated


class UnconfiguredDetector:
    def readiness(self) -> dict:
        message = "Configure a licensed local vision model and enabled verified rules to analyze uploaded videos."
        return {"ready": False, "name": "unconfigured", "model_available": False, "message": message, "messages": [message]}

    def analyze_windows(self, windows: list[dict], rules: list[dict], deadline: float) -> list[dict]:
        raise DetectionError("A real detector is not configured")
