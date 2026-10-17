"""Report safe operational readiness without exposing paths or credentials."""

import shutil
import time


def get_readiness(settings, store, detector) -> tuple[dict, list]:
    from backend.app.services.rules import active_rules, load_rules

    reasons: list[str] = []
    active = []
    try:
        rules = load_rules(settings.rules_file)
        active = active_rules(rules)
    except Exception:
        reasons.append("The local rule registry is missing or invalid. Check RULES_FILE and its validated schema.")
    if not active:
        reasons.append("Register at least one enabled, verified, applicable rule before real analysis.")
    ffmpeg = bool(shutil.which(settings.ffmpeg_binary) and shutil.which(settings.ffprobe_binary))
    if not ffmpeg:
        reasons.append("Install FFmpeg and ffprobe and make both available to the API and worker.")
    heartbeat = store.last_heartbeat()
    worker_alive = bool(heartbeat and time.time() - heartbeat < settings.worker_heartbeat_seconds)
    if not worker_alive:
        reasons.append("Start the local analysis worker; its heartbeat is unavailable.")
    try:
        readiness = detector.readiness()
        if hasattr(readiness, "model_dump"):
            readiness = readiness.model_dump()
        detector_ready = bool(readiness.get("ready", False))
        model_available = bool(readiness.get("model_available", detector_ready))
    except Exception:
        readiness = {}
        detector_ready = model_available = False
    if not detector_ready:
        # Adapter messages are fixed operator guidance; never relay remote errors.
        reasons.append("Configure a licensed local vision model and verify the detector connection.")
    # Fixed capability guidance is nonblocking; readiness is not an accuracy claim.
    # Do not relay arbitrary detector messages, which may contain private context.
    notices = []
    if getattr(detector, "supports_binary_candidates", False):
        notices.append("Binary model quality is unvalidated and scores are uncalibrated. "
                       "Event categories, start/end boundaries and legal applicability require human review.")
    status = {
        "ready": bool(active and ffmpeg and worker_alive and detector_ready),
        "backend_available": True,
        "worker_heartbeat": heartbeat,
        "worker_alive": worker_alive,
        "ffmpeg_available": ffmpeg,
        "detector_name": readiness.get("name", settings.detector_backend),
        "model_available": model_available,
        "active_verified_rules": len(active),
        "reasons": reasons,
        "notices": notices,
        "limits": {"max_upload_mb": settings.max_upload_mb, "max_video_seconds": settings.max_video_seconds},
        "demo_enabled": settings.enable_demo,
    }
    return status, active
