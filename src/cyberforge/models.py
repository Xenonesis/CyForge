from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LabState(StrEnum):
    IDLE = "idle"
    DEPLOYING = "deploying"
    ACTIVE = "active"
    RESETTING = "resetting"
    FAILED = "failed"
    TERMINATED = "terminated"


class ChallengeDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=3)
    name: str = Field(min_length=3)
    description: str = Field(min_length=3)
    tactic: str = Field(min_length=2)
    technique: dict[str, str]
    platforms: dict[str, dict[str, dict[str, str]]]


class LabSession(BaseModel):
    id: str
    user_id: str
    challenge_id: str
    state: LabState = LabState.IDLE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    connection: dict[str, Any] = Field(default_factory=dict)
    last_error: str | None = None


class AuditEvent(BaseModel):
    id: str
    action: str
    status: str
    lab_id: str | None = None
    user_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditQuery(BaseModel):
    action: str | None = None
    status: str | None = None
    user_id: str | None = None
    lab_id: str | None = None
    request_id: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class AuditEventPage(BaseModel):
    items: list[AuditEvent] = Field(default_factory=list)
    total: int = 0
    limit: int
    offset: int


class DeployLabRequest(BaseModel):
    user_id: str = Field(min_length=1)
    challenge_id: str = Field(min_length=1)


class ValidateChallengeRequest(BaseModel):
    payload: dict[str, Any]


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
