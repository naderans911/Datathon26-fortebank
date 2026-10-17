"""Synthetic-only tests for actual-format organizer-label imports and resolution."""
from __future__ import annotations

import ast
import csv
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from backend.app.ml.dataset import load_labels, norm_stem, parse_time
from backend.app.training.labels import LabelDataError, WORKBOOK_HEADERS, import_labels, normalize_label, parse_timestamp
from backend.app.training.reporting import write_local_report
from backend.app.training.resolver import resolve_records
from backend.app.training.validation import validate_labels


def record(name="Х-8", *, positive=True, timestamp="1минута 8 секунда", row=2):
    return {"source_sheet": "labels", "source_row": row, "filename_raw": name,
            "timestamp_raw": timestamp if positive else None,
            "timestamp_sec": parse_timestamp(timestamp) if positive else None,
            "label_raw": "нарушение" if positive else "без нарушения",
            "has_violation": positive, "matching_key": norm_stem(name), "resolved_video_path": None,
            "event_type": None, "event_start_sec": None, "event_end_sec": None, "rule_id": None,
            "review_status": "not_reviewed"}


def json_input(tmp_path, records, **metadata):
    path = tmp_path / "synthetic-labels.json"
    path.write_text(json.dumps({"records": records, **metadata}, ensure_ascii=False), encoding="utf-8")
    return path


def workbook_input(tmp_path, records):
    openpyxl = pytest.importorskip("openpyxl", reason="XLSX tests require the declared openpyxl dependency")
    workbook = openpyxl.Workbook()
    workbook.active.title = "unrelated"
    workbook.active.append(["Do not use the active sheet"])
    sheet = workbook.create_sheet("labels")
    sheet.append(WORKBOOK_HEADERS)
    for entry in records:
        sheet.append([entry["filename_raw"], entry["timestamp_raw"], entry["label_raw"]])
    path = tmp_path / "synthetic-original.xlsx"
    workbook.save(path)
    workbook.close()
    return path


@pytest.mark.parametrize(("raw", "expected"), [
    ("22 секунда", 22), ("5 секунда", 5), ("57 секунда", 57),
    ("1минута 8 секунда", 68), ("1минута8секунда", 68),
    ("  1 МИНУТА 8 СЕКУНДА  ", 68), ("2 минуты", 120),
    ("0 секунда", 0), (0, 0), (0.25, 0.25), ("1,5 секунды", 1.5),
    (None, None), ("", None), ("   ", None),
])
def test_whole_russian_timestamp_parser(raw, expected):
    assert parse_timestamp(raw) == expected
    assert parse_time(raw) == expected


@pytest.mark.parametrize("raw", ["1минута 8 секунда garbage", "before 22 секунда", "1 8",
                                    "00:22", "22", "-2 секунда", "22 seconds", "нет",
                                    True, float("nan"), float("inf"), -1, {"seconds": 22}])
def test_ambiguous_or_unsupported_timestamp_is_rejected(raw):
    with pytest.raises(LabelDataError):
        parse_timestamp(raw)


@pytest.mark.parametrize(("raw", "expected"), [("нарушение", True), ("без нарушения", False),
                                              ("  БЕЗ   НАРУШЕНИЯ  ", False)])
def test_exact_normalized_binary_mapping(raw, expected):
    assert normalize_label(raw) is expected


@pytest.mark.parametrize("raw", ["", None, "неизвестно", "0", "false", "нет", "нарушение?", False])
def test_unknown_labels_are_not_negative(raw):
    with pytest.raises(LabelDataError):
        normalize_label(raw)


def test_json_records_preserve_unicode_null_negative_and_numbering_gaps(tmp_path):
    rows = [record("X-1"), record("Х-2", positive=False, row=3), record("Х-8", row=4), record("Х-48", positive=False, row=5)]
    result = import_labels(json_input(tmp_path, rows))
    assert result.valid, result.issues
    assert [item["filename_raw"] for item in result.records] == ["X-1", "Х-2", "Х-8", "Х-48"]
    assert len(result.records) == 4
    assert result.records[1]["timestamp_sec"] is None
    assert result.records[1]["timestamp_raw"] is None
    assert result.records[0]["event_start_sec"] is None and result.records[0]["rule_id"] is None
    assert result.records[2]["matching_key"] == "X-8"
    assert norm_stem("Х-АБВ.mov") == "X-АБВ"  # No general Cyrillic transliteration.
    assert norm_stem("x-8.mov") == "x-8"  # No implicit case folding.
    assert len(result.source_fingerprint["sha256"]) == 64


