# Language/OCR 브리지 단위 테스트

from datetime import date

from app.agents.language.contracts import (
    ComponentStatus,
    ComponentValidation,
    LanguageAssistantInput,
    LanguageAssistantOutput,
    RetrievalMetadata,
    ValidationSummary,
)
from app.agents.workflow_graph.language_bridge import (
    LanguageGuideBridge,
    build_ask_worker_request_context,
    renewal_as_language_parent,
)
from app.agents.workflow_graph.ocr_bridge import DocumentOcrNode, normalize_ocr_fields
from app.agents.workflow_graph.state import empty_renewal_state


# CLOVA 필드 → 신분 슬롯 매핑
def test_normalize_ocr_fields_maps_clova_names() -> None:
    out = normalize_ocr_fields(
        {
            "passport_number": "M123",
            "surname": "NGUYEN",
            "given_names": "VAN AN",
            "date_of_birth": "1990-01-02",
            "alien_registration_number": "123456-7890123",
        }
    )
    assert out["passport_number"] == "M123"
    assert out["full_name"] == "NGUYEN VAN AN"
    assert out["date_of_birth"] == "1990-01-02"
    assert out["alien_registration_number"] == "123456-7890123"


# documents.fields 우선 사용, stub 미호출
def test_document_ocr_node_uses_document_fields() -> None:
    node = DocumentOcrNode()
    state = empty_renewal_state(
        task_id="t1",
        request_id="r1",
        instruction="체류연장",
        documents=[
            {
                "document_type": "passport",
                "fields": {
                    "passport_number": "P-REAL",
                    "surname": "LEE",
                    "given_names": "HWI",
                },
            }
        ],
    )
    patch = node(state)
    assert patch["ocr_result"]["passport_number"] == "P-REAL"
    assert patch["slots"]["full_name"] == "LEE HWI"


# ask_worker RequestContext 기본 생성
def test_build_ask_worker_request_context() -> None:
    state = empty_renewal_state(
        task_id="t1",
        request_id="r1",
        instruction="체류연장",
        slots={"stay_expiry_date": "2026-09-30"},
    )
    state["missing_slots"] = ["passport_number", "alien_registration_number"]
    ctx = build_ask_worker_request_context(state)
    assert ctx["deadline"] == date(2026, 9, 30)
    assert "여권" in ctx["requested_items"][0]


# Language guide 성공 시 State에 language_assistant 적재
def test_language_guide_bridge_invokes_service() -> None:
    class _Fake:
        def invoke(self, request: LanguageAssistantInput) -> LanguageAssistantOutput:
            return LanguageAssistantOutput(
                worker_id=request.worker_id,
                target_language="vi",
                generation_status="success",
                requires_human_review=False,
                standard_korean_text="표준 안내",
                easy_korean_text="쉬운 안내",
                translated_text="Ban can nop ho so",
                component_status=ComponentStatus(
                    standard_korean="success",
                    easy_korean="success",
                    translation="success",
                ),
                validation=ValidationSummary(
                    standard_korean=ComponentValidation(status="passed", retry_count=0),
                    easy_korean=ComponentValidation(status="passed", retry_count=0),
                    translation=ComponentValidation(status="passed", retry_count=0),
                ),
                warnings=(),
                retrieval_metadata=RetrievalMetadata(
                    dataset_version="v1",
                    query_strategies=("canonical",),
                    reference_ids=(),
                    reference_count=0,
                    fallback_used=False,
                    degraded_components=(),
                ),
            )

    state = empty_renewal_state(
        task_id="t1",
        request_id="r1",
        instruction="체류연장",
        worker_id="worker-1",
        slots={"nationality": "VN", "stay_expiry_date": "2026-09-30"},
    )
    state["worker_record"] = {
        "worker_id": "worker-1",
        "preferred_language": "vi",
        "nationality_code": "VN",
    }
    state["missing_slots"] = ["passport_number"]
    patch = LanguageGuideBridge(service=_Fake())(state)
    assert patch["guide_message"] == "표준 안내"
    assert "쉬운 안내" in patch["worker_request_message"]
    assert patch["language_assistant"]["target_language"] == "vi"
    parent = renewal_as_language_parent({**state, **patch})  # type: ignore[arg-type]
    assert parent["preferred_language"] == "vi"


# service=None(503 미구성) → placeholder만
def test_language_guide_bridge_none_service_uses_placeholder() -> None:
    state = empty_renewal_state(task_id="t1", request_id="r1", instruction="체류연장")
    patch = LanguageGuideBridge(service=None)(state)
    assert "language_assistant" not in patch
    assert patch["guide_review_required"] is True
    assert patch["guide_failure_code"] == "LANGUAGE_ASSISTANT_NOT_CONFIGURED"
    assert patch["worker_request_message"] is None
    assert patch["step"]
    assert patch["active_subgraph"] == "language"


# invoke 예외 시 placeholder 폴백
def test_language_guide_bridge_invoke_error_falls_back() -> None:
    class _Boom:
        def invoke(self, request: LanguageAssistantInput) -> LanguageAssistantOutput:
            del request
            raise RuntimeError("qdrant down")

    state = empty_renewal_state(
        task_id="t1",
        request_id="r1",
        instruction="체류연장",
        worker_id="worker-1",
    )
    patch = LanguageGuideBridge(service=_Boom())(state)
    assert "language_assistant" not in patch
    assert patch["guide_review_required"] is True
    assert patch["guide_failure_code"] == "LANGUAGE_ASSISTANT_INVOCATION_FAILED"
    assert patch["worker_request_message"] is None
    assert patch["active_subgraph"] == "language"
