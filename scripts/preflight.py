"""Safe setup checks: never print environment values, credentials, or media details."""
import importlib.util
import shutil
import subprocess
import sys


def main() -> None:
    print(f"Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    for binary in ("node", "npm.cmd" if sys.platform == "win32" else "npm"):
        location = shutil.which(binary)
        if not location:
            print(f"{binary}: missing")
            continue
        result = subprocess.run([location, "--version"], capture_output=True, text=True, timeout=10)
        print(f"{binary}: {result.stdout.strip() if result.returncode == 0 else 'unavailable'}")
    for module in ("fastapi", "pydantic", "httpx", "psutil"):
        print(f"{module}: {'installed' if importlib.util.find_spec(module) else 'missing'}")
    from backend.app.core.config import Settings
    settings = Settings()
    for label in ("ffmpeg", "ffprobe"):
        binary = str(getattr(settings, f"{label}_binary"))
        try:
            result = subprocess.run([binary, "-version"], capture_output=True, timeout=10)
            state = "available" if result.returncode == 0 else "unavailable"
        except (OSError, subprocess.TimeoutExpired):
            state = "missing; install FFmpeg or configure its binary path in .env"
        print(f"{label}: {state}")
    print("Readiness for real analysis is reported by /api/ui/status after starting the API and worker.")


if __name__ == "__main__":
    # Direct script invocation must also resolve the repository package.
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
