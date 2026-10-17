"""Train binary point-supervised local scoring from validated, private caches.

Only the nearest sampled frame to a supplied positive point is a positive
training example. Other moments in that positive clip remain UNKNOWN. Confirmed
negative clips supply negatives. Types, durations and related-session groups are
not inferred. Validation splits whole clips, never individual frames.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.ml.features import FEATURE_VERSION  # noqa: E402
from backend.app.ml.scorer import SCORER_FILE, SCORER_MANIFEST, build_matrix, peaks  # noqa: E402


def point_supervision(record: dict, timestamps: list[float], duration: float, maximum_distance: float = 1.0):
    """Return -1 for unknown, 0 for confirmed negatives, 1 for one point anchor."""
    import numpy as np
    times = np.asarray(timestamps, dtype=np.float64)
    if (times.ndim != 1 or not len(times) or not np.isfinite(times).all() or np.any(np.diff(times) < 0)
            or not math.isfinite(duration) or duration <= 0 or not math.isfinite(maximum_distance)
            or times[0] < 0 or times[-1] > duration or maximum_distance < 0):
        raise ValueError("Invalid source timestamp timeline")
    labels = np.full(len(times), -1, dtype=np.int8)
    binary = record.get("has_violation")
    if binary is False:
        if record.get("timestamp_sec") is not None:
            raise ValueError("A negative record cannot contain a positive point")
        labels[:] = 0
    elif binary is True:
        point = record.get("timestamp_sec")
        if point is None:
            return labels
        if isinstance(point, bool) or not isinstance(point, (int, float)) or not math.isfinite(point) or not 0 <= point <= duration:
            raise ValueError("Positive point lies outside its source duration")
        closest = int(np.argmin(np.abs(times - point)))
        if abs(float(times[closest]) - point) <= maximum_distance:
            labels[closest] = 1
    else:
        raise ValueError("Binary label is unknown; resolve the record before training")
    return labels


def make_model(kind: str = "lr", regularization: float = 1.0, pca: int = 16, *, rows: int, columns: int):
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    components = min(max(pca, 0), max(rows - 1, 1), columns)
    reduction = [PCA(n_components=components, random_state=0)] if components else []
    if kind == "hgb":
        from sklearn.ensemble import HistGradientBoostingClassifier
        classifier = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, random_state=0)
    else:
        classifier = LogisticRegression(C=regularization, max_iter=3000, random_state=0)
    return make_pipeline(StandardScaler(), *reduction, classifier)


def training_rows(videos: list[dict]):
    import numpy as np
    usable = [video for video in videos if np.any(video["labels"] >= 0)]
    counts = {label: sum(video["label"] == label for video in usable) for label in (0, 1)}
    if not all(counts.values()):
        raise ValueError("Training requires point-labelled positive clips and confirmed negative clips")
    matrices, labels, weights = [], [], []
    for video in usable:
        keep = video["labels"] >= 0
        matrices.append(video["matrix"][keep])
        labels.append(video["labels"][keep])
        weights.extend([1 / (counts[video["label"]] * int(keep.sum()))] * int(keep.sum()))
    weight_array = np.asarray(weights)
    weight_array *= len(weight_array) / weight_array.sum()
    return np.vstack(matrices), np.concatenate(labels), weight_array


def fit_model(videos: list[dict], *, kind: str = "lr", regularization: float = 1.0, pca: int = 16):
    matrix, labels, weights = training_rows(videos)
    model = make_model(kind, regularization, pca, rows=len(matrix), columns=matrix.shape[1])
    step = list(model.named_steps)[-1]
    model.fit(matrix, labels, **{f"{step}__sample_weight": weights})
    return model


def evaluate_candidates(videos: list[dict], predictions: list, threshold: float, point_tolerance: float = 2.0) -> dict:
    tp = fn = fp = tn = labelled_points = localized_points = 0
    distances = []
    for video, scores in zip(videos, predictions, strict=True):
        candidates = peaks(scores, video["timestamps"], threshold)
        flagged = bool(candidates)
        if video["label"] == 1:
            tp += int(flagged)
            fn += int(not flagged)
            point = video["point"]
            if point is not None:
                labelled_points += 1
                if candidates:
                    error = min(abs(video["timestamps"][candidate["peak"]] - point) for candidate in candidates)
                    distances.append(error)
                    localized_points += int(error <= point_tolerance)
        else:
            fp += int(flagged)
            tn += int(not flagged)
    import numpy as np
    return {"threshold": float(threshold), "tp_clips": tp, "fn_clips": fn, "fp_clips": fp, "tn_clips": tn,
            "balanced_clip_accuracy": 0.5 * (tp / max(tp + fn, 1) + tn / max(tn + fp, 1)),
            "labelled_points": labelled_points, "localized_labelled_points": localized_points,
            "point_tolerance_sec": point_tolerance, "median_nearest_candidate_error_sec": float(np.median(distances)) if distances else None}


def load_group_manifest(path: Path, matching_keys: list[str]) -> tuple[dict[str, str], str]:
    """Use only explicitly supplied related-recording groups; never filenames."""
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Group manifest exceeds the size limit")
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("groups"), dict):
        raise ValueError("Group manifest must contain schema_version=1 and a groups mapping")
    groups = data["groups"]
    if any(key not in groups or not isinstance(groups[key], str) or not 1 <= len(groups[key].strip()) <= 200
           for key in matching_keys):
        raise ValueError("Every selected record needs an explicit nonempty group identifier")
    return {key: groups[key] for key in matching_keys}, hashlib.sha256(raw).hexdigest()


def cross_validate(videos: list[dict], *, folds: int = 5, kind: str = "lr", regularization: float = 1.0, pca: int = 16):
    import numpy as np
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
    counts = [sum(video["label"] == label for video in videos) for label in (0, 1)]
    groups_provided = all(video.get("group_id") is not None for video in videos)
    if any(video.get("group_id") is not None for video in videos) and not groups_provided:
        raise ValueError("Explicit recording groups must cover every training clip")
    if groups_provided:
        counts = [len({video["group_id"] for video in videos if video["label"] == label}) for label in (0, 1)]
    number = min(folds, *counts)
    if number < 2:
        raise ValueError("Whole-clip validation needs at least two clips in each binary class")
    splitter = StratifiedGroupKFold if groups_provided else StratifiedKFold
    splits = splitter(n_splits=number, shuffle=True, random_state=0)
    predictions = [None] * len(videos)
    groups = [video["group_id"] for video in videos] if groups_provided else None
    for train_indices, test_indices in splits.split(np.zeros(len(videos)), [video["label"] for video in videos], groups):
        if groups_provided and ({groups[index] for index in train_indices} & {groups[index] for index in test_indices}):
            raise ValueError("Related recording groups cannot cross a training fold")
        model = fit_model([videos[index] for index in train_indices], kind=kind, regularization=regularization, pca=pca)
        positive_column = list(model.classes_).index(1)
        for index in test_indices:
            predictions[index] = model.predict_proba(videos[index]["matrix"])[:, positive_column]
    grid = [evaluate_candidates(videos, predictions, float(threshold)) for threshold in np.linspace(0.05, 0.95, 37)]
    chosen = max(grid, key=lambda item: (item["balanced_clip_accuracy"], item["localized_labelled_points"], item["threshold"]))
    return chosen, grid, number


def load_training_caches(records: list[dict], features_dir: Path, maximum_distance: float) -> tuple[list[dict], dict]:
    by_key = {record["matching_key"]: record for record in records}
    if len(by_key) != len(records):
        raise ValueError("Duplicate label matching keys")
    videos, fingerprints, seen, matched_keys = [], set(), set(), set()
    unknown_frames = 0
    for path in sorted(features_dir.glob("*.json")):
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Feature cache exceeds the bounded size limit")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 2 or data.get("feature_version") != FEATURE_VERSION:
            raise ValueError("Legacy caches must be re-extracted with explicit frame observation masks")
        if data.get("dataset_split") != "training":
            raise ValueError("Only explicitly designated training caches may fit the scorer")
        record = by_key.get(data.get("matching_key"))
        if record is None:
            raise ValueError("A feature cache has no matching validated label record")
        if record["matching_key"] in matched_keys:
            raise ValueError("Multiple feature caches match the same label record")
        matched_keys.add(record["matching_key"])
        content_id = data.get("source_sha256")
        if (not isinstance(content_id, str) or len(content_id) != 64
                or any(character not in "0123456789abcdef" for character in content_id) or content_id in seen):
            raise ValueError("Duplicate or invalid source content identities would compromise clip validation")
        seen.add(content_id)
        supervision = point_supervision(record, data["timestamps"], data["duration_sec"], maximum_distance)
        unknown_frames += int((supervision < 0).sum())
        if not any(supervision >= 0):
            continue
        matrix = build_matrix(data["features"], data["timestamps"], FEATURE_VERSION)
        videos.append({"content_id": content_id, "matching_key": record["matching_key"], "matrix": matrix, "labels": supervision,
                       "label": int(record["has_violation"]), "point": record.get("timestamp_sec"), "timestamps": data["timestamps"]})
        fingerprints.add(json.dumps(data["extractor"], sort_keys=True))
    if matched_keys != set(by_key):
        raise ValueError("Every selected label record needs its own validated local feature cache")
    if not videos or len(fingerprints) != 1:
        raise ValueError("Consistent local feature artifacts and supervised training caches are required")
    return videos, {"vision_artifacts": json.loads(next(iter(fingerprints))), "unknown_frames_excluded": unknown_frames}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--features-dir", type=Path, default=ROOT / "cache" / "features" / "training")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "models" / "scorers", help="Base directory for versioned scorer runs")
    parser.add_argument("--run-id", default=None, help="Optional unique artifact version (letters, numbers, underscore, hyphen)")
    parser.add_argument("--groups", type=Path, help="Explicit user-provided related-recording groups; never inferred")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--point-max-distance", type=float, default=1.0)
    parser.add_argument("--model", choices=["lr", "hgb"], default="lr")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--C", type=float, default=1.0)
    parser.add_argument("--pca", type=int, default=16)
    args = parser.parse_args()
    if not 2 <= args.folds <= 10 or args.C <= 0 or not 0 <= args.pca <= 128 or not 0 <= args.point_max_distance <= 5:
        raise ValueError("Invalid training configuration")
    from backend.app.training.labels import import_labels
    imported = import_labels(args.labels)
    if not imported.valid:
        raise ValueError("Resolve label import issues before training")
    videos, metadata = load_training_caches(imported.records, args.features_dir, args.point_max_distance)
    group_fingerprint = None
    if args.groups:
        groups, group_fingerprint = load_group_manifest(args.groups, [video["matching_key"] for video in videos])
        for video in videos:
            video["group_id"] = groups[video["matching_key"]]
    chosen, grid, folds = cross_validate(videos, folds=args.folds, kind=args.model, regularization=args.C, pca=args.pca)
    model = fit_model(videos, kind=args.model, regularization=args.C, pca=args.pca)
    bundle = {"schema_version": 2, "feature_version": FEATURE_VERSION, "supervision": "binary_point_v1",
              "model": model, "threshold": chosen["threshold"], "smoothing_radius": 0,
              "point_max_distance_sec": args.point_max_distance, "vision_artifacts": metadata["vision_artifacts"]}
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    if not run_id or len(run_id) > 100 or any(not (character.isascii() and (character.isalnum() or character in "_-")) for character in run_id):
        raise ValueError("Invalid artifact version identifier")
    output_dir = args.output_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    import joblib
    temporary = output_dir / f"{SCORER_FILE}.tmp"
    joblib.dump(bundle, temporary)
    with temporary.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    temporary.replace(output_dir / SCORER_FILE)
    manifest = {"schema_version": 2, "feature_version": FEATURE_VERSION, "sha256": digest,
                "supervision": "binary_point_v1", "classification_available": False, "event_boundaries_available": False,
                "scikit_learn_version": importlib.metadata.version("scikit-learn")}
    (output_dir / SCORER_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    training_manifest = {"schema_version": 1, "run_id": run_id,
                         "training_source_sha256": sorted(video["content_id"] for video in videos),
                         "groups_provided": bool(args.groups), "groups_manifest_sha256": group_fingerprint,
                         "labels_input_sha256": imported.input_fingerprint.get("sha256"),
                         "training_group_ids": sorted({video["group_id"] for video in videos}) if args.groups else []}
    (output_dir / "training_manifest.json").write_text(json.dumps(training_manifest, indent=2) + "\n", encoding="utf-8")
    report = {"schema_version": 2, "training_clips": len(videos), "whole_clip_folds": folds, "chosen": chosen, "grid": grid,
              "unknown_frames_excluded": metadata["unknown_frames_excluded"], "types_available": False, "boundaries_available": False,
              "limitations": ["Point labels do not establish event extent or exhaustively mark all positive moments.",
                  ("Explicit related recording groups are kept within folds; the supplied grouping still requires review." if args.groups else
                   "Related recording/session groups are unavailable; whole-clip splits cannot establish independence of related clips."),
                  "This validation selected the threshold. An independent held-out test is required for a final performance claim.",
                  "Additional candidates in positive clips are unlabelled, not automatically false positives."]}
    report["groups_provided"] = bool(args.groups)
    report_path = args.report or ROOT / "reports" / "training" / run_id / "train_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scorer_saved": True, "training_clips": len(videos), "whole_clip_folds": folds,
                      "unknown_frames_excluded": metadata["unknown_frames_excluded"], "classification_available": False,
                      "run_id": run_id, "groups_provided": bool(args.groups)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(f"Training failed ({type(error).__name__}); review local label and feature validation.", file=sys.stderr)
        raise SystemExit(1) from None
