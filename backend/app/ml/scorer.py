"""Binary local scorer. Point labels do not establish types or event boundaries."""
from __future__ import annotations

import hashlib
import json
import math
import warnings
from pathlib import Path

from .features import FEATURE_VERSION, TRACKED

SCORER_FILE = "scorer.joblib"
SCORER_MANIFEST = "scorer.manifest.json"


def object_stats(objects: list[dict]):
    import numpy as np
    counts = np.zeros(len(TRACKED), dtype=np.float32)
    best = np.zeros(len(TRACKED), dtype=np.float32)
    for item in objects:
        if item["label"] not in TRACKED:
            continue
        index = TRACKED.index(item["label"])
        counts[index] += 1
        best[index] = max(best[index], item["score"])
    people = [item for item in objects if item["label"] == "person"]
    area = sum((item["box"][2] - item["box"][0]) * (item["box"][3] - item["box"][1]) for item in people)
    cx = np.mean([(item["box"][0] + item["box"][2]) / 2 for item in people]) if people else 0.5
    cy = np.mean([(item["box"][1] + item["box"][3]) / 2 for item in people]) if people else 0.5
    return np.concatenate([np.minimum(counts, 5) / 5, best, [area, cx, cy]]).astype(np.float32)


def build_matrix(features: list[dict], timestamps: list[float], feature_version: int = FEATURE_VERSION):
    import numpy as np
    if feature_version not in {1, FEATURE_VERSION}:
        raise ValueError("Unsupported scorer feature schema")
    if not features or len(features) != len(timestamps) or len(features) > 1000:
        raise ValueError("Feature rows do not match sampled timestamps")
    times = np.asarray(timestamps, dtype=np.float64)
    if not np.isfinite(times).all() or np.any(times < 0) or np.any(np.diff(times) < 0):
        raise ValueError("Feature timestamps must be finite and chronological")
    emb = np.asarray([frame["embedding"] for frame in features], dtype=np.float32)
    if emb.ndim != 2 or not 1 <= emb.shape[1] <= 4096 or not np.isfinite(emb).all():
        raise ValueError("Invalid bounded scene embeddings")
    if any(not frame.get("objects_observed", True) and frame["objects"] for frame in features):
        raise ValueError("Objects cannot be copied onto an unobserved frame")
    obj = np.stack([object_stats(frame["objects"]) for frame in features])
    prev, nxt = np.vstack([emb[:1], emb[:-1]]), np.vstack([emb[1:], emb[-1:]])
    motion_prev = np.linalg.norm(emb - prev, axis=1, keepdims=True)
    motion_next = np.linalg.norm(nxt - emb, axis=1, keepdims=True)
    context = np.stack([emb[max(0, index - 2):index + 3].mean(axis=0) for index in range(len(features))])
    deviation = emb - emb.mean(axis=0, keepdims=True)
    position = times.astype(np.float32)[:, None] / max(float(times[-1]), 1e-6)
    columns = [emb, context, deviation, (nxt - prev), motion_prev, motion_next, obj, position]
    if feature_version == FEATURE_VERSION:
        columns.append(np.asarray([frame.get("objects_observed", True) for frame in features], dtype=np.float32)[:, None])
    matrix = np.hstack(columns).astype(np.float32)
    if not np.isfinite(matrix).all():
        raise ValueError("Features contain nonfinite values")
    return matrix


def smooth(values, radius: int = 0):
    import numpy as np
    values = np.asarray(values, dtype=np.float64)
    if not 0 <= radius <= 5 or values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("Invalid binary model scores")
    if not len(values) or not radius:
        return values
    return np.convolve(np.pad(values, radius, mode="edge"), np.ones(2 * radius + 1) / (2 * radius + 1), mode="valid")


