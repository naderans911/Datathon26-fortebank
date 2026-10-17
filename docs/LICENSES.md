# Dependency and model licensing

No model weights, official Forte logo or proprietary font files are distributed. Model choice is intentionally unset. Before configuring a model, record the exact artifact/version, upstream license, commercial-use terms, redistribution obligations and any use restrictions. Ollama's software license does not license the weights it runs.

Primary component licenses permit commercial use subject to their terms and required notices. Preserve license files when distributing dependencies or compiled bundles. Package versions are fixed in `requirements.lock` and `frontend/package-lock.json`. The installed dependency inventory is recorded in `DEPENDENCY_LICENSES.json` after setup.

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
