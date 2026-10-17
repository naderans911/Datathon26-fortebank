"""Durable local worker with a process supervisor and wall-clock deadline.

Run from the repository root: python -m backend.app.workers.runner
The --check flag exits successfully only when a current worker heartbeat exists.
"""

import argparse
import concurrent.futures
import logging
import multiprocessing
import os
import queue
import signal
import time
import uuid

import psutil

from backend.app.core.config import Settings
from backend.app.core.retention import purge_expired
from backend.app.db.store import Store
from backend.app.schemas.job import validate_result


LOGGER = logging.getLogger("forte.worker")


def _error(exc: BaseException) -> dict:
    # Raw subprocess/model errors can contain footage, credentials or filesystem paths.
    # The local logs intentionally record exception types only.
    if isinstance(exc, TimeoutError):
        return {"code": "deadline_exceeded", "message": "The analysis deadline expired. No complete verdict was produced."}
    code = getattr(exc, "code", None)
    safe_codes = {
        "deadline_exceeded": "The analysis deadline expired. No complete verdict was produced.",
        "invalid_media": "The uploaded media could not be processed. Check decodability, duration and configured media limits.",
        "detector_failed": "The local detector could not produce valid observations. Check the local model and rules.",
        "invalid_video": "The file could not be decoded as a supported video.",
        "video_too_long": "The video exceeds the configured duration limit.",
        "detector_unavailable": "The local detector became unavailable during analysis.",
        "invalid_model_output": "The local detector returned invalid observations. No complete verdict was produced.",
        "resource_limit": "The analysis exceeded configured resource limits.",
    }
    if code in safe_codes:
        return {"code": code, "message": safe_codes[code]}
    return {"code": "analysis_failed", "message": "Local analysis could not be completed. Check the video and local engine configuration, then submit a new job."}


def _child(job: dict, settings: Settings, channel, detector=None):
    if os.name != "nt":
        os.setsid()
    try:
        from backend.app.detectors.factory import build_detector
        from backend.app.services.pipeline import process_job

        detector = detector or build_detector(settings)
        result = process_job(job, settings, detector, lambda stage: channel.put(("progress", stage)))
        validate_result(result, job, settings)
        channel.put(("result", result))
    except BaseException as exc:
        channel.put(("error", _error(exc)))


def terminate_tree(process):
    """Terminate the job and FFmpeg descendants on Windows and POSIX."""
    if process.pid is None:
        return
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        children = []
        parent = None
    for child in reversed(children):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    if parent:
        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass
    _, remaining = psutil.wait_procs(children + ([parent] if parent else []), timeout=2)
    for child in remaining:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    if process.is_alive():
        process.kill()
    process.join(timeout=2)


def _directory_size(directory) -> int:
    size = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file():
                size += path.stat().st_size
        except FileNotFoundError:
            pass
    return size


def supervise(job: dict, settings: Settings, store: Store, worker_id: str, detector=None):
    context = multiprocessing.get_context("spawn")
    channel = context.Queue(maxsize=32)
    process = context.Process(target=_child, args=(job, settings, channel, detector), daemon=False)
    result = None
    error = None
    process.start()
    next_storage_check = 0
    try:
        while True:
            now = time.time()
            store.heartbeat(worker_id)
            store.progress(job["id"])
            if now >= job["deadline_at"]:
                error = _error(TimeoutError())
                break
            if now >= next_storage_check:
                directory = settings.storage_dir / "jobs" / job["id"]
                allocation = job["size_bytes"] + settings.max_job_output_mb * 1024 * 1024
                if _directory_size(directory) > allocation:
                    error = {"code": "resource_limit", "message": "The analysis exceeded its configured storage allocation."}
                    break
                next_storage_check = now + 2
            try:
                kind, payload = channel.get(timeout=min(0.5, max(0.01, job["deadline_at"] - now)))
            except queue.Empty:
                if not process.is_alive():
                    error = {"code": "worker_interrupted", "message": "The analysis process stopped before producing a complete result."}
                    break
                continue
            if kind == "progress":
                store.progress(job["id"], payload)
            elif kind == "error":
                error = payload
                break
            elif kind == "result":
                result = payload
                break
    finally:
        # A result is only valid while inside the original acceptance budget.
        # Shutdown also kills a child stalled during process teardown.
        terminate_tree(process)
        channel.close()
        channel.join_thread()
    if error:
        store.fail(job["id"], error["code"], error["message"])
    elif result is not None:
        if not store.complete(job["id"], result):
            error = _error(TimeoutError())
            store.fail(job["id"], error["code"], error["message"])


def process_once(settings: Settings, detector=None, *, supervised: bool = True, worker_id: str | None = None) -> bool:
    """Claim one job. The unsupervised hook exists only for injected unit-test detectors."""
    if not supervised and detector is None:
        raise ValueError("Unsupervised processing requires an explicitly injected test detector.")
    store = Store(settings.database_path)
    worker_id = worker_id or f"worker-{uuid.uuid4().hex}"
    store.heartbeat(worker_id)
    store.recover(settings.worker_heartbeat_seconds * 3)
    job = store.claim(worker_id, settings.worker_concurrency)
    if not job:
        return False
    version = f"{settings.detector_backend}:{settings.local_vision_model or 'unset'}:adapter-v1"
    if detector is not None:
        version = f"injected:{type(detector).__name__}"
    store.detector_used(job["id"], version)
    if supervised:
        supervise(job, settings, store, worker_id, detector)
    else:
        try:
            from backend.app.services.pipeline import process_job
            result = process_job(job, settings, detector, lambda stage: store.progress(job["id"], stage))
            validate_result(result, job, settings)
            if not store.complete(job["id"], result):
                raise TimeoutError()
        except Exception as exc:
            safe = _error(exc)
            store.fail(job["id"], safe["code"], safe["message"])
    return True


def main():
    parser = argparse.ArgumentParser(description="Run the supervised local video worker.")
    parser.add_argument("--check", action="store_true", help="Exit 0 when a live worker heartbeat exists; 1 otherwise.")
    args = parser.parse_args()
    settings = Settings()
    store = Store(settings.database_path)
    if args.check:
        heartbeat = store.last_heartbeat()
        raise SystemExit(0 if heartbeat and time.time() - heartbeat < settings.worker_heartbeat_seconds else 1)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    worker_ids = [f"worker-{uuid.uuid4().hex}" for _ in range(settings.worker_concurrency)]
    # Threads only supervise; actual media/model work runs in isolated child processes.
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.worker_concurrency) as executor:
        pending = {}
        next_cleanup = 0
        try:
            while not stopping:
                if time.time() >= next_cleanup:
                    store.recover(settings.worker_heartbeat_seconds * 3)
                    purge_expired(settings, store)
                    next_cleanup = time.time() + 60
                for worker_id in worker_ids:
                    store.heartbeat(worker_id)
                    future = pending.get(worker_id)
                    if future is not None and not future.done():
                        continue
                    if future is not None:
                        try:
                            future.result()
                        except Exception as exc:
                            LOGGER.error("Worker operation failed (%s).", type(exc).__name__)
                    pending[worker_id] = executor.submit(process_once, settings, supervised=True, worker_id=worker_id)
                time.sleep(0.5)
        finally:
            # In-flight jobs remain bounded by their acceptance deadline during shutdown.
            for future in pending.values():
                try:
                    future.result()
                except Exception:
                    pass
            for worker_id in worker_ids:
                store.remove_worker(worker_id)


if __name__ == "__main__":
    main()
