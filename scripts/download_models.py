"""One-time download of the Apache-2.0 model weights into ./models (needs internet once).

After this the service runs fully offline (HF_HUB_OFFLINE=1 is enforced at runtime).
    python scripts/download_models.py
"""
from pathlib import Path

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "PekingU/rtdetr_r18vd": "rtdetr_r18vd",   # COCO object detector, Apache-2.0
    "facebook/dinov2-small": "dinov2-small",  # scene embedding, Apache-2.0
}

for repo, folder in MODELS.items():
    target = ROOT / "models" / folder
    print(f"-> {repo} -> {target}")
    snapshot_download(repo, local_dir=target, allow_patterns=["*.json", "*.safetensors", "*.txt", "*.md"])
print("Done. Weights are in ./models")
