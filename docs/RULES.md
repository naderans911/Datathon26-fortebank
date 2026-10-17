# Rule registry and model setup

Production starts with `config/rules.json` containing an empty array. A working local model alone is insufficient for readiness. Add at least one enabled, verified rule applicable to the actual camera setup and procedure.

Each record contains `id`, `title`, `event_type`, `jurisdiction`, `source_type`, `document_title`, `source_url`, `section_or_paragraph`, `relevant_excerpt`, `observed_condition`, `required_context`, `interpretation`, `limitations`, `verification_status`, `verified_at`, `enabled`, and `version`. The schema validates the shape and readiness requirements; a human must verify the truth, current applicability, and permission to use the source. A model cannot mark a rule verified.

Use the actual source text, version and verification date. Cite a verified Kazakhstan regulatory source for a regulatory claim. Clearly distinguish internal policy, legislation, and material published by another bank. A visible condition must be distinguishable from the interpretation. Explain required context and what cannot be concluded from overhead silent video. A missing paragraph reference must remain null and visible, not guessed.

`examples/synthetic-rules.json` demonstrates only a synthetic colored-shape condition. It is not a cashier regulation and must not be promoted into the production registry. Demo findings are not evidence of detection accuracy.

For local inference, choose and review a vision-capable model's actual license first. Prepare its weights on your own machine using the model vendor's documented process. This project intentionally does not choose or download weights. Set `DETECTOR_BACKEND=ollama` and `LOCAL_VISION_MODEL` to the installed local tag. On a native Windows setup use `OLLAMA_BASE_URL=http://127.0.0.1:11434`. Restart Ollama with cloud features disabled as described in `DEPLOYMENT.md`. Inspect System status before uploading real footage.

Restart both the API and worker after changing `.env`; each loads its settings at startup. With Compose, recreate both services using `docker compose up -d --force-recreate api worker`. Confirm readiness again before uploading.

The adapter rejects cloud/remote model metadata and public endpoints. A non-loopback service must be an explicitly allowed internal host resolving only to private addresses. Such an allowlist is an operator declaration that the service is controlled by the team. Network restrictions still matter. No telemetry or cloud fallback is added by this app.

Review observations against the footage and original source. A negative result only reports the absence of indicators under the configured rules and sampling coverage; it is not proof of compliance. Unknown categories and unseen angles require validation and may be missed.
