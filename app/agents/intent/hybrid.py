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


# BERT 우선·필요 시 A.X 보조 파이프라인
class HybridIntentPipeline:

    # 설정값으로 BERT·가드레일·선택적 A.X 구성
    def __init__(
        self,
        *,
        bert_model_dir: str,
        device: str = "cpu",
        label_prob_threshold: float = 0.55,
        margin_threshold: float = 0.76,
        max_trained_labels: int = 3,
        hf_token: str | None = None,
        enable_ax: bool = False,
        ax_base_model_name: str = "skt/A.X-4.0-Light",
        ax_adapter_path: str = "fowoco/ax-intent-qlora",
        ax_max_new_tokens: int = 96,
    ) -> None:
        self.bert = BertIntentModel(
            model_dir=bert_model_dir,
            device=device,
            label_prob_threshold=label_prob_threshold,
            hf_token=hf_token,
        )
        self.guardrail = HRRoutingGuardrail(
            margin_threshold=margin_threshold,
            max_trained_labels=max_trained_labels,
            label_prob_threshold=label_prob_threshold,
        )
        self.ax: AxIntentModel | None = None
        if enable_ax:
            try:
                self.ax = AxIntentModel(
                    base_model_name=ax_base_model_name,
                    adapter_path=ax_adapter_path,
                    device=self.bert.device,
                    max_new_tokens=ax_max_new_tokens,
                    hf_token=hf_token,
                )
            except Exception:
                logger.exception("A.X load failed — BERT-only degraded mode")

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
                )
            except Exception:
                logger.exception("A.X inference failed — BERT fallback")
                return HybridIntentPrediction(
                    intents=bert_intents,
                    scores=probs,
                    selected_model="BERT_FALLBACK",
                    degraded=True,
                )
        return HybridIntentPrediction(
            intents=bert_intents,
            scores=probs,
            selected_model="BERT",
            degraded=False,
        )
