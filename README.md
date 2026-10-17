# Datathon 26 · ForteBank — AI-проверка кассовой дисциплины по видео

**Полное описание решения: [docs/SOLUTION.md](docs/SOLUTION.md)** (архитектура, модели, нормативная база, типы нарушений, ограничения).

Быстрый старт на macOS (Apple Silicon):

```bash
bash scripts/mac_setup.sh   # установка + веса моделей (один раз)
bash scripts/run_mac.sh     # сервис + публичная ссылка для жюри
```

Детектор `DETECTOR_BACKEND=cv` работает полностью локально: RT-DETR + DINOv2 + обученный временной классификатор. Правила взяты из постановления НБРК № 231 (`config/rules.json`).

---

## Forte Cash Review (base platform)

A connected, local-first video review prototype for the ForteBank Datathon 26 case. Upload a cashier video, follow persistent processing stages, and inspect timestamped findings, actual JPEG evidence and the source interpretation behind each finding. A human inspector makes the final assessment.

**Datathon prototype, not an official ForteBank service.** The production rule registry starts empty and the detector starts unconfigured. Real analysis remains unavailable until you supply a licensed local vision model and verified applicable rules. The separate synthetic demo can demonstrate the interface without a GPU. No banking detection accuracy or five-minute inference performance is claimed.

## Included

- React/TypeScript evidence-review UI, Forte colors, editable text and theme, responsive navigation, upload validation, processing recovery, video seeking, evidence enlargement, rule search and system readiness.
- FastAPI judging endpoints with `X-API-Key`, anonymous session-owned UI jobs and media, CSRF/origin checks, upload/rate/storage bounds and retention cleanup.
- Persistent SQLite queue, atomic job claims, a separate worker supervisor, heartbeat recovery and a deadline that includes accepted queue time.
- Local FFprobe/FFmpeg validation, source presentation timestamps, bounded temporal sampling, audio-free browser previews and real JPEG evidence.
- Replaceable unconfigured/Ollama detector adapters, strict structured-output and reference validation, local endpoint controls and rule snapshots.
- Isolated synthetic positive, negative and failed demonstrations, generated locally and disabled by default.

## Windows PowerShell setup

