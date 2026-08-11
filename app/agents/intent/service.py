# Intent·Slot — HF 하이브리드 또는 EXPIRY_RENEWAL 고정. WF는 Knowledge catalog 근거

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

# Knowledge workflow_catalog.yaml: intent → workflow id (동일 intent면 catalog 등장 순)
INTENT_TO_WORKFLOWS: dict[str, list[str]] = {
    "WORKER_ONBOARDING": ["WF-WRK-001"],
    "EXPIRY_RENEWAL": ["WF-STY-001", "WF-CON-001"],
    "DOCUMENT_REQUEST": ["WF-DOC-001", "WF-ADM-001"],
    "PAYROLL_EXPLANATION": ["WF-PAY-001"],
    "WORK_INSTRUCTION": ["WF-INS-001"],
    "EMPLOYMENT_CHANGE": ["WF-CHG-001"],
}

_WF_ID_PATTERN = re.compile(r"^WF-[A-Z]{3}-\d{3}$")


# Intent형·WF형 constraint를 WF catalog id 목록으로 정규화
def expand_workflow_constraints(constraints: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for item in constraints:
        targets = INTENT_TO_WORKFLOWS.get(item, [item])
        for workflow_id in targets:
            if workflow_id not in seen:
                seen.add(workflow_id)
                expanded.append(workflow_id)
    return expanded


# WF-XXX-000 형태인지 확인
def is_workflow_catalog_id(value: str) -> bool:
    return bool(_WF_ID_PATTERN.match(value))


# 요청 constraint에 맞춰 응답에 실을 workflowId 결정
def public_workflow_id(
    *,
    internal_workflow_id: str,
    intent: str,
    constraints: list[str],
) -> str:
    if not constraints:
        return internal_workflow_id
    if intent in constraints:
        return intent
    if internal_workflow_id in constraints:
        return internal_workflow_id
    for constraint in constraints:
        mapped = INTENT_TO_WORKFLOWS.get(constraint, [])
        if internal_workflow_id in mapped:
            return constraint
    return internal_workflow_id


# 의도 후보 WF에 constraint 적용 (다후보는 catalog 순 첫 id)
def resolve_workflow_id(
    intent: str,
    workflow_constraints: list[str] | None,
) -> str:
    candidate_workflows = list(INTENT_TO_WORKFLOWS.get(intent, []))
    if workflow_constraints:
        expanded = set(expand_workflow_constraints(workflow_constraints))
        constrained = [w for w in candidate_workflows if w in expanded]
        if constrained:
            candidate_workflows = constrained
        elif intent not in workflow_constraints and not any(
            is_workflow_catalog_id(c) for c in workflow_constraints
        ):
            candidate_workflows = []
    return candidate_workflows[0] if candidate_workflows else ""


@dataclass
# Intent 분류와 Slot 추출 결과
class IntentResult:

    intent: str
    confidence: float | None
    workflow_id: str
    model_provider: str
    model_name: str
    model_version: str
    extracted_slots: dict[str, str] = field(default_factory=dict)
    prompt_version: str = "not-applicable"
    confidence_source: str = "UNAVAILABLE"
    bert_routing_score: float | None = None
    evidence: str | None = None


# 교체 가능한 Intent 분류기 계약
class IntentClassifier(Protocol):

    # 모델 초기화·A.X 가용성 진단 (조회 시 lazy load 금지)
    def runtime_status(self) -> dict[str, object]: ...

    # 지시문 Intent 분류·관련 Slot 추출
    def classify(
        self,
        instruction: str,
        *,
        workflow_constraints: list[str] | None = None,
    ) -> IntentResult: ...


# 재갱신 Intent 고정 — 슬롯은 Server worker 시드에 맡김 (발화 정규식 추출 없음)
class FixedExpiryRenewalIntentAgent:

    # 운영 상태 — 모델 기능이 꺼진 고정 규칙 모드
    def runtime_status(self) -> dict[str, object]:
        return {
            "intentModelEnabled": False,
            "axEnabled": False,
            "initialized": True,
            "bertAvailable": False,
            "axAvailable": False,
            "degraded": False,
            "promptVersion": "not-applicable",
        }

    # 항상 EXPIRY_RENEWAL로 두고 workflowId만 채움
    def classify(
        self,
        instruction: str,
        *,
        workflow_constraints: list[str] | None = None,
    ) -> IntentResult:
        del instruction
        intent = "EXPIRY_RENEWAL"
        return IntentResult(
            intent=intent,
            confidence=1.0,
            workflow_id=resolve_workflow_id(intent, workflow_constraints),
            model_provider="internal",
            model_name="fixed-expiry-renewal",
            model_version="rules",
            extracted_slots={},
            confidence_source="MODEL",
        )


# 멀티라벨 예측에서 대표 Intent·confidence 선택
def _primary_intent(
    intents: list[str], scores: dict[str, float]
) -> tuple[str, float]:
    if not intents:
        return "OUT_OF_SCOPE", 0.0
    if "OUT_OF_SCOPE" in intents and len(intents) == 1:
        return "OUT_OF_SCOPE", float(scores.get("OUT_OF_SCOPE") or 0.5)
    ranked = [i for i in intents if i != "OUT_OF_SCOPE"]
    if not ranked:
        return "OUT_OF_SCOPE", float(scores.get("OUT_OF_SCOPE") or 0.5)
    if scores:
        best = max(ranked, key=lambda name: float(scores.get(name) or 0.0))
        return best, float(scores.get(best) or 0.0)
    return ranked[0], 0.85


# HF BERT(+선택 A.X) 하이브리드 → IntentClassifier
class HybridHfIntentAgent:

    # 파이프라인은 첫 classify 때 lazy 로드
    def __init__(self, pipeline: object | None = None) -> None:
        self._pipeline = pipeline
        self._load_error: str | None = None

    # 설정 기반 HybridIntentPipeline 확보
    def _ensure_pipeline(self) -> object | None:
        if self._pipeline is not None:
            return self._pipeline
        if self._load_error is not None:
            return None
        try:
            import os

            from app.core.config import get_settings

            from .hybrid import HybridIntentPipeline

            settings = get_settings()
            token = settings.hf_token or os.environ.get("HF_TOKEN")
            self._pipeline = HybridIntentPipeline(
                bert_model_dir=settings.intent_bert_model_dir,
                bert_model_revision=settings.intent_bert_model_revision,
                device=settings.intent_device,
                label_prob_threshold=settings.intent_label_prob_threshold,
                margin_threshold=settings.intent_margin_threshold,
                max_trained_labels=settings.intent_max_trained_labels,
                hf_token=token,
                enable_ax=settings.intent_enable_ax,
                ax_base_model_name=settings.intent_ax_base_model,
                ax_base_revision=settings.intent_ax_base_revision,
                ax_adapter_path=settings.intent_ax_adapter_path,
                ax_adapter_revision=settings.intent_ax_adapter_revision,
                ax_max_new_tokens=settings.intent_ax_max_new_tokens,
            )
        except Exception as exc:
            self._load_error = str(exc)
            logger.exception("HF Intent pipeline load failed — fixed EXPIRY fallback")
            return None
        return self._pipeline

    # lazy-load 상태를 바꾸지 않고 readiness 진단값을 반환
    def runtime_status(self) -> dict[str, object]:
        from app.core.config import get_settings

        from .prompts import AX_INTENT_PROMPT_VERSION

        settings = get_settings()
        pipeline = self._pipeline
        initialized = pipeline is not None
        ax_enabled = bool(
            getattr(pipeline, "ax_enabled", settings.intent_enable_ax)
            if initialized
            else settings.intent_enable_ax
        )
        bert_available = initialized and getattr(pipeline, "bert", None) is not None
        ax_available = initialized and getattr(pipeline, "ax", None) is not None
        return {
            "intentModelEnabled": True,
            "axEnabled": ax_enabled,
            "initialized": initialized,
            "bertAvailable": bert_available,
            "axAvailable": ax_available,
            "degraded": self._load_error is not None
            or (initialized and ax_enabled and not ax_available),
            "promptVersion": (
                AX_INTENT_PROMPT_VERSION
                if ax_enabled
                else "not-applicable"
            ),
        }

    # HF 분류 결과를 IntentResult로 변환
    def classify(
        self,
        instruction: str,
        *,
        workflow_constraints: list[str] | None = None,
    ) -> IntentResult:
        pipeline = self._ensure_pipeline()
        if pipeline is None:
            result = FixedExpiryRenewalIntentAgent().classify(
                instruction, workflow_constraints=workflow_constraints
            )
            result.model_version = "fallback"
            return result
        prediction = pipeline.predict(instruction)  # type: ignore[attr-defined]
        primary_intent, _ = _primary_intent(
            prediction.intents, prediction.scores
        )
        is_ax = prediction.selected_model == "AX"
        # MVP는 대표 Intent 한 개만 공개한다. A.X는 원문 등장 순서의 첫 항목을 사용한다.
        representative = (
            prediction.intents[0]
            if is_ax and prediction.intents
            else primary_intent
        )
        bert_score = prediction.scores.get(representative)
        from app.core.config import get_settings

        settings = get_settings()
        model_name = (
            settings.intent_ax_base_model
            if prediction.selected_model == "AX"
            else settings.intent_bert_model_dir
        )
        return IntentResult(
            intent=representative,
            confidence=None if is_ax else float(bert_score or 0.0),
            workflow_id=resolve_workflow_id(representative, workflow_constraints),
            extracted_slots={},
            model_provider="huggingface",
            model_name=model_name,
            model_version=prediction.selected_model,
            prompt_version=prediction.prompt_version,
            confidence_source="UNAVAILABLE" if is_ax else "BERT",
            bert_routing_score=(float(bert_score) if bert_score is not None else None),
            evidence=(prediction.evidence or {}).get(representative),
        )


# 설정에 따라 HF 하이브리드 또는 재갱신 고정 분류기 생성
def build_intent_agent() -> IntentClassifier:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.intent_model_enabled:
        return HybridHfIntentAgent()
    return FixedExpiryRenewalIntentAgent()
