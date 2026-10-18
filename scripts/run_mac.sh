#!/bin/bash
# Start API + worker + public tunnel; keeps the Mac awake. Stop with Ctrl+C.
# Safe to re-run: stale instances from a previous start are stopped first.
cd "$(dirname "$0")/.."
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTORCH_ENABLE_MPS_FALLBACK=1
mkdir -p logs
pkill -f "uvicorn backend.app.main:app" 2>/dev/null
pkill -f "backend.app.workers.runner" 2>/dev/null
pkill -f "cloudflared tunnel --url http://127.0.0.1:8000" 2>/dev/null
pkill -f "ngrok http" 2>/dev/null
# Optional stable address: NGROK_DOMAIN=xxx.ngrok-free.dev in .env (after `ngrok config add-authtoken`).
NGROK_DOMAIN=$(grep -E "^NGROK_DOMAIN=" .env 2>/dev/null | cut -d= -f2- | tr -d '[:space:]')
sleep 1
rm -f logs/public_url.txt

.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips='*' > logs/api.log 2>&1 &
API=$!
.venv/bin/python -m backend.app.workers.runner > logs/worker.log 2>&1 &
WORKER=$!
caffeinate -dimsu -w $API &

if [ -n "$NGROK_DOMAIN" ]; then
  # Stable URL: ngrok keeps the same domain across reconnects and restarts.
  echo "https://$NGROK_DOMAIN" > logs/public_url.txt
  echo "Public URL (give this to the jury): https://$NGROK_DOMAIN"
  (
    while kill -0 $API 2>/dev/null; do
      ngrok http 8000 --url="https://$NGROK_DOMAIN" --log stdout --log-format logfmt >> logs/ngrok.log 2>&1
      echo "ngrok stopped; restarting in 3 s (same URL)..."
      sleep 3
    done
  ) &
  TUNNEL=$!
else
# Restart the quick tunnel if it drops; every restart gets a NEW public URL.
(
  while kill -0 $API 2>/dev/null; do
    cloudflared tunnel --url http://127.0.0.1:8000 2>&1 \
      | grep --line-buffered -Eo "https://[a-z0-9-]+\.trycloudflare\.com" \
      | while read -r url; do
          echo "$url" > logs/public_url.txt
          echo "Public URL (give this to the jury): $url"
        done
    echo "Tunnel stopped; restarting in 5 s (the public URL will change)..."
    sleep 5
  done
) &
TUNNEL=$!
fi

trap 'pkill -P $TUNNEL 2>/dev/null; kill $TUNNEL $API $WORKER 2>/dev/null; pkill -f "cloudflared tunnel --url http://127.0.0.1:8000"; pkill -f "ngrok http"; exit' INT TERM
sleep 4
echo "Local:  http://127.0.0.1:8000"
echo "Starting public tunnel... the URL is also saved to logs/public_url.txt"
wait $API
