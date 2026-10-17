"""Deterministic, local label-to-video resolution; no renaming or guessed paths."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

from .labels import VIDEO_EXT, issue, matching_key


@dataclass
class ResolutionResult:
    records: list[dict]
    issues: list[dict] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(item["severity"] == "error" for item in self.issues)

    def to_dict(self) -> dict:
        return {"valid": self.valid, "records": self.records, "issues": self.issues}


def list_videos(directory: Path) -> list[Path]:
    root = Path(directory).resolve()
    return sorted((path for path in root.rglob("*")
                   if path.is_file() and path.suffix.lower() in VIDEO_EXT
                   and path.resolve().is_relative_to(root)), key=lambda path: path.as_posix())


def resolve_records(records: list[dict], video_dir: str | Path) -> ResolutionResult:
    root = Path(video_dir).resolve()
    result = ResolutionResult(copy.deepcopy(records))
    if not root.is_dir():
        result.issues.append(issue("missing_video", "The configured local video directory does not exist."))
        return result
    inventory = list_videos(root)
    mapping: dict[str, list[int]] = {}
    for index, record in enumerate(result.records):
        record["resolved_video_path"] = None
        record["resolution_method"] = None
        name = record.get("filename_raw")
        if not isinstance(name, str) or not name or any(char in name for char in "/\\\x00"):
            result.issues.append(issue("invalid_identifier", "The filename identifier cannot be resolved safely.", index, record))
            continue
        suffix = Path(name).suffix
        stem = name[:-len(suffix)] if suffix.lower() in VIDEO_EXT else name
        candidates = [path for path in inventory if path.name == name]
        method = "exact_filename"
        if not candidates:
            candidates = [path for path in inventory if path.stem == stem]
            method = "exact_stem"
        if not candidates:
            candidates = [path for path in inventory if matching_key(path.name) == matching_key(name)]
            method = "leading_x_alias"
        if not candidates:
            result.issues.append(issue("missing_video", "No permitted local video matches this identifier.", index, record))
            continue
        if len(candidates) != 1:
            result.issues.append(issue("ambiguous_match", "More than one video matches at the highest-priority resolution step.", index, record))
            continue
        resolved = str(candidates[0].resolve())
        record["resolved_video_path"] = resolved
        record["resolution_method"] = method
        mapping.setdefault(resolved, []).append(index)
    for indices in mapping.values():
        if len(indices) > 1:
            for index in indices:
                record = result.records[index]
                result.issues.append(issue("duplicate_mapping", "Multiple label records resolve to this video; explicit review is required.", index, record))
                record["resolved_video_path"] = None
                record["resolution_method"] = None
    return result
