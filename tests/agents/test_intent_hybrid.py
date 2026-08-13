# HF Intent 에이전트·대표 Intent 선택 단위 테스트

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

from app.agents.intent.guardrail import HRRoutingGuardrail
from app.agents.intent.hybrid import HybridIntentPipeline, HybridIntentPrediction
from app.agents.intent.prompts import AX_INTENT_PROMPT_VERSION
from app.agents.intent.service import (
    FixedExpiryRenewalIntentAgent,
    HybridHfIntentAgent,
    _primary_intent,
    build_intent_agent,
)
from app.core.config import get_settings


# 점수 있을 때 최고 점수 Intent 선택
def test_primary_intent_picks_highest_score() -> None:
    intent, conf = _primary_intent(
        ["DOCUMENT_REQUEST", "EXPIRY_RENEWAL"],
        {"DOCUMENT_REQUEST": 0.4, "EXPIRY_RENEWAL": 0.91},
    )
    assert intent == "EXPIRY_RENEWAL"
    assert conf == 0.91


# OUT_OF_SCOPE 단독 유지
def test_primary_intent_out_of_scope_alone() -> None:
    intent, conf = _primary_intent(["OUT_OF_SCOPE"], {"OUT_OF_SCOPE": 0.8})
    assert intent == "OUT_OF_SCOPE"
    assert conf == 0.8


# 기본 빌드는 재갱신 고정
def test_build_intent_agent_defaults_to_fixed() -> None:
    agent = build_intent_agent()
    assert isinstance(agent, FixedExpiryRenewalIntentAgent)
    result = agent.classify("아무 말")
    assert result.intent == "EXPIRY_RENEWAL"
    assert result.workflow_id in {"WF-STY-001", "WF-CON-001", ""}
    assert result.confidence_source == "MODEL"


# 주입된 파이프라인으로 Hybrid 에이전트 분류
def test_hybrid_agent_maps_pipeline_prediction() -> None:
    class _FakePipe:
        def predict(self, instruction: str) -> HybridIntentPrediction:
            del instruction
            return HybridIntentPrediction(
                intents=["EXPIRY_RENEWAL"],
                scores={"EXPIRY_RENEWAL": 0.93},
                selected_model="BERT",
            )

    agent = HybridHfIntentAgent(pipeline=_FakePipe())
    result = agent.classify("응웬반안 체류연장")
    assert result.intent == "EXPIRY_RENEWAL"
    assert result.confidence == 0.93
    assert result.workflow_id == "WF-STY-001"
    assert result.model_provider == "huggingface"
    assert result.model_name == get_settings().intent_bert_model_dir
    assert result.model_version == "BERT"
    assert result.prompt_version == "not-applicable"
    assert result.confidence_source == "BERT"
    assert result.bert_routing_score == 0.93


def test_hybrid_agent_routes_contract_workflow_from_instruction() -> None:
    class _FakePipe:
        def predict(self, instruction: str) -> HybridIntentPrediction:
            del instruction
            return HybridIntentPrediction(
                intents=["EXPIRY_RENEWAL"],
                scores={"EXPIRY_RENEWAL": 0.93},
                selected_model="BERT",
            )

    result = HybridHfIntentAgent(pipeline=_FakePipe()).classify(
        "근로계약 종료 전에 재계약 준비해줘"
    )

    assert result.workflow_id == "WF-CON-001"


# A.X는 Knowledge prompt의 발화문 등장 순서를 대표 Intent에도 유지
def test_hybrid_agent_preserves_ax_intent_order() -> None:
    class _FakePipe:
        def predict(self, instruction: str) -> HybridIntentPrediction:
            del instruction
            return HybridIntentPrediction(
                intents=["DOCUMENT_REQUEST", "EXPIRY_RENEWAL"],
                scores={"DOCUMENT_REQUEST": 0.2, "EXPIRY_RENEWAL": 0.95},
                evidence={"DOCUMENT_REQUEST": "서류를 요청해"},
                selected_model="AX",
                prompt_version=AX_INTENT_PROMPT_VERSION,
            )

    agent = HybridHfIntentAgent(pipeline=_FakePipe())
    result = agent.classify("서류를 요청해. 체류연장도 준비해줘")

    assert result.intent == "DOCUMENT_REQUEST"
    assert result.workflow_id == "WF-DOC-001"
    assert result.confidence is None
    assert result.confidence_source == "UNAVAILABLE"
    assert result.bert_routing_score == 0.2
    assert result.evidence == "서류를 요청해"
    assert result.extracted_slots == {}
    assert result.prompt_version == AX_INTENT_PROMPT_VERSION


