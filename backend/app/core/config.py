"""Validated configuration. Environment variables never enter browser responses."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False, hide_input_in_errors=True)

    app_env: Literal["development", "test", "production"] = "development"
    jury_api_key: str = Field(default="", repr=False)
    detector_backend: Literal["unconfigured", "ollama", "cv"] = "unconfigured"
    cv_model_dir: Path = Path("./models")
    cv_device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    cv_threshold: float | None = Field(None, gt=0, lt=1)
    ollama_base_url: str = "http://127.0.0.1:11434"
    local_vision_model: str = ""
    allowed_ollama_hosts: list[str] = Field(default_factory=list)
    ollama_timeout_seconds: float = Field(60, gt=0, le=240)
    enable_demo: bool = False
    max_upload_mb: int = Field(100, ge=1, le=2048)
    max_video_seconds: float = Field(300, gt=0, le=3600)
    job_deadline_seconds: float = Field(285, gt=0, le=285)
    worker_concurrency: int = Field(1, ge=1, le=4)
    max_queue_size: int = Field(8, ge=1, le=100)
    max_storage_mb: int = Field(2048, ge=1)
    max_job_output_mb: int = Field(256, ge=1)
    upload_rate_per_hour: int = Field(12, ge=1)
    storage_dir: Path = Path("./storage")
    rules_file: Path = Path("./config/rules.json")
    frontend_dist: Path = Path("./frontend/dist")
    retention_hours: float | None = Field(None, gt=0)
    session_hours: int = Field(24, ge=1, le=720)
    secure_cookies: bool = False
    public_origin: str = ""
    worker_heartbeat_seconds: float = Field(15, ge=3, le=120)
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    sampling_fps: float = Field(0.25, gt=0, le=5)
    window_seconds: float = Field(16, ge=1, le=120)
    max_sample_frames: int = Field(80, ge=2, le=1000)
    max_events: int = Field(24, ge=1, le=100)
    max_evidence_bytes: int = Field(12 * 1024 * 1024, ge=1024)
    sample_width: int = Field(640, ge=160, le=1920)

    @field_validator("retention_hours", mode="before")
    @classmethod
    def empty_retention(cls, value):
        return None if value == "" else value

    @field_validator("storage_dir", "rules_file", "frontend_dist", "cv_model_dir")
    @classmethod
    def absolute_paths(cls, value: Path) -> Path:
        return value.resolve()

    @model_validator(mode="after")
    def deployment_requirements(self):
        if self.public_origin:
            origin = urlsplit(self.public_origin)
            if (origin.scheme not in {"http", "https"} or not origin.hostname or origin.username
                    or origin.password or origin.query or origin.fragment or origin.path not in {"", "/"}):
                raise ValueError("PUBLIC_ORIGIN must be a plain HTTP(S) origin without credentials or a path.")
        if self.app_env == "production":
            if self.retention_hours is None:
                raise ValueError("Production requires an explicit RETENTION_HOURS policy.")
            if not self.secure_cookies or not self.public_origin.startswith("https://"):
                raise ValueError("Production requires SECURE_COOKIES=true and an HTTPS PUBLIC_ORIGIN.")
            if len(self.jury_api_key) < 32:
                raise ValueError("Production requires a generated JURY_API_KEY of at least 32 characters.")
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def database_path(self) -> Path:
        return self.storage_dir / "jobs.sqlite3"
