from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

REPOSITORY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}$"


def normalize_repository(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(REPOSITORY_PATTERN, value) or value.split("/")[1] in {".", ".."}:
        raise ValueError("Repository must use the owner/name format.")
    return value


class AnalysisRequest(BaseModel):
    repository: str = Field(max_length=140, examples=["fastapi/fastapi"])

    @field_validator("repository")
    @classmethod
    def normalize_repository(cls, value: str) -> str:
        return normalize_repository(value)


class ActionItemRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=200)
    title: str = Field(min_length=3, max_length=240)
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")

    _repository = field_validator("repository")(normalize_repository)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("Title must contain at least three non-whitespace characters.")
        return value.strip()
