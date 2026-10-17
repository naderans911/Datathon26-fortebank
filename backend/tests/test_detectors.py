import socket
import time
from types import SimpleNamespace

import httpx
import pytest

from backend.app.detectors.base import DetectionError, UnconfiguredDetector, validate_observations
from backend.app.detectors.ollama import OllamaDetector, local_endpoint, validate_model_name
from backend.app.services.rules import load_rules, validate_rules


def test_unconfigured_never_reports_negative():
    detector = UnconfiguredDetector()
    assert not detector.readiness()["ready"]
    with pytest.raises(DetectionError):
        detector.analyze_windows([], [], time.time() + 10)


@pytest.mark.parametrize("url", ["https://api.example.com", "http://169.254.169.254", "http://0.0.0.0", "http://192.168.1.5", "http://user:password@127.0.0.1", "http://127.0.0.1/remote", "file:///x"])
def test_public_unapproved_or_credentialed_endpoints_rejected(url, monkeypatch):
    original = socket.getaddrinfo
    monkeypatch.setattr(socket, "getaddrinfo", lambda hostname, port, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))] if hostname == "api.example.com" else original(hostname, port, **kwargs))
    with pytest.raises(DetectionError):
        local_endpoint(url)


def test_private_host_requires_explicit_allowlist_and_pins_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 11434))])
    with pytest.raises(DetectionError):
        local_endpoint("http://ollama:11434")
    endpoint, host = local_endpoint("http://ollama:11434", ["ollama"])
    assert endpoint == "http://10.1.2.3:11434" and host == "ollama:11434"


@pytest.mark.parametrize("name", ["", "vision:cloud", "remote-cloud", "https://cloud.example/model"])
def test_cloud_model_names_rejected(name):
    with pytest.raises(DetectionError):
        validate_model_name(name)


@pytest.fixture
def detector():
    return OllamaDetector(SimpleNamespace(local_vision_model="local-vision:latest", ollama_base_url="http://127.0.0.1:11434",
                                          allowed_ollama_hosts=[], ollama_timeout_seconds=3, max_events=24))


@pytest.mark.parametrize("metadata", [{"capabilities": ["completion"]}, {"capabilities": ["vision"], "remote_host": "https://cloud.example"}])
def test_readiness_checks_model_capability_and_remote_metadata(detector, monkeypatch, metadata):
    monkeypatch.setattr(detector, "_request", lambda method, route, **kwargs: {"models": [{"name": "local-vision:latest"}]} if route == "/api/tags" else metadata)
    assert not detector.readiness()["ready"]


def test_redirects_are_not_followed(detector, monkeypatch):
    original = httpx.Client
    calls = []

    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://public.example"})

    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return original(**kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(httpx, "Client", client)
    with pytest.raises(DetectionError):
        detector._request("GET", "/api/tags")
    assert len(calls) == 1 and "127.0.0.1" in calls[0]


@pytest.mark.parametrize("overrides", [{"rule_id": "invented"}, {"frame_ids": ["invented"]}, {"frame_ids": ["b", "a"]}, {"confidence": 0.99}])
def test_unknown_ids_temporal_order_and_extra_fields_rejected(overrides):
    value = {"rule_id": "known", "frame_ids": ["a"], "observation": "A shape is visible.", "event_key": "shape", **overrides}
    with pytest.raises(DetectionError):
        validate_observations([value], [{"id": "a", "timestamp_sec": 1}, {"id": "b", "timestamp_sec": 2}], [{"id": "known"}])


def test_malformed_model_output_retries_then_fails(detector, monkeypatch, tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"\xff\xd8\xff\xd9")
    count = []
    monkeypatch.setattr(detector, "_check_model", lambda *args: {})

    def bad_response(*args, **kwargs):
        count.append(1)
        return {"done": True, "response": "This is not JSON"}

    monkeypatch.setattr(detector, "_request", bad_response)
    with pytest.raises(DetectionError, match="invalid"):
        detector.analyze_windows([{"frames": [{"id": "frame-1", "timestamp_sec": 0, "path": str(image)}]}], [{"id": "rule-1"}], time.time() + 30)
    assert len(count) == 2


def test_structured_local_request_validates_known_references(detector, monkeypatch, tmp_path):
    import base64
    import json
    from PIL import Image
    image = tmp_path / "frame.jpg"
    Image.new("RGB", (16, 16), "magenta").save(image, format="JPEG")
    monkeypatch.setattr(detector, "_check_model", lambda *args: {})

    def valid_response(method, route, *, body, timeout):
        assert method == "POST" and route == "/api/generate"
        assert body["stream"] is False and isinstance(body["format"], dict)
        assert base64.b64decode(body["images"][0]) == image.read_bytes()
        return {"done": True, "response": json.dumps({"observations": [{"rule_id": "rule-1", "frame_ids": ["frame-1"], "observation": "A magenta shape is visible.", "event_key": "magenta-shape"}]})}

    monkeypatch.setattr(detector, "_request", valid_response)
    results = detector.analyze_windows([{"frames": [{"id": "frame-1", "timestamp_sec": 0, "path": str(image)}]}], [{"id": "rule-1"}], time.time() + 30)
    assert results[0]["rule_id"] == "rule-1"


def test_event_limit_rejected_not_truncated():
    values = [{"rule_id": None, "frame_ids": ["a"], "observation": "Visible shape", "event_key": str(i)} for i in range(3)]
    with pytest.raises(DetectionError, match="limit"):
        validate_observations(values, [{"id": "a", "timestamp_sec": 0}], [], max_events=2)


def test_empty_registry_and_synthetic_exclusion(tmp_path):
    registry = tmp_path / "rules.json"
    registry.write_text("[]", encoding="utf-8")
    assert load_rules(registry) == []
    with pytest.raises(ValueError):
        validate_rules([{"id": "invalid"}])


@pytest.mark.local_model
def test_configured_local_model_readiness():
    from backend.app.core.config import Settings
    settings = Settings()
    if not settings.local_vision_model:
        pytest.skip("No locally installed vision model configured; banking inference remains unvalidated")
    assert OllamaDetector(settings).readiness()["ready"]
