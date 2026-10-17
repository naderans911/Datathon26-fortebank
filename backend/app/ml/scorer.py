"""Temporal violation scorer trained on the labelled Datathon clips.

Per sampled frame we build: scene embedding, embedding motion (difference to the
previous / next sample), local temporal mean, and object statistics. A
class-balanced classifier predicts P(violation near this frame). Peaks above the
calibrated threshold become events; an optional type head assigns a rule.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .features import TRACKED

SCORER_FILE = "scorer.joblib"


def object_stats(objects: list[dict]) -> np.ndarray:
    counts = np.zeros(len(TRACKED), dtype=np.float32)
    best = np.zeros(len(TRACKED), dtype=np.float32)
    for item in objects:
        index = TRACKED.index(item["label"])
        counts[index] += 1
        best[index] = max(best[index], item["score"])
    people = [item for item in objects if item["label"] == "person"]
    area = sum((o["box"][2] - o["box"][0]) * (o["box"][3] - o["box"][1]) for o in people)
    cx = np.mean([(o["box"][0] + o["box"][2]) / 2 for o in people]) if people else 0.5
    cy = np.mean([(o["box"][1] + o["box"][3]) / 2 for o in people]) if people else 0.5
    return np.concatenate([np.minimum(counts, 5) / 5, best, [area, cx, cy]]).astype(np.float32)


def build_matrix(features: list[dict], timestamps: list[float]) -> np.ndarray:
    emb = np.asarray([f["embedding"] for f in features], dtype=np.float32)
    obj = np.stack([object_stats(f["objects"]) for f in features])
    n = len(features)
    prev = np.vstack([emb[:1], emb[:-1]])
    nxt = np.vstack([emb[1:], emb[-1:]])
    motion_prev = np.linalg.norm(emb - prev, axis=1, keepdims=True)
    motion_next = np.linalg.norm(nxt - emb, axis=1, keepdims=True)
    # Local context: mean of +-2 samples.
    ctx = np.stack([emb[max(0, i - 2):i + 3].mean(axis=0) for i in range(n)])
    # Deviation of this moment from the whole clip (what is unusual here).
    deviation = emb - emb.mean(axis=0, keepdims=True)
    duration = max(timestamps[-1], 1e-6)
    position = np.asarray(timestamps, dtype=np.float32)[:, None] / duration
    return np.hstack([emb, ctx, deviation, (nxt - prev), motion_prev, motion_next, obj, position]).astype(np.float32)


def smooth(values: np.ndarray, radius: int = 1) -> np.ndarray:
    if len(values) == 0:
        return values
    kernel = np.ones(2 * radius + 1) / (2 * radius + 1)
    padded = np.pad(values, radius, mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def peaks(prob: np.ndarray, timestamps: list[float], threshold: float, merge_gap: float = 4.0) -> list[dict]:
    """Segments where smoothed probability >= threshold, merged when close; peak frame per segment."""
    above = np.where(prob >= threshold)[0]
    segments: list[list[int]] = []
    for index in above:
        if segments and timestamps[index] - timestamps[segments[-1][-1]] <= merge_gap:
            segments[-1].append(int(index))
        else:
            segments.append([int(index)])
    events = []
    for seg in segments:
        peak = max(seg, key=lambda i: prob[i])
        events.append({"start": seg[0], "end": seg[-1], "peak": peak, "score": float(prob[peak])})
    return events


class Scorer:
    def __init__(self, bundle: dict):
        self.bundle = bundle
        self.model = bundle["model"]
        self.threshold = float(bundle["threshold"])
        self.type_model = bundle.get("type_model")
        self.type_rules: dict = bundle.get("type_rules", {})
        self.default_type = bundle.get("default_type")

    @classmethod
    def load(cls, model_dir: Path) -> "Scorer | None":
        path = Path(model_dir) / SCORER_FILE
        if not path.is_file():
            return None
        import joblib
        return cls(joblib.load(path))

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return smooth(self.model.predict_proba(matrix)[:, 1], radius=1)

    def classify(self, row: np.ndarray) -> tuple[str | None, float]:
        """Return (type_name, confidence) for an event row; None when no type head."""
        if self.type_model is None:
            return None, 0.0
        proba = self.type_model.predict_proba(row[None, :])[0]
        best = int(np.argmax(proba))
        return str(self.type_model.classes_[best]), float(proba[best])