def peaks(scores, timestamps: list[float], threshold: float, merge_gap: float = 4.0) -> list[dict]:
    """Group nearby candidate samples, not annotated violation intervals."""
    import numpy as np
    scores = np.asarray(scores, dtype=np.float64)
    if (scores.ndim != 1 or len(scores) != len(timestamps) or not np.isfinite(scores).all()
            or np.any((scores < 0) | (scores > 1)) or not 0 < threshold < 1 or merge_gap < 0):
        raise ValueError("Invalid temporal candidate output")
    segments: list[list[int]] = []
    for index in np.flatnonzero(scores >= threshold):
        if segments and timestamps[index] - timestamps[segments[-1][-1]] <= merge_gap:
            segments[-1].append(int(index))
        else:
            segments.append([int(index)])
    return [{"start": segment[0], "end": segment[-1], "peak": max(segment, key=lambda index: scores[index]),
             "score": float(max(scores[index] for index in segment))} for segment in segments]


class Scorer:
    """Only load an operator-provided local joblib artifact; joblib is executable.

    Existing trusted artifacts remain supported as feature v1, with a visible
    legacy/unvalidated provenance warning. Legacy type heads are never used.
    """
    def __init__(self, bundle: dict, digest: str | None = None):
        if not isinstance(bundle, dict) or "model" not in bundle:
            raise ValueError("Invalid local scorer bundle")
        self.model = bundle["model"]
        self.threshold = float(bundle["threshold"])
        self.feature_version = int(bundle.get("feature_version", 1))
        self.vision_artifacts = bundle.get("vision_artifacts")
        self.smoothing_radius = int(bundle.get("smoothing_radius", 1 if self.feature_version == 1 else 0))
        if self.feature_version not in {1, FEATURE_VERSION} or not math.isfinite(self.threshold) or not 0 < self.threshold < 1:
            raise ValueError("Invalid scorer configuration")
        if not 0 <= self.smoothing_radius <= 5 or not callable(getattr(self.model, "predict_proba", None)):
            raise ValueError("Unsupported binary classifier")
        classes = list(getattr(self.model, "classes_", []))
        if len(classes) != 2 or set(classes) != {0, 1}:
            raise ValueError("Scorer must have explicit binary classes 0 and 1")
        self.positive_column = classes.index(1)
        self.provenance = {"digest": digest, "feature_version": self.feature_version,
                           "supervision": bundle.get("supervision", "legacy_unvalidated"),
                           "classification_available": False, "event_boundaries_available": False,
                           "threshold_calibrated_probability": False}

    @classmethod
    def load(cls, model_dir: Path) -> "Scorer":
        path = Path(model_dir) / SCORER_FILE
        if not path.is_file() or not 0 < path.stat().st_size <= 128 * 1024 * 1024:
            raise ValueError("A bounded local binary scorer artifact is required")
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        manifest_path = Path(model_dir) / SCORER_MANIFEST
        metadata = None
        if manifest_path.is_file():
            metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
            if metadata.get("sha256") != digest:
                raise ValueError("Local scorer checksum does not match its manifest")
        import joblib
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            bundle = joblib.load(path)
        if any(type(warning.message).__name__ == "InconsistentVersionWarning" for warning in caught):
            raise ValueError("The local scorer requires the scikit-learn version used to serialize it")
        scorer = cls(bundle, digest=digest)
        if metadata and metadata.get("feature_version") != scorer.feature_version:
            raise ValueError("Scorer manifest feature schema does not match its artifact")
        return scorer

    def predict(self, matrix):
        import numpy as np
        if matrix.ndim != 2 or not len(matrix) or not np.isfinite(matrix).all():
            raise ValueError("Invalid scorer input matrix")
        expected = getattr(self.model, "n_features_in_", None)
        if expected is None or matrix.shape[1] != expected:
            raise ValueError("Scorer and local feature extractor schemas are incompatible")
        output = np.asarray(self.model.predict_proba(matrix), dtype=np.float64)
        if (output.shape != (len(matrix), 2) or not np.isfinite(output).all()
                or np.any((output < 0) | (output > 1)) or not np.allclose(output.sum(axis=1), 1.0, atol=1e-5)):
            raise ValueError("Local scorer returned invalid binary scores")
        return smooth(output[:, self.positive_column], self.smoothing_radius)
