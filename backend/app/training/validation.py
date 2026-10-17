"""Local media validation of imported labels without exposing footage or content."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import math
from pathlib import Path
import time

from backend.app.services.media import probe_video

from .labels import issue
from .resolver import resolve_records

FAILURE_CODES = ("missing_video", "ambiguous_match", "duplicate_mapping", "invalid_media",
                 "invalid_timestamp", "timestamp_outside_video", "missing_or_unknown_label")


@dataclass
class ValidationResult:
    records: list[dict]
    issues: list[dict] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(item["severity"] == "error" for item in self.issues)

    def to_dict(self) -> dict:
        counts = {code: sum(item["code"] == code for item in self.issues) for code in FAILURE_CODES}
        return {"valid": self.valid, "records": self.records, "issues": self.issues, "failure_counts": counts,
                "summary": {"record_count": len(self.records),
                            "valid_records": sum(row.get("validation_status") == "valid" for row in self.records),
                            "resolved_records": sum(bool(row.get("resolved_video_path")) for row in self.records),
                            "positive_records": sum(row.get("has_violation") is True for row in self.records),
                            "negative_records": sum(row.get("has_violation") is False for row in self.records)}}


def validate_labels(records: list[dict], video_dir: str | Path, settings, *,
                    import_issues: list[dict] | None = None, probe=None,
                    probe_timeout_seconds: float = 60) -> ValidationResult:
    """Check actual local files and timestamps; probe injection is for synthetic tests."""
    resolved = resolve_records(records, video_dir)
    result = ValidationResult(resolved.records, copy.deepcopy(import_issues or []) + resolved.issues)
    probe_function = probe or probe_video
    for index, record in enumerate(result.records):
        record["duration_sec"] = None
        label = record.get("has_violation")
        timestamp = record.get("timestamp_sec")
        if not isinstance(label, bool):
            result.issues.append(issue("missing_or_unknown_label", "Only explicit positive/negative labels can be validated.", index, record))
        timestamp_ok = timestamp is None or (not isinstance(timestamp, bool)
                      and isinstance(timestamp, (int, float)) and math.isfinite(timestamp) and timestamp >= 0)
        if not timestamp_ok or (label is True and timestamp is None) or (label is False and timestamp is not None):
            result.issues.append(issue("invalid_timestamp", "The timestamp is invalid or inconsistent with the explicit binary label.", index, record))
        path = record.get("resolved_video_path")
        if path:
            try:
                metadata = probe_function(Path(path), settings, time.time() + probe_timeout_seconds)
                duration = metadata["duration_sec"]
                if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
                    raise ValueError
                record["duration_sec"] = float(duration)
                if timestamp_ok and timestamp is not None and timestamp > duration:
                    result.issues.append(issue("timestamp_outside_video", "The supplied point timestamp is outside the decoded video duration.", index, record))
            except Exception:
                result.issues.append(issue("invalid_media", "The resolved video could not be probed as valid local media.", index, record))
        record["validation_status"] = "invalid" if any(
            item["severity"] == "error" and item.get("record_index") in (None, index) for item in result.issues) else "valid"
    # Later duplicate/global failures must also invalidate every affected record.
    for index, record in enumerate(result.records):
        if any(item["severity"] == "error" and item.get("record_index") in (None, index) for item in result.issues):
            record["validation_status"] = "invalid"
    unique = {}
    for item in result.issues:
        unique.setdefault((item["code"], item.get("record_index")), item)
    result.issues = list(unique.values())
    return result
