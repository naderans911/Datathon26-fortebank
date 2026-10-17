"""Record installed package license declarations and bundled notice files."""
import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    python = []
    for distribution in importlib.metadata.distributions():
        if distribution.metadata["Name"].lower() in {"pip", "setuptools"}:
            continue
        metadata = distribution.metadata
        license_value = metadata.get("License-Expression") or metadata.get("License")
        if not license_value:
            license_value = "; ".join(value for value in metadata.get_all("Classifier", []) if value.startswith("License ::"))
        notices = [str(file).replace("\\", "/") for file in distribution.files or []
                   if any(word in Path(str(file)).name.lower() for word in ("license", "copying", "notice"))]
        python.append({"name": metadata["Name"], "version": distribution.version,
                       "license": license_value or "Review bundled notices", "notice_files": notices})
    frontend = []
    lock_path = ROOT / "frontend/package-lock.json"
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        for package_path, package in lock.get("packages", {}).items():
            if not package_path:
                continue
            installed = ROOT / "frontend" / package_path
            manifest = installed / "package.json"
            package_metadata = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
            license_value = package_metadata.get("license") or package.get("license") or "Review upstream notices"
            notices = [file.name for file in installed.iterdir() if file.is_file()
                       and any(word in file.name.lower() for word in ("license", "copying", "notice"))] if installed.is_dir() else []
            frontend.append({"name": package_metadata.get("name", package_path.split("node_modules/")[-1]),
                             "version": package.get("version"), "license": license_value,
                             "dev": package.get("dev", False), "notice_files": notices})
    inventory = {"note": "Installed package declarations/notices; model artifacts are not included. Preserve full upstream licenses when distributing dependencies.",
                 "python": sorted(python, key=lambda value: value["name"].lower()),
                 "frontend": sorted(frontend, key=lambda value: value["name"].lower())}
    target = ROOT / "docs/DEPENDENCY_LICENSES.json"
    target.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Recorded {len(python)} Python and {len(frontend)} frontend dependency entries.")


if __name__ == "__main__":
    main()
