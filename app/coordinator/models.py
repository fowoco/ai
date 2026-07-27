"""프로토타입용 업무카드 모델.

영속 저장·승인·권한은 server의 WorkItem이 담당한다.
여기서의 TaskCard는 전이 규칙·복합 분리 로직을 로컬에서 검증하기 위한
임시 표현이다. client는 `/api/work-items`만 호출해야 한다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .transitions import TERMINAL_STATUSES, TaskStatus, require_transition


class TaskCardCreate(BaseModel):
    """업무카드 생성 초안. server WorkItem create DTO에 대응한다."""

    workflow_id: str = Field(pattern=r"^WF-[A-Z]{3}-\d{3}$")
    title: str = Field(min_length=1, max_length=200)
    slots: dict[str, Any] = Field(default_factory=dict)
    source_request_id: str | None = None
    worker_id: str | None = None


class TaskCard(BaseModel):
    """비영속 업무카드 스냅샷. 프로세스 재시작 시 사라진다."""

    id: UUID = Field(default_factory=uuid4)
    workflow_id: str
    title: str
    status: TaskStatus = TaskStatus.DRAFT
    slots: dict[str, Any] = Field(default_factory=dict)
    source_request_id: str | None = None
    worker_id: str | None = None
    group_id: UUID | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    history: list[dict[str, Any]] = Field(default_factory=list)

    def transition_to(self, target: TaskStatus, *, reason: str = "") -> None:
        require_transition(self.status, target)
        now = datetime.now(UTC)
        self.history.append(
            {
                "from": self.status.value,
                "to": target.value,
                "reason": reason,
                "at": now.isoformat(),
            }
        )
        self.status = target
        self.updated_at = now

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES
