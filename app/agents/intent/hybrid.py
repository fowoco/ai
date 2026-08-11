# BERT + 가드레일 + (선택) A.X 하이브리드 Intent 추론

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .guardrail import HRRoutingGuardrail
from .models_hf import AxIntentModel, BertIntentModel

logger = logging.getLogger(__name__)


@dataclass
# 하이브리드 분류 한 건의 정규화 결과
class HybridIntentPrediction:

    intents: list[str]
    scores: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, str | None] = field(default_factory=dict)
    selected_model: str = "BERT"
    degraded: bool = False
    prompt_version: str = "not-applicable"


# BERT 우선·필요 시 A.X 보조 파이프라인
class HybridIntentPipeline:

    # 설정값으로 BERT·가드레일·선택적 A.X 구성
    def __init__(
        self,
        *,
        bert_model_dir: str,
        bert_model_revision: str | None = None,
        device: str = "cpu",
        label_prob_threshold: float = 0.55,
        margin_threshold: float = 0.76,
        max_trained_labels: int = 3,
        hf_token: str | None = None,
        enable_ax: bool = False,
        ax_base_model_name: str = "skt/A.X-4.0-Light",
        ax_base_revision: str | None = None,
        ax_adapter_path: str = "fowoco/ax-intent-qlora",
        ax_adapter_revision: str | None = None,
        ax_max_new_tokens: int = 96,
    ) -> None:
        self.bert = BertIntentModel(
            model_dir=bert_model_dir,
            device=device,
            label_prob_threshold=label_prob_threshold,
            hf_token=hf_token,
            revision=bert_model_revision,
        )
        self.guardrail = HRRoutingGuardrail(
            margin_threshold=margin_threshold,
            max_trained_labels=max_trained_labels,
            label_prob_threshold=label_prob_threshold,
        )
        self.ax: AxIntentModel | None = None
        self.ax_enabled = enable_ax
        if enable_ax:
            try:
                self.ax = AxIntentModel(
                    base_model_name=ax_base_model_name,
                    adapter_path=ax_adapter_path,
                    device=self.bert.device,
                    max_new_tokens=ax_max_new_tokens,
                    hf_token=hf_token,
                    base_revision=ax_base_revision,
                    adapter_revision=ax_adapter_revision,
                )
            except Exception:
                logger.exception("A.X load failed — BERT-only degraded mode")

    # readiness 전에 각 활성 모델의 첫 forward/generate를 완료한다.
    def warmup(self) -> None:
        self.bert.predict("체류기간 연장 준비해줘")
        if not self.ax_enabled:
            return
        if self.ax is None:
            raise RuntimeError("A.X is enabled but unavailable")
        self.ax.predict("여권 사본을 요청해줘")

    # instruction → 정규화 Intent 예측
    def predict(self, instruction: str) -> HybridIntentPrediction:
        probs, margin, bert_intents = self.bert.predict(instruction)
        route = self.guardrail.should_route_to_ax(instruction, probs, margin)
        if route.should_route and self.ax is not None:
            try:
                ax_items = self.ax.predict(instruction)
                intents = [str(i.get("intent")) for i in ax_items if i.get("intent")]
                evidence = {
                    str(i.get("intent")): i.get("evidence")
                    for i in ax_items
                    if i.get("intent")
                }
                return HybridIntentPrediction(
                    intents=intents or bert_intents,
                    scores=probs,
                    evidence=evidence,
                    selected_model="AX",
                    degraded=False,
                    prompt_version=self.ax.prompt_version,
                )
            except Exception:
                logger.exception("A.X inference failed — BERT fallback")
                return HybridIntentPrediction(
                    intents=bert_intents,
                    scores=probs,
                    selected_model="BERT_FALLBACK",
                    degraded=True,
                    prompt_version=AxIntentModel.prompt_version,
                )
        if route.should_route and self.ax_enabled:
            return HybridIntentPrediction(
                intents=bert_intents,
                scores=probs,
                selected_model="BERT_FALLBACK",
                degraded=True,
                prompt_version=AxIntentModel.prompt_version,
            )
        return HybridIntentPrediction(
            intents=bert_intents,
            scores=probs,
            selected_model="BERT",
            degraded=False,
        )