def test_only_explicit_negative_becomes_compatibility_empty_list(tmp_path):
    path = json_input(tmp_path, [record("X-1", timestamp="0 секунда"), record("Х-2", positive=False, row=3)])
    assert load_labels(path) == {"X-1": [0.0], "X-2": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["records"][1]["label_raw"] = ""
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    imported = import_labels(path)
    assert not imported.valid and imported.records[1]["has_violation"] is None
    assert any(item["code"] == "missing_or_unknown_label" for item in imported.issues)
    with pytest.raises(LabelDataError):
        load_labels(path)


def test_timestamp_and_binary_companion_disagreements_are_errors(tmp_path):
    raw = record()
    raw["timestamp_sec"] = 1
    raw["has_violation"] = False
    imported = import_labels(json_input(tmp_path, [raw]))
    assert not imported.valid
    assert {item["code"] for item in imported.issues} >= {"invalid_timestamp", "missing_or_unknown_label"}


def test_negative_zero_is_not_silently_treated_as_blank(tmp_path):
    raw = record(positive=False)
    raw.update(timestamp_raw=0, timestamp_sec=0)
    result = import_labels(json_input(tmp_path, [raw]))
    assert not result.valid and result.records[0]["timestamp_sec"] == 0
    assert any(item["code"] == "invalid_timestamp" for item in result.issues)


def test_actual_xlsx_headers_sheet_and_source_fingerprint(tmp_path):
    rows = [record("X-1", timestamp="22 секунда"), record("Х-8", positive=False, row=3)]
    path = workbook_input(tmp_path, rows)
    original = path.read_bytes()
    imported = import_labels(path)
    assert imported.valid, imported.issues
    assert imported.records[0]["source_sheet"] == "labels"
    assert imported.records[0]["source_row"] == 2
    assert imported.records[0]["timestamp_raw"] == "22 секунда"
    assert imported.records[1]["timestamp_sec"] is None
    assert path.read_bytes() == original
    normalized = tmp_path / "normalized.json"
    normalized.write_text(json.dumps(imported.to_dict(), ensure_ascii=False), encoding="utf-8")
    checked = import_labels(normalized, source_workbook=path)
    assert checked.valid and checked.provenance_status == "verified_against_source"
    modified = imported.to_dict()
    modified["records"][0]["timestamp_raw"] = "23 секунда"
    modified["records"][0]["timestamp_sec"] = 23
    normalized.write_text(json.dumps(modified, ensure_ascii=False), encoding="utf-8")
    assert any(item["code"] == "source_mismatch" for item in import_labels(normalized, source_workbook=path).issues)


def test_xlsx_exact_headers_required(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    workbook.active.title = "labels"
    workbook.active.append(["name", "timestamp", "label"])
    path = tmp_path / "wrong.xlsx"
    workbook.save(path)
    workbook.close()
    result = import_labels(path)
    assert not result.valid and result.issues[0]["code"] == "invalid_format"


def test_utf8_bom_csv_preserves_raw_unicode_and_explicit_binary(tmp_path):
    rows = [record("X-1"), record("Х-48", positive=False, row=3)]
    path = tmp_path / "normalized.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for entry in rows:
            writer.writerow({**entry, "has_violation": str(entry["has_violation"]).lower()})
    result = import_labels(path)
    assert result.valid, result.issues
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert result.records[1]["filename_raw"] == "Х-48"
    assert result.records[1]["has_violation"] is False
    assert result.records[1]["timestamp_sec"] is None


def test_legacy_filename_dictionary_is_not_misread_as_records(tmp_path):
    path = tmp_path / "old.json"
    path.write_text('{"X-1.mov": []}', encoding="utf-8")
    assert not import_labels(path).valid


def touch(root, filename):
    target = root / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"synthetic resolver fixture; not real footage")
    return target.resolve()


def test_exact_filename_and_exact_stem_precede_alias(tmp_path):
    exact = touch(tmp_path, "X-1.MOV")
    touch(tmp_path, "Х-1.mov")
    result = resolve_records([record("X-1.MOV")], tmp_path)
    assert result.valid and result.records[0]["resolved_video_path"] == str(exact)
    assert result.records[0]["resolution_method"] == "exact_filename"
    result = resolve_records([record("X-1")], tmp_path)
    assert result.valid and result.records[0]["resolved_video_path"] == str(exact)
    assert result.records[0]["resolution_method"] == "exact_stem"


def test_unique_alias_and_ambiguity_are_explicit(tmp_path):
    target = touch(tmp_path, "Х-8.MOV")
    result = resolve_records([record("X-8")], tmp_path)
    assert result.valid
    assert result.records[0]["resolution_method"] == "leading_x_alias"
    assert result.records[0]["filename_raw"] == "X-8"
    assert result.records[0]["resolved_video_path"] == str(target)
    touch(tmp_path, "subdirectory/Х-8.mp4")
    result = resolve_records([record("X-8")], tmp_path)
    assert not result.valid and result.issues[0]["code"] == "ambiguous_match"
    assert result.records[0]["resolved_video_path"] is None


def test_duplicate_mapping_missing_and_identifier_traversal(tmp_path):
    touch(tmp_path, "X-8.mov")
    result = resolve_records([record("X-8"), record("Х-8", row=3), record("X-48", row=4), record("../X-8", row=5)], tmp_path)
    assert {item["code"] for item in result.issues} == {"duplicate_mapping", "missing_video", "invalid_identifier"}
    assert all(row["resolved_video_path"] is None for row in result.records)


def test_duration_validation_reports_all_required_failure_groups(tmp_path):
    for name in ["X-1.mov", "Х-2.mov", "X-3.mov", "X-4.mov", "X-5.mov"]:
        touch(tmp_path, name)
    touch(tmp_path, "a/Х-8.mov")
    touch(tmp_path, "b/Х-8.mp4")
    rows = [record("X-1", timestamp="0 секунда"), record("Х-2", timestamp="57 секунда", row=3),
            record("X-3", positive=False, row=4), record("X-4", row=5), record("X-5", row=6),
            record("Х-5", row=7), record("X-8", row=8), record("X-48", row=9)]
    rows[4]["has_violation"] = None
    rows[3]["timestamp_sec"] = -1
    def probe(path, settings, deadline):
        if path.stem == "X-3":
            raise ValueError("Synthetic invalid media")
        return {"duration_sec": 10.0}
    result = validate_labels(rows, tmp_path, SimpleNamespace(), probe=probe)
    assert not result.valid
    assert set(result.to_dict()["failure_counts"]) == {
        "missing_video", "ambiguous_match", "duplicate_mapping", "invalid_media",
        "invalid_timestamp", "timestamp_outside_video", "missing_or_unknown_label"}
    assert all(count >= 1 for count in result.to_dict()["failure_counts"].values())
    assert result.records[0]["validation_status"] == "valid"
    assert result.records[0]["timestamp_sec"] == 0
    assert result.records[1]["duration_sec"] == 10.0


def test_timestamp_bounds_against_real_generated_synthetic_mov(tmp_path):
    from backend.app.core.config import Settings
    from backend.app.services.media import run_media
    settings = Settings()
    # Only generated lavfi footage is used; the user's data directory is never read.
    source = tmp_path / "X-1.mov"
    run_media([settings.ffmpeg_binary, "-v", "error", "-y", "-f", "lavfi", "-i",
               "color=c=magenta:s=160x96:r=30:d=2", "-an", "-c:v", "mpeg4", str(source)], time.time() + 30)
    rows = [record("X-1", timestamp="1 секунда")]
    valid = validate_labels(rows, tmp_path, settings)
    assert valid.valid, valid.issues
    assert valid.records[0]["duration_sec"] == pytest.approx(2, abs=.1)
    rows[0]["timestamp_sec"] = 3
    assert any(item["code"] == "timestamp_outside_video" for item in validate_labels(rows, tmp_path, settings).issues)


def test_cli_import_is_local_and_does_not_print_identifiers(tmp_path):
    path = json_input(tmp_path, [record("Х-PRIVATE-SYNTHETIC")])
    output = tmp_path / "report.json"
    command = [sys.executable, "scripts/import_labels.py", str(path), "--output", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "PRIVATE-SYNTHETIC" not in result.stdout
    assert json.loads(output.read_text(encoding="utf-8"))["records"][0]["timestamp_sec"] == 68
    original = path.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        write_local_report(path, {}, sources=[path])
    assert path.read_bytes() == original


def test_jury_inference_modules_never_import_organizer_label_helpers():
    root = Path(__file__).resolve().parents[1] / "app"
    paths = [root / "main.py", root / "ml/scorer.py", root / "ml/features.py"]
    for directory in ["api", "detectors", "services", "workers"]:
        paths.extend((root / directory).glob("*.py"))
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "training" not in module and not module.endswith("ml.dataset"), path.name
            elif isinstance(node, ast.Import):
                assert all("training" not in alias.name and not alias.name.endswith("ml.dataset") for alias in node.names), path.name
