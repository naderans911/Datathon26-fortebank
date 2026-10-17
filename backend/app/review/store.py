"""Local validated-label catalog and atomic, revisioned annotation documents."""
import hashlib
import json
import math
import os
import threading
import time
from pathlib import Path

from .models import Annotation


class ReviewError(ValueError):
    pass


class RevisionConflict(ReviewError):
    pass


class ReviewStore:
    def __init__(self, labels: Path, video_root: Path, annotation_root: Path):
        self.video_root = video_root.resolve()
        self.annotation_root = annotation_root.resolve()
        self.lock = threading.RLock()
        self.records = {}
        self.excluded = 0
        try:
            if labels.stat().st_size > 64 * 1024 * 1024:
                raise ReviewError("The validated label export is too large.")
            export = json.loads(labels.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ReviewError("Open a readable validated label export before starting local review.") from exc
        records = export.get("records")
        issues = export.get("issues", [])
        if not isinstance(records, list) or not isinstance(issues, list):
            raise ReviewError("The label export must contain validated records and issues.")
        if any(issue.get("severity") == "error" and issue.get("record_index") is None for issue in issues):
            raise ReviewError("The label export has an unresolved global validation error.")
        invalid = {issue.get("record_index") for issue in issues if issue.get("severity") == "error"}
        fingerprint = export.get("source_fingerprint")
        self.fingerprint = fingerprint.get("sha256") if isinstance(fingerprint, dict) else None
        if not isinstance(self.fingerprint, str) or len(self.fingerprint) != 64:
            raise ReviewError("The validated label export needs a source fingerprint.")
        for index, record in enumerate(records):
            if not isinstance(record, dict) or index in invalid or record.get("validation_status") != "valid":
                self.excluded += 1
                continue
            try:
                source = Path(record["resolved_video_path"]).resolve(strict=True)
                duration = float(record["duration_sec"])
                point = record.get("timestamp_sec")
                if (not source.is_relative_to(self.video_root) or not source.is_file()
                        or source.suffix.lower() not in {".mov", ".mp4", ".m4v", ".mkv"}
                        or not math.isfinite(duration) or duration <= 0
                        or (point is not None and (not isinstance(point, (int, float))
                            or not math.isfinite(point) or point < 0 or point > duration))
                        or not isinstance(record.get("has_violation"), bool)):
                    raise ValueError
            except (OSError, KeyError, TypeError, ValueError):
                self.excluded += 1
                continue
            identity = {"source_fingerprint": self.fingerprint, "source_sheet": record.get("source_sheet"),
                        "source_row": record.get("source_row"), "record_index": index}
            record_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:32]
            self.records[record_id] = {"identity": identity, "source": source, "record": record,
                                       "duration_sec": duration}

    def item(self, record_id):
        if record_id not in self.records:
            raise KeyError(record_id)
        return self.records[record_id]

    def video(self, record_id):
        source = self.item(record_id)["source"].resolve(strict=True)
        if not source.is_relative_to(self.video_root) or not source.is_file():
            raise ReviewError("The matched local video is unavailable.")
        return source

    def annotation(self, record_id):
        self.item(record_id)
        path = self.annotation_root / f"{record_id}.json"
        if not path.exists():
            return Annotation()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if document["source"] != self.item(record_id)["identity"]:
                raise ValueError
            return Annotation.model_validate(document["annotation"])
        except (OSError, ValueError, KeyError) as exc:
            raise ReviewError("The saved annotation is invalid; restore it from a local backup.") from exc

    def summary(self, record_id):
        item = self.item(record_id)
        source = item["record"]
        annotation = self.annotation(record_id)
        return {"id": record_id, "filename": source["filename_raw"],
                "has_violation": source["has_violation"], "timestamp_sec": source.get("timestamp_sec"),
                "duration_sec": item["duration_sec"], "review_status": annotation.status,
                "event_count": len(annotation.events)}

    def detail(self, record_id):
        return {"source": self.summary(record_id), "annotation": self.annotation(record_id).model_dump(),
                "video_url": f"/api/review/items/{record_id}/video"}

    def save(self, record_id, annotation: Annotation):
        item = self.item(record_id)
        for event in annotation.events:
            if any(value is not None and value > item["duration_sec"] for value in (event.start_sec, event.end_sec)):
                raise ReviewError("Event boundaries must fall within the video duration.")
        with self.lock:
            current = self.annotation(record_id)
            if annotation.revision != current.revision:
                raise RevisionConflict("This annotation changed in another tab. Reload before saving.")
            updated = annotation.model_copy(update={"revision": current.revision + 1})
            document = {"schema_version": 1, "source": item["identity"], "updated_at": time.time(),
                        "annotation": updated.model_dump()}
            self.annotation_root.mkdir(parents=True, exist_ok=True)
            target = self.annotation_root / f"{record_id}.json"
            temporary = target.with_suffix(".tmp")
            try:
                with temporary.open("w", encoding="utf-8") as stream:
                    json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            except OSError as exc:
                raise ReviewError("The local annotation could not be saved.") from exc
            return updated
