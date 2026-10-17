"""Validate organizer labels against local files and decoded media durations.

Run only on permitted local training/validation footage. Output stays in an
ignored local report; no media, labels, filenames or observations are printed.
"""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.config import Settings  # noqa: E402
from backend.app.training.labels import import_labels  # noqa: E402
from backend.app.training.reporting import write_local_report  # noqa: E402
from backend.app.training.validation import validate_labels  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--video-dir", required=True, type=Path)
    parser.add_argument("--source-workbook", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/training/labels-validation.json")
    parser.add_argument("--probe-timeout", type=float, default=60)
    args = parser.parse_args()
    if not 0 < args.probe_timeout <= 600:
        parser.error("--probe-timeout must be positive and no greater than 600 seconds.")
    imported = import_labels(args.labels, source_workbook=args.source_workbook)
    validated = validate_labels(imported.records, args.video_dir, Settings(), import_issues=imported.issues,
                                probe_timeout_seconds=args.probe_timeout)
    payload = {**imported.to_dict(), **validated.to_dict(), "video_checks_performed": True,
               "notice": "A point timestamp is not an event boundary or legal-rule mapping. No model has been trained by this validation."}
    sources = [args.labels] + ([args.source_workbook] if args.source_workbook else [])
    try:
        write_local_report(args.output, payload, sources=sources)
    except (OSError, ValueError):
        print("Validation report could not be written safely. Choose an ignored local report path.", file=sys.stderr)
        return 2
    print(f"Checked {len(payload['records'])} records; valid records: {payload['summary']['valid_records']}.")
    for code, count in payload["failure_counts"].items():
        print(f"{code}: {count}")
    print("Full details and any alias resolutions are stored only in the local report.")
    return 0 if payload["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
