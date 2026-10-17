"""API/queue/security contracts with generated media and injected test detectors."""

import base64
import concurrent.futures
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.core.config import Settings
from backend.app.detectors.base import UnconfiguredDetector
from backend.app.main import create_app
from backend.app.services.media import run_media
from backend.app.workers.runner import process_once


class TestDetector:
    __test__ = False

    def __init__(self, positive=False, invalid=False):
        self.positive, self.invalid = positive, invalid

    def readiness(self):
        return {"ready": True, "name": "injected-test-detector", "model_available": True}

    def analyze_windows(self, windows, rules, deadline):
        if self.invalid:
            return [{"rule_id": "invented-rule", "frame_ids": ["invented-frame"], "observation": "Invalid fixture", "event_key": "invalid"}]
        if not self.positive:
            return []
        frames = windows[0]["frames"]
        timestamp_frame = frames[min(1, len(frames) - 1)]["id"]
        return [{"rule_id": rules[0]["id"], "frame_ids": [timestamp_frame],
                 "observation": f"Generated shape {index} is visible.", "event_key": f"shape-{index}"} for index in range(2)]


class SlowDetector(TestDetector):
    def __init__(self, pid_path):
        self.pid_path = str(pid_path)

    def analyze_windows(self, windows, rules, deadline):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Path(self.pid_path).write_text(str(child.pid))
        time.sleep(60)
        return []


def tool(name):
    configured = os.getenv(f"{name.upper()}_BINARY") or shutil.which(name)
    if configured:
        return str(configured)
    found = next(Path(__file__).resolve().parents[2].glob(f".tools/**/{name}.exe"), None)
    if found:
        return str(found)
    pytest.skip(f"{name} is needed for locally generated-media contract tests")


@pytest.fixture
def rule():
    return {"id": "TEST-ONLY", "title": "Test fixture", "event_type": "Generated shape event",
            "jurisdiction": "Test environment", "source_type": "internal_procedure", "document_title": "Test-only procedure",
            "source_url": None, "section_or_paragraph": None, "relevant_excerpt": "Generated shapes are visible.",
            "observed_condition": "A generated shape is visible.", "required_context": ["Test fixture"],
            "interpretation": "Test-only interpretation; no banking claim.", "limitations": ["Test fixture only"],
            "verification_status": "verified", "verified_at": "2026-01-01", "enabled": True, "version": "1"}


@pytest.fixture
def settings(tmp_path, rule):
    registry = tmp_path / "rules.json"
    registry.write_text(json.dumps([rule]), encoding="utf-8")
    return Settings(_env_file=None, storage_dir=tmp_path / "storage", rules_file=registry,
                    jury_api_key="test-key-never-used-in-deployment", ffmpeg_binary=sys.executable,
                    ffprobe_binary=sys.executable, max_upload_mb=1, max_job_output_mb=8,
                    max_storage_mb=128, sampling_fps=2, upload_rate_per_hour=50)


@pytest.fixture
def media_settings(settings):
    return settings.model_copy(update={"ffmpeg_binary": tool("ffmpeg"), "ffprobe_binary": tool("ffprobe")})


def client_for(settings, detector=None):
    app = create_app(settings, detector or TestDetector())
    app.state.store.heartbeat("test-worker")
    return TestClient(app)


def auth(settings):
    return {"X-API-Key": settings.jury_api_key}


def synthetic_video(settings, tmp_path):
    video = tmp_path / "test.mov"
    run_media([settings.ffmpeg_binary, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
               "testsrc2=size=160x96:rate=30:duration=2", "-c:v", "mpeg4", "-q:v", "3", "-an", str(video)], time.time() + 30)
    return video.read_bytes()


def upload(client, settings, content=b"probe-at-worker"):
    return client.post("/api/v1/analyze", headers=auth(settings), files={"file": ("clip.mov", content, "video/quicktime")})


def ui_session(client):
    response = client.get("/api/ui/session")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_required_and_incorrect_judge_keys(settings):
    with client_for(settings) as client:
        for headers in ({}, {"X-API-Key": "wrong"}):
            assert client.post("/api/v1/analyze", headers=headers, files={"file": ("a.mov", b"data")}).status_code == 401
            assert client.get("/api/v1/jobs/" + "a" * 32, headers=headers).status_code == 401
        assert client.get("/api/v1/jobs/" + "a" * 32, headers=auth(settings)).status_code == 404


