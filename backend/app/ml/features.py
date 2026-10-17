"""Offline RT-DETR objects and DINOv2 embeddings for local sampled frames.

No model is imported or loaded by readiness. Runtime uses local safetensors,
never custom repository code, and never copies a detection onto another frame.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import struct
import threading
import time
from pathlib import Path

DETECTOR_DIR = "rtdetr_r18vd"
EMBEDDER_DIR = "dinov2-small"
FEATURE_VERSION = 2
TRACKED = ["person", "cell phone", "handbag", "backpack", "suitcase", "book", "laptop", "cup", "bottle",
           "scissors", "keyboard", "mouse", "remote"]
OBJECT_SCORE = 0.45
_lock = threading.Lock()
_cache: dict = {}


def model_paths(model_dir: Path) -> dict[str, Path]:
    return {"detector": Path(model_dir) / DETECTOR_DIR, "embedder": Path(model_dir) / EMBEDDER_DIR}


def _valid_safetensors(path: Path) -> bool:
    """Validate bounded tensor header/data offsets without importing Torch."""
    try:
        size = path.stat().st_size
        with path.open("rb") as source:
            raw = source.read(8)
            if len(raw) != 8:
                return False
            header_size = struct.unpack("<Q", raw)[0]
            if not 2 <= header_size <= min(16 * 1024 * 1024, size - 8):
                return False
            header = json.loads(source.read(header_size))
        tensors = [value for key, value in header.items() if key != "__metadata__"]
        return bool(tensors) and all(isinstance(item, dict) and isinstance(item.get("data_offsets"), list)
            and len(item["data_offsets"]) == 2 and 0 <= item["data_offsets"][0] < item["data_offsets"][1]
            <= size - 8 - header_size for item in tensors)
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def artifacts_status(model_dir: Path) -> dict:
    missing = []
    for name, directory in model_paths(model_dir).items():
        try:
            config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
            processor = json.loads((directory / "preprocessor_config.json").read_text(encoding="utf-8"))
            expected = "rt_detr" if name == "detector" else "dinov2"
            valid = config.get("model_type") == expected and isinstance(processor, dict)
            valid = valid and _valid_safetensors(directory / "model.safetensors")
        except (OSError, ValueError, AttributeError):
            valid = False
        if not valid:
            missing.append(name)
    return {"ready": not missing, "missing_artifacts": missing}


def models_present(model_dir: Path) -> bool:
    return artifacts_status(model_dir)["ready"]


def missing_dependencies() -> list[str]:
    # Checking module specs avoids allocating Torch/model memory in the API.
    return [name for name in ("torch", "torchvision", "transformers", "numpy", "sklearn", "joblib", "safetensors")
            if importlib.util.find_spec(name) is None]


def sha256_file(path: Path) -> str:
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def artifact_fingerprint(model_dir: Path) -> dict:
    """Safe public provenance: hashes/revisions, never training IDs or media."""
    result = {}
    for name, directory in model_paths(model_dir).items():
        manifest = directory / "artifact_manifest.json"
        entry = {"sha256": sha256_file(directory / "model.safetensors")}
        if manifest.is_file():
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            expected = metadata.get("files", {}).get("model.safetensors")
            if expected and expected != entry["sha256"]:
                raise ValueError("Local vision artifact checksum does not match its manifest")
            entry.update({key: metadata[key] for key in ("repository", "revision", "license") if key in metadata})
        result[name] = entry
    return result


def pick_device(preference: str = "auto") -> str:
    import torch
    if preference not in {"auto", "cpu", "cuda", "mps"}:
        raise ValueError("Unsupported local inference device")
    if preference != "auto":
        if preference == "cuda" and not torch.cuda.is_available():
            raise ValueError("Configured CUDA device is unavailable")
        if preference == "mps" and not (getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()):
            raise ValueError("Configured MPS device is unavailable")
        return preference
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _deadline(deadline: float | None) -> None:
    if deadline is not None and time.time() >= deadline:
        raise TimeoutError("Local feature extraction deadline expired")


def load_models(model_dir: Path, device: str = "auto", deadline: float | None = None) -> dict:
    _deadline(deadline)
    if not models_present(model_dir):
        raise ValueError("Complete local safetensors and image processors are required")
    stamps = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size)
                   for directory in model_paths(model_dir).values()
                   for path in (directory / "model.safetensors", directory / "config.json", directory / "preprocessor_config.json"))
    key = (str(Path(model_dir).resolve()), device, stamps)
    with _lock:
        if key in _cache:
            return _cache[key]
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        import torch
        from transformers import AutoImageProcessor, AutoModel, RTDetrForObjectDetection

        torch.set_num_threads(max(1, min(int(os.environ.get("CV_NUM_THREADS", "2")), 4)))
        dev = pick_device(device)
        paths = model_paths(model_dir)
        fingerprint = artifact_fingerprint(model_dir)
        common = {"local_files_only": True, "trust_remote_code": False}
        det_proc = AutoImageProcessor.from_pretrained(paths["detector"], use_fast=False, **common)
        det = RTDetrForObjectDetection.from_pretrained(paths["detector"], use_safetensors=True, **common).to(dev).eval()
        _deadline(deadline)
        emb_proc = AutoImageProcessor.from_pretrained(paths["embedder"], use_fast=False, **common)
        emb = AutoModel.from_pretrained(paths["embedder"], use_safetensors=True, **common).to(dev).eval()
        _deadline(deadline)
        _cache.clear()  # One worker/device/model set; do not retain obsolete weights.
        _cache[key] = {"device": dev, "det_proc": det_proc, "det": det, "emb_proc": emb_proc,
                       "emb": emb, "artifacts": fingerprint}
        return _cache[key]


def extract(frame_paths: list[str], model_dir: Path, device: str = "auto", deadline: float | None = None,
            batch_size: int = 1, det_stride: int = 1) -> list[dict]:
    """Objects are present only on the exact frame actually passed to RT-DETR.

    A stride >1 is optional explicit sampling; skipped frames carry an observation
    mask and no detections. It is never evidence that an object persisted/moved.
    """
    if not frame_paths or len(frame_paths) > 1000 or not 1 <= batch_size <= 8 or not 1 <= det_stride <= 16:
        raise ValueError("Invalid bounded feature extraction settings")
    _deadline(deadline)
    models = load_models(model_dir, device, deadline)
    import torch
    from PIL import Image

    dev, results = models["device"], []
    id2label = models["det"].config.id2label
    for start in range(0, len(frame_paths), batch_size):
        _deadline(deadline)
        images = []
        try:
            for path in frame_paths[start:start + batch_size]:
                with Image.open(path) as source:
                    if source.width * source.height > 4_194_304:
                        raise ValueError("Sampled image exceeds inference resolution limit")
                    images.append(source.convert("RGB"))
            sizes = [(image.height, image.width) for image in images]
            det_local = [index for index in range(len(images)) if (start + index) % det_stride == 0]
            post_map = {}
            with torch.inference_mode():
                if det_local:
                    inputs = models["det_proc"](images=[images[index] for index in det_local], return_tensors="pt").to(dev)
                    output = models["det"](**inputs)
                    post = models["det_proc"].post_process_object_detection(output, threshold=OBJECT_SCORE,
                        target_sizes=torch.tensor([sizes[index] for index in det_local], device=dev))
                    post_map = dict(zip(det_local, post, strict=True))
                _deadline(deadline)
                inputs = models["emb_proc"](images=images, return_tensors="pt").to(dev)
                output = models["emb"](**inputs).last_hidden_state
                vectors = torch.nn.functional.normalize(torch.cat([output[:, 0], output[:, 1:].mean(dim=1)], dim=1), dim=1).float().cpu()
            _deadline(deadline)
            for index, (height, width) in enumerate(sizes):
                objects = []
                item = post_map.get(index)
                if item is not None:
                    for score, label, box in zip(item["scores"].tolist(), item["labels"].tolist(), item["boxes"].tolist(), strict=True):
                        name = id2label.get(label, id2label.get(str(label), str(label)))
                        if name not in TRACKED:
                            continue
                        if not all(math.isfinite(float(value)) for value in [score, *box]):
                            raise ValueError("The local object model returned nonfinite values")
                        x0, y0, x1, y1 = box
                        coordinates = [x0 / width, y0 / height, x1 / width, y1 / height]
                        coordinates = [max(0.0, min(1.0, value)) for value in coordinates]
                        if coordinates[0] >= coordinates[2] or coordinates[1] >= coordinates[3]:
                            continue
                        objects.append({"label": name, "score": float(score), "box": coordinates})
                embedding = vectors[index].tolist()
                if not embedding or not all(math.isfinite(value) for value in embedding):
                    raise ValueError("The local embedding model returned invalid features")
                results.append({"embedding": embedding, "objects": objects, "objects_observed": item is not None})
        finally:
            for image in images:
                image.close()
    return results
