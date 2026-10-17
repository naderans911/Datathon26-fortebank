"""Operational readiness must not hide unvalidated binary-model limitations."""
import time
from types import SimpleNamespace

from backend.app.core.readiness import get_readiness


def test_binary_quality_notice_remains_visible_when_components_ready(monkeypatch):
    monkeypatch.setattr("backend.app.services.rules.load_rules", lambda _path: [
        {"enabled": True, "verification_status": "verified", "source_type": "regulation"}
    ])
    monkeypatch.setattr("backend.app.core.readiness.shutil.which", lambda _binary: "synthetic-tool")
    settings = SimpleNamespace(rules_file="synthetic-registry", ffmpeg_binary="synthetic-ffmpeg",
                               ffprobe_binary="synthetic-ffprobe", worker_heartbeat_seconds=15,
                               detector_backend="cv", max_upload_mb=100, max_video_seconds=300,
                               enable_demo=False)
    store = SimpleNamespace(last_heartbeat=lambda: time.time())
    detector = SimpleNamespace(supports_binary_candidates=True, readiness=lambda: {
        "ready": True, "name": "cv-local", "model_available": True,
        "messages": ["private-synthetic-marker: never relay raw detector details"],
    })
    status, _ = get_readiness(settings, store, detector)
    assert status["ready"] and not status["reasons"]
    assert "unvalidated" in status["notices"][0] and "uncalibrated" in status["notices"][0]
    assert "private-synthetic-marker" not in str(status)
