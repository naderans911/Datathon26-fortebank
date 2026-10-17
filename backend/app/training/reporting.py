"""Private, atomic local reports; never overwrite an original label source."""
from __future__ import annotations

from datetime import date, datetime, time
import json
import math
from pathlib import Path
import uuid


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (date, datetime, time)):
        return {"unsupported_type": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, float) and not math.isfinite(value):
        return {"unsupported_type": "float", "value": str(value)}
    return value


def write_local_report(target: Path, payload: dict, *, sources: list[Path] = ()) -> None:
    target = target.resolve()
    root = Path(__file__).resolve().parents[3]
    if any(target == path.resolve() for path in sources):
        raise ValueError("Reports cannot overwrite an original label source.")
    if target.is_relative_to(root) and target.relative_to(root).parts[0] not in {"reports", "data", "cache", "storage"}:
        raise ValueError("Repository-local reports must use an ignored reports/, data/, cache/ or storage/ directory.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
