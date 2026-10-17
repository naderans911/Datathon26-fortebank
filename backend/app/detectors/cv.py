"""Fully local computer-vision detector (no LLM, no network).

1. Per sampled frame: RT-DETR COCO objects + DINOv2 scene embedding (backend/app/ml/features.py).
2. Learned temporal scorer (models/scorer.joblib, trained by scripts/train.py) finds
   moments resembling labelled violations; a type head maps them to a violation type.
3. Transparent heuristics add events the scorer may miss (e.g. a phone in the cash zone).

Every event is mapped to a verified rule via config/violation_types.json. The
detector only describes what is visible; it never asserts invisible facts.
"""
from __future__ import annotations

import json
from pathlib import Path

from .base import DetectionError

TYPES_FILE = Path(__file__).resolve().parents[3] / "config" / "violation_types.json"


def load_types() -> dict:
    try:
        return json.loads(TYPES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"types": {}, "default_type": None}


def _evidence(indices: list[int], frames: list[dict]) -> list[str]:
    unique = sorted(set(indices), key=lambda i: frames[i]["timestamp_sec"])
    if len(unique) > 3:
        unique = [unique[0], unique[len(unique) // 2], unique[-1]]
    return [frames[i]["id"] for i in unique]


class CVDetector:
    def __init__(self, settings):
        self.settings = settings
        self.model_dir = Path(settings.cv_model_dir)
        self.provenance = {"name": "cv-local", "model": "rtdetr_r18vd+dinov2-small+scorer", "adapter_version": "1",
                           "digest": None}

    def readiness(self) -> dict:
        from backend.app.ml.features import models_present
        from backend.app.ml.scorer import SCORER_FILE
        messages = []
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except ImportError:
            messages.append("Install the ML requirements (requirements-ml.txt).")
        if not models_present(self.model_dir):
            messages.append("Local model weights are missing: run scripts/download_models.py once.")
        if not (self.model_dir / SCORER_FILE).is_file():
            messages.append("No trained scorer yet: run scripts/train.py (heuristics-only mode).")
        ready = not any("missing" in m or "Install" in m for m in messages)
        return {"ready": ready, "name": "cv-local", "model_available": ready,
                "message": messages[0] if messages else "Local CV detector ready.", "messages": messages}

    def analyze_windows(self, windows: list[dict], rules: list[dict], deadline: float) -> list[dict]:
        from backend.app.ml.features import extract
        from backend.app.ml.scorer import Scorer, build_matrix, peaks

        seen, frames = set(), []
        for window in windows:
            for frame in window["frames"]:
                if frame["id"] not in seen:
                    seen.add(frame["id"])
                    frames.append(frame)
        frames.sort(key=lambda f: f["timestamp_sec"])
        if len(frames) < 2:
            raise DetectionError("Too few frames were sampled for analysis")
        try:
            features = extract([f["path"] for f in frames], self.model_dir, self.settings.cv_device, deadline)
        except TimeoutError as exc:
            raise DetectionError("The analysis deadline was exceeded") from exc
        except Exception as exc:  # model/runtime failure must not leak details
            raise DetectionError("The local vision models failed to run") from exc

        rule_ids = {rule["id"] for rule in rules}
        config = load_types()
        types = config.get("types", {})
        timestamps = [f["timestamp_sec"] for f in frames]
        observations: list[dict] = []

        def add(type_name: str | None, indices: list[int], detail: str, key: str):
            spec = types.get(type_name or "") or types.get(config.get("default_type") or "", {})
            rule_id = spec.get("rule_id")
            if rule_id not in rule_ids:
                rule_id = None  # pipeline reports it as unmapped, never as a violation
            text = (spec.get("observation") or "Обнаружено действие, похожее на нарушение.") + " " + detail
            observations.append({"rule_id": rule_id, "frame_ids": _evidence(indices, frames),
                                 "observation": text.strip()[:1200], "event_key": key[:100]})

        scorer = Scorer.load(self.model_dir)
        if scorer is not None:
            matrix = build_matrix(features, timestamps)
            prob = scorer.predict(matrix)
            threshold = self.settings.cv_threshold or scorer.threshold
            for number, event in enumerate(peaks(prob, timestamps, threshold)):
                type_name, confidence = scorer.classify(matrix[event["peak"]])
                type_name = type_name or scorer.default_type
                detail = (f"Фрагмент {timestamps[event['start']]:.1f}–{timestamps[event['end']]:.1f} с; "
                          f"уверенность модели {event['score']:.0%}.")
                add(type_name, [event["peak"], event["start"], event["end"]], detail, f"scorer-{number}")

        observations.extend(self._heuristics(features, frames, types, rule_ids))
        return observations[: getattr(self.settings, "max_events", 24)]

    def _heuristics(self, features: list[dict], frames: list[dict], types: dict, rule_ids: set) -> list[dict]:
        """Phone visible for >= 2 consecutive samples -> communication device in the cash zone."""
        spec = types.get("phone_in_cash_zone")
        if not spec or spec.get("rule_id") not in rule_ids or not spec.get("heuristic", True):
            return []
        hits = [i for i, f in enumerate(features)
                if any(o["label"] == "cell phone" and o["score"] >= spec.get("min_score", 0.6) for o in f["objects"])]
        runs: list[list[int]] = []
        for i in hits:
            if runs and i - runs[-1][-1] <= 1:
                runs[-1].append(i)
            else:
                runs.append([i])
        out = []
        for number, run in enumerate(r for r in runs if len(r) >= 2):
            mid = run[len(run) // 2]
            out.append({"rule_id": spec["rule_id"], "frame_ids": _evidence([run[0], mid, run[-1]], frames),
                        "observation": (spec["observation"] + f" Телефон виден в кадре "
                                        f"{frames[run[0]]['timestamp_sec']:.1f}–{frames[run[-1]]['timestamp_sec']:.1f} с.")[:1200],
                        "event_key": f"phone-{number}"})
        return out

