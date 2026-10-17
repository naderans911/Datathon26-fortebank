# Deployment and offline operation

No public application has been deployed by creating this repository. GitHub stores source; GitHub Pages cannot run this Python/video worker stack. Deploy the containers or native processes on a team-controlled machine with the required CPU/GPU and persistent local storage.

## Local Docker Compose

Create `.env` with `python scripts/setup_env.py`, then run `docker compose up --build -d`. The API binds the host's loopback port 8000. The React build is served from the API. The worker shares the `review-data` volume and the read-only rule configuration. Inspect `docker compose ps` and System status; an HTTP health check alone does not mean the analysis model is ready.

Compose uses an internal network for API, worker, and optional Ollama, preventing ordinary outbound internet access from those containers. The Ollama service has no published port and sets `OLLAMA_NO_CLOUD=1` in the actual inference process. It is enabled with `docker compose --profile local-model up -d`. Configure a licensed, prepared local vision model first; neither startup nor analysis downloads model weights.

The inference image is pinned to Ollama 0.40.5; its [upstream release](https://github.com/ollama/ollama/releases/tag/v0.40.5) was checked during implementation. Images, OS packages, npm/Python packages and selected weights need preparation while internet is available. Build and cache images ahead of the offline test. For reproducible delivery, record image digests and the exact FFmpeg package/build with your deployment evidence.

Prepared Ollama weights must be placed in the `ollama-models` volume using an approved local copy/import workflow. Do not temporarily expose the Ollama port to the public. Container `127.0.0.1` means that container: the application connects to `http://ollama:11434` on the private Compose network, allowlisted with `ALLOWED_OLLAMA_HOSTS=["ollama"]`. Native Windows processes use `http://127.0.0.1:11434`.

## Native Ollama

Stop an already running Ollama service before starting another instance. In the PowerShell process that actually launches the service:

```powershell
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_HOST = '127.0.0.1:11434'
ollama serve
```

Setting this only in the FastAPI environment does not configure an independently running Ollama service. Verify the service configuration as described in the [Ollama FAQ](https://docs.ollama.com/faq). Do not choose a `:cloud` model. The adapter checks installed model metadata and vision capability, blocks public destinations, rejects remote-model metadata, and never follows redirects. A team-hosted internal service requires an explicit allowed host and private DNS results. HTTPS certificates must be valid for the pinned private IP.

## Public HTTPS application

Place a trusted HTTPS reverse proxy in front of the API's loopback endpoint. Configure the proxy's request-body size to at most the application upload limit plus multipart overhead and a bounded upload timeout. Keep the worker, SQLite files, media volume, model service, and environment private. Forward only the necessary application port. Restrict forwarded-header trust to your actual proxy, and configure per-client upload rate limits at that proxy as well.

Set these private deployment values in `.env`:

```dotenv
APP_ENV=production
SECURE_COOKIES=true
PUBLIC_ORIGIN=https://your-actual-application-domain
RETENTION_HOURS=24
```

The retention value above is an example, not a competition permission. Choose a period within the permitted data-use window; production startup rejects an unspecified retention policy. Configure a generated `JURY_API_KEY` of at least 32 characters. Deliver the key privately to judges, never in source, URLs, screenshots, browser bundles, or public documentation.

Verify the two exact routes over HTTPS: `POST /api/v1/analyze` and `GET /api/v1/jobs/{job_id}`, with `X-API-Key`. Verify a valid `.mov` acceptance, actual processing stages, completed evidence, wrong-key denial, cross-session denial, and failure states. Confirm the worker heartbeat, model, FFmpeg and verified rules in System status. Restart containers and confirm a retained job remains accessible to its owning session.

The worker periodically applies a configured retention policy to terminal jobs. A manual purge is `python scripts/purge.py`, or `docker compose exec api python scripts/purge.py`. The browser can delete its own terminal result. Preserve active jobs until the supervisor stops them. Backups, filesystem snapshots and external proxy logs require their own retention policy.

## Offline verification

1. Prepare dependencies, containers, FFmpeg and a licensed model without using judging footage.
2. Confirm the actual Ollama service has `OLLAMA_NO_CLOUD=1` and no public inference port. Verify the installed model is local and vision-capable.
3. Block outbound internet for the application, worker and Ollama at the network/firewall boundary while preserving the internal network. Do this in an isolated deployment, not by disabling unrelated services on a shared machine.
4. Load the local application, upload a locally generated synthetic fixture, and verify real adapter execution, state transitions, evidence and authenticated media access. Synthetic fixture processing does not establish real banking accuracy.
5. Inspect network telemetry locally: no runtime dependency should request internet resources. Then benchmark permitted training/validation footage locally, without copying its frames, logs or derived reports into cloud-assistant tools.

The offline deployment, GPU behavior, real-model inference and public HTTPS path must be verified on the target host. This source delivery does not claim they have been tested.

The supervisor terminates the job process and its FFmpeg descendants at the deadline. Closing a client connection requests cancellation of an in-flight Ollama request; termination of computation inside an independently running inference service must be verified on that service/version. Bound Ollama concurrency and host/container memory separately. This prototype does not claim that a client disconnect alone is a universal GPU cancellation mechanism.
