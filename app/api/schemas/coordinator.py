"""Coordinator Internal API schemas (프로토타입).

client 공개 계약이 아니다. server WorkItem DTO 설계 참고용이다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.coordinator.transitions import TaskStatus


class TaskCardCreateRequest(BaseModel):
    workflow_id: str = Field(pattern=r"^WF-[A-Z]{3}-\d{3}$")
    title: str = Field(min_length=1, max_length=200)
    slots: dict[str, Any] = Field(default_factory=dict)
    source_request_id: str | None = None
    worker_id: str | None = None


class CompositeCreateRequest(BaseModel):
    cards: list[TaskCardCreateRequest] = Field(min_length=2)
    source_request_id: str | None = None


class TransitionRequest(BaseModel):
    target: TaskStatus
    reason: str = ""


class ValidateTransitionRequest(BaseModel):
    current: TaskStatus
    target: TaskStatus


class ValidateTransitionResponse(BaseModel):
    current: TaskStatus
    target: TaskStatus
    allowed: bool
    allowed_targets: list[TaskStatus]


class TaskCardResponse(BaseModel):
    id: UUID
    workflow_id: str
    title: str
    status: TaskStatus
    slots: dict[str, Any]
    source_request_id: str | None
    worker_id: str | None
    group_id: UUID | None
    evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    history: list[dict[str, Any]]


class AllowedTransitionsResponse(BaseModel):
    card_id: UUID
    current: TaskStatus
    allowed: list[TaskStatus]
