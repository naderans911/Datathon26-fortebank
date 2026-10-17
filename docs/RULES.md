# Rule registry and local model setup

`config/rules.json` currently contains **six supplied entries**, all enabled and marked `verification_status: "verified"`. Those fields and recorded dates were preserved from the supplied registry. The legal text, current law and applicability were **not independently reverified in this implementation session**. A registry flag is configuration metadata, not proof that a source applies to a particular video or procedure.

Each rule contains an ID, event type, jurisdiction, source type, document title and URL, optional pinpoint section, relevant excerpt, visible condition, required context, interpretation, limitations, verification status/date, enabled flag and version. Schema validation checks structure; a human must verify source accuracy, current applicability and any permission needed to use it. Keep regulation, internal procedure and another bank's published material distinct. Preserve missing references as null rather than guessing them.

Operational readiness currently requires at least one enabled entry marked verified, an available detector, FFmpeg/ffprobe and a live worker. This gate also applies to the CV backend. It does **not** mean that the CV model has evaluated or matched those rules.

## Binary CV findings and rule-backed observations

The local CV backend combines RT-DETR and DINOv2 features with a fitted binary scorer. Feature weights alone are not a cashier-violation detector. Scores meeting or exceeding the configured threshold produce generic **`Possible violation (unclassified)`** candidates at sampled source timestamps. The internal observation has `rule_id: null`; the rich review result has `rule: null`. The judging response retains its existing schema and does not add a rule-ID field.

The binary scorer does not infer an action category, an event's start/end boundaries or an applicable legal provision. Its scores are uncalibrated. Neighboring evidence frames and groups of candidate samples provide review context; they are not annotated event intervals. Legacy type heads are not used. A CV candidate can produce the contract's `violation` verdict while remaining a human-review candidate, not a legal determination.

The separate rule-based adapter accepts only supplied active rule IDs and real sampled frame IDs. A mapped event uses the accepted rule snapshot, including its configured event type and interpretation. An ordinary observation with no verified rule mapping remains an unmapped observation, not a violation event. Only the explicitly supported binary-candidate path can create a generic event without a rule assertion.

## Model preparation and validation limits

Set `DETECTOR_BACKEND=cv` for local CV inference. `CV_MODEL_DIR` points to the vision artifacts; `CV_SCORER_DIR`, when set, points to the separate trusted scorer directory. `scripts/download_models.py` is an explicit, one-time download command for pinned official feature-model revisions and writes artifact hashes. Runtime inference uses local artifacts and does not download models or consult organizer labels. Review the recorded model licenses and distribution requirements before use.

A compatible private fitted scorer is required. Only load a trusted scorer: joblib artifacts can execute code. The existing development-machine scorer is retained locally but is not distributed in the current Git tree. Compatibility with its legacy feature schema is supported; missing provenance remains recorded as `legacy_unvalidated`. Its execution has been demonstrated on synthetic media. Its training supervision, banking detection quality, calibration and generalization have **not** been validated by that smoke test. Fresh installations must supply a compatible trusted artifact or train one locally; missing or incompatible models cannot return a successful negative verdict.

`DETECTOR_BACKEND=ollama` remains an alternative local adapter. Configure a reviewed vision model with `LOCAL_VISION_MODEL` and the local service URL; the default native endpoint is `http://127.0.0.1:11434`. Cloud/remote model metadata and public endpoints are rejected. An explicitly allowed internal host must resolve only to private addresses. See [deployment guidance](DEPLOYMENT.md) for local-service restrictions. Restart both API and worker after configuration changes and recheck System status.

## Labels and human annotation

Organizer binary labels and point timestamps do not establish categories, boundaries or rule applicability. Import, resolution and validation run locally outside the judging pipeline. The separate opt-in loopback reviewer on port 8001 preserves those source fields and saves human annotations in separate revisioned documents. Candidate rule IDs remain drafts for later verification, even when an observation is marked reviewed. Neither source labels nor reviewer annotations are looked up during production inference.

`examples/synthetic-rules.json` and the opt-in demo are synthetic interface fixtures, isolated from production rules and judge results. They do not validate detection accuracy. A successful negative result means no indicators under the configured detector, threshold and sampling coverage; it is not proof of compliance. Missing prerequisites, corrupt inputs, model errors and incomplete processing remain unavailable or failed states.
