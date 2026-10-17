# Solution overview

The application accepts videos through a React interface or the exact jury API, validates media locally with FFmpeg, processes a persistent SQLite job in a separate worker, and presents timestamped JPEG evidence for human review.

The strict training importer, resolver and local validation command are described in [LABEL_IMPORT.md](LABEL_IMPORT.md). Source metadata supplies binary labels and points, not event categories, boundaries, legal mappings or recording groups. A separate annotation workflow enriches local records; organizer labels must never be consulted by jury inference.

CV inference uses local pretrained RT-DETR and DINOv2 features with a separately fitted scorer. Feature-model downloads do not train a violation classifier. Private scorer weights and per-video annotations are excluded from the current Git tree. Older reported accuracy/timing numbers have not been independently reproduced by this implementation work and are not presented as validated performance.

The supplied rule registry records sources separately from model outputs. An unclassified binary model flag does not justify inventing a specific event category or legal provision. A reviewer must verify visible conduct, context and source applicability.

See [README](../README.md) for commands, [API.md](API.md) for the unchanged jury contract, [ARCHITECTURE.md](ARCHITECTURE.md) for components, and [VALIDATION.md](VALIDATION.md) for checks actually executed. No competition-readiness, real-camera accuracy or five-minute completion guarantee is implied by synthetic tests.
