"""Measure complete local analysis, without changing .env or extrapolating runtimes.

Default: locally generated synthetic shapes (runtime smoke, no accuracy claim).
For permitted local footage: DATA_DIR --labels LABELS --dataset-split validation.
The judge set is never a benchmark/training input. Reports stay local/ignored.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.config import Settings  # noqa: E402
from backend.app.detectors.cv import CVDetector  # noqa: E402
from backend.app.schemas.job import validate_result  # noqa: E402
from backend.app.services.media import run_media  # noqa: E402
from backend.app.services.pipeline import process_job  # noqa: E402
from backend.app.services.rules import active_rules, load_rules  # noqa: E402


def synthetic_source(path: Path, settings, seconds: float) -> None:
    run_media([settings.ffmpeg_binary, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
               f"testsrc2=size=640x360:rate=30:duration={seconds}", "-c:v", "mpeg4", "-q:v", "3",
               "-an", str(path)], time.time() + 30)


def benchmark_source(source: Path, settings, detector, rules: list[dict], workdir: Path) -> dict:
    job_id = uuid.uuid4().hex
    folder = workdir / "jobs" / job_id
    folder.mkdir(parents=True)
    shutil.copyfile(source, folder / "source.mov")
    started = time.time()
    job = {"id": job_id, "source_path": str((folder / "source.mov").resolve()), "rules_snapshot": rules,
           "accepted_at": started, "deadline_at": started + settings.job_deadline_seconds}
    stage_times = {}
    previous = [None, started]

    def progress(stage):
        now = time.time()
        if previous[0] is not None:
            stage_times[previous[0]] = now - previous[1]
        previous[:] = [stage, now]

    try:
        result = validate_result(process_job(job, settings, detector, progress), job, settings)
        stage_times[previous[0]] = time.time() - previous[1]
        return {"status": "done", "runtime_sec": time.time() - started, "duration_sec": result["duration_sec"],
                "verdict": result["verdict"], "candidate_times": [event["timecode_sec"] for event in result["events"]],
                "stage_runtimes_sec": stage_times, "detector": result.get("detector", {})}
    except Exception as error:
        return {"status": "failed", "runtime_sec": time.time() - started,
                "error_code": getattr(error, "code", "analysis_failed")}


def summarize(rows: list[dict], *, synthetic: bool) -> dict:
    completed = [row for row in rows if row["status"] == "done"]
    summary = {"clips_attempted": len(rows), "completed": len(completed), "failed": len(rows) - len(completed),
               "completed_under_300_sec": sum(row["runtime_sec"] < 300 for row in completed),
               "total_runtime_sec": sum(row["runtime_sec"] for row in rows),
               "synthetic": synthetic, "accuracy_measured": False}
    if not synthetic:
        tp = tn = fp = fn = points = localized = 0
        for row in completed:
            positive = row.get("has_violation")
            flagged = row["verdict"] == "violation"
            if positive is True:
                tp += int(flagged)
                fn += int(not flagged)
                point = row.get("timestamp_sec")
                if point is not None:
                    points += 1
                    localized += int(any(abs(timestamp - point) <= 2 for timestamp in row["candidate_times"]))
            elif positive is False:
                fp += int(flagged)
                tn += int(not flagged)
        summary.update(tp_clips=tp, tn_clips=tn, fp_clips=fp, fn_clips=fn, labelled_points=points,
                       localized_labelled_points=localized, point_tolerance_sec=2,
                       metrics_scope="Completed clips only; failures are separately counted as unprocessed.")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, nargs="?")
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--dataset-split", choices=["training", "validation"])
    parser.add_argument("--synthetic-seconds", type=float, default=6)
    parser.add_argument("--device", choices=["cpu", "auto", "cuda", "mps"], default="cpu")
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "benchmark.json")
    args = parser.parse_args()
    if not 1 <= args.synthetic_seconds <= 300:
        raise ValueError("Synthetic clip duration must be between 1 and 300 seconds")
    configured = Settings()
    rules = active_rules(load_rules(configured.rules_file))
    if not rules:
        raise ValueError("Configure applicable verified rules before benchmarking the full analysis service")
    detector = CVDetector(configured.model_copy(update={"cv_device": args.device}))
    if not detector.readiness()["ready"]:
        raise ValueError("The local model prerequisites are not ready")
    records = []
    if args.data:
        if args.labels is None or args.dataset_split is None:
            raise ValueError("Real local benchmarking requires explicit labels and training/validation designation")
        from backend.app.training.labels import import_labels
        from backend.app.training.resolver import resolve_records
        imported = import_labels(args.labels)
        if not imported.valid:
            raise ValueError("Resolve label import issues before benchmarking")
        resolved = resolve_records(imported.records, args.data)
        if resolved.issues:
            raise ValueError("Resolve local video matching issues before benchmarking")
        records = resolved.records
    elif args.labels or args.dataset_split:
        raise ValueError("Dataset options require an explicit local data directory")
    rows = []
    with tempfile.TemporaryDirectory(prefix="forte-benchmark-") as directory:
        workdir = Path(directory)
        settings = configured.model_copy(update={"storage_dir": workdir, "cv_device": args.device})
        if not args.data:
            source = workdir / "synthetic.mov"
            synthetic_source(source, settings, args.synthetic_seconds)
            records = [{"resolved_video_path": str(source)}]
        for number, record in enumerate(records):
            row = benchmark_source(Path(record["resolved_video_path"]), settings, detector, rules, workdir)
            row["cold_process"] = number == 0
            if args.data:
                row.update(has_violation=record["has_violation"], timestamp_sec=record.get("timestamp_sec"))
            rows.append(row)
    summary = summarize(rows, synthetic=args.data is None)
    report = {"schema_version": 2, "summary": summary, "records": rows, "device_requested": args.device,
              "limitations": ["Measured on this machine and these inputs only; no longest-clip extrapolation or five-minute guarantee.",
                             "Synthetic runs measure software/runtime behavior, never banking detection accuracy.",
                             "Point labels do not establish event type, boundaries, or exhaustive event coverage.",
                             "Unmatched candidates in positive clips are not automatically false positives."]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(f"Benchmark unavailable ({type(error).__name__}); check local prerequisites and labels.", file=sys.stderr)
        raise SystemExit(1) from None
