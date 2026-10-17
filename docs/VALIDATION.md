# Validation record

Validated on 18 October 2026 local time, on Windows with Python 3.13.0, Node.js 24.19.0, npm 11.17.0 and FFmpeg/ffprobe 9.0.2. The machine has two CPU cores and approximately 8 GB RAM. All test inputs were generated synthetic fixtures. No organizer workbook, competition footage, real extracted frames or video-derived descriptions were opened by the coding agent.

## Automated checks

| Check | Result |
| --- | --- |
| Backend synthetic suite | 162 passing tests, 1 optional local vision-model test skipped |
| Ruff over `backend` and `scripts` | Passed |
| Python dependency consistency (`pip check`) | Passed |
| Frontend component tests | 16 passed |
| TypeScript, ESLint, formatting and production build | Passed |
| Upload/results browser regression | 4 passed at desktop/mobile widths |
| Isolated local annotation browser checks | 2 passed at desktop/mobile widths |
| GitHub Actions, milestones 1–3 | Successful for `3790b54`, `8a938a5`, `54430b4` |

The backend total combines a full run of 152 passes/one skip and ten subsequently added readiness/controller cases, all passing. The skipped test needs an optional Ollama vision model; CV execution was verified separately below. One upstream Starlette TestClient deprecation warning does not affect the results.

Coverage includes Russian whole-string timestamp parsing (`1минута 8 секунда` → 68), blank negatives, explicit zero, exact binary labels, raw Unicode preservation, exact-match priority, unique/ambiguous aliases, duplicate mapping rejection, numbering gaps, normalized source comparison, duration/timestamp checks, multiple revisioned local annotations and public isolation. Training checks cover unknown positive-clip samples, whole-video and explicit recording-group separation, fixed held-out thresholds, overlap rejection, versioned artifacts and inference isolation from label readers.

API tests exercise both binary outcomes with injected synthetic detectors, actual MOV/JPEG extraction, generic null-rule candidates, multiple events, malformed input, ownership/CSRF, wrong keys, missing readiness, queue/storage limits, deadlines and child termination. Controller tests ensure active uploads/analyses cannot be interrupted by restart or tunnel-origin changes, and that shutdown uses the persisted database and holds an admission lock.

## Actual CV execution on synthetic inputs

The installed CPU runtime uses torch 2.9.1+cpu, torchvision 0.24.1+cpu, transformers 4.57.3 and scikit-learn 1.9.1. The last version matches the trusted legacy scorer's serialization; an incompatible version failed explicitly during setup and was corrected. Official RT-DETR/DINOv2 weights were downloaded at pinned revisions and SHA-256 checked. Neither feature weights nor the private scorer are included in the current Git tree.

| End-to-end check | Observed result |
| --- | --- |
| Cold offline feature/scorer execution on three generated JPEGs | Completed in 18.255 seconds, zero candidates |
| Local jury HTTP upload, generated eight-second MOV | HTTP 202, processing, done; `no_violation`, zero candidates; 56.554 seconds |
| Public HTTPS jury HTTP upload, same generated MOV | HTTP 202, processing, done; exact successful JSON schema; 47.533 seconds |
| Public browser upload, generated eight-second MOV | Actual CV result completed in 42.935 seconds; `no_violation`, zero candidates |
| Missing or incorrect jury key | HTTP 401 |
| Public annotation API path | HTTP 404 |
| Local service controller | Starts API/worker, confirms fresh heartbeat, stops and restarts its owned processes |

These measurements include upload/poll overhead for the HTTP tests. They prove that the real model path executes and returns a binary result on those generated inputs. They do not establish banking accuracy, positive-event recall, legal applicability, calibration, or the runtime of longer footage. Positive evidence and failed-job behavior are covered by synthetic injected-detector tests; an actual positive banking example was not evaluated.

The public browser check verified the visible model-quality notice, upload acceptance, refresh recovery, terminal result, decoded video playback, secure HttpOnly session cookies, inaccessible annotation API and deletion of the owned synthetic job. Desktop and mobile screenshots were inspected with no horizontal overflow. Screenshots and the local verification report remain in ignored `.local/qa/`.

At two sampled frames per second, long videos may exceed the 285-second queue-and-processing deadline on this CPU. Such work returns a failed state, never a clean verdict. Benchmark the intended footage locally before relying on timing; no longest-clip extrapolation or five-minute performance guarantee is made.

## Remaining local validation

Run the README import/validation commands against the supplied workbook and real videos locally. The supplied 42-row audit is metadata only; actual file presence, alias resolution, media duration and timestamp bounds have not been certified. Review event types, observations, boundaries and candidate rule mappings in the separate local screen. Keep all rule applicability decisions as drafts until checked against the original legal source.

Prepare group-independent splits, train a new versioned scorer on permitted training data and run fixed-threshold held-out evaluation. The legacy scorer's quality and training supervision remain unvalidated. Review intervals/types are stored but are not consumed by the current point-supervised trainer. Judging footage must not enter training or tuning.

GPU execution, Docker deployment, independent firewall-isolated operation, unseen camera views and sustained public hosting have not been validated. A quick-tunnel link is temporary and requires the computer to stay awake and online. The dependency inventory records 56 Python and 315 frontend package entries; see [licenses](LICENSES.md) for artifact versions and notices.