# INTENT_MODEL_ENABLED=true → HybridHfIntentAgent
def test_build_intent_agent_enabled_returns_hybrid(monkeypatch) -> None:
    monkeypatch.setenv("FOWOCO_INTENT_MODEL_ENABLED", "true")
    get_settings.cache_clear()
    try:
        agent = build_intent_agent()
        assert isinstance(agent, HybridHfIntentAgent)
    finally:
        get_settings.cache_clear()


def test_hybrid_runtime_status_reports_loaded_ax_and_prompt(monkeypatch) -> None:
    monkeypatch.setenv("FOWOCO_INTENT_ENABLE_AX", "true")
    get_settings.cache_clear()
    try:
        pipeline = type(
            "LoadedPipeline",
            (),
            {"bert": object(), "ax": object(), "ax_enabled": True},
        )()
        status = HybridHfIntentAgent(pipeline=pipeline).runtime_status()

        assert status == {
            "intentModelEnabled": True,
            "axEnabled": True,
            "initialized": True,
            "bertAvailable": True,
            "axAvailable": True,
            "ready": True,
            "warmupCompleted": True,
            "degraded": False,
            "promptVersion": AX_INTENT_PROMPT_VERSION,
        }
    finally:
        get_settings.cache_clear()


def test_hybrid_warmup_marks_agent_ready() -> None:
    class _WarmablePipeline:
        bert = object()
        ax = object()
        ax_enabled = True

        def __init__(self) -> None:
            self.calls = 0

        def warmup(self) -> None:
            self.calls += 1

    pipeline = _WarmablePipeline()
    agent = HybridHfIntentAgent(pipeline=pipeline)

    agent.warmup()

    assert pipeline.calls == 1
    assert agent.runtime_status()["ready"] is True
    assert agent.runtime_status()["warmupCompleted"] is True


def test_hybrid_loader_is_singleton_under_concurrent_first_requests(
    monkeypatch,
) -> None:
    started = Event()
    release = Event()
    counter_lock = Lock()
    calls = 0

    class _FakeHybridPipeline:
        def __init__(self, **kwargs: object) -> None:
            nonlocal calls
            del kwargs
            with counter_lock:
                calls += 1
            started.set()
            assert release.wait(timeout=2)

    monkeypatch.setattr(
        "app.agents.intent.hybrid.HybridIntentPipeline", _FakeHybridPipeline
    )
    agent = HybridHfIntentAgent()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(agent._ensure_pipeline)
        assert started.wait(timeout=2)
        second = executor.submit(agent._ensure_pipeline)
        release.set()
        assert first.result(timeout=2) is not None
        assert second.result(timeout=2) is not None

    assert calls == 1


