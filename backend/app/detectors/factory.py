from .base import UnconfiguredDetector


def build_detector(settings):
    if settings.detector_backend == "ollama":
        from .ollama import OllamaDetector
        return OllamaDetector(settings)
    if settings.detector_backend == "cv":
        from .cv import CVDetector
        return CVDetector(settings)
    return UnconfiguredDetector()


create_detector = build_detector