def test_missing_model_rules_and_worker_are_not_ready(settings):
    with client_for(settings, UnconfiguredDetector()) as client:
        assert not client.get("/api/ui/status").json()["ready"]
        assert upload(client, settings).status_code == 503
    settings.rules_file.write_text("[]")
    with client_for(settings) as client:
        status = client.get("/api/ui/status").json()
        assert status["active_verified_rules"] == 0 and not status["ready"]
        assert upload(client, settings).status_code == 503
    settings.rules_file.write_text("invalid json")
    with client_for(settings) as client:
        assert client.get("/api/ui/rules").status_code == 503
        client.app.state.store.remove_worker("test-worker")
        assert not client.get("/api/ui/status").json()["worker_alive"]


def test_size_empty_extension_and_request_body_limits(settings):
    with client_for(settings) as client:
        assert upload(client, settings, b"").status_code == 422
        assert upload(client, settings, b"x" * (settings.max_upload_bytes + 1)).status_code == 413
        assert upload(client, settings, b"x" * (settings.max_upload_bytes * 3)).status_code == 413
        assert client.post("/api/v1/analyze", headers=auth(settings), files={"file": ("a.exe", b"content")}).status_code == 415
        assert not list((settings.storage_dir / "jobs").glob("*/source.mov"))


@pytest.mark.parametrize("positive", [False, True])
def test_exact_judge_contract_real_mov_evidence_and_refresh(media_settings, tmp_path, positive):
    detector = TestDetector(positive)
    with client_for(media_settings, detector) as client:
        response = upload(client, media_settings, synthetic_video(media_settings, tmp_path))
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        pending = client.get(f"/api/v1/jobs/{job_id}", headers=auth(media_settings)).json()
        assert pending == {"job_id": job_id, "status": "processing"}
        assert process_once(media_settings, detector, supervised=False)
        result = client.get(f"/api/v1/jobs/{job_id}", headers=auth(media_settings)).json()
        assert set(result) == {"job_id", "status", "verdict", "violations"}
        assert result["status"] == "done"
        assert result["verdict"] == ("violation" if positive else "no_violation")
        assert len(result["violations"]) == (2 if positive else 0)
        for event in result["violations"]:
            assert set(event) == {"type", "timecode_sec", "description", "evidence_frames"}
            assert 0 <= event["timecode_sec"] <= 2
            assert 1 <= len(event["evidence_frames"]) <= 3
            for frame in event["evidence_frames"]:
                assert set(frame) == {"timestamp_sec", "image_base64"}
                assert not frame["image_base64"].startswith("data:")
                with Image.open(io.BytesIO(base64.b64decode(frame["image_base64"], validate=True))) as image:
                    assert image.format == "JPEG"
                    image.verify()
    # Rebuilding the app proves state is in SQLite, not an in-memory test cache.
    with client_for(media_settings, detector) as reloaded:
        assert reloaded.get(f"/api/v1/jobs/{job_id}", headers=auth(media_settings)).json() == result


def test_corrupt_and_malformed_model_output_are_failed(media_settings, tmp_path):
    for contents, detector in [(b"not a movie", TestDetector()), (synthetic_video(media_settings, tmp_path), TestDetector(invalid=True))]:
        with client_for(media_settings, detector) as client:
            job_id = upload(client, media_settings, contents).json()["job_id"]
            assert process_once(media_settings, detector, supervised=False)
            result = client.get(f"/api/v1/jobs/{job_id}", headers=auth(media_settings)).json()
            assert set(result) == {"job_id", "status", "error"}
            assert result["status"] == "failed" and result["error"]["code"]
            assert str(tmp_path) not in json.dumps(result)


