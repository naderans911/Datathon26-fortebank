# API contract

Both judging routes require the correct backend-configured `X-API-Key`. Keys are compared safely and never included in UI responses. Development OpenAPI is available at `/openapi.json`; endpoint metadata describes the judge and browser routes.

`POST /api/v1/analyze` accepts multipart form data with one field named `file`. `.mov` is supported. The service streams accepted uploads into a controlled job directory and returns HTTP 202 with `{"job_id":"opaque-id"}`. It does not wait for inference. Before acceptance, missing readiness gives 503, unsupported formats 415, invalid input 422, excessive size 413, throttling 429, and capacity exhaustion 503. Actual corrupt/undecodable media discovered by the worker fails the accepted job.

`GET /api/v1/jobs/{job_id}` returns one of the following. Unknown or demo job IDs return 404.

```json
{"job_id":"opaque-id","status":"processing"}
```

```json
{"job_id":"opaque-id","status":"done","verdict":"no_violation","violations":[]}
```

```json
{
  "job_id":"opaque-id",
  "status":"done",
  "verdict":"violation",
  "violations":[{
    "type":"Possible violation (unclassified)",
    "timecode_sec":2.4,
    "description":"Binary visual candidate. No verified rule mapping or legal basis has been established. Human review required.",
    "evidence_frames":[{"timestamp_sec":2.4,"image_base64":"actual-JPEG-base64-without-data-URL-prefix"}]
  }]
}
```

These snippets document the schema; they are not runtime fixtures. A positive result requires at least one event with one to three genuine JPEG frames. Timestamps are numeric seconds within the original clip duration. Distinct events may share timestamps. Successful verdict values are exactly `no_violation` and `violation`.

The CV adapter emits generic binary candidates; it does not infer an event category or legal provision from organizer binary labels. Its uncalibrated score is a model output, not proof of a visible action. A `no_violation` response means no candidate crossed the configured threshold in the sampled analysis. It is not a guarantee of compliant conduct. The browser's richer event has `rule:null` when no verified mapping exists; the required jury JSON fields remain unchanged.

```json
{"job_id":"opaque-id","status":"failed","error":{"code":"deadline_exceeded","message":"The analysis deadline expired. No complete verdict was produced."}}
```

The safe error object is an application extension. Failed jobs never include a successful verdict. Other safe error categories include invalid media, invalid model output, unavailable local prerequisites, and interrupted work. Queue time after acceptance consumes the same 285-second maximum budget.

## Browser API

`GET /api/ui/session` issues an anonymous HttpOnly cookie and returns `csrf_token`. Mutating calls need `X-CSRF-Token` and same-origin checks. `GET /api/ui/status` reports operational readiness without secrets. `GET /api/ui/rules` exposes the local read-only rule registry. Upload uses `POST /api/ui/analyze`. Job state uses `GET /api/ui/jobs/{job_id}` and includes a richer `result` on completion. Media is served only through session-owned `/api/ui/jobs/{job_id}/media/{filename}` URLs. `DELETE /api/ui/jobs/{job_id}` removes an owned terminal result and its media. Anonymous sessions expire; there is no account recovery or cross-session history.

When explicitly enabled, `/api/ui/demo/{positive|negative|failed}` generates isolated synthetic fixtures owned by the caller's session. These do not enter the real queue or judge result namespace and cannot make real analysis ready.

## Local judge example

Use an environment variable populated privately. Do not paste a real key into committed scripts or logs.

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/analyze -H "X-API-Key: $env:JURY_API_KEY" -F "file=@C:\private-data\validation.mov"
curl.exe http://127.0.0.1:8000/api/v1/jobs/REPLACE_WITH_JOB_ID -H "X-API-Key: $env:JURY_API_KEY"
```

The API key here is passed in process arguments by curl; on a shared machine prefer a private HTTP client that reads it from environment/config internally. The local benchmark runs the media pipeline directly and does not need the jury key.