Run commands from the repository root. Install Python 3.13 and Node.js 24 LTS, plus a recent FFmpeg build containing both `ffmpeg.exe` and `ffprobe.exe`. The official [FFmpeg download page](https://ffmpeg.org/download.html) links Windows builds; review the license of the actual build you use. No global PowerShell execution-policy changes are needed.

```powershell
node --version
npm.cmd --version
python --version
ffmpeg -version
ffprobe -version

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
npm.cmd --prefix frontend ci
.\.venv\Scripts\python.exe scripts/setup_env.py
.\.venv\Scripts\python.exe scripts/preflight.py
npm.cmd --prefix frontend run build
```

`setup_env.py` creates an ignored `.env` containing a generated judge key and preserves an existing file. It does not print the key. If FFmpeg is not on PATH, set `FFMPEG_BINARY` and `FFPROBE_BINARY` in `.env` to your executable paths (forward slashes are convenient in dotenv files).

Start these in **two PowerShell terminals**, both at the repository root:

```powershell
# Terminal 1: API and built frontend
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2: persistent analysis worker
.\.venv\Scripts\python.exe -m backend.app.workers.runner
```

Open **http://127.0.0.1:8000**. System status reports the actual local prerequisites. API documentation is at `/docs`, with the generated schema at `/openapi.json`; it uses no external CDN assets.

For frontend development, run `npm.cmd --prefix frontend run dev` in a third terminal and open its local URL. Vite proxies API requests to port 8000. On macOS/Linux, use `.venv/bin/python` and `npm` instead of the Windows command paths.

## Try the synthetic demo

Set `ENABLE_DEMO=true` in your private `.env`, restart the API, and open **http://127.0.0.1:8000/demo**. FFmpeg is required to generate the moving-shape footage. The demo includes positive, negative and failed states, clearly labelled as synthetic. No model, GPU, bank procedure or competition footage is involved. The real upload path remains disabled until its own prerequisites pass.

To enable real analysis, prepare a commercially usable vision model locally, set `DETECTOR_BACKEND=ollama` and `LOCAL_VISION_MODEL` to its installed tag, configure the actual Ollama service with `OLLAMA_NO_CLOUD=1`, and register verified applicable rules. Restart **both the API and worker** after changing `.env` so they use the same configuration. See [rule/model configuration](docs/RULES.md) and [deployment/offline operation](docs/DEPLOYMENT.md). Nothing in setup automatically downloads model weights.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check backend scripts
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run test:e2e
```

The browser tests use installed Chrome on Windows, or a prepared Playwright Chromium elsewhere. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to an existing Chromium-based browser if needed. On a clean Linux setup, prepare the browser with `cd frontend` then `npx playwright install chromium`. Browser installation requires internet during setup. The local-model integration test is explicitly skipped until a model is configured; it is not a simulated pass. See [validation results and limits](docs/VALIDATION.md).

For the optional connected browser checks, start the built API with `ENABLE_DEMO=true`, then set `$env:LIVE_API_URL='http://127.0.0.1:8000'` before running `npm.cmd --prefix frontend run test:e2e`. These checks generate and delete synthetic jobs. Without that variable, only the connected checks are skipped; isolated UI checks still run. Repeated connected runs may reach the demo rate limit; use a separate test instance with a higher process-only `UPLOAD_RATE_PER_HOUR` if needed.

## Judge API and local evaluation

The exact routes are `POST /api/v1/analyze` (multipart `file`, prompt HTTP 202 with `job_id`) and `GET /api/v1/jobs/{job_id}`. Both require `X-API-Key`. Completion uses only `no_violation` or `violation`; failed or incomplete jobs never receive a successful verdict. [Full API contract](docs/API.md).

Run evaluation only on permitted training/validation footage and only locally:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark.py C:\private-data\validation --dataset-split validation --labels C:\private-data\labels.json
```

Optional label JSON maps filenames to timestamp lists, for example `{"synthetic.mov":[2.0]}`. The script records measured wall time, completion within five minutes and timestamp-based precision/recall when labels exist. It cannot measure class accuracy from timestamp-only labels. Results remain in ignored `reports/`. Never run this on judging footage or upload real data, frames, observations or reports to a cloud assistant.

## Storage and cleanup

All jobs, media, previews and SQLite metadata live under ignored `storage/`, outside the frontend. Sessions protect UI media. A browser session can delete its own completed or failed job. Set an explicitly permitted `RETENTION_HOURS`; the worker periodically removes expired terminal jobs. Manual cleanup is:

```powershell
.\.venv\Scripts\python.exe scripts/purge.py
```

Do not remove active job folders manually. Public deployment requires an explicit retention setting, HTTPS origin, secure cookies and a generated judge key. Configure separate retention for any backups. Secrets, videos, model weights and reports are excluded from Git and Docker build context.

## Docker and deployment

```powershell
docker compose up --build -d
docker compose ps
docker compose logs --tail 30 api worker
```

The API/frontend and worker share persistent local storage. Optional Ollama runs on an internal network with cloud features disabled and no exposed inference port. The application binds only host loopback; publish it through your own HTTPS reverse proxy. Source pushed to GitHub is not a public running application. Read [deployment requirements](docs/DEPLOYMENT.md) before exposing uploads.

## Project map

| Path | Purpose |
| --- | --- |
| `frontend/src/` | Pages, review components, API client, text and theme |
| `backend/app/api/` | Judge and session-scoped UI endpoints |
| `backend/app/core/`, `db/`, `workers/` | Configuration, safety controls, persistence and supervision |
| `backend/app/services/`, `detectors/` | Rules, local media, pipeline and replaceable inference |
| `config/rules.json` | Empty production registry; add verified rules intentionally |
| `examples/` | Clearly synthetic rule example |
| `scripts/` | Private setup, prerequisite checks, purge and local benchmark |
| `docs/` | [Architecture](docs/ARCHITECTURE.md), [case notes](docs/CASE_NOTES.md), [compliance](docs/COMPLIANCE.md), [licenses](docs/LICENSES.md) |

The [official Forte brand reference](https://forte.kz/en/logo) informed the supplied magenta/dark-magenta/coral/sky palette. This prototype uses a text title and system font fallback; it does not redistribute an official logo or proprietary font asset.
