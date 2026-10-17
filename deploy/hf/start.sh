#!/bin/bash
# Container entry point: worker in the background, API in the foreground on the Space port.
cd /app
python -m backend.app.workers.runner &
exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 7860 \
  --proxy-headers --forwarded-allow-ips='*'
