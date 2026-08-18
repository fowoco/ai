# 업무 카드 상태값과 허용 전이 (지식 카탈로그와 맞춘 코드)

from __future__ import annotations

from enum import StrEnum


# 오케스트레이션이 쓰는 태스크 상태
class TaskStatus(StrEnum):

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

# 서버 task.status 허용값 (IN_PROGRESS 없음 — 응답에 쓰지 않음)
SERVER_PUBLIC_STATUSES: frozenset[str] = frozenset(
    {
        TaskStatus.DRAFT.value,
        TaskStatus.NEEDS_INFO.value,
        TaskStatus.READY_FOR_REVIEW.value,
        TaskStatus.APPROVED.value,
        TaskStatus.WAITING_WORKER.value,
        TaskStatus.WAITING_EXTERNAL.value,
        TaskStatus.COMPLETED.value,
        TaskStatus.CANCELLED.value,
    }
)


# 내부 상태를 서버 task.status로 정규화
def to_public_status(status: str | None) -> str:
    if not status:
        return TaskStatus.DRAFT.value
    if status == TaskStatus.IN_PROGRESS.value:
        return TaskStatus.DRAFT.value
    if status in SERVER_PUBLIC_STATUSES:
        return status
    return TaskStatus.DRAFT.value


ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.DRAFT: frozenset(
        {
            TaskStatus.NEEDS_INFO,
            TaskStatus.READY_FOR_REVIEW,
            TaskStatus.WAITING_WORKER,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.NEEDS_INFO: frozenset(
        {
            TaskStatus.DRAFT,
            TaskStatus.READY_FOR_REVIEW,
            TaskStatus.WAITING_WORKER,
            TaskStatus.IN_PROGRESS,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.READY_FOR_REVIEW: frozenset(
        {TaskStatus.APPROVED, TaskStatus.NEEDS_INFO, TaskStatus.CANCELLED}
    ),
    TaskStatus.APPROVED: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset(
        {
            TaskStatus.WAITING_WORKER,
            TaskStatus.WAITING_EXTERNAL,
            TaskStatus.NEEDS_INFO,
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_WORKER: frozenset(
        {TaskStatus.IN_PROGRESS, TaskStatus.NEEDS_INFO, TaskStatus.COMPLETED, TaskStatus.CANCELLED}
    ),
    TaskStatus.WAITING_EXTERNAL: frozenset(
        {TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.CANCELLED}
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


# 허용되지 않는 상태 전이
class TransitionError(Exception):

    # 현재·목표 상태 기록
    def __init__(self, current: TaskStatus, target: TaskStatus) -> None:
        super().__init__(f"Cannot transition from {current.value} to {target.value}")
        self.current = current
        self.target = target


# 전이가 허용되면 True
def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


# 불허 전이면 TransitionError 발생
def require_transition(current: TaskStatus, target: TaskStatus) -> None:
    if not can_transition(current, target):
        raise TransitionError(current, target)