def test_sessions_csrf_origin_and_job_ownership(settings):
    with client_for(settings) as first, client_for(settings) as second:
        first_headers = ui_session(first)
        second_headers = ui_session(second)
        file = {"file": ("a.mov", b"probe in worker")}
        assert first.post("/api/ui/analyze", files=file).status_code == 403
        assert first.post("/api/ui/analyze", headers=second_headers, files=file).status_code == 403
        assert first.post("/api/ui/analyze", headers={**first_headers, "Origin": "https://attacker.example"}, files=file).status_code == 403
        response = first.post("/api/ui/analyze", headers=first_headers, files=file)
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        assert first.get(f"/api/ui/jobs/{job_id}").status_code == 200
        assert second.get(f"/api/ui/jobs/{job_id}").status_code == 404
        assert second.get(f"/api/ui/jobs/{job_id}/media/preview.mp4").status_code == 404
        assert second.delete(f"/api/ui/jobs/{job_id}", headers=second_headers).status_code == 404
        assert first.delete(f"/api/ui/jobs/{job_id}", headers=first_headers).status_code == 409
        assert first.get("/api/ui/session").json()["csrf_token"] == first_headers["X-CSRF-Token"]


def test_ui_media_whitelist_and_cleanup(media_settings, tmp_path):
    detector = TestDetector(True)
    with client_for(media_settings, detector) as client:
        headers = ui_session(client)
        response = client.post("/api/ui/analyze", headers=headers, files={"file": ("a.mov", synthetic_video(media_settings, tmp_path))})
        job_id = response.json()["job_id"]
        process_once(media_settings, detector, supervised=False)
        result = client.get(f"/api/ui/jobs/{job_id}").json()["result"]
        assert client.get(result["preview_url"]).headers["content-type"] == "video/mp4"
        frame_url = result["events"][0]["evidence_frames"][0]["url"]
        assert client.get(frame_url).headers["content-type"] == "image/jpeg"
        assert client.get(frame_url).headers["cache-control"] == "no-store"
        assert client.get(f"/api/ui/jobs/{job_id}/media/source.mov").status_code == 404
        assert client.get(f"/api/ui/jobs/{job_id}/media/..%2F..%2Fjobs.sqlite3").status_code == 404
        assert client.delete(f"/api/ui/jobs/{job_id}", headers=headers).status_code == 204
        assert client.get(f"/api/ui/jobs/{job_id}").status_code == 404
        assert not (media_settings.storage_dir / "jobs" / job_id).exists()


def test_queue_admission_atomic_claim_deadline_and_snapshot(settings):
    settings = settings.model_copy(update={"max_queue_size": 1})
    with client_for(settings) as client:
        job_id = upload(client, settings).json()["job_id"]
        assert upload(client, settings).status_code == 503
        store = client.app.state.store
        snapshot = store.get(job_id)["rules_snapshot"]
        settings.rules_file.write_text("[]")
        assert store.get(job_id)["rules_snapshot"] == snapshot
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(store.claim, ["a", "b", "c", "d"]))
        assert sum(result is not None for result in results) == 1
        with store.connect() as connection:
            connection.execute("UPDATE jobs SET deadline_at=? WHERE id=?", (time.time() - 1, job_id))
        result = client.get(f"/api/v1/jobs/{job_id}", headers=auth(settings)).json()
        assert result["status"] == "failed" and result["error"]["code"] == "deadline_exceeded"
        assert not store.complete(job_id, {"events": []})


def test_public_rate_limit_cannot_be_bypassed_by_new_cookie(settings):
    settings = settings.model_copy(update={"upload_rate_per_hour": 1})
    with client_for(settings) as first, client_for(settings) as second:
        first_headers, second_headers = ui_session(first), ui_session(second)
        assert first.post("/api/ui/analyze", headers=first_headers, files={"file": ("a.mov", b"data")}).status_code == 202
        assert second.post("/api/ui/analyze", headers=second_headers, files={"file": ("b.mov", b"data")}).status_code == 429


def test_demo_disabled_and_isolated_from_judge(media_settings):
    with client_for(media_settings) as client:
        ui_session(client)
        assert client.get("/api/ui/demo/positive").status_code == 404
    enabled = media_settings.model_copy(update={"enable_demo": True})
    with client_for(enabled, UnconfiguredDetector()) as client:
        ui_session(client)
        demo = client.get("/api/ui/demo/positive")
        assert demo.status_code == 200
        data = demo.json()
        assert data["demo"] and data["result"]["verdict"] == "violation"
        assert client.get(data["result"]["preview_url"]).status_code == 200
        assert client.get(f"/api/v1/jobs/{data['job_id']}", headers=auth(enabled)).status_code == 404
        assert not client.get("/api/ui/status").json()["ready"]
        assert upload(client, enabled).status_code == 503


