"""Explicit retention policy for stored media and terminal analysis records."""

import re
import shutil
import time


def purge_expired(settings, store) -> int:
    """Delete terminal jobs older than configured hours; return deleted count.

    No retention period is assumed. Paths are derived from validated opaque IDs,
    resolved and checked against the dedicated jobs directory before deletion.
    """
    count = 0
    jobs_root = (settings.storage_dir / "jobs").resolve()
    if settings.retention_hours is not None:
        for job in store.expired(settings.retention_hours):
            if not re.fullmatch(r"[a-f0-9]{32}", job["id"]):
                continue
            directory = (jobs_root / job["id"]).resolve()
            if directory.parent != jobs_root or not directory.is_relative_to(jobs_root):
                continue
            try:
                if directory.exists():
                    shutil.rmtree(directory)
            except OSError:
                # Keep the metadata for another cleanup attempt if files are busy.
                continue
            store.delete(job["id"])
            count += 1
    with store.connect() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
        connection.execute("DELETE FROM rate_events WHERE occurred_at<?", (time.time() - 3600,))
        connection.execute("DELETE FROM workers WHERE heartbeat_at<?", (time.time() - 3600,))
    return count
