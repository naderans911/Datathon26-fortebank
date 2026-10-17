"""Import actual organizer-label metadata locally; never modify the workbook."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.training.labels import import_labels  # noqa: E402
from backend.app.training.reporting import write_local_report  # noqa: E402
from backend.app.training.resolver import resolve_records  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path, help="Original XLSX, normalized JSON records object, or UTF-8 BOM CSV.")
    parser.add_argument("--source-workbook", type=Path, help="Optional original XLSX for fingerprint/content verification.")
    parser.add_argument("--video-dir", type=Path, help="Optional actual local video directory for filename resolution only.")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/training/labels-import.json")
    args = parser.parse_args()
    imported = import_labels(args.labels, source_workbook=args.source_workbook)
    payload = imported.to_dict()
    if args.video_dir:
        resolution = resolve_records(imported.records, args.video_dir)
        payload["records"] = resolution.records
        payload["issues"] += resolution.issues
        payload["valid"] = imported.valid and resolution.valid
    payload["video_checks_performed"] = False
    payload["notice"] = "Metadata import and optional filename resolution do not verify video duration, detection, categories or rules."
    sources = [args.labels] + ([args.source_workbook] if args.source_workbook else [])
    try:
        write_local_report(args.output, payload, sources=sources)
    except (OSError, ValueError):
        print("Import report could not be written safely. Choose an ignored local report path; preserve source files.", file=sys.stderr)
        return 2
    print(f"Imported {len(payload['records'])} metadata records; validation errors: {len(payload['issues'])}.")
    print("Local report written. Media contents were not inspected. Run validate_labels.py locally for video checks.")
    return 0 if payload["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
