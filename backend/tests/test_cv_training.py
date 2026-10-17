"""Synthetic correctness tests; never load private labels, caches or real footage."""
import json
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from backend.app.detectors.base import DetectionError, validate_observations
from backend.app.detectors.cv import CVDetector
from backend.app.ml.features import _valid_safetensors, artifacts_status
from backend.app.ml.scorer import Scorer, build_matrix, peaks
from scripts.train import cross_validate, evaluate_candidates, load_group_manifest, point_supervision, training_rows


def test_readiness_does_not_import_ml_or_load_models(tmp_path):
    code = (
        "import json,sys; from pathlib import Path; from types import SimpleNamespace;"
        "from backend.app.detectors.cv import CVDetector;"
        f"result=CVDetector(SimpleNamespace(cv_model_dir=Path({str(tmp_path)!r}))).readiness();"
        "print(json.dumps({'ready':result['ready'],'torch_loaded':'torch' in sys.modules,"
        "'numpy_loaded':'numpy' in sys.modules}))"
    )
    result = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True, timeout=20)
    assert json.loads(result.stdout) == {"ready": False, "torch_loaded": False, "numpy_loaded": False}


def fake_artifact(directory, model_type):
    directory.mkdir(parents=True)
    (directory / "config.json").write_text(json.dumps({"model_type": model_type}))
    (directory / "preprocessor_config.json").write_text("{}")
    header = json.dumps({"weight": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    (directory / "model.safetensors").write_bytes(struct.pack("<Q", len(header)) + header + b"\0" * 4)


def test_readiness_requires_weights_and_processor_not_only_config(tmp_path):
    fake_artifact(tmp_path / "rtdetr_r18vd", "rt_detr")
    fake_artifact(tmp_path / "dinov2-small", "dinov2")
    assert artifacts_status(tmp_path)["ready"]
    (tmp_path / "dinov2-small" / "model.safetensors").write_bytes(b"broken")
    assert not artifacts_status(tmp_path)["ready"]


def test_safetensor_header_is_bounded(tmp_path):
    artifact = tmp_path / "invalid.safetensors"
    artifact.write_bytes(struct.pack("<Q", 100_000_000) + b"{}")
    assert not _valid_safetensors(artifact)


def test_point_labels_never_make_other_positive_clip_frames_negative():
    pytest.importorskip("numpy")
    record = {"has_violation": True, "timestamp_sec": 2.1}
    labels = point_supervision(record, [0, 1, 2, 3, 4], 5, maximum_distance=0.5)
    assert labels.tolist() == [-1, -1, 1, -1, -1]
    assert point_supervision({"has_violation": True, "timestamp_sec": None}, [0, 1], 2).tolist() == [-1, -1]
    assert point_supervision({"has_violation": True, "timestamp_sec": 0.5}, [0, 1], 2, 0.1).tolist() == [-1, -1]


@pytest.mark.parametrize("record", [
    {"has_violation": False, "timestamp_sec": 1},
    {"has_violation": True, "timestamp_sec": -1},
    {"has_violation": True, "timestamp_sec": 99},
    {"has_violation": None, "timestamp_sec": None},
])
def test_invalid_or_unknown_supervision_is_not_negative(record):
    pytest.importorskip("numpy")
    with pytest.raises(ValueError):
        point_supervision(record, [0, 1], 2)


def test_confirmed_negative_clips_and_unknown_frames_in_training():
    np = pytest.importorskip("numpy")
    negative = point_supervision({"has_violation": False, "timestamp_sec": None}, [0, 1, 2], 3)
    assert negative.tolist() == [0, 0, 0]
    videos = [
        {"label": 0, "matrix": np.zeros((3, 2)), "labels": negative},
        {"label": 1, "matrix": np.ones((3, 2)), "labels": np.array([-1, 1, -1])},
    ]
    matrix, labels, weights = training_rows(videos)
    assert matrix.shape == (4, 2) and labels.tolist() == [0, 0, 0, 1]
    assert weights[:3].sum() == pytest.approx(weights[3])


def test_whole_clip_cv_uses_binary_point_supervision_without_types_or_groups():
    np = pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    videos = []
    for label in (0, 1):
        for index in range(3):
            matrix = np.array([[label * 4 + index / 10, 0], [label * 4 + index / 10, 1], [label * 4 + index / 10, 2]])
            videos.append({"label": label, "matrix": matrix, "labels": np.array([-1, 1, -1] if label else [0, 0, 0]),
                           "timestamps": [0, 1, 2], "point": 1 if label else None})
    chosen, grid, folds = cross_validate(videos, folds=3, pca=1)
    assert folds == 3 and len(grid) == 37
    assert chosen["tp_clips"] + chosen["fn_clips"] == 3
    assert chosen["tn_clips"] + chosen["fp_clips"] == 3
    assert "spurious_events_in_violation_videos" not in chosen


def test_additional_positive_clip_candidates_are_not_assumed_false_positives():
    pytest.importorskip("numpy")
    metrics = evaluate_candidates([{"label": 1, "point": 1, "timestamps": [0, 1, 10]}], [[0.1, 0.9, 0.9]], 0.5)
    assert metrics["tp_clips"] == 1 and metrics["fp_clips"] == 0 and metrics["localized_labelled_points"] == 1


def test_feature_schema_marks_unobserved_frames_and_rejects_carried_objects():
    np = pytest.importorskip("numpy")
    features = [{"embedding": [1.0, 0.0], "objects": [], "objects_observed": True},
                {"embedding": [0.0, 1.0], "objects": [], "objects_observed": False}]
    current, legacy = build_matrix(features, [0, 1], 2), build_matrix(features, [0, 1], 1)
    assert current.shape[1] == legacy.shape[1] + 1
    np.testing.assert_array_equal(current[:, -1], [1, 0])
    features[1]["objects"] = [{"label": "cell phone", "score": 0.8, "box": [0, 0, 1, 1]}]
    with pytest.raises(ValueError, match="copied"):
        build_matrix(features, [0, 1])


class FixedBinaryModel:
    classes_ = [0, 1]
    n_features_in_ = 2

    def predict_proba(self, matrix):
        import numpy as np
        return np.tile([0.25, 0.75], (len(matrix), 1))


def test_legacy_scorer_remains_binary_and_schema_checked():
    np = pytest.importorskip("numpy")
    scorer = Scorer({"model": FixedBinaryModel(), "threshold": 0.5, "default_type": "invented", "type_model": object()})
    assert scorer.feature_version == 1
    assert not scorer.provenance["classification_available"]
    assert not hasattr(scorer, "classify")
    np.testing.assert_allclose(scorer.predict(np.zeros((3, 2))), [0.75] * 3)
    with pytest.raises(ValueError, match="incompatible"):
        scorer.predict(np.zeros((3, 3)))


def test_missing_scorer_and_checksum_mismatch_are_failures(tmp_path):
    pytest.importorskip("numpy")
    joblib = pytest.importorskip("joblib")
    with pytest.raises(ValueError, match="required"):
        Scorer.load(tmp_path)
    joblib.dump({"model": FixedBinaryModel(), "threshold": 0.5}, tmp_path / "scorer.joblib")
    (tmp_path / "scorer.manifest.json").write_text(json.dumps({"sha256": "0" * 64}))
    with pytest.raises(ValueError, match="checksum"):
        Scorer.load(tmp_path)


def test_incompatible_serialized_sklearn_version_fails_before_inference(monkeypatch, tmp_path):
    joblib = pytest.importorskip("joblib")
    exceptions = pytest.importorskip("sklearn.exceptions")
    import warnings
    (tmp_path / "scorer.joblib").write_bytes(b"synthetic-placeholder")

    def load(_):
        warnings.warn(exceptions.InconsistentVersionWarning(estimator_name="SyntheticEstimator",
                      current_sklearn_version="new", original_sklearn_version="old"))
        return {"model": FixedBinaryModel(), "threshold": 0.5}

    monkeypatch.setattr(joblib, "load", load)
    with pytest.raises(ValueError, match="version used to serialize"):
        Scorer.load(tmp_path)


def test_binary_candidates_need_explicit_adapter_capability_and_valid_anchor():
    frames = [{"id": "frame-1", "timestamp_sec": 0}]
    observation = {"kind": "binary_candidate", "rule_id": None, "frame_ids": ["frame-1"], "anchor_frame_id": "frame-1",
                   "observation": "Binary classifier candidate, no category asserted.", "event_key": "candidate"}
    with pytest.raises(DetectionError):
        validate_observations([observation], frames, [])
    assert validate_observations([observation], frames, [], allow_binary_candidates=True)
    with pytest.raises(DetectionError):
        validate_observations([{**observation, "anchor_frame_id": "invented"}], frames, [], allow_binary_candidates=True)
    with pytest.raises(DetectionError):
        validate_observations([{**observation, "rule_id": "known"}], frames, [{"id": "known"}], allow_binary_candidates=True)


def test_cv_binary_candidate_never_uses_default_legal_type(monkeypatch, tmp_path):
    np = pytest.importorskip("numpy")
    from backend.app.ml import features, scorer
    class StubScorer:
        feature_version = 2
        vision_artifacts = None
        threshold = 0.5
        provenance = {"supervision": "synthetic_unit_test"}
        def predict(self, matrix):
            return np.array([0.1, 0.8, 0.1])
    monkeypatch.setattr(scorer.Scorer, "load", lambda _: StubScorer())
    monkeypatch.setattr(features, "extract", lambda *args, **kwargs: [{"embedding": [1, 0], "objects": [], "objects_observed": True}] * 3)
    monkeypatch.setattr(features, "load_models", lambda *args: {"artifacts": {}})
    detector = CVDetector(SimpleNamespace(cv_model_dir=tmp_path, cv_device="cpu", cv_threshold=None, max_events=24))
    frames = [{"id": f"f{i}", "path": str(tmp_path / f"{i}.jpg"), "timestamp_sec": i} for i in range(3)]
    output = detector.analyze_windows([{"frames": frames}], [{"id": "irrelevant-rule"}], time.time() + 10)
    assert len(output) == 1 and output[0]["rule_id"] is None
    assert output[0]["kind"] == "binary_candidate" and output[0]["anchor_frame_id"] == "f1"
    assert "uncalibrated" in output[0]["observation"] and "%" not in output[0]["observation"]


def test_cv_model_failure_never_returns_empty_success(monkeypatch, tmp_path):
    from backend.app.ml.scorer import Scorer
    monkeypatch.setattr(Scorer, "load", lambda _: (_ for _ in ()).throw(ValueError("invalid scorer")))
    detector = CVDetector(SimpleNamespace(cv_model_dir=tmp_path, cv_device="cpu", cv_threshold=None))
    frames = [{"id": f"f{i}", "path": "synthetic.jpg", "timestamp_sec": i} for i in range(2)]
    with pytest.raises(DetectionError, match="failed"):
        detector.analyze_windows([{"frames": frames}], [], time.time() + 10)


def test_peaks_are_sample_support_not_claimed_boundaries():
    pytest.importorskip("numpy")
    candidates = peaks([0.1, 0.8, 0.9, 0.1, 0.8], [0, 1, 2, 3, 10], 0.5)
    assert [candidate["peak"] for candidate in candidates] == [2, 4]
    assert all("event_type" not in candidate and "rule_id" not in candidate for candidate in candidates)


def test_explicit_groups_must_cover_selected_records_but_allow_global_manifest(tmp_path):
    manifest = tmp_path / "groups.json"
    manifest.write_text(json.dumps({"schema_version": 1, "groups": {"clip-a": "session-1", "clip-b": "session-2"}}))
    groups, digest = load_group_manifest(manifest, ["clip-a"])
    assert groups == {"clip-a": "session-1"} and len(digest) == 64
    with pytest.raises(ValueError, match="Every selected record"):
        load_group_manifest(manifest, ["clip-c"])


def test_related_clips_cannot_cross_training_validation_fold(monkeypatch):
    np = pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    from scripts import train
    videos = []
    for group in range(3):
        for label in (0, 1):
            videos.append({"label": label, "group_id": f"session-{group}",
                           "matrix": np.array([[group, label], [group, label]], dtype=float),
                           "labels": np.array([-1, 1] if label else [0, 0]),
                           "timestamps": [0, 1], "point": 1 if label else None})
    seen_test_groups = set()

    def fit(training_videos, **kwargs):
        training_groups = {int(video["matrix"][0, 0]) for video in training_videos}
        class GroupCheckingModel:
            classes_ = [0, 1]

            def predict_proba(self, matrix):
                test_group = int(matrix[0, 0])
                assert test_group not in training_groups
                seen_test_groups.add(test_group)
                positive = matrix[:, 1] * 0.8 + 0.1
                return np.column_stack((1 - positive, positive))
        return GroupCheckingModel()

    monkeypatch.setattr(train, "fit_model", fit)
    chosen, _, folds = cross_validate(videos, folds=3)
    assert folds == 3 and seen_test_groups == {0, 1, 2}
    assert chosen["tp_clips"] == 3 and chosen["tn_clips"] == 3


def test_training_cli_saves_versioned_binary_artifact_and_never_overwrites(tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    features_dir, output_dir = tmp_path / "features", tmp_path / "scorers"
    features_dir.mkdir()
    records, groups = [], {}
    for label in (0, 1):
        for index in range(3):
            key = f"synthetic-{label}-{index}"
            records.append({"filename_raw": key, "timestamp_raw": 1 if label else None,
                            "timestamp_sec": 1 if label else None, "has_violation": bool(label),
                            "label_raw": "нарушение" if label else "без нарушения"})
            groups[key] = f"synthetic-session-{index}"
            frames = [{"embedding": [label * 4 + index / 10, number / 10], "objects": [], "objects_observed": True}
                      for number in range(3)]
            cache = {"schema_version": 2, "feature_version": 2, "dataset_split": "training", "matching_key": key,
                     "source_sha256": f"{label * 3 + index:064x}", "timestamps": [0, 1, 2], "duration_sec": 3,
                     "features": frames, "extractor": {"detector": {"sha256": "a" * 64}, "embedder": {"sha256": "b" * 64}}}
            (features_dir / f"{key}.json").write_text(json.dumps(cache), encoding="utf-8")
    labels_path, groups_path = tmp_path / "labels.json", tmp_path / "groups.json"
    labels_path.write_text(json.dumps({"records": records}, ensure_ascii=False), encoding="utf-8")
    groups_path.write_text(json.dumps({"schema_version": 1, "groups": groups}), encoding="utf-8")
    report = tmp_path / "report.json"
    command = [sys.executable, "scripts/train.py", str(labels_path), "--features-dir", str(features_dir),
               "--output-dir", str(output_dir), "--run-id", "synthetic-v1", "--groups", str(groups_path),
               "--folds", "3", "--pca", "1", "--report", str(report)]
    first = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert first.returncode == 0, first.stderr
    scorer = Scorer.load(output_dir / "synthetic-v1")
    assert scorer.feature_version == 2 and scorer.provenance["supervision"] == "binary_point_v1"
    assert not scorer.provenance["classification_available"] and scorer.smoothing_radius == 0
    manifest = json.loads((output_dir / "synthetic-v1" / "training_manifest.json").read_text())
    assert len(manifest["training_source_sha256"]) == 6 and manifest["groups_provided"]
    training_report = json.loads(report.read_text())
    assert training_report["unknown_frames_excluded"] == 6
    assert training_report["groups_provided"] and not training_report["types_available"]
    original_digest = scorer.provenance["digest"]
    second = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert second.returncode == 1
    assert Scorer.load(output_dir / "synthetic-v1").provenance["digest"] == original_digest