def test_supervised_deadline_stops_underlying_descendant(media_settings, tmp_path):
    settings = media_settings.model_copy(update={"job_deadline_seconds": 4})
    pid_file = tmp_path / "descendant.pid"
    detector = SlowDetector(pid_file)
    with client_for(settings, detector) as client:
        job_id = upload(client, settings, synthetic_video(settings, tmp_path)).json()["job_id"]
        started = time.monotonic()
        assert process_once(settings, detector, supervised=True)
        elapsed = time.monotonic() - started
        data = client.get(f"/api/v1/jobs/{job_id}", headers=auth(settings)).json()
        assert data["status"] == "failed" and data["error"]["code"] == "deadline_exceeded"
        assert elapsed < 10
        assert pid_file.exists(), "The injected detector must run before this deadline test is meaningful"
        assert not psutil.pid_exists(int(pid_file.read_text()))


def test_production_requires_explicit_secure_configuration(settings):
    with pytest.raises(ValueError, match="RETENTION_HOURS"):
        Settings(_env_file=None, app_env="production")
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(_env_file=None, app_env="production", retention_hours=24)
    valid = Settings(_env_file=None, app_env="production", retention_hours=24, secure_cookies=True,
                     public_origin="https://review.example", jury_api_key="x" * 40)
    assert valid.secure_cookies


def test_queue_time_is_included_without_any_worker_claim(settings):
    with client_for(settings) as client:
        job_id = upload(client, settings).json()["job_id"]
        store = client.app.state.store
        with store.connect() as connection:
            connection.execute("UPDATE jobs SET deadline_at=? WHERE id=?", (time.time() - 1, job_id))
        response = client.get(f"/api/v1/jobs/{job_id}", headers=auth(settings)).json()
        assert response["status"] == "failed"
        assert response["error"]["code"] == "deadline_exceeded"
        assert store.claim("late-worker") is None


def test_storage_admission_limit_and_retention(settings, tmp_path):
    from backend.app.core.retention import purge_expired

    too_small = settings.model_copy(update={"max_storage_mb": 1})
    with client_for(too_small) as client:
        assert upload(client, too_small).status_code == 503
    retained = settings.model_copy(update={"retention_hours": 1})
    with client_for(retained) as client:
        old_id = upload(client, retained).json()["job_id"]
        active_id = upload(client, retained).json()["job_id"]
        store = client.app.state.store
        store.fail(old_id, "test_failure", "Synthetic test failure")
        with store.connect() as connection:
            connection.execute("UPDATE jobs SET accepted_at=? WHERE id IN (?,?)", (time.time() - 7200, old_id, active_id))
        assert purge_expired(retained, store) == 1
        assert not (retained.storage_dir / "jobs" / old_id).exists()
        assert store.get(old_id) is None
        assert store.get(active_id)["status"] == "queued"
        assert (retained.storage_dir / "jobs" / active_id / "source.mov").exists()


def test_generated_documentation_has_no_remote_assets(settings):
    with client_for(settings) as client:
        page = client.get("/docs")
        assert page.status_code == 200
        assert "cdn.jsdelivr.net" not in page.text and "unpkg.com" not in page.text
        schema = client.get("/openapi.json").json()
        assert "X-API-Key" in json.dumps(schema["components"]["securitySchemes"])
        assert "JudgeDone" in schema["components"]["schemas"]


def test_chunked_upload_limit_is_enforced_without_content_length(settings):
    with client_for(settings) as client:
        boundary = "synthetic-test-boundary"
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"clip.mov\""
                "\r\nContent-Type: video/quicktime\r\n\r\n").encode()
        body = iter([head, b"x" * (3 * settings.max_upload_bytes), f"\r\n--{boundary}--\r\n".encode()])
        response = client.post("/api/v1/analyze", content=body, headers={
            **auth(settings), "Content-Type": f"multipart/form-data; boundary={boundary}",
        })
        assert response.status_code == 413
