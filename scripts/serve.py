"""Manage only this project's local services; optional HTTPS tunnel is explicit."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time

import httpx
import psutil
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.core.config import Settings  # noqa: E402

RUNTIME = ROOT / ".local/runtime"
STATE = RUNTIME / "services.json"


def read_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {"processes": {}}


def write_state(state):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temp.replace(STATE)


def owned_process(record):
    try:
        process = psutil.Process(record["pid"])
        if abs(process.create_time() - record["created"]) > 0.1:
            return None
        if Path(process.cwd()).resolve() != ROOT or process.cmdline() != record["command"]:
            return None
        return process
    except (psutil.Error, KeyError):
        return None


def stop_record(record):
    process = owned_process(record)
    if process is None:
        return
    children = process.children(recursive=True)
    for item in reversed(children + [process]):
        try:
            item.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(children + [process], timeout=8)
    if alive:
        raise RuntimeError("A managed process did not stop; inspect local runtime logs.")


def stop_records(state, records):
    database = Path(state["database_path"]) if state.get("database_path") else None
    connection = None
    try:
        if database is not None and database.exists():
            connection = sqlite3.connect(str(database), timeout=15)
            # Freeze admission/claims while deciding whether a restart is safe.
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('receiving','queued','processing')").fetchone()[0]
            if active:
                raise RuntimeError("An upload or analysis is active. Wait for completion before restarting services.")
        for record in reversed(list(records)):
            stop_record(record)
    finally:
        if connection is not None:
            connection.rollback()
            connection.close()


def stop(state):
    stop_records(state, state.get("processes", {}).values())
    state = {"processes": {}}
    write_state(state)
    return state


def spawn(state, name, command, environment):
    existing = state["processes"].get(name)
    if existing and owned_process(existing):
        return
    RUNTIME.mkdir(parents=True, exist_ok=True)
    creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    with (RUNTIME / f"{name}.stdout.log").open("ab") as stdout, (RUNTIME / f"{name}.stderr.log").open("ab") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, creationflags=creationflags,
                                   start_new_session=os.name != "nt")
    managed = psutil.Process(process.pid)
    state["processes"][name] = {"pid": process.pid, "created": managed.create_time(), "command": managed.cmdline()}
    write_state(state)


def wait_http(url, seconds=40):
    deadline = time.monotonic() + seconds
    with httpx.Client(timeout=2, trust_env=False) as client:
        while time.monotonic() < deadline:
            try:
                if client.get(url).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
    raise RuntimeError(f"Service did not become healthy: {url}. Inspect .local/runtime logs.")


def require_free_port(state, name, port):
    if state["processes"].get(name) and owned_process(state["processes"][name]):
        return
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise RuntimeError(f"Port {port} is already occupied by an unmanaged service. Stop that service before starting this controller.") from None


def wait_worker(state, seconds=30):
    deadline = time.monotonic() + seconds
    with httpx.Client(timeout=3, trust_env=False) as client:
        while time.monotonic() < deadline:
            record = state["processes"]["worker"]
            if not owned_process(record):
                raise RuntimeError("Worker exited during startup. Inspect .local/runtime/worker.stderr.log.")
            try:
                status = client.get("http://127.0.0.1:8000/api/ui/status").json()
                if status.get("worker_alive") and (status.get("worker_heartbeat") or 0) >= record["created"]:
                    return
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.5)
    raise RuntimeError("Worker has no fresh heartbeat. Inspect local worker logs.")


def start(state, public=False, review=False):
    settings = Settings()
    if state.get("database_path") and state["database_path"] != str(settings.database_path):
        if any(owned_process(record) for record in state["processes"].values()):
            raise RuntimeError("Storage configuration changed. Use restart so every service shares the new database.")
    state["database_path"] = str(settings.database_path)
    environment = {**{key: value for key, value in dotenv_values(ROOT / ".env").items() if value is not None},
                   **os.environ}
    environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                       OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
    local_env = {**environment, "APP_ENV": "development", "SECURE_COOKIES": "false", "PUBLIC_ORIGIN": ""}
    require_free_port(state, "api", 8000)
    spawn(state, "api", [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"], local_env)
    spawn(state, "worker", [sys.executable, "-m", "backend.app.workers.runner"], environment)
    wait_http("http://127.0.0.1:8000/healthz")
    wait_worker(state)
    state["web_url"] = "http://127.0.0.1:8000"
    if review:
        require_free_port(state, "review", 8001)
        review_env = {**local_env, "ENABLE_LOCAL_REVIEW": "true"}
        spawn(state, "review", [sys.executable, "-m", "uvicorn", "backend.app.review.app:create_app", "--factory", "--host", "127.0.0.1", "--port", "8001", "--no-proxy-headers"], review_env)
        wait_http("http://127.0.0.1:8001/review")
        state["review_url"] = "http://127.0.0.1:8001/review"
    if public:
        require_free_port(state, "public_api", 8002)
        if settings.retention_hours is None or len(settings.jury_api_key) < 32:
            raise RuntimeError("Public mode requires explicit RETENTION_HOURS and a generated JURY_API_KEY in private .env.")
        tunnel = shutil.which("cloudflared") or str(ROOT / ".tools/cloudflared/cloudflared.exe")
        if not Path(tunnel).is_file():
            raise RuntimeError("Install cloudflared or put the official binary in .tools/cloudflared/cloudflared.exe.")
        if not state["processes"].get("tunnel") or not owned_process(state["processes"]["tunnel"]):
            (RUNTIME / "tunnel.stderr.log").write_text("", encoding="utf-8")
            spawn(state, "tunnel", [tunnel, "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", "http://127.0.0.1:8002"], environment)
        deadline = time.monotonic() + 45
        public_url = None
        while time.monotonic() < deadline:
            log = (RUNTIME / "tunnel.stderr.log").read_text(encoding="utf-8", errors="replace")
            matches = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", log)
            if matches:
                public_url = matches[-1]
                break
            time.sleep(0.5)
        if public_url is None:
            raise RuntimeError("Tunnel did not return a public URL. Local app remains available; inspect tunnel log.")
        previous_public = state["processes"].get("public_api")
        if previous_public and state.get("public_url") != public_url:
            stop_records(state, [previous_public])
            state["processes"].pop("public_api", None)
        public_env = {**environment, "APP_ENV": "production", "SECURE_COOKIES": "true", "PUBLIC_ORIGIN": public_url}
        spawn(state, "public_api", [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8002", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"], public_env)
        wait_http("http://127.0.0.1:8002/healthz")
        wait_http(public_url + "/healthz", seconds=45)
        state["public_url"] = public_url
    write_state(state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "restart", "stop", "status"))
    parser.add_argument("--public", action="store_true", help="Create an HTTPS quick tunnel to the public API only.")
    parser.add_argument("--review", action="store_true", help="Start the separate local annotation service on8001.")
    args = parser.parse_args()
    os.chdir(ROOT)
    state = read_state()
    if args.action in {"restart", "stop"}:
        state = stop(state)
    if args.action in {"start", "restart"}:
        state = start(state, args.public, args.review)
    for name, record in state["processes"].items():
        print(f"{name}: {'running' if owned_process(record) else 'stopped'}")
    for name in ("web_url", "public_url", "review_url"):
        if state.get(name):
            print(f"{name}: {state[name]}")
    print("Jury key stays in private .env; it is never printed by this controller.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
