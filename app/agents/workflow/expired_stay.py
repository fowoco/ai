"""체류기간 경과 예외를 법적 결론 없이 HR 확인 흐름으로 변환한다."""

from __future__ import annotations

from dataclasses import dataclass

EXPIRED_STAY_VARIANT = "EXPIRED_STAY_EXCEPTION"
EXPIRED_STAY_WORKFLOW_ID = "WF-STY-EXC-001"
EMPLOYMENT_CHANGE_WORKFLOW_ID = "WF-CHG-001"

_SUPPORTED_STATUSES = {
    "APPROVED",
    "APPLICATION_PENDING",
    "UNKNOWN",
    "NOT_APPLIED",
    "EMPLOYMENT_ENDED",
}


@dataclass(frozen=True)
class ExpiredStayDecision:
    next_action: str
    questions: list[dict[str, str]]
    suggested_workflow_ids: list[str]
    case_signals: list[str]


def decide_expired_stay_exception(status: str | None) -> ExpiredStayDecision:
    """Server가 확인한 상태만 사용하고 AI가 체류·고용 상태를 추론하지 않는다."""
    normalized = status.strip().upper() if status else "UNKNOWN"
    if normalized not in _SUPPORTED_STATUSES:
        normalized = "UNKNOWN"

    if normalized == "APPROVED":
        return ExpiredStayDecision(
            next_action="REVIEW_UPDATED_EXPIRY_DATE",
            questions=[
                {
                    "key": "new_stay_expiry_date",
                    "prompt": "승인 결과 증빙의 새 체류만료일을 확인해 주세요.",
                }
            ],
            suggested_workflow_ids=[],
            case_signals=["REVIEW_STAY_APPROVAL_EVIDENCE"],
        )
    if normalized == "APPLICATION_PENDING":
        return ExpiredStayDecision(
            next_action="TRACK_APPLICATION_RESULT",
            questions=[
                {
                    "key": "next_review_at",
                    "prompt": "접수증을 확인하고 다음 확인 예정일을 지정해 주세요.",
                }
            ],
            suggested_workflow_ids=[],
            case_signals=["WAIT_FOR_EXTERNAL_STAY_RESULT"],
        )
    if normalized == "NOT_APPLIED":
        return ExpiredStayDecision(
            next_action="REQUEST_HR_STATUS_CONFIRMATION",
            questions=[
                {
                    "key": "stay_verification_evidence",
                    "prompt": "신청 여부와 현재 고용 상태를 증빙과 함께 확인해 주세요.",
                }
            ],
            suggested_workflow_ids=[],
            case_signals=["REVIEW_STAY_EXCEPTION"],
        )
    if normalized == "EMPLOYMENT_ENDED":
        return ExpiredStayDecision(
            next_action="REVIEW_EMPLOYMENT_CHANGE",
            questions=[
                {
                    "key": "employment_end_evidence",
                    "prompt": "HR이 확인한 고용 종료 근거와 처리일을 검토해 주세요.",
                }
            ],
            suggested_workflow_ids=[EMPLOYMENT_CHANGE_WORKFLOW_ID],
            case_signals=["SUGGEST_EMPLOYMENT_CHANGE_REVIEW"],
        )
    return ExpiredStayDecision(
        next_action="REQUEST_HR_STATUS_CONFIRMATION",
        questions=[
            {
                "key": "stay_verification_status",
                "prompt": "연장 승인·신청 중·미신청·고용 종료 중 현재 확인된 상태를 선택해 주세요.",
            }
        ],
        suggested_workflow_ids=[],
        case_signals=["REVIEW_STAY_EXCEPTION"],
    )
