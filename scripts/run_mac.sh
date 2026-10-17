#!/bin/bash
# Start API + worker + public tunnel; keeps the Mac awake. Stop with Ctrl+C.
cd "$(dirname "$0")/.."
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTORCH_ENABLE_MPS_FALLBACK=1
mkdir -p logs
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips='*' > logs/api.log 2>&1 &
API=$!
.venv/bin/python -m backend.app.workers.runner > logs/worker.log 2>&1 &
WORKER=$!
caffeinate -dimsu -w $API &
trap 'kill $API $WORKER 2>/dev/null; exit' INT TERM
sleep 4
echo "Local:  http://127.0.0.1:8000"
echo "Starting public tunnel... the https://....trycloudflare.com link below is the URL for the jury."
cloudflared tunnel --url http://127.0.0.1:8000 2>&1 | grep --line-buffered -Eo "https://[a-z0-9-]+\.trycloudflare\.com" &
wait $API
