# 필수 slot 누락 검사 — required는 Knowledge/workflow catalog 근거. 모호표현은 Knowledge 주입만

from __future__ import annotations

from dataclasses import dataclass, field

# Knowledge required_slots / workflow_catalog required_slots_ref 와 동일
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


# 필수 slot·모호표현 검사기 (모호표현은 Knowledge 패턴 주입 시에만)
class AmbiguityAgent:

    # required는 builtin(Catalog), patterns는 Knowledge 로드 시에만
    def __init__(
        self,
        required_slots: dict[str, list[str]] | None = None,
        ambiguity_patterns: list[dict[str, str]] | None = None,
    ) -> None:
        self._required_slots = required_slots or _BUILTIN_REQUIRED_SLOTS
        self._ambiguity_patterns = ambiguity_patterns or []

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

    # Knowledge 주입 패턴으로 지시문 모호 표현 탐지
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
