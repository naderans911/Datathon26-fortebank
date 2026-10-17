"""Held-out evaluation safeguards, using synthetic metadata and generated media."""
import json
import subprocess
import sys

import pytest

from backend.app.core.config import Settings
from scripts.benchmark import summarize, synthetic_source
from scripts.evaluate import check_split, evaluate_records, load_training_manifest, source_digest


def rows():
    return [{"matching_key": "X-1", "has_violation": True, "timestamp_sec": 1.0, "source_sha256": "a" * 64,
             "resolved_video_path": "synthetic-one.mov"},
            {"matching_key": "X-2", "has_violation": False, "timestamp_sec": None, "source_sha256": "b" * 64,
             "resolved_video_path": "synthetic-two.mov"}]


def manifest(**changes):
    return {"schema_version": 1, "training_source_sha256": ["c" * 64], "groups_provided": False,
            "training_group_ids": [], **changes}


def test_split_checks_actual_content_and_explicit_groups_only():
    assert not check_split(rows(), None)["held_out_independence_verified"]
    no_groups = check_split(rows(), manifest())
    assert no_groups["content_overlap_checked"] and no_groups["group_independence"] == "unknown"
    with pytest.raises(ValueError, match="content overlaps"):
        check_split(rows(), manifest(training_source_sha256=["a" * 64]))
    with pytest.raises(ValueError, match="Duplicate source"):
        check_split([rows()[0], rows()[0]], manifest())
    grouped = manifest(groups_provided=True, training_group_ids=["training-session"])
    groups = {"X-1": "validation-session", "X-2": "another-validation-session"}
    assert check_split(rows(), grouped, groups)["held_out_independence_verified"]
    with pytest.raises(ValueError, match="groups overlap"):
        check_split(rows(), grouped, {**groups, "X-1": "training-session"})
    # Explicit group claims alone cannot replace missing training provenance.
    assert check_split(rows(), None, groups)["group_independence"] == "unknown"


def test_manifest_missing_is_unknown_but_malformed_is_rejected(tmp_path):
    assert load_training_manifest(tmp_path) is None
    path = tmp_path / "training_manifest.json"
    path.write_text(json.dumps(manifest()), encoding="utf-8")
    assert load_training_manifest(tmp_path) == manifest()
    path.write_text(json.dumps(manifest(training_source_sha256=["filename.mov"])), encoding="utf-8")
    with pytest.raises(ValueError, match="identify training source"):
        load_training_manifest(tmp_path)


def test_fixed_threshold_and_failures_remain_unprocessed(tmp_path):
    settings = Settings(_env_file=None, cv_threshold=.63)
    observed = []

    def run(source, current, detector, rules, workdir):
        observed.append(current.cv_threshold)
        return {"status": "done", "runtime_sec": 2, "verdict": "violation", "candidate_times": [1.0],
                "detector": {"digest": "good" if len(observed) == 1 else "changed"}}

    result = evaluate_records(rows(), settings, object(), [], tmp_path, scorer_digest="good", runner=run)
    assert observed == [.63, .63]
    assert result[1]["status"] == "failed" and result[1]["error_code"] == "scorer_changed"
    summary = summarize(result, synthetic=False)
    assert summary["completed"] == 1 and summary["failed"] == 1
    assert summary["tp_clips"] == 1 and summary["tn_clips"] == 0
    assert summary["localized_labelled_points"] == 1
    assert result[0]["cold_process"] and not result[1]["cold_process"]


def test_scorer_path_is_optional_and_resolved_independently(tmp_path):
    assert Settings(_env_file=None).cv_scorer_dir is None
    assert Settings(_env_file=None, cv_scorer_dir="").cv_scorer_dir is None
    settings = Settings(_env_file=None, cv_scorer_dir=tmp_path / "version", cv_model_dir=tmp_path / "weights")
    assert settings.cv_scorer_dir == (tmp_path / "version").resolve()
    assert settings.cv_model_dir == (tmp_path / "weights").resolve()


def test_evaluation_cli_requires_explicit_validation_split():
    process = subprocess.run([sys.executable, "scripts/evaluate.py", "--data", "synthetic",
                              "--labels", "synthetic.json", "--dataset-split", "training"],
                             capture_output=True, text=True, timeout=30)
    assert process.returncode == 2
    assert "invalid choice" in process.stderr


def test_full_generated_video_pipeline_produces_real_evidence(tmp_path):
    settings = Settings().model_copy(update={"storage_dir": tmp_path, "sampling_fps": 2})
    source = tmp_path / "input.mov"
    synthetic_source(source, settings, 2)
    rule = {"id": "TEST-EVALUATION", "title": "Synthetic test", "event_type": "Synthetic event",
            "jurisdiction": "Test", "source_type": "internal_procedure", "document_title": "Synthetic test procedure",
            "source_url": None, "section_or_paragraph": None, "relevant_excerpt": "Generated shapes move.",
            "observed_condition": "Generated shape motion", "required_context": ["Synthetic test"],
            "interpretation": "Test-only interpretation", "limitations": ["Synthetic only"],
            "verification_status": "verified", "verified_at": "2026-01-01", "enabled": True, "version": "1"}

    class GeneratedDetector:
        supports_binary_candidates = True
        provenance = {"digest": "synthetic-digest"}

        def analyze_windows(self, windows, rules, deadline):
            identifier = windows[0]["frames"][1]["id"]
            return [{"rule_id": None, "kind": "binary_candidate", "frame_ids": [identifier],
                     "anchor_frame_id": identifier, "observation": "A generated shape moves.", "event_key": "synthetic"}]

    record = {**rows()[0], "resolved_video_path": str(source), "source_sha256": source_digest(source)}
    result = evaluate_records([record], settings, GeneratedDetector(), [rule], tmp_path,
                              scorer_digest="synthetic-digest")
    assert result[0]["status"] == "done" and result[0]["verdict"] == "violation"
    evidence = list((tmp_path / "jobs").glob("*/evidence/*.jpg"))
    assert evidence and all(path.stat().st_size > 0 for path in evidence)
    assert "preparing_evidence" in result[0]["stage_runtimes_sec"]
    assert len(result[0]["candidate_times"]) == 1
    assert source_digest(source) == record["source_sha256"]
