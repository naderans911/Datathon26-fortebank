from .base import UnconfiguredDetector


def build_detector(settings):
    if settings.detector_backend == "ollama":
        from .ollama import OllamaDetector
        return OllamaDetector(settings)
    return UnconfiguredDetector()


create_detector = build_detector
