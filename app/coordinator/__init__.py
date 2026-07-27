"""Coordinator — 전이 규칙 계약과 오케스트레이션 프로토타입.

영속 WorkItem API는 fowoco-server 소유다. 이 패키지는 knowledge 상태머신과
복합 요청 분리를 검증·제안하는 AI 쪽 로직이다.
"""

from .models import TaskCard, TaskCardCreate
from .service import CoordinatorService
from .transitions import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    TaskStatus,
    TransitionError,
    allowed_targets,
    can_transition,
    require_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "CoordinatorService",
    "TaskCard",
    "TaskCardCreate",
    "TaskStatus",
    "TransitionError",
    "allowed_targets",
    "can_transition",
    "require_transition",
]
