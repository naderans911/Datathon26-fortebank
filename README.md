# Forte Cash Review

Local video review for the ForteBank Datathon. A React interface uploads a video to FastAPI, a separate SQLite-backed worker processes it, and the result includes a binary verdict, timestamps and actual JPEG evidence. This is an independent prototype; a model flag is a review aid, not a legal determination.

The actual organizer workbook contains binary labels and point timestamps. It does **not** supply event categories, event boundaries, applicable rules, recording groups or a trained detector. The importer preserves that distinction. No real workbook or footage is included in this repository.

## Windows setup

Use Python 3.13, Node.js 24, and FFmpeg/ffprobe. Run commands from this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock -r requirements-training.txt
npm.cmd --prefix frontend ci
.\.venv\Scripts\python.exe scripts/setup_env.py
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe scripts/preflight.py
```

The private `.env` contains the generated jury key. Existing settings are preserved. If FFmpeg is not on PATH, set `FFMPEG_BINARY` and `FFPROBE_BINARY` to the two executable paths. No credentials belong in Git or frontend code.

Start the API and worker in separate PowerShell terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
.\.venv\Scripts\python.exe -m backend.app.workers.runner
```

Open **http://127.0.0.1:8000** on that computer. The local API base is **http://127.0.0.1:8000/api/v1**. A localhost link is not reachable from another computer. GitHub stores the source; it does not host this Python/video application.

## Actual label import and validation

The importer reads the exact `labels` worksheet and three Russian headers, normalized JSON with a top-level `records` array, or UTF-8 BOM CSV. It parses the complete Russian timestamp (`1минута 8 секунда` becomes 68), retains blank negative timestamps as null, and rejects unknown labels instead of treating them as negative.

Only the known leading Cyrillic `Х`/Latin `X` alias is allowed for matching. Exact filenames and exact stems have priority. Missing, ambiguous and duplicate mappings fail explicitly; video filenames are never renamed.

Run these commands yourself on permitted training/validation footage. They do not modify the workbook:

```powershell
.\.venv\Scripts\python.exe scripts/import_labels.py C:\private-data\open_labels.xlsx --video-dir C:\private-data\videos --output reports\training\labels-import.json
.\.venv\Scripts\python.exe scripts/validate_labels.py C:\private-data\open_labels.xlsx --video-dir C:\private-data\videos --output reports\training\labels-validation.json
```

Reports remain local and ignored. Importing metadata does not establish that video files exist, timestamps fit their durations, or a detector is trained. The validation command checks the actual files. See [the actual-format import guide](docs/LABEL_IMPORT.md) for formats, fingerprints and failure categories.

## Local annotation workspace

After local validation, review matched videos on the separate loopback service. It supports video playback, jumping to the supplied point, multiple events, visible observations, optional manually entered boundaries, candidate rule IDs and draft/reviewed status. Source labels and points remain read-only. Candidate legal mappings remain drafts even when an observation is marked reviewed.

```powershell
$env:ENABLE_LOCAL_REVIEW='true'
$env:LOCAL_REVIEW_LABELS='C:\Users\YOUR_USER\path\to\datathon26\reports\training\labels-validation.json'
$env:LOCAL_REVIEW_VIDEO_ROOT='C:\private-data\videos'
$env:LOCAL_REVIEW_DATA_DIR='C:\private-data\annotations'
.\.venv\Scripts\python.exe -m uvicorn backend.app.review.app:create_app --factory --env-file .env --host 127.0.0.1 --port 8001 --no-proxy-headers
```

Open **http://127.0.0.1:8001/review**. Use the actual absolute validation-report path above. Annotations are revisioned local JSON files; simultaneous stale saves are rejected. The review service rejects public hosts, remote clients, forwarded requests and cross-origin writes. Never expose port8001 through a tunnel or mount its routes in the jury app.

For synthetic review tests, run `npm.cmd --prefix frontend run test:review`. The test creates its own synthetic labels/video, starts and stops an isolated review service, and leaves real data untouched.

## Model and rules

`config/rules.json` contains the supplied rule registry. Its source references and applicability must be reviewed independently of binary training labels. A point label cannot identify a Kazakhstan legal provision. Candidate mappings made during annotation remain drafts.

Local CV inference uses RT-DETR and DINOv2 feature models plus a private fitted scorer. Official feature weights alone are not a cashier-violation classifier. The previous scorer is retained on the existing development machine but is no longer distributed in the current Git tree. Fresh installations must supply a trusted compatible scorer or train one locally. See [model/rule configuration](docs/RULES.md) and [architecture](docs/ARCHITECTURE.md).

Synthetic demo examples are opt-in with `ENABLE_DEMO=true`; they demonstrate the interface and do not validate detection accuracy. Missing models and processing failures must not produce a negative verdict. Restart both API and worker after changing `.env`.

## Jury API

Both endpoints require `X-API-Key`:

- `POST /api/v1/analyze`: multipart field `file`; returns HTTP202 and `job_id`.
- `GET /api/v1/jobs/{job_id}`: processing, failed, or done with `violation` / `no_violation`.

A successful positive result includes actual JPEG base64 evidence. Failed jobs have no successful verdict. See [the exact contract](docs/API.md). `/docs` and `/openapi.json` are served locally without external CDN assets. Deliver the private key separately to judges; never put it in a public README or URL.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check backend scripts
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run test:e2e
```

Tests use synthetic fixtures. Browser tests use installed Chrome on Windows; elsewhere install Playwright Chromium first. Optional real-model tests require local weights. Test and validation results are recorded in [VALIDATION.md](docs/VALIDATION.md), with environment-dependent limits called out explicitly.

## Privacy and maintenance

Keep workbooks, normalized records, annotations, feature caches, videos, model weights and evaluation reports in ignored local paths. The current Git tree excludes the legacy scorer and per-video annotations; older Git commits have not been rewritten. Real data is never sent to a cloud coding tool. Do not train on judging footage.

Uploads and job metadata are in private `storage/`. Set an explicit permitted `RETENTION_HOURS`; worker cleanup applies to terminal jobs. Annotation records and backups need their own retention policy. Public operation requires HTTPS, secure cookies, a generated jury key, rate/storage limits and an explicit retention setting. See [deployment guidance](docs/DEPLOYMENT.md).

Theme tokens are in `frontend/src/styles/theme.css`; UI text is in `frontend/src/locales/en.ts`. Add detectors through `backend/app/detectors/` and its factory. Preserve the jury contract and keep all training-label reads outside inference.
