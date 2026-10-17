# Case coverage and remaining validation

The assessment weights below are reproduced from the supplied brief. Implemented behavior and synthetic execution checks are separate from real-world detection quality or legal verification.

| Assessment | Weight | Implemented coverage | Remaining validation |
| --- | ---: | --- | --- |
| Detection | 25 | Local RT-DETR/DINOv2 features and a fitted binary scorer; sampled candidate moments; explicit missing-model and processing failures | Legacy scorer execution is proven on synthetic media; training supervision, precision, recall, calibration and banking quality remain unvalidated |
| Localization/evidence | 15 | Source presentation timestamps, actual JPEG frames, preview seeking and multiple findings | Real-camera coverage and localization accuracy are unvalidated; candidate grouping and supplied point labels are not event boundaries |
| Classification | 15 | CV candidates use the fixed generic type `Possible violation (unclassified)`; no legacy type head or invented action taxonomy | Binary organizer labels do not train or establish violation categories; category accuracy is unvalidated |
| Rule justification | 15 | Six supplied enabled registry entries marked verified; source snapshots; observation separated from interpretation; CV candidates have no asserted rule | Registry legal text/current applicability were not independently reverified in this session; a binary score cannot select a legal provision |
| Robustness | 10 | Invalid/oversized input handling, bounded resources, deadlines, persistent jobs, ownership and explicit failures | Viewpoint changes, occlusion, brief events and sustained target-host load remain unvalidated |
| Product readiness | 10 | Connected upload/results/status UI, worker/API, evidence review, local annotation editor, offline assets and isolated synthetic demos | Consult the current validation record for deployment checks; an HTTP health check or Git push does not establish detector quality or public availability |
| Technical solution/locality | 10 | Local FFmpeg and CV inference; optional restricted local Ollama adapter; labels and annotation storage excluded from production inference | Synthetic model execution does not validate GPU throughput, real-data accuracy or every deployment environment |

## Result semantics

- `.mov` and the other documented upload formats use the shared durable job queue, persisted progress and terminal recovery.
- The judging routes retain `X-API-Key` authentication and their exact processing/done/failed response contract.
- A completed `violation` result requires nonempty findings with one to three genuine JPEG evidence frames each. A completed `no_violation` result has an empty findings array.
- CV findings are generic review candidates: the internal `rule_id` is null, the rich UI event's `rule` is null, and no category or legal applicability is inferred. The judge schema remains unchanged.
- The rule-based adapter may produce a mapped event only with an active accepted rule ID and sampled evidence. Ordinary unmapped observations do not become rule-backed violations.
- A negative result means no indicators under the detector, threshold and available sampling coverage. It is not proof of complete compliance. Missing detection logic, unavailable prerequisites, decode/model errors, deadline expiry and other failed processing must never become successful negatives.

## Data separation and human review

Organizer labels are binary labels with optional point timestamps. They do not supply event categories, start/end boundaries, legal mappings or reliable recording-group metadata. The local importer preserves raw fields, validates identifiers and timestamps, resolves exact matches before the narrow documented alias, and rejects ambiguous or duplicate mappings.

The reviewer is a separate, explicitly enabled loopback service on port 8001. It rejects public hosts, remote clients, forwarded requests and cross-origin writes; it must never be tunneled or mounted in the judging API. Matched videos are played locally. Supplied labels and points remain read-only; multiple human annotations, optional inspected boundaries and candidate rule references are saved separately with revision conflict checks. Marking an annotation reviewed does not verify its candidate legal mapping.

Production inference examines uploaded media using the configured local detector. It does not search filenames, organizer workbooks, normalized label exports or saved reviewer annotations for answers. No real workbook, footage or video-derived descriptions were read by cloud tools for the implementation checks. Local source data, annotation files, feature caches, evaluation reports and private model artifacts stay outside the current Git tree.

Demo fixtures are opt-in, synthetic and isolated from judging results and production readiness. The application adds no identity matching, emotion analysis, audio inference, hidden-transaction claims or disciplinary recommendations. It has no cloud video-inference fallback, automatic runtime model download or online legal lookup. One-time official feature-model downloads require an explicit setup command.

Resource and evidence limits fail explicitly rather than silently turning overflow into a successful result. Sparse sampling can miss short actions; uncalibrated model scores and an operationally ready service do not establish accuracy. A human must review candidate moments, the surrounding video and any proposed source applicability.

See [RULES.md](RULES.md) for model/rule semantics and [VALIDATION.md](VALIDATION.md) for checks actually executed. Synthetic execution proves that the tested software path runs; it does not validate cashier-procedure detection.
