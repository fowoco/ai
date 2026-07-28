"""Ambiguity Agent — 필수 slot 누락 감지 + 모호표현 사전 매칭.

Knowledge 패키지의 required_slots와 ambiguity_patterns를 사용한다.
Knowledge가 설치되어 있지 않으면 내장 규칙으로 폴백한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_BUILTIN_REQUIRED_SLOTS: dict[str, list[str]] = {
    "WF-WRK-001": ["worker_id"],
    "WF-STY-001": ["worker_id", "stay_expiry_date"],
    "WF-CON-001": ["worker_id", "contract_end_date"],
    "WF-DOC-001": ["worker_id", "document_type"],
    "WF-PAY-001": ["worker_id", "pay_period"],
    "WF-INS-001": ["worker_id"],
    "WF-CHG-001": ["worker_id", "change_type"],
    "WF-ADM-001": ["worker_id", "document_type"],
}

def _p(pid: str, cat: str, term: str, q: str) -> dict[str, str]:
    return {"pattern_id": pid, "category": cat, "term": term, "question": q}


_Q_DATE = "정확한 날짜를 알려주세요."
_Q_WHAT = "구체적으로 어떤 것을 말씀하시나요?"

_BUILTIN_AMBIGUITY_PATTERNS: list[dict[str, str]] = [
    _p("AMB-TIME-01", "TIME", "조만간", _Q_DATE),
    _p("AMB-TIME-02", "TIME", "나중에", _Q_DATE),
    _p("AMB-TIME-03", "TIME", "곧", _Q_DATE),
    _p("AMB-OBJ-01", "OBJECT", "그거", _Q_WHAT),
    _p("AMB-OBJ-02", "OBJECT", "저거", _Q_WHAT),
    _p("AMB-AMT-01", "AMOUNT", "좀", "정확한 수량이나 금액을 알려주세요."),
    _p("AMB-ACT-01", "ACTION", "처리", "어떤 작업을 원하시는지 구체적으로 말씀해주세요."),
]


@dataclass
class AmbiguityMatch:
    pattern_id: str
    category: str
    matched_term: str
    question: str


@dataclass
class AmbiguityResult:
    missing_slots: list[str] = field(default_factory=list)
    ambiguities: list[AmbiguityMatch] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.missing_slots or self.ambiguities)


class AmbiguityAgent:
    """규칙 기반 모호성 검출기."""

    def __init__(
        self,
        required_slots: dict[str, list[str]] | None = None,
        ambiguity_patterns: list[dict[str, str]] | None = None,
    ) -> None:
        self._required_slots = required_slots or _BUILTIN_REQUIRED_SLOTS
        self._ambiguity_patterns = ambiguity_patterns or _BUILTIN_AMBIGUITY_PATTERNS

    def check(
        self,
        workflow_id: str,
        extracted_slots: dict[str, str],
        instruction: str,
    ) -> AmbiguityResult:
        missing = self._find_missing_slots(workflow_id, extracted_slots)
        ambiguities = self._find_ambiguities(instruction)
        return AmbiguityResult(missing_slots=missing, ambiguities=ambiguities)

    def _find_missing_slots(
        self, workflow_id: str, extracted_slots: dict[str, str]
    ) -> list[str]:
        required = self._required_slots.get(workflow_id, [])
        return [s for s in required if s not in extracted_slots]

    def _find_ambiguities(self, instruction: str) -> list[AmbiguityMatch]:
        matches: list[AmbiguityMatch] = []
        for pattern in self._ambiguity_patterns:
            if pattern["term"] in instruction:
                matches.append(
                    AmbiguityMatch(
                        pattern_id=pattern["pattern_id"],
                        category=pattern["category"],
                        matched_term=pattern["term"],
                        question=pattern["question"],
                    )
                )
        return matches
