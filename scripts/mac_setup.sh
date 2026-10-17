#!/bin/bash
# One-time setup on macOS (Apple Silicon). Run from the repo root:  bash scripts/mac_setup.sh
set -e
cd "$(dirname "$0")/.."
if ! command -v brew >/dev/null; then
  echo ">> Homebrew not found. Installing (it will ask for your Mac password)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
echo ">> Installing python, ffmpeg, node, cloudflared"
brew install python@3.13 ffmpeg node cloudflared
PY=$(brew --prefix python@3.13)/bin/python3.13
[ -d .venv ] || $PY -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.in -r requirements-ml.txt
echo ">> Building frontend"
npm --prefix frontend ci
npm --prefix frontend run build
echo ">> Creating .env"
.venv/bin/python scripts/setup_env.py || true
set_env() { if grep -q "^$1=" .env; then sed -i '' "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }
set_env DETECTOR_BACKEND cv
set_env SAMPLING_FPS 2
set_env MAX_SAMPLE_FRAMES 400
set_env WINDOW_SECONDS 16
set_env RETENTION_HOURS 72
set_env CV_DEVICE auto
echo ">> Downloading model weights (one time, ~300 MB)"
.venv/bin/python scripts/download_models.py
echo ""
echo "DONE. Judge API key:"; grep ^JURY_API_KEY .env
