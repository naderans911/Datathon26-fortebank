# Architecture

The React application and FastAPI API share one origin in a built deployment. The Vite development server proxies `/api` to the local API. The browser uses an anonymous HttpOnly session cookie and a separate CSRF header; it never receives the judge API key.

```mermaid
flowchart LR
    B[Browser] --> U[Session-scoped UI API]
    J[Judge with X-API-Key] --> A[Judge API]
    U --> S[Shared upload service]
    A --> S
    S --> D[(SQLite job queue)]
    S --> F[Private local media]
    D --> W[Worker supervisor]
    W --> P[Isolated job process]
    P --> V[FFprobe and FFmpeg]
    P --> L[Local-only detector adapter]
    P --> R[Verified rule snapshot]
    P --> D
    P --> F
```

SQLite persists accepted jobs before acknowledgement. Claiming uses a database transaction. Worker heartbeats, job deadlines, and recovery retain a truthful state across process restarts. The deadline starts at acceptance, including time in the queue. A supervisor terminates processing and child tools when the budget expires. Queue/storage limits reject overload. The initial deployment uses one worker supervisor; concurrency is configurable and bounded.

The media pipeline probes the container, decodes locally, uses presentation timestamps, samples chronological windows, validates detector output, extracts actual JPEG evidence, and generates an audio-free MP4 preview. Classified detector output may map only verified rule IDs. CV binary candidates have no legal mapping (`rule:null` in the richer UI result); they still use the unchanged jury schema with a generic event type and explicit uncertainty. When a mapped rule exists, its source text is stored with the job so later registry edits cannot silently change prior findings. Judge responses carry JPEG base64; UI responses carry authenticated media URLs.

The detector interface separates model integration from HTTP and the UI. `UnconfiguredDetector` never reports ready. `OllamaLocalDetector` supports images and schema-constrained output, with no tools, model pulls, external searches, redirects, or cloud fallback. Deterministic code resolves frame IDs to timestamps and rules to source references. Model observations and footage are untrusted data.

`CVDetector` loads local RT-DETR/DINOv2 feature weights and a trusted binary scorer inside the isolated job process. Readiness checks do not import or allocate the heavy model. Every reported object belongs to a frame actually observed by the detector. Temporal score peaks are candidate moments, not annotated event boundaries. A legacy scorer may run with an explicit unvalidated-quality notice; its type classifier is ignored. Missing, incompatible or failed models cannot produce a negative verdict. Upload filenames and hashes are used for display/storage bookkeeping only, never answer selection.

Workbook import, deterministic local resolution, duration validation, feature extraction, training and evaluation are separate offline tools. A standalone loopback annotation app runs on port 8001 and is not mounted in the jury API. It reads a local validated report and stores revisioned reviewed events separately from organizer metadata. The main/public API and worker never load organizer labels. Feature, scorer, preprocessing, threshold and source manifests retain separate provenance; explicit recording groups constrain train/evaluation separation when supplied.

Synthetic demo fixtures have separate routes and storage. Demo enablement does not change real readiness. Demo data cannot enter the judge job namespace. There are no employee accounts, identity scores, banking transactions, or disciplinary decisions.

## Extension points

- Colors and radii: `frontend/src/styles/theme.css`.
- Interface wording: `frontend/src/locales/`.
- New detector: implement the adapter contract in `backend/app/detectors/`, then add an explicit factory selection and tests. Keep frame/rule validation in deterministic services.
- New rule: add a schema-valid record to `config/rules.json` after source/context verification. See `RULES.md`.
- New workflow: add a service and API contract, then presentation components. Preserve authorization and job ownership for every media route.

No real detector accuracy or viewpoint robustness has been established. Sampling can miss brief events, and local models can misinterpret actions. Human inspection remains required. Independently hosted inference processes need their own memory/concurrency bounds and cancellation verification; the worker cannot forcibly terminate a separate service's GPU computation through HTTP alone.
