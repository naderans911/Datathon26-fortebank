"""Deploy the full service to a Hugging Face Docker Space (CPU, always-on URL).

    hf auth login                      # once, with a Write token
    python scripts/deploy_hf.py [OWNER/SPACE_NAME]

The jury key is read from .env and stored as a Space secret (never uploaded as a file).
Inference stays inside the container: weights are shipped with the image, HF_HUB_OFFLINE=1.
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {
    "APP_ENV": "production", "DETECTOR_BACKEND": "cv", "CV_DEVICE": "cpu",
    "SAMPLING_FPS": "2", "MAX_SAMPLE_FRAMES": "400", "SAMPLE_WIDTH": "640", "WINDOW_SECONDS": "16",
    "MAX_UPLOAD_MB": "100", "MAX_VIDEO_SECONDS": "300", "JOB_DEADLINE_SECONDS": "285",
    "WORKER_CONCURRENCY": "1", "MAX_QUEUE_SIZE": "30", "MAX_STORAGE_MB": "8192",
    "RETENTION_HOURS": "48", "SECURE_COOKIES": "true", "ENABLE_DEMO": "false",
    "STORAGE_DIR": "/app/storage", "RULES_FILE": "/app/config/rules.json",
}


def read_env_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("JURY_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("JURY_API_KEY is missing in .env")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("space", nargs="?", help="OWNER/NAME (default: <your user>/fortebank-cash-review)")
    args = ap.parse_args()
    api = HfApi()
    space = args.space or f"{api.whoami()['name']}/fortebank-cash-review"
    origin = "https://" + space.replace("/", "-").replace("_", "-").replace(".", "-").lower() + ".hf.space"
    key = read_env_key()
    if len(key) < 32:
        sys.exit("JURY_API_KEY must be at least 32 characters for APP_ENV=production")
    for required in ("models/scorer.joblib", "models/rtdetr_r18vd/config.json",
                     "models/dinov2-small/config.json", "frontend/dist/index.html"):
        if not (ROOT / required).is_file():
            sys.exit(f"Missing {required}: run download_models.py / train.py / the frontend build first")

    stage = Path(tempfile.mkdtemp(prefix="hf-space-"))
    try:
        for name in ("Dockerfile", "start.sh", "README.md"):
            shutil.copy(ROOT / "deploy" / "hf" / name, stage / name)
        shutil.copy(ROOT / "requirements.lock", stage / "requirements.lock")
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "tests")
        for folder in ("backend", "config", "frontend/dist", "models"):
            shutil.copytree(ROOT / folder, stage / folder, ignore=ignore)

        api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True, private=False)
        api.add_space_secret(space, "JURY_API_KEY", key)
        for name, value in {**SETTINGS, "PUBLIC_ORIGIN": origin}.items():
            api.add_space_variable(space, name, value)
        api.upload_folder(repo_id=space, repo_type="space", folder_path=stage,
                          commit_message="Deploy ForteBank cash review service")
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    print(f"Space:  https://huggingface.co/spaces/{space}")
    print(f"URL:    {origin}   (build takes ~5-10 min; check the Space 'Logs' tab)")


if __name__ == "__main__":
    main()
