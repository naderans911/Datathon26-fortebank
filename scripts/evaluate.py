"""Evaluate explicitly held-out local videos at the deployed, fixed threshold.

No model fitting or threshold search occurs here. Training content and supplied
recording/session groups are checked for overlap when their manifest is present.
Missing provenance is reported as unknown independence, never as a valid split.
Labels, reports, and generated evidence remain local; stdout contains aggregates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.config import Settings  # noqa: E402
from backend.app.detectors.cv import CVDetector  # noqa: E402
from backend.app.ml.scorer import SCORER_FILE, Scorer  # noqa: E402
from backend.app.services.rules import active_rules, load_rules  # noqa: E402
from backend.app.training.labels import import_labels  # noqa: E402
from backend.app.training.reporting import write_local_report  # noqa: E402
from backend.app.training.validation import validate_labels  # noqa: E402
from scripts.benchmark import benchmark_source, summarize  # noqa: E402


def source_digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def load_training_manifest(scorer_dir: Path) -> dict | None:
    path = scorer_dir / "training_manifest.json"
    if not path.exists():
        return None
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("The training manifest exceeds the supported size limit")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unsupported training provenance manifest")
    content_ids = data.get("training_source_sha256")
    if (not isinstance(content_ids, list) or not content_ids
            or any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value) for value in content_ids)):
        raise ValueError("The training manifest must identify training source content")
    supplied = data.get("groups_provided")
    groups = data.get("training_group_ids", [])
    if (not isinstance(supplied, bool) or not isinstance(groups, list)
            or any(not isinstance(value, str) or not value.strip() for value in groups)
            or (supplied and not groups)):
        raise ValueError("Invalid training group provenance")
    return data


def check_split(records: list[dict], manifest: dict | None, groups: dict | None = None) -> dict:
    """Use actual content identities and explicit groups; never infer sessions."""
    content = [record["source_sha256"] for record in records]
    if len(set(content)) != len(content):
        raise ValueError("Duplicate source content in the evaluation set requires explicit review")
    checks = {"declared_split": "validation", "content_overlap_checked": manifest is not None,
              "group_overlap_checked": False, "group_independence": "unknown",
              "training_manifest_available": manifest is not None}
    if manifest is not None:
        if set(content) & set(manifest["training_source_sha256"]):
            raise ValueError("Evaluation content overlaps the scorer training set")
        if groups is not None and manifest["groups_provided"]:
            evaluation_groups = {groups[record["matching_key"]] for record in records}
            if evaluation_groups & set(manifest["training_group_ids"]):
                raise ValueError("Evaluation groups overlap the scorer training groups")
            checks.update(group_overlap_checked=True, group_independence="explicit_groups_disjoint")
    checks["held_out_independence_verified"] = checks["content_overlap_checked"] and checks["group_overlap_checked"]
    return checks


def evaluate_records(records: list[dict], settings, detector, rules: list[dict], workdir: Path,
                     *, scorer_digest: str, runner=None) -> list[dict]:
    """Run the complete media/evidence pipeline; injected runner is for tests only."""
    run = runner or benchmark_source
    rows = []
    for number, record in enumerate(records):
        row = run(Path(record["resolved_video_path"]), settings, detector, rules, workdir)
        if row["status"] == "done" and row.get("detector", {}).get("digest") != scorer_digest:
            row = {"status": "failed", "runtime_sec": row["runtime_sec"], "error_code": "scorer_changed"}
        row.update(has_violation=record["has_violation"], timestamp_sec=record.get("timestamp_sec"),
                   source_sha256=record["source_sha256"], cold_process=number == 0)
        rows.append(row)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--source-workbook", type=Path)
    parser.add_argument("--dataset-split", choices=["validation"], required=True)
    parser.add_argument("--scorer-dir", type=Path)
    parser.add_argument("--groups", type=Path)
    parser.add_argument("--device", choices=["cpu", "auto", "cuda", "mps"])
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "training" / "evaluation.json")
    args = parser.parse_args(argv)
    configured = Settings()
    if args.scorer_dir is not None:
        configured = configured.model_copy(update={"cv_scorer_dir": args.scorer_dir.resolve()})
    if args.device is not None:
        configured = configured.model_copy(update={"cv_device": args.device})
    scorer_dir = configured.cv_scorer_dir or configured.cv_model_dir
    imported = import_labels(args.labels, source_workbook=args.source_workbook)
    validated = validate_labels(imported.records, args.data, configured, import_issues=imported.issues)
    sources = [args.labels, scorer_dir / SCORER_FILE, scorer_dir / "training_manifest.json"]
    sources.extend(path for path in (args.source_workbook, args.groups) if path is not None)
    sources.extend(Path(record["resolved_video_path"]) for record in validated.records if record.get("resolved_video_path"))
    if not validated.valid:
        write_local_report(args.report, {"schema_version": 1, "status": "validation_failed",
                           "source_fingerprint": imported.source_fingerprint, **validated.to_dict()}, sources=sources)
        print(json.dumps({"evaluation_started": False, "validation_errors": len(validated.issues)}))
        return 1
    records = validated.records
    for record in records:
        record["source_sha256"] = source_digest(Path(record["resolved_video_path"]))
    manifest = load_training_manifest(scorer_dir)
    groups, group_fingerprint = None, None
    if args.groups is not None:
        from scripts.train import load_group_manifest
        groups, group_fingerprint = load_group_manifest(args.groups, [record["matching_key"] for record in records])
    split = check_split(records, manifest, groups)
    rules = active_rules(load_rules(configured.rules_file))
    if not rules:
        raise ValueError("Configure applicable verified rules before evaluating the full analysis service")
    scorer = Scorer.load(scorer_dir)
    threshold = configured.cv_threshold if configured.cv_threshold is not None else scorer.threshold
    # Freeze the deployed value once. No validation labels are used to choose it.
    configured = configured.model_copy(update={"cv_threshold": threshold})
    with tempfile.TemporaryDirectory(prefix="forte-evaluate-") as directory:
        settings = configured.model_copy(update={"storage_dir": Path(directory)})
        detector = CVDetector(settings)
        if not detector.readiness()["ready"]:
            raise ValueError("The local model prerequisites are not ready")
        rows = evaluate_records(records, settings, detector, rules, Path(directory), scorer_digest=scorer.provenance["digest"])
    summary = summarize(rows, synthetic=False)
    summary.update(accuracy_measured=bool(summary["completed"]), binary_clip_metrics_measured=bool(summary["completed"]), threshold_selected_on_evaluation=False,
                   held_out_independence_verified=split["held_out_independence_verified"])
    report = {"schema_version": 1, "status": "completed" if not summary["failed"] else "incomplete",
              "summary": summary, "records": rows, "split_checks": split,
              "source_fingerprint": imported.source_fingerprint, "source_provenance": imported.provenance_status,
              "groups_manifest_sha256": group_fingerprint, "scorer_digest": scorer.provenance["digest"],
              "fixed_threshold": threshold, "device_requested": configured.cv_device,
              "limitations": ["Point labels do not establish event type, start/end boundaries or exhaustive event coverage.",
                  "Unmatched candidates in positive clips remain unlabelled; they are not automatically false positives.",
                  "Failures are unprocessed clips, not clean results; clip metrics cover completed clips only.",
                  "Without explicit group metadata and training provenance, independence from related recordings is unknown.",
                  "Results apply to the supplied local validation set; they do not establish hidden judge performance.",
                  "Measured full media/evidence pipeline runtime excludes API queue and upload time; no five-minute guarantee."]}
    write_local_report(args.report, report, sources=sources)
    print(json.dumps(summary))
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as error:
        print(f"Evaluation unavailable ({type(error).__name__}); check local labels, split provenance and model prerequisites.", file=sys.stderr)
        raise SystemExit(1) from None
