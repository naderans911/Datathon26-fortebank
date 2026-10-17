"""Cache local features for explicit training/validation records; never judging videos.

python scripts/extract_features.py DATA_DIR --labels LABELS --dataset-split training
Only aggregate progress is printed. Media identifiers and derived features stay
in the ignored cache; this command does not transmit frames or descriptions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.config import Settings  # noqa: E402
from backend.app.ml.features import FEATURE_VERSION, artifact_fingerprint, extract, load_models  # noqa: E402
from backend.app.services.media import extract_frames, probe_video, sample_indices  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--dataset-split", choices=["training", "validation"], required=True)
    parser.add_argument("--fps", type=float, default=2.0)
    parser.add_argument("--max-frames", type=int, default=400)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda", "mps"], default="cpu")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "cache" / "features")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    from backend.app.training.labels import import_labels
    from backend.app.training.resolver import resolve_records

    imported = import_labels(args.labels)
    if not imported.valid:
        raise ValueError("Label import has unresolved issues; run the local label validator first")
    resolved = resolve_records(imported.records, args.data)
    if resolved.issues:
        raise ValueError("Some label records cannot be resolved uniquely to local videos")
    settings = Settings().model_copy(update={"sampling_fps": args.fps, "max_sample_frames": args.max_frames})
    if not 0 < args.fps <= 5 or not 2 <= args.max_frames <= 1000:
        raise ValueError("Invalid bounded sampling configuration")
    output_dir = args.output_dir / args.dataset_split
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_sampling = {"sampling_fps": settings.sampling_fps, "max_sample_frames": settings.max_sample_frames,
                         "sample_width": settings.sample_width, "object_stride": 1}
    expected_artifacts = artifact_fingerprint(settings.cv_model_dir)
    seen_sources = set()
    completed, failed = 0, 0
    for number, record in enumerate(resolved.records, 1):
        source = Path(record["resolved_video_path"])
        with source.open("rb") as handle:
            source_digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if source_digest in seen_sources:
            raise ValueError("Multiple label records resolve to identical video content; resolve duplicates before extraction")
        seen_sources.add(source_digest)
        target = output_dir / f"{source_digest}.json"
        if target.is_file() and not args.force:
            if target.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("Existing feature cache exceeds the size limit")
            cached = json.loads(target.read_text(encoding="utf-8"))
            if (cached.get("schema_version") != 2 or cached.get("feature_version") != FEATURE_VERSION
                    or cached.get("dataset_split") != args.dataset_split or cached.get("source_sha256") != source_digest
                    or cached.get("matching_key") != record["matching_key"]
                    or cached.get("sampling") != expected_sampling
                    or {key: item.get("sha256") for key, item in cached.get("extractor", {}).items()}
                    != {key: item.get("sha256") for key, item in expected_artifacts.items()}):
                raise ValueError("Existing cache configuration differs; explicitly re-extract with --force")
            completed += 1
            continue
        started = time.time()
        deadline = started + settings.job_deadline_seconds
        try:
            with tempfile.TemporaryDirectory(prefix="forte-feature-") as work:
                metadata = probe_video(source, settings, deadline)
                frames = extract_frames(source, Path(work), sample_indices(metadata, settings), metadata, settings, deadline)
                features = extract([frame["path"] for frame in frames], settings.cv_model_dir, args.device, deadline,
                                   batch_size=1, det_stride=1)
                data = {"schema_version": 2, "feature_version": FEATURE_VERSION, "dataset_split": args.dataset_split,
                        "source_sha256": source_digest, "matching_key": record["matching_key"],
                        "filename_raw": record["filename_raw"], "duration_sec": metadata["duration_sec"],
                        "timestamps": [frame["timestamp_sec"] for frame in frames], "features": features,
                        "sampling": expected_sampling,
                        "extractor": load_models(settings.cv_model_dir, args.device, deadline)["artifacts"]}
                temporary = target.with_suffix(".json.tmp")
                temporary.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
                temporary.replace(target)
            completed += 1
        except Exception:
            failed += 1
            # Never print filenames, annotations, paths, model output or raw errors.
            print(f"Record {number}: local feature extraction failed; no cache result was saved.")
    print(json.dumps({"completed": completed, "failed": failed, "dataset_split": args.dataset_split}))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(f"Feature preparation failed ({type(error).__name__}); inspect the local validator report.", file=sys.stderr)
        raise SystemExit(1) from None
