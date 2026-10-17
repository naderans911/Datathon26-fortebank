"""Local-only evaluation on training/validation footage. Never use judging videos.

Labels are JSON: {"clip.mov": [timestamp_seconds, ...]}. No violation types are
inferred from those labels. Reports remain in ignored reports/.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def score(predicted: list[float], actual: list[float], tolerance: float) -> dict:
    remaining = list(actual)
    matched = 0
    for timestamp in sorted(predicted):
        candidates = [(abs(timestamp - label), i) for i, label in enumerate(remaining)]
        if candidates:
            distance, index = min(candidates)
            if distance <= tolerance:
                matched += 1
                remaining.pop(index)
    return {
        "matched_events": matched,
        "predicted_events": len(predicted),
        "labelled_events": len(actual),
        "timestamp_tolerance_sec": tolerance,
        "precision": matched / len(predicted) if predicted else None,
        "recall": matched / len(actual) if actual else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--dataset-split", choices=["train", "validation"], required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--tolerance", type=float, default=2.0)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    try:
        local = ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        local = parsed.hostname == "localhost"
    if not local or parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        parser.error("The benchmark only accepts a loopback application URL.")
    if args.tolerance < 0:
        parser.error("Tolerance must be nonnegative.")
    load_dotenv(ROOT / ".env")
    key = os.environ.get("JURY_API_KEY")
    if not key:
        parser.error("Configure JURY_API_KEY privately in .env or the environment.")
    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else {}
    rows = []
    with httpx.Client(base_url=args.base_url, headers={"X-API-Key": key}, timeout=120,
                      follow_redirects=False, trust_env=False) as client:
        for path in sorted(args.directory.iterdir()):
            if path.suffix.lower() not in {".mov", ".mp4", ".m4v", ".mkv"}:
                continue
            started = time.monotonic()
            with path.open("rb") as stream:
                response = client.post("/api/v1/analyze", files={"file": (path.name, stream)})
            row = {"filename": path.name, "dataset_split": args.dataset_split}
            if response.status_code != 202:
                row.update(status="rejected", http_status=response.status_code)
            else:
                job_id = response.json()["job_id"]
                result = {"status": "processing"}
                while time.monotonic() - started < 310:
                    response = client.get(f"/api/v1/jobs/{job_id}")
                    response.raise_for_status()
                    result = response.json()
                    if result["status"] != "processing":
                        break
                    time.sleep(1)
                row.update(status=result["status"], verdict=result.get("verdict"))
                predicted = [item["timecode_sec"] for item in result.get("violations", [])]
                row["event_timestamps"] = predicted
                if result["status"] == "done" and path.name in labels:
                    row["label_metrics"] = score(predicted, labels[path.name], args.tolerance)
            row["wall_seconds"] = round(time.monotonic() - started, 3)
            row["returned_within_five_minutes"] = row["status"] == "done" and row["wall_seconds"] < 300
            rows.append(row)
    directory = ROOT / "reports"
    directory.mkdir(exist_ok=True)
    report = directory / f"benchmark-{int(time.time())}.json"
    report.write_text(json.dumps({"warning": "Local video-derived report. Do not publish.",
                                  "results": rows}, indent=2), encoding="utf-8")
    print("Evaluation finished. The report is saved locally under ignored reports/; no video details printed.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, httpx.HTTPError, ValueError, KeyError):
        print("Evaluation failed. Check the local service, labels, and file access; details suppressed.", file=sys.stderr)
        raise SystemExit(1)
