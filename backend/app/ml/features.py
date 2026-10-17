"""Local per-frame visual features: COCO objects (RT-DETR) + scene embedding (DINOv2).

Both models are Apache-2.0 and are loaded only from the local ``models/`` folder
(``scripts/download_models.py`` fetches them once). Nothing is sent over the network
at inference time: ``local_files_only=True`` and HF offline mode are enforced.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

DETECTOR_DIR = "rtdetr_r18vd"
EMBEDDER_DIR = "dinov2-small"

# COCO classes that matter at a cash desk (names as in the RT-DETR id2label map).
TRACKED = ["person", "cell phone", "handbag", "backpack", "suitcase", "book", "laptop", "cup", "bottle",
           "scissors", "keyboard", "mouse", "remote"]
OBJECT_SCORE = 0.45

_lock = threading.Lock()
_cache: dict = {}


def model_paths(model_dir: Path) -> dict:
    return {"detector": Path(model_dir) / DETECTOR_DIR, "embedder": Path(model_dir) / EMBEDDER_DIR}


def models_present(model_dir: Path) -> bool:
    return all((path / "config.json").is_file() for path in model_paths(model_dir).values())


def pick_device(preference: str = "auto") -> str:
    import torch
    if preference != "auto":
        return preference
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_models(model_dir: Path, device: str = "auto") -> dict:
    key = (str(model_dir), device)
    with _lock:
        if key in _cache:
            return _cache[key]
        import torch
        from transformers import AutoImageProcessor, AutoModel, RTDetrForObjectDetection

        paths = model_paths(model_dir)
        dev = pick_device(device)
        det_proc = AutoImageProcessor.from_pretrained(paths["detector"], local_files_only=True)
        det = RTDetrForObjectDetection.from_pretrained(paths["detector"], local_files_only=True).to(dev).eval()
        emb_proc = AutoImageProcessor.from_pretrained(paths["embedder"], local_files_only=True)
        emb = AutoModel.from_pretrained(paths["embedder"], local_files_only=True).to(dev).eval()
        torch.set_grad_enabled(False)
        _cache[key] = {"device": dev, "det_proc": det_proc, "det": det, "emb_proc": emb_proc, "emb": emb}
        return _cache[key]


def extract(frame_paths: list[str], model_dir: Path, device: str = "auto", deadline: float | None = None,
            batch_size: int = 8, det_stride: int | None = None) -> list[dict]:
    """Return one dict per frame: {"embedding": list[float], "objects": [{label, score, box}]}.

    Boxes are normalized [x0, y0, x1, y1] in 0..1 image coordinates.
    """
    import torch
    from PIL import Image

    models = load_models(model_dir, device)
    dev = models["device"]
    id2label = models["det"].config.id2label
    # Object detection is the expensive part; run it on every `det_stride`-th frame and
    # carry objects forward in between (embeddings are still computed for every frame).
    stride = max(1, int(det_stride or os.environ.get("CV_DET_STRIDE", 2)))
    results: list[dict] = []
    last_objects: list = []
    for start in range(0, len(frame_paths), batch_size):
        if deadline is not None and time.time() >= deadline - 20:
            raise TimeoutError("feature extraction deadline")
        images = [Image.open(path).convert("RGB") for path in frame_paths[start:start + batch_size]]
        sizes = [(img.height, img.width) for img in images]
        det_local = [i for i in range(len(images)) if (start + i) % stride == 0]
        post_map = {}
        with torch.inference_mode():
            if det_local:
                det_in = models["det_proc"](images=[images[i] for i in det_local], return_tensors="pt").to(dev)
                det_out = models["det"](**det_in)
                post = models["det_proc"].post_process_object_detection(
                    det_out, threshold=OBJECT_SCORE, target_sizes=torch.tensor([sizes[i] for i in det_local]))
                post_map = dict(zip(det_local, post))
            emb_in = models["emb_proc"](images=images, return_tensors="pt").to(dev)
            emb_out = models["emb"](**emb_in)
            cls = emb_out.last_hidden_state[:, 0]
            patch_mean = emb_out.last_hidden_state[:, 1:].mean(dim=1)
            vectors = torch.nn.functional.normalize(torch.cat([cls, patch_mean], dim=1), dim=1).float().cpu()
        for index, (height, width) in enumerate(sizes):
            if index not in post_map:
                results.append({"embedding": vectors[index].tolist(), "objects": last_objects})
                continue
            objects = []
            item = post_map[index]
            for score, label, box in zip(item["scores"].tolist(), item["labels"].tolist(), item["boxes"].tolist()):
                name = id2label.get(label, str(label))
                if name not in TRACKED:
                    continue
                x0, y0, x1, y1 = box
                objects.append({"label": name, "score": round(score, 3),
                                "box": [max(0.0, x0 / width), max(0.0, y0 / height),
                                        min(1.0, x1 / width), min(1.0, y1 / height)]})
            last_objects = objects
            results.append({"embedding": vectors[index].tolist(), "objects": objects})
    return results
