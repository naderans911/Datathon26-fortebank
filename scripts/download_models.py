"""Explicit one-time download of fixed, licensed pretrained vision artifacts.

Importing this module never downloads anything. Runtime inference is offline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "PekingU/rtdetr_r18vd": {"directory": "rtdetr_r18vd", "revision": "ac77a11ff0170a41b771c03264987f8ce2b0d753", "license": "Apache-2.0"},
    "facebook/dinov2-small": {"directory": "dinov2-small", "revision": "ed25f3a31f01632728cabb09d1542f84ab7b0056", "license": "Apache-2.0"},
}
FILES = ["README.md", "config.json", "model.safetensors", "preprocessor_config.json"]


def write_manifest(target: Path, repository: str, spec: dict) -> dict:
    hashes = {}
    for name in FILES:
        with (target / name).open("rb") as source:
            hashes[name] = hashlib.file_digest(source, "sha256").hexdigest()
    manifest = {"schema_version": 1, "repository": repository, "revision": spec["revision"],
                "license": spec["license"], "files": hashes}
    temporary = target / "artifact_manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target / "artifact_manifest.json")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "models")
    args = parser.parse_args()
    from huggingface_hub import snapshot_download
    for repository, spec in MODELS.items():
        target = args.output_dir / spec["directory"]
        print(f"Preparing {repository} at pinned revision {spec['revision']}")
        snapshot_download(repo_id=repository, revision=spec["revision"], local_dir=target, allow_patterns=FILES)
        write_manifest(target, repository, spec)
    print("Pretrained vision artifacts prepared. A local binary scorer is still required for real analysis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