def test_hybrid_loader_forwards_pinned_model_revisions(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeHybridPipeline:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setenv("FOWOCO_INTENT_BERT_MODEL_REVISION", "bert-commit")
    monkeypatch.setenv("FOWOCO_INTENT_AX_BASE_REVISION", "base-commit")
    monkeypatch.setenv("FOWOCO_INTENT_AX_ADAPTER_REVISION", "adapter-commit")
    monkeypatch.setattr(
        "app.agents.intent.hybrid.HybridIntentPipeline", _FakeHybridPipeline
    )
    get_settings.cache_clear()
    try:
        agent = HybridHfIntentAgent()
        assert agent._ensure_pipeline() is not None
        assert captured["bert_model_revision"] == "bert-commit"
        assert captured["ax_base_revision"] == "base-commit"
        assert captured["ax_adapter_revision"] == "adapter-commit"
    finally:
        get_settings.cache_clear()


# 파이프라인 로드 실패 시 재갱신 고정 폴백
def test_hybrid_load_failure_falls_back_to_fixed(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.agents.intent.hybrid.HybridIntentPipeline", _boom)
    agent = HybridHfIntentAgent()
    result = agent.classify("체류연장 준비해줘")
    assert result.intent == "EXPIRY_RENEWAL"
    assert result.model_provider == "internal"
    assert result.model_name == "fixed-expiry-renewal"
    assert result.model_version == "fallback"
    assert agent._load_error is not None


# margin 통과 시 BERT 유지
def test_guardrail_pass_bert_when_confident() -> None:
    gate = HRRoutingGuardrail(margin_threshold=0.76)
    out = gate.should_route_to_ax(
        "응웬반안 체류연장 준비",
        {"EXPIRY_RENEWAL": 0.92, "DOCUMENT_REQUEST": 0.05},
        margin=0.87,
    )
    assert out.should_route is False
    assert out.category == "Pass_BERT"


# 서류 키워드면 A.X 라우팅
def test_guardrail_routes_on_document_keyword() -> None:
    gate = HRRoutingGuardrail()
    out = gate.should_route_to_ax(
        "신청서 서류 챙겨줘",
        {"DOCUMENT_REQUEST": 0.8},
        margin=0.9,
    )
    assert out.should_route is True
    assert out.category == "Rule_Document"


def test_pipeline_calls_ax_when_guardrail_routes() -> None:
    class _Bert:
        device = "cpu"

        def predict(self, _instruction: str) -> tuple[dict[str, float], float, list[str]]:
            return {"DOCUMENT_REQUEST": 0.8}, 0.9, ["DOCUMENT_REQUEST"]

    class _Guardrail:
        def should_route_to_ax(self, *_args: object) -> object:
            return type("Route", (), {"should_route": True})()

    class _Ax:
        prompt_version = AX_INTENT_PROMPT_VERSION

        def predict(self, _instruction: str) -> list[dict[str, str]]:
            return [{"intent": "DOCUMENT_REQUEST", "evidence": "서류 챙겨줘"}]

    pipeline = HybridIntentPipeline.__new__(HybridIntentPipeline)
    pipeline.bert = _Bert()
    pipeline.guardrail = _Guardrail()
    pipeline.ax = _Ax()
    pipeline.ax_enabled = True

    prediction = pipeline.predict("서류 챙겨줘")

    assert prediction.selected_model == "AX"
    assert prediction.intents == ["DOCUMENT_REQUEST"]
    assert prediction.evidence == {"DOCUMENT_REQUEST": "서류 챙겨줘"}
    assert prediction.prompt_version == AX_INTENT_PROMPT_VERSION


def test_pipeline_warmup_runs_bert_and_enabled_ax() -> None:
    calls: list[tuple[str, str]] = []

    class _Bert:
        def predict(self, instruction: str) -> None:
            calls.append(("BERT", instruction))

    class _Ax:
        def predict(self, instruction: str) -> None:
            calls.append(("AX", instruction))

    pipeline = HybridIntentPipeline.__new__(HybridIntentPipeline)
    pipeline.bert = _Bert()
    pipeline.ax = _Ax()
    pipeline.ax_enabled = True

    pipeline.warmup()

    assert [model for model, _ in calls] == ["BERT", "AX"]


def test_pipeline_marks_fallback_when_ax_enabled_but_unavailable() -> None:
    class _Bert:
        device = "cpu"

        def predict(self, _instruction: str) -> tuple[dict[str, float], float, list[str]]:
            return {"DOCUMENT_REQUEST": 0.8}, 0.9, ["DOCUMENT_REQUEST"]

    class _Guardrail:
        def should_route_to_ax(self, *_args: object) -> object:
            return type("Route", (), {"should_route": True})()

    pipeline = HybridIntentPipeline.__new__(HybridIntentPipeline)
    pipeline.bert = _Bert()
    pipeline.guardrail = _Guardrail()
    pipeline.ax = None
    pipeline.ax_enabled = True

    prediction = pipeline.predict("서류 챙겨줘")

    assert prediction.selected_model == "BERT_FALLBACK"
    assert prediction.degraded is True
    assert prediction.prompt_version == AX_INTENT_PROMPT_VERSION
