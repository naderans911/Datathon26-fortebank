# Actual organizer label metadata

The supplied description of `open_labels.xlsx` identifies worksheet `labels`, headers `наименование файла`, `таймстемп`, `нарушение / без нарушения`, and 42 records: 22 explicit positives and 20 explicit negatives. Those are expectations for that supplied version, not hardcoded application limits or proof of 42 video files on disk. The development tests use synthetic workbooks only.

## Supported parsing

- Full Russian quantities: `22 секунда` →22, `5 секунда` →5, `57 секунда` →57, `1минута 8 секунда` →68. Grammatical minute/second forms, decimal quantities and unit abbreviations are documented in the parser.
- Actual numeric Excel/JSON timestamp cells mean numeric seconds, including explicit zero. Text with no unit, spreadsheet dates/times, partial matches and unsupported formats fail. Canonical `timestamp_sec` CSV fields are explicitly numeric seconds.
- Blank negative timestamps stay null. Missing positive timestamps and timestamps on explicitly negative rows are inconsistent metadata and fail validation.
- Only normalized exact `нарушение` and `без нарушения` labels map to true and false. Missing/unknown labels remain errors.

`filename_raw`, `timestamp_raw` and `label_raw` are preserved. Only the leading capital Cyrillic `Х` maps to Latin `X` in an optional matching key; other letters and filename text are untouched. No extra records are generated from numeric gaps.

## Local commands

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-training.txt
.\.venv\Scripts\python.exe scripts/import_labels.py C:\private-data\open_labels.xlsx --video-dir C:\private-data\videos --output reports\training\labels-import.json
.\.venv\Scripts\python.exe scripts/validate_labels.py C:\private-data\open_labels.xlsx --video-dir C:\private-data\videos --output reports\training\labels-validation.json
```

To compare a normalized companion with its original source:

```powershell
.\.venv\Scripts\python.exe scripts/import_labels.py C:\private-data\ForteBank_Labels_Normalized.json --source-workbook C:\private-data\open_labels.xlsx --video-dir C:\private-data\videos --output reports\training\labels-import.json
```

The original workbook is never overwritten. Imports record SHA-256 source/input fingerprints and source rows. A companion's declaration is checked against the provided workbook when available. JSON must contain a `records` array; it is not interpreted as a jury result or filename-to-answer dictionary. UTF-8 BOM CSV uses explicit true/false values and blank unknown fields. Source metadata cannot silently establish a successful path resolution or reviewed event annotations.

## Resolution and validation

The local resolver inventories permitted video files, including `.mov` and `.MOV`, and applies these steps in order: exact filename, exact stem, then the explicitly allowed leading-letter alias. Only one candidate at the highest applicable step is accepted. Symlink escapes, ambiguous matches and multiple records mapped to one video are rejected. No file is renamed. The local report stores original identifiers, actual resolved paths and the resolution method.

Validation probes actual media and checks point timestamps against duration. It separates missing video, ambiguous match, duplicate mapping, invalid media, invalid timestamp, timestamp outside video and missing/unknown label. An invalid timestamp is not converted to zero. A terminal report is not evidence that every file passed: inspect `valid`, `failure_counts` and each record's `validation_status`.

Reports print only aggregate counts to the terminal. Paths, original metadata and alias-resolution details stay in ignored local reports. The commands return a nonzero exit code for invalid metadata or media. These real-video checks have not been performed by the cloud coding workflow.

## Review and training semantics

A supplied point is not an event start/end interval. A positive video can contain multiple events. Positive-video frames outside the supplied point are unknown, not automatic negatives. Event type, observation, boundaries, candidate rule and recording/session group require separate local human review.

Keep source labels, enriched annotations, split manifests, preprocessing, thresholds, model artifacts and verified rule registry versions separate. All clips from one video belong in one split. Use actual recording/session groups when known; consecutive numeric filenames do not establish groups. Proposed 30/6/6 class-balanced splits are proposals only and cannot override group independence.

Organizer labels are for local training/evaluation only. Jury inference does not import this package, read the workbook or select an answer by filename, identifier, checksum or row order.
