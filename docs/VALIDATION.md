# Validation record

## Actual-label and local-review update

- Actual-format importer/resolver/validation: **53 synthetic tests passed**, including generated XLSX and MOV fixtures. Russian timestamps, null negatives, unknown labels, preserved Unicode, exact-before-alias matching, ambiguity/duplicate rejection, numbering gaps, source comparison and timestamp bounds are covered.
- Separate local annotation server: **16 tests passed**, including loopback/Host/Origin/forwarded-request restrictions, session/CSRF, persistent multi-event saves, stale-revision rejection, media range access and path boundaries.
- Frontend: **15 component tests passed**, TypeScript/ESLint/format and production build passed. Isolated local-review browser tests **2 passed** at desktop/mobile widths; existing upload/results browser regression **4 passed**.
- Synthetic review screenshots were inspected at both widths. No organizer workbook, real footage or video-derived descriptions were read for these tests. Real-data matching, duration and annotation review remain local operator work.

The original foundation record follows. New inference/runtime validation is recorded separately when completed.

Validated on Windows with Python 3.13.0, Node.js 24.19.0, npm 11.17.0 and a checksum-verified FFmpeg/ffprobe 9.0.2 build. All video inputs were locally generated synthetic fixtures. No competition footage or observations were inspected or transmitted.

| Check | Result |
| --- | --- |
| `python -m pytest -q` | 52 passed, 1 skipped in 19.10 seconds |
| `python -m ruff check backend scripts` | Passed |
| `python -m pip check` | Passed; no broken dependency requirements |
| Live API + worker smoke over HTTP | Passed: heartbeat, honest unconfigured readiness, offline docs, positive/negative/failed synthetic demos, protected JPEG/MP4, judge/demo isolation, terminal deletion |
| Frontend TypeScript checks, ESLint and production build | Passed |
| Frontend component tests | 10 passed across four files |
| Required npm dependency/peer consistency | `npm ls --all --omit=optional` passed |
| Desktop/mobile browser checks | 6 passed: four isolated UI checks and two connected API checks |

Backend tests exercise the exact judge contract through both endpoints with injected test-only detectors and real MOV/JPEG extraction; positive and negative verdicts; multiple simultaneous events; malformed files/model output; ownership/CSRF; missing prerequisites; queue/storage limits; expired queued jobs; child-process termination at the deadline; rule snapshots; cleanup; offline documentation; VFR, source start PTS and rotation; demo isolation; local endpoint restrictions; unknown frame/rule references; and explicit overflow failures.

Browser checks use installed Chrome at 1440×1000 and 390×844. They cover keyboard access and dialog focus, disabled real upload when prerequisites are missing, no horizontal overflow, refresh recovery, independently selectable simultaneous events, matching selected-event observations, actual JPEG loading, decoded video playback and preview seeking, and connected positive/negative/failed synthetic states. Connected tests delete the generated jobs and run serially to respect the demo generation guard. Screenshots were inspected at both widths and remain in ignored local output folders. Repeated local browser runs used a process-only demo rate limit of 60/hour; the shipped default remains 12/hour.

The one skipped test requires an installed local vision model (`LOCAL_VISION_MODEL` is unset). It does not count as inference validation. One upstream Starlette TestClient deprecation warning was emitted about a future HTTP client migration; it did not affect the passing tests.

The dependency inventory records 29 Python packages and 315 frontend lockfile entries, with declared licenses for every entry. Runtime frontend license texts are retained in `frontend/THIRD_PARTY_LICENSES.json`. This inventory does not approve an unspecified model or replace the notices required when distributing dependencies.

The Windows FFmpeg archive matched the [build provider's published SHA-256](https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip.sha256): `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`. Binaries and generated media remain ignored locally.

Real model inference, banking detection accuracy, unseen camera-angle performance, GPU throughput, deployment-container execution, public HTTPS access, and target-host offline behavior have not been validated. A source push does not deploy the application.
