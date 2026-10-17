"""Human annotations remain separate from immutable organizer labels."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnnotationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    event_type: str = Field(default="", max_length=200)
    observation: str = Field(default="", max_length=4000)
    start_sec: float | None = Field(default=None, ge=0)
    end_sec: float | None = Field(default=None, ge=0)
    candidate_rule_id: str | None = Field(default=None, max_length=200)
    status: Literal["draft", "reviewed"] = "draft"

    @model_validator(mode="after")
    def validate_event(self):
        if self.start_sec is not None and self.end_sec is not None and self.end_sec < self.start_sec:
            raise ValueError("An event end must not precede its start.")
        if self.status == "reviewed" and not self.observation.strip():
            raise ValueError("A reviewed event requires a visible observation.")
        return self


class Annotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(default=0, ge=0)
    status: Literal["draft", "reviewed"] = "draft"
    events: list[AnnotationEvent] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def unique_events(self):
        if len({event.id for event in self.events}) != len(self.events):
            raise ValueError("Event identifiers must be unique.")
        if self.status == "reviewed" and any(event.status != "reviewed" for event in self.events):
            raise ValueError("Review each event before marking the record reviewed.")
        return self
