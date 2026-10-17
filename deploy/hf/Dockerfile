# Hugging Face Docker Space: API + worker in one container, CPU inference, no external AI APIs.
# Built from a staging folder assembled by scripts/deploy_hf.py (repo code + frontend/dist + models/).
FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 user
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && pip install --no-cache-dir torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir transformers==5.20.1 scikit-learn==1.9.1 numpy==2.5.4 joblib==1.6.0 openpyxl==3.1.5
COPY --chown=user backend/ ./backend/
COPY --chown=user config/ ./config/
COPY --chown=user frontend/dist/ ./frontend/dist/
COPY --chown=user models/ ./models/
COPY --chown=user start.sh ./start.sh
RUN mkdir -p /app/storage && chown -R user:user /app
USER user
EXPOSE 7860
CMD ["bash", "start.sh"]
