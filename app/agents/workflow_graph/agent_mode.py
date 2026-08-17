from enum import StrEnum


class AgentExecutionMode(StrEnum):
    """Renewal Graph의 실제 실행 방식을 선택한다."""

    LEGACY = "LEGACY"
    SHADOW = "SHADOW"
