"""Validated, locally snapshotted rule registry. No runtime source research."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=160)
    jurisdiction: str = Field(min_length=1, max_length=100)
    source_type: Literal["regulation", "internal_procedure", "other_bank_public_document", "synthetic"]
    document_title: str = Field(min_length=1, max_length=300)
    source_url: str | None = Field(default=None, max_length=2000)
    section_or_paragraph: str | None = Field(default=None, max_length=200)
    relevant_excerpt: str = Field(min_length=1, max_length=6000)
    observed_condition: str = Field(min_length=1, max_length=2000)
    required_context: list[str] = Field(max_length=20)
    interpretation: str = Field(min_length=1, max_length=3000)
    limitations: list[str] = Field(max_length=20)
    verification_status: Literal["draft", "verified", "disabled"]
    verified_at: str | None = None
    enabled: bool
    version: str = Field(min_length=1, max_length=80)

    @field_validator("source_url")
    @classmethod
    def safe_source_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Source links must be ordinary HTTP(S) links without credentials")
        return value

    @field_validator("required_context", "limitations")
    @classmethod
    def bounded_text_list(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 2000 for value in values):
            raise ValueError("Context and limitations must contain bounded nonempty text")
        return values

    @model_validator(mode="after")
    def verified_source(self) -> "Rule":
        if self.verification_status == "verified":
            if not self.verified_at:
                raise ValueError("Verified rules require a recorded verification date")
            try:
                datetime.fromisoformat(self.verified_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("verified_at must be ISO 8601") from exc
            if self.source_type == "regulation" and not re.search(r"kazakhstan|казахстан", self.jurisdiction, re.I):
                raise ValueError("Regulatory grounding must explicitly identify Kazakhstan")
        return self


def validate_rules(values: list[dict], *, allow_synthetic: bool = False) -> list[dict]:
    if not isinstance(values, list) or len(values) > 200:
        raise ValueError("Rule registry must be an array with at most 200 rules")
    rules = [Rule.model_validate(item).model_dump(mode="json") for item in values]
    if len({rule["id"] for rule in rules}) != len(rules):
        raise ValueError("Rule IDs must be unique")
    if not allow_synthetic and any(rule["source_type"] == "synthetic" for rule in rules):
        raise ValueError("Synthetic rules are forbidden in the production registry")
    return rules


def load_rules(path: str | Path) -> list[dict]:
    registry = Path(path)
    if registry.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Rule registry exceeds 2 MiB")
    return validate_rules(json.loads(registry.read_text(encoding="utf-8")))


def active_rules(rules: list[dict]) -> list[dict]:
    return [rule for rule in rules if rule["enabled"] and rule["verification_status"] == "verified"
            and rule["source_type"] != "synthetic"]
