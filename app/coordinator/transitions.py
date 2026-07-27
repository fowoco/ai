"""업무카드 상태 전이 계약.

knowledge `workflow_catalog.yaml` policy.state_model과 동일하다.

이 모듈은 LLM 없이 코드로만 전이를 검증한다. 영속 WorkItem(업무카드)의
소유권은 `fowoco-server`에 있다. AI는 전이 가능 여부 검증·추천에만 쓰고,
server가 엔티티를 구현할 때 이 규칙을 그대로 이식한다.

client 공개 경로 `/api/work-items`와는 별개이며, 이 모듈은 공개 REST가 아니다.
"""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    """knowledge 9상태. server WorkItem.status와 동일하게 맞출 것."""

    DRAFT = "DRAFT"
    NEEDS_INFO = "NEEDS_INFO"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_WORKER = "WAITING_WORKER"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
)

ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.DRAFT: frozenset(
        {TaskStatus.NEEDS_INFO, TaskStatus.READY_FOR_REVIEW, TaskStatus.CANCELLED}
    ),
    TaskStatus.NEEDS_INFO: frozenset(
        {TaskStatus.DRAFT, TaskStatus.READY_FOR_REVIEW, TaskStatus.CANCELLED}
    ),
    TaskStatus.READY_FOR_REVIEW: frozenset(
        {TaskStatus.APPROVED, TaskStatus.NEEDS_INFO, TaskStatus.CANCELLED}
    ),
    TaskStatus.APPROVED: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset(
        {
            TaskStatus.WAITING_WORKER,
            TaskStatus.WAITING_EXTERNAL,
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_WORKER: frozenset(
        {TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.CANCELLED}
    ),
    TaskStatus.WAITING_EXTERNAL: frozenset(
        {TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.CANCELLED}
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


class TransitionError(Exception):
    """허용되지 않는 상태 전이."""

    def __init__(self, current: TaskStatus, target: TaskStatus) -> None:
        super().__init__(f"Cannot transition from {current.value} to {target.value}")
        self.current = current
        self.target = target


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def allowed_targets(current: TaskStatus) -> list[TaskStatus]:
    return sorted(ALLOWED_TRANSITIONS.get(current, frozenset()), key=lambda s: s.value)


def require_transition(current: TaskStatus, target: TaskStatus) -> None:
    if not can_transition(current, target):
        raise TransitionError(current, target)


def is_terminal(status: TaskStatus) -> bool:
    return status in TERMINAL_STATUSES
