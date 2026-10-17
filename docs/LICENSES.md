# Dependency and model licensing

No model weights, official Forte logo or proprietary font files are distributed in the current Git tree. Native CV uses RT-DETR R18 and DINOv2 Small feature weights downloaded separately from their official model repositories. The private fitted binary scorer has separate provenance and is not published. Preserve exact artifact versions and upstream notices when distributing a deployment. Ollama's software license does not license the weights it runs.

| Local feature artifact | Pinned revision | Declared license |
| --- | --- | --- |
| [PekingU/rtdetr_r18vd](https://huggingface.co/PekingU/rtdetr_r18vd) | `ac77a11ff0170a41b771c03264987f8ce2b0d753` | Apache-2.0 |
| [facebook/dinov2-small](https://huggingface.co/facebook/dinov2-small) | `ed25f3a31f01632728cabb09d1542f84ab7b0056` | Apache-2.0 |

The downloader records file SHA-256 values, repository, revision and license in ignored local manifests. These feature models are not ready-made cashier-violation detectors. A legacy local scorer's existence and successful loading do not establish its training-data permissions or accuracy.

Primary component licenses permit commercial use subject to their terms and required notices. Preserve license files when distributing dependencies or compiled bundles. Direct package versions are fixed in `requirements.lock`, `requirements-ml.txt`, `requirements-training.txt` and `frontend/package-lock.json`; official CPU torch/torchvision versions are specified in Windows setup. The installed inventory in `DEPENDENCY_LICENSES.json` currently records 56 Python and 315 frontend entries. It includes transitive versions and notice locations, and is not a model-license approval.

| Component | License / source |
| --- | --- |
| FastAPI | [MIT](https://github.com/fastapi/fastapi/blob/master/LICENSE) |
| Uvicorn / Starlette | BSD-3-Clause; package notices |
| Pydantic / pydantic-settings | MIT; package notices |
| HTTPX | [BSD-3-Clause](https://github.com/encode/httpx/blob/master/LICENSE.md) |
| python-multipart | Apache-2.0; package notices |
| psutil | BSD-3-Clause; package notices |
| Pillow | MIT-CMU plus bundled library notices; package notices |
| React / React DOM / React Router | MIT; package notices |
| Vite / Vitest | MIT; package notices |
| TypeScript / Playwright | Apache-2.0; package notices |
| Python | PSF-2.0 and bundled component notices |
| SQLite | Public domain; included through Python |
| Ollama | [MIT](https://github.com/ollama/ollama/blob/main/LICENSE); model licenses separate |
| FFmpeg | Depends on build options: LGPL-2.1-or-later normally, GPL when GPL components are enabled; [upstream licensing](https://ffmpeg.org/legal.html) |

The preview encoder uses `libx264`, requiring an FFmpeg build that includes it. The downloaded Windows test build is kept only in ignored `.tools/`; its GPL notices and build metadata must be retained with that binary. Compose installs the distribution's FFmpeg package. Commercial use is allowed under the applicable open-source terms, but distributing binaries/container images requires satisfying the exact build's license and source obligations. Codecs may have additional patent considerations in the deployment jurisdiction; a software license list does not settle those.

No ready-made cashier-violation product is embedded. No accuracy, model license approval or regulation verification is implied by the synthetic examples. The official Forte reference is used for the requested palette only; this application is explicitly identified as a hackathon prototype.
