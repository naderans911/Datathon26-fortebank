"""Only synthetic labels/media: local reviewer isolation, persistence and boundaries."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.review.app import ReviewSettings, create_app
from backend.app.review.models import Annotation
from backend.app.review.store import ReviewError, ReviewStore, RevisionConflict


@pytest.fixture
def review_files(tmp_path):
    videos = tmp_path / "videos"
    videos.mkdir()
    video = videos / "synthetic.mov"
    video.write_bytes(b"synthetic fixture; transcoding is replaced in the media test")
    records = [{"filename_raw": "synthetic.mov", "resolved_video_path": str(video),
                "source_sheet": "Synthetic", "source_row": 2, "timestamp_sec": 4.0,
                "timestamp_raw": "00:04", "has_violation": True, "label_raw": "1",
                "duration_sec": 12.0, "validation_status": "valid"}]
    export = {"records": records, "source_fingerprint": {"sha256": "a" * 64}, "issues": []}
    labels = tmp_path / "validated.json"
    labels.write_text(json.dumps(export), encoding="utf-8")
    return labels, videos, tmp_path / "annotations", export


def client_for(files, **changes):
    labels, videos, annotations, _ = files
    settings = ReviewSettings(enabled=True, labels=labels, video_root=videos, data_dir=annotations,
                              frontend_dist=annotations.parent / "dist")
    for name, value in changes.items():
        setattr(settings, name, value)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8001", client=("127.0.0.1", 48000))


def establish(client):
    response = client.get("/api/review/session")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"], "Origin": "http://127.0.0.1:8001"}


def example_annotation():
    return {"revision": 0, "status": "draft", "notes": "Synthetic review only", "events": [
        {"id": "shape-a", "event_type": "", "observation": "A generated square is visible.",
         "start_sec": None, "end_sec": None, "candidate_rule_id": None, "status": "draft"},
        {"id": "shape-b", "event_type": "Shape contact", "observation": "A generated circle touches a line.",
         "start_sec": 3.5, "end_sec": 5, "candidate_rule_id": "candidate-only", "status": "reviewed"}]}


def test_disabled_review_does_not_load_labels(review_files):
    client = client_for(review_files, enabled=False, labels=Path("nonexistent-private-file"))
    assert client.get("/api/review/session").status_code == 403


@pytest.mark.parametrize("headers", [
    {"Host": "public.example"}, {"Origin": "https://public.example"},
    {"X-Forwarded-Host": "public.example"}, {"X-Forwarded-For": "127.0.0.1"},
    {"Forwarded": "for=127.0.0.1;host=public.example"}, {"Sec-Fetch-Site": "cross-site"},
])
def test_public_tunnel_and_cross_origin_requests_rejected(review_files, headers):
    assert client_for(review_files).get("/api/review/session", headers=headers).status_code == 403


def test_non_loopback_peer_denied_even_with_local_host(review_files):
    local = client_for(review_files)
    client = TestClient(local.app, base_url="http://127.0.0.1:8001", client=("192.0.2.10", 80))
    assert client.get("/api/review/session").status_code == 403


def test_session_csrf_separate_annotation_and_revision(review_files):
    labels = review_files[0]
    original_bytes = labels.read_bytes()
    client = client_for(review_files)
    assert client.get("/api/review/items").status_code == 401
    headers = establish(client)
    listing = client.get("/api/review/items").json()
    record_id = listing["items"][0]["id"]
    route = f"/api/review/items/{record_id}"
    initial = client.get(route).json()
    assert initial["source"]["timestamp_sec"] == 4
    assert initial["annotation"]["events"] == []
    assert "resolved_video_path" not in json.dumps(initial)
    annotation = example_annotation()
    assert client.put(route + "/annotation", json=annotation).status_code == 403
    no_origin = {"X-CSRF-Token": headers["X-CSRF-Token"]}
    assert client.put(route + "/annotation", json=annotation, headers=no_origin).status_code == 403
    response = client.put(route + "/annotation", json=annotation, headers=headers)
    assert response.status_code == 200
    assert response.json()["annotation"]["revision"] == 1
    assert client.put(route + "/annotation", json=annotation, headers=headers).status_code == 409
    assert labels.read_bytes() == original_bytes
    recovered = client.get(route).json()
    assert recovered["source"]["timestamp_sec"] == 4
    assert recovered["annotation"]["events"][0]["start_sec"] is None
    assert len(recovered["annotation"]["events"]) == 2
    restarted = client_for(review_files)
    establish(restarted)
    assert restarted.get(route).json()["annotation"] == recovered["annotation"]
    assert client.get("/api/review/items/not-a-record/video").status_code == 404


@pytest.mark.parametrize("change", [
    {"start_sec": 8, "end_sec": 3}, {"end_sec": 13}, {"start_sec": -1},
    {"status": "reviewed", "observation": ""},
])
def test_annotation_validation_does_not_echo_private_input(review_files, change):
    client = client_for(review_files)
    headers = establish(client)
    record_id = client.get("/api/review/items").json()["items"][0]["id"]
    annotation = example_annotation()
    annotation["notes"] = "private-synthetic-marker"
    annotation["events"][0].update(change)
    response = client.put(f"/api/review/items/{record_id}/annotation", json=annotation, headers=headers)
    assert response.status_code == 422
    assert "private-synthetic-marker" not in response.text


def test_unresolved_invalid_outside_root_excluded_and_global_error_rejected(review_files, tmp_path):
    labels, videos, annotations, export = review_files
    export["records"].append({**export["records"][0], "validation_status": "invalid"})
    export["records"].append({**export["records"][0], "resolved_video_path": None})
    outside = tmp_path / "outside.mov"
    outside.write_bytes(b"synthetic")
    export["records"].append({**export["records"][0], "resolved_video_path": str(outside)})
    labels.write_text(json.dumps(export))
    store = ReviewStore(labels, videos, annotations)
    assert len(store.records) == 1 and store.excluded == 3
    export["issues"] = [{"severity": "error", "record_index": None, "code": "source_mismatch"}]
    labels.write_text(json.dumps(export))
    with pytest.raises(ReviewError, match="global"):
        ReviewStore(labels, videos, annotations)


def test_stale_revision_cannot_overwrite_and_duplicate_event_ids_rejected(review_files):
    store = ReviewStore(*review_files[:3])
    record_id = next(iter(store.records))
    annotation = Annotation.model_validate(example_annotation())
    store.save(record_id, annotation)
    with pytest.raises(RevisionConflict):
        store.save(record_id, annotation)
    bad = copy.deepcopy(example_annotation())
    bad["events"][1]["id"] = bad["events"][0]["id"]
    with pytest.raises(ValueError):
        Annotation.model_validate(bad)


def test_local_preview_requires_session_supports_range_and_no_source_path(review_files, monkeypatch):
    def fake_transcode(command, **_kwargs):
        Path(command[-1]).write_bytes(b"0123456789")
    monkeypatch.setattr("backend.app.review.app.subprocess.run", fake_transcode)
    client = client_for(review_files)
    establish(client)
    item = client.get("/api/review/items").json()["items"][0]
    response = client.get(f"/api/review/items/{item['id']}/video", headers={"Range": "bytes=2-5"})
    assert response.status_code == 206 and response.content == b"2345"
    assert response.headers["Cache-Control"] == "no-store"
    assert str(review_files[1]) not in str(response.headers)
