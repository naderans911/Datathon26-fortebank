"""Local binary visual scoring; no filename lookup, inferred legal type or LLM."""
from __future__ import annotations

import time
from pathlib import Path

from .base import DetectionError


class CVDetector:
    supports_binary_candidates = True

    def __init__(self, settings):
        self.settings = settings
        self.model_dir = Path(settings.cv_model_dir)
        self.scorer_dir = Path(getattr(settings, "cv_scorer_dir", None) or self.model_dir)
        self.provenance = {"name": "cv-local", "model": "rtdetr_r18vd+dinov2-small+binary-scorer",
                           "adapter_version": "2", "classification_available": False,
                           "event_boundaries_available": False, "accuracy_validated": False}

    def readiness(self) -> dict:
        # No Torch, NumPy, sklearn or model imports/loads in the API process.
        from backend.app.ml.features import artifacts_status, missing_dependencies
        from backend.app.ml.scorer import SCORER_FILE, SCORER_MANIFEST
        messages, missing = [], missing_dependencies()
        artifacts = artifacts_status(self.model_dir)
        scorer_path = self.scorer_dir / SCORER_FILE
        scorer_exists = scorer_path.is_file() and 0 < scorer_path.stat().st_size <= 128 * 1024 * 1024
        if missing:
            messages.append("Install the pinned local ML requirements before enabling CV analysis.")
        if not artifacts["ready"]:
            messages.append("Complete local RT-DETR and DINOv2 weights/configuration are missing or invalid.")
        if not scorer_exists:
            messages.append("A trained local binary scorer is required; missing detection logic cannot return a clean result.")
        if scorer_exists and not (self.scorer_dir / SCORER_MANIFEST).is_file():
            messages.append("The existing local scorer has legacy provenance; quality and training supervision are unvalidated.")
        messages.append("Binary findings remain unclassified. Event categories and legal mappings require human review.")
        ready = not missing and artifacts["ready"] and scorer_exists
        return {"ready": ready, "name": "cv-local", "model_available": artifacts["ready"] and scorer_exists,
                "message": messages[0], "messages": messages}

    def analyze_windows(self, windows: list[dict], rules: list[dict], deadline: float) -> list[dict]:
        from backend.app.ml.features import extract, load_models
        from backend.app.ml.scorer import Scorer, build_matrix, peaks
        seen, frames = set(), []
        for window in windows:
            for frame in window["frames"]:
                if frame["id"] not in seen:
                    seen.add(frame["id"])
                    frames.append(frame)
        frames.sort(key=lambda frame: frame["timestamp_sec"])
        if len(frames) < 2:
            raise DetectionError("Too few source frames were sampled for binary visual analysis")
        try:
            if time.time() >= deadline:
                raise TimeoutError
            scorer = Scorer.load(self.scorer_dir)
            # All supplied frames are actually observed; no stale object carry-forward.
            features = extract([frame["path"] for frame in frames], self.model_dir,
                               self.settings.cv_device, deadline, batch_size=1, det_stride=1)
            artifacts = load_models(self.model_dir, self.settings.cv_device, deadline)["artifacts"]
            if scorer.vision_artifacts is not None and (
                {name: data.get("sha256") for name, data in scorer.vision_artifacts.items()}
                != {name: data.get("sha256") for name, data in artifacts.items()}
            ):
                raise ValueError("Scorer training artifacts do not match the installed vision models")
            timestamps = [frame["timestamp_sec"] for frame in frames]
            matrix = build_matrix(features, timestamps, scorer.feature_version)
            scores = scorer.predict(matrix)
            threshold = self.settings.cv_threshold if self.settings.cv_threshold is not None else scorer.threshold
            candidates = peaks(scores, timestamps, threshold)
            if len(candidates) > getattr(self.settings, "max_events", 24):
                raise DetectionError("Detected events exceed the configured limit; no partial verdict was saved")
            self.provenance.update(scorer.provenance)
            self.provenance["artifacts"] = artifacts
            if time.time() >= deadline:
                raise TimeoutError
        except TimeoutError as exc:
            raise DetectionError("The analysis deadline was exceeded") from exc
        except DetectionError:
            raise
        except Exception as exc:
            raise DetectionError("The local binary vision model failed or its feature schema is incompatible") from exc
        observations = []
        for number, candidate in enumerate(candidates):
            peak = candidate["peak"]
            indices = sorted({max(0, peak - 1), peak, min(len(frames) - 1, peak + 1)})
            observations.append({"kind": "binary_candidate", "rule_id": None,
                "frame_ids": [frames[index]["id"] for index in indices], "anchor_frame_id": frames[peak]["id"],
                "observation": ("The local visual classifier flagged this sampled moment for human review. "
                                f"Model score {candidate['score']:.3f} is uncalibrated; it does not identify a visible action or legal violation."),
                "event_key": f"binary-candidate-{number}"})
        return observations
