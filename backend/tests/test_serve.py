"""Controller lifecycle checks use synthetic databases and never stop real processes."""
import json
import sqlite3
from types import SimpleNamespace

import pytest

from scripts import serve


def database(path, statuses=()):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE jobs (status TEXT NOT NULL)")
        connection.executemany("INSERT INTO jobs(status) VALUES (?)", [(status,) for status in statuses])
    return path


@pytest.mark.parametrize("status", ["receiving", "queued", "processing"])
@pytest.mark.parametrize("all_services", [False, True])
def test_active_jobs_refuse_every_stop_before_process_mutation(tmp_path, monkeypatch, status, all_services):
    path = database(tmp_path / "synthetic.sqlite3", [status])
    record = {"pid": 123, "created": 1, "command": ["synthetic"]}
    state = {"database_path": str(path), "processes": {"public_api": record}}
    stopped, saved = [], []
    monkeypatch.setattr(serve, "stop_record", stopped.append)
    monkeypatch.setattr(serve, "write_state", saved.append)
    with pytest.raises(RuntimeError, match="upload or analysis is active"):
        serve.stop(state) if all_services else serve.stop_records(state, [record])
    assert stopped == [] and saved == []
    assert state["processes"]["public_api"] == record
    # Refusal also releases the write lock rather than leaving admission blocked.
    with sqlite3.connect(path, timeout=0) as connection:
        connection.execute("INSERT INTO jobs(status) VALUES ('done')")


def test_stop_uses_persisted_database_even_after_environment_change(tmp_path, monkeypatch):
    previous = database(tmp_path / "previous.sqlite3", ["processing"])
    changed = database(tmp_path / "changed.sqlite3")
    state_path = tmp_path / "services.json"
    state_path.write_text(json.dumps({"database_path": str(previous), "processes": {"worker": {"pid": 123}}}))
    monkeypatch.setattr(serve, "STATE", state_path)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "new-storage"))
    monkeypatch.setattr(serve, "Settings", lambda: SimpleNamespace(database_path=changed))
    stopped = []
    monkeypatch.setattr(serve, "stop_record", stopped.append)
    with pytest.raises(RuntimeError, match="upload or analysis is active"):
        serve.stop(serve.read_state())
    assert stopped == []
    assert json.loads(state_path.read_text())["database_path"] == str(previous)


def test_stop_holds_admission_lock_until_every_selected_process_stops(tmp_path, monkeypatch):
    path = database(tmp_path / "synthetic.sqlite3", ["done", "failed"])
    records = [{"pid": 1}, {"pid": 2}]
    stopped = []

    def stop(record):
        with sqlite3.connect(path, timeout=0) as other:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("INSERT INTO jobs(status) VALUES ('receiving')")
        stopped.append(record)

    monkeypatch.setattr(serve, "stop_record", stop)
    serve.stop_records({"database_path": str(path)}, records)
    assert stopped == list(reversed(records))
    with sqlite3.connect(path, timeout=0) as connection:
        connection.execute("INSERT INTO jobs(status) VALUES ('receiving')")


def test_public_tunnel_rotation_obeys_active_job_guard(tmp_path, monkeypatch):
    path = database(tmp_path / "synthetic.sqlite3", ["receiving"])
    tool = tmp_path / "cloudflared"
    tool.write_text("synthetic test placeholder")
    (tmp_path / "tunnel.stderr.log").write_text("https://synthetic-new-url.trycloudflare.com")
    old_public = {"pid": 4, "command": ["synthetic-public-api"]}
    state = {"database_path": str(path), "public_url": "https://synthetic-old-url.trycloudflare.com",
             "processes": {"api": {"pid": 1}, "worker": {"pid": 2}, "tunnel": {"pid": 3}, "public_api": old_public}}
    monkeypatch.setattr(serve, "Settings", lambda: SimpleNamespace(database_path=path, retention_hours=24, jury_api_key="x" * 32))
    monkeypatch.setattr(serve, "RUNTIME", tmp_path)
    monkeypatch.setattr(serve, "dotenv_values", lambda _: {})
    monkeypatch.setattr(serve, "owned_process", lambda _: object())
    monkeypatch.setattr(serve, "require_free_port", lambda *args: None)
    monkeypatch.setattr(serve, "wait_http", lambda *args, **kwargs: None)
    monkeypatch.setattr(serve, "wait_worker", lambda *args: None)
    monkeypatch.setattr(serve.shutil, "which", lambda _: str(tool))
    spawned, stopped, saved = [], [], []
    monkeypatch.setattr(serve, "spawn", lambda state, name, *args: spawned.append(name))
    monkeypatch.setattr(serve, "stop_record", stopped.append)
    monkeypatch.setattr(serve, "write_state", saved.append)
    with pytest.raises(RuntimeError, match="upload or analysis is active"):
        serve.start(state, public=True)
    assert stopped == [] and saved == [] and "public_api" not in spawned
    assert state["processes"]["public_api"] == old_public
    assert state["public_url"] == "https://synthetic-old-url.trycloudflare.com"
