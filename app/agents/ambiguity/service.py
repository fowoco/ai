# 필수 slot 누락과 모호 표현을 규칙으로 검사하는 Ambiguity 에이전트

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


# 내장 모호표현 한 줄을 패턴 dict로 생성
# 내장 모호표현 패턴 한 줄 생성
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
# 매칭된 모호 표현 한 건
class AmbiguityMatch:

    pattern_id: str
    category: str
    matched_term: str
    question: str


@dataclass
# 누락 slot과 모호 표현 검사 결과
class AmbiguityResult:

    missing_slots: list[str] = field(default_factory=list)
    ambiguities: list[AmbiguityMatch] = field(default_factory=list)

    @property
    # 누락 또는 모호 표현이 있으면 True
    def has_issues(self) -> bool:
        return bool(self.missing_slots or self.ambiguities)


# 필수 slot·모호표현 규칙 검사기 (Knowledge 또는 builtin)
class AmbiguityAgent:

    # 규칙 테이블 주입 미주입 시 builtin
    def __init__(
        self,
        required_slots: dict[str, list[str]] | None = None,
        ambiguity_patterns: list[dict[str, str]] | None = None,
    ) -> None:
        self._required_slots = required_slots or _BUILTIN_REQUIRED_SLOTS
        self._ambiguity_patterns = ambiguity_patterns or _BUILTIN_AMBIGUITY_PATTERNS

    # 워크플로 기준으로 누락 slot과 모호 표현 검사
    def check(
        self,
        workflow_id: str,
        extracted_slots: dict[str, str],
        instruction: str,
    ) -> AmbiguityResult:
        missing = self._find_missing_slots(workflow_id, extracted_slots)
        ambiguities = self._find_ambiguities(instruction)
        return AmbiguityResult(missing_slots=missing, ambiguities=ambiguities)

    # 필수 slot 중 비어 있는 키 목록 반환
    def _find_missing_slots(
        self, workflow_id: str, extracted_slots: dict[str, str]
    ) -> list[str]:
        required = self._required_slots.get(workflow_id, [])
        return [s for s in required if s not in extracted_slots]

    # 지시문 모호 표현 탐지
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
