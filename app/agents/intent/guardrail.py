# BERT 예측을 A.X로 넘길지 결정하는 라우팅 규칙

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
# 가드레일 라우팅 결과
class RoutingResult:

    should_route: bool
    reason: str
    category: str


@dataclass
# HR Intent BERT→A.X 라우팅 가드레일
class HRRoutingGuardrail:

    margin_threshold: float = 0.76
    max_trained_labels: int = 3
    label_prob_threshold: float = 0.55
    status_kw: list[str] = field(
        default_factory=lambda: ["없음", "완료", "이상없", "특이사항", "특이문의"]
    )
    action_kw: list[str] = field(default_factory=lambda: ["배치", "라인", "지시"])
    doc_kw: list[str] = field(
        default_factory=lambda: ["신청서", "서류", "챙겨", "접수", "명단확인"]
    )

    @staticmethod
    # 공백 제거 정규화
    def _normalize(text: str) -> str:
        return text.replace(" ", "")

    # A.X 호출 여부·사유 판정
    def should_route_to_ax(
        self, hr_input: str, probs: dict[str, float], margin: float
    ) -> RoutingResult:
        clean_input = self._normalize(hr_input)
        activated_count = sum(1 for p in probs.values() if p >= self.label_prob_threshold)
        if activated_count >= self.max_trained_labels:
            return RoutingResult(
                should_route=True,
                reason=f"활성 label {activated_count}개 (학습 최댓값 {self.max_trained_labels}개 이상)",
                category="OOD_Label_Count",
            )
        if any(kw in clean_input for kw in self.status_kw):
            return RoutingResult(
                should_route=True, reason="완료/상태 보고 키워드 감지", category="Rule_Status"
            )
        action_matches = sum(1 for kw in self.action_kw if kw in clean_input)
        if action_matches >= 2:
            return RoutingResult(
                should_route=True,
                reason=f"배치/라인/지시 키워드 {action_matches}개 감지",
                category="Rule_Action",
            )
        if "급여계좌" in clean_input or ("급여" in clean_input and "확인" in clean_input):
            return RoutingResult(
                should_route=True, reason="급여계좌 관련 경계 키워드 감지", category="Rule_Salary"
            )
        if any(kw in clean_input for kw in self.doc_kw):
            return RoutingResult(
                should_route=True, reason="서류 확보 키워드 감지", category="Rule_Document"
            )
        if margin < self.margin_threshold:
            return RoutingResult(
                should_route=True,
                reason=f"margin {margin:.3f} < {self.margin_threshold}",
                category="Low_Margin",
            )
        return RoutingResult(
            should_route=False, reason="BERT 신뢰 구간 통과", category="Pass_BERT"
        )
