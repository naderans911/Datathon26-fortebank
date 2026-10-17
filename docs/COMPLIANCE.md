# Case coverage and remaining validation

The weights below are reproduced from the supplied brief. Implementation coverage is separate from real-world performance.

| Assessment | Weight | Foundation coverage | Remaining validation |
| --- | ---: | --- | --- |
| Detection | 25 | Replaceable local vision adapter; temporal windows; strict observations; no fake successful fallback | Licensed weights, actual detector quality and recall on permitted data are unvalidated |
| Localization/evidence | 15 | Source presentation timestamps; actual JPEGs; browser seek; multiple events including simultaneous events | Real-camera codec and timing coverage on target hardware/data is unvalidated |
| Classification | 15 | Event type derives from configured verified rule, not invented model taxonomy | No real violation taxonomy is supplied; unseen categories unvalidated |
| Rule justification | 15 | Validated registry, source excerpt/version snapshot, observation separated from interpretation | Production registry is empty; no regulatory claim is fabricated |
| Robustness | 10 | Corrupt/oversized input failures, capacity bounds, session isolation, deadlines and recovery | Real viewpoint/occlusion robustness and sustained load unvalidated |
| Product readiness | 10 | Connected UI/API/worker, status, evidence review, offline assets, synthetic demo, container configuration | No public HTTPS deployment or judge credentials delivered; target-host smoke test required |
| Technical solution/locality | 10 | Local FFmpeg/Ollama path, internal service restrictions, disabled cloud mode, local persistence | Real-model offline and GPU tests on target deployment pending |

## Required behavior

- `.mov` uploads, prompt job acceptance, persisted progress and terminal recovery.
- Exact judging routes and `X-API-Key`; processing/done/failed status contract.
- `violation` requires nonempty events and genuine JPEG base64; `no_violation` has an empty array.
- Source-time bounds, multiple findings, selected-event video seeking and readable rule sources.
- Errors, unavailable prerequisites and interrupted work do not become compliance claims.
- Demo is opt-in, synthetic and isolated from judge results and readiness.
- No identity matching, emotion analysis, audio inference, hidden-transaction claims or disciplinary recommendations.
- No cloud video inference, automatic model downloads, online legal lookup or runtime tracking.
- Private storage and media routes, CSRF/session isolation, source snapshots, bounded resources and cleanup.

Implementation-specific limits (sampling, event count, evidence bytes, upload size) are configurable or documented. Resource overflow fails explicitly rather than silently dropping observations into a successful result. Sparse sampling can miss brief events. A human must assess every finding and the original source applicability.

See [VALIDATION.md](VALIDATION.md) for checks actually executed and outstanding environment-dependent checks. The synthetic test suite does not validate real cashier-procedure detection.
