---
title: ForteBank Cash Review
emoji: 🏦
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

AI-сервис проверки кассовой дисциплины по видео (Datathon 26 · ForteBank).
Все модели (RT-DETR r18, DINOv2-small, обученный скорер) работают внутри контейнера на CPU;
внешние AI/API при обработке видео не используются.

API: `POST /api/v1/analyze` (multipart `file`, заголовок `X-API-Key`) → `{job_id}`;
`GET /api/v1/jobs/{job_id}` → `{status, verdict, violations[...]}`.
