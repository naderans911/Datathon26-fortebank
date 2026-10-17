"""Apply the configured retention policy to terminal jobs and their private media."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.config import Settings  # noqa: E402
from backend.app.core.retention import purge_expired  # noqa: E402
from backend.app.db.store import Store  # noqa: E402


def main() -> None:
    settings = Settings()
    if settings.retention_hours is None:
        raise SystemExit("Set RETENTION_HOURS to an explicitly chosen policy before purging.")
    purge_expired(settings, Store(settings.database_path))
    print("Retention policy applied to eligible completed/failed jobs. Active jobs were preserved.")


if __name__ == "__main__":
    main()
