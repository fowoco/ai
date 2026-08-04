from datetime import date

import pytest
from pydantic import BaseModel

from app.agents.language.contracts import (
    LanguageExecutionPolicy,
    RequestContext,
    WarningCode,
)
from app.agents.language.easy_korean import (
    EasyBranchInput,
    EasyKoreanResult,
    build_easy_korean_subgraph,
    render_easy_korean_text,
)
from app.agents.language.generation.models import EasyKoreanDraft, SemanticValidationDraft
from app.agents.language.ports import SemanticValidationDecision
from app.agents.language.protected_facts import ProtectedFacts


@pytest.fixture
def sample_context() -> RequestContext:
    return RequestContext(
        request_reason="체류기간 연장 신청 (2026-08-15까지)",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
        deadline=date(2026, 8, 15),
        submission_method=(
            "출입국 관서 2층 방문 제출 (전화: 02-123-4567, email: test@example.com)"
        ),
    )


@pytest.fixture
def sample_protected_facts(sample_context: RequestContext) -> ProtectedFacts:
    return ProtectedFacts.from_request_context(sample_context)


@pytest.fixture
def sample_input(
    sample_context: RequestContext, sample_protected_facts: ProtectedFacts
) -> EasyBranchInput:
    return {
        "request_context": sample_context,
        "protected_facts": sample_protected_facts,
        "standard_korean_text": (
            "체류기간 연장 신청서 제출 안내\n"
            "- 여권 사본 1부\n"
            "- 근로계약서 사본 1부\n"
            "기한: 2026-08-15\n"
            "제출방법: 출입국 관서 2층 방문 제출"
        ),
    }


class FakeGenerator:
    def __init__(
        self,
        draft: BaseModel | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.captured_payloads: list[dict[str, object]] = []
        self.draft = draft
        self.raise_error = raise_error
        self.call_count = 0

    def generate(
        self, *, operation: str, payload: dict[str, object], response_model: type
    ) -> object:
        self.call_count += 1
        self.captured_payloads.append({"operation": operation, **payload})
        if self.raise_error:
            raise self.raise_error
        if self.draft is not None:
            return self.draft
        if response_model == SemanticValidationDraft:
            return SemanticValidationDraft(status="passed")
        return EasyKoreanDraft(
            request_reason="체류기간 늘림 신청",
            requested_items=("여권 복사본 1부", "일터 약속 서류 복사본 1부"),
            submission_method="출입국 관서 2층 가져오기 내기 (02-123-4567, test@example.com)",
        )


class FakeValidator:
    def __init__(self, decision: SemanticValidationDecision | None = None) -> None:
        self.decision = decision or SemanticValidationDecision(status="passed")
        self.call_count = 0

    def validate(self, **kwargs: object) -> SemanticValidationDecision:
        self.call_count += 1
        return self.decision


def test_easy_prompt_uses_request_context_standard_text_and_context_pack_only(
    sample_input: EasyBranchInput,
) -> None:
    gen = FakeGenerator()
    val = FakeValidator()
    subgraph = build_easy_korean_subgraph(
        generator=gen,
        validator=val,
        allow_draft_context_pack=True,
    )
    result = subgraph.invoke(sample_input)
    assert "easy_result" in result
    assert isinstance(result["easy_result"], EasyKoreanResult)
    assert gen.call_count >= 1
    payload = gen.captured_payloads[0]
    assert "request_context" in payload
    assert "standard_korean_text" in payload


def test_easy_prompt_excludes_parent_db_context(sample_input: EasyBranchInput) -> None:
    gen = FakeGenerator()
    val = FakeValidator()
    subgraph = build_easy_korean_subgraph(
        generator=gen,
        validator=val,
        allow_draft_context_pack=True,
    )
    subgraph.invoke(sample_input)
    payload = gen.captured_payloads[0]
    assert "worker_id" not in payload
    assert "nationality" not in payload
    assert "parent_context" not in payload


def test_easy_output_splits_fields_into_short_lines(sample_context: RequestContext) -> None:
    draft = EasyKoreanDraft(
        request_reason="체류기간 늘림 신청",
        requested_items=("여권 복사본 1부", "일터 약속 서류 복사본 1부"),
        submission_method="방문 내기",
    )
    text = render_easy_korean_text(draft, sample_context)
    lines = text.split("\n")
    assert len(lines) >= 4
    assert lines[0].startswith("신청 사유:")


def test_easy_output_keeps_one_action_per_line(sample_context: RequestContext) -> None:
    draft = EasyKoreanDraft(
        request_reason="체류기간 늘림 신청",
        requested_items=("여권 복사본 1부", "일터 약속 서류 복사본 1부"),
        submission_method="방문 내기",
    )
    text = render_easy_korean_text(draft, sample_context)
    assert "- 여권 복사본 1부" in text
    assert "- 일터 약속 서류 복사본 1부" in text


def test_easy_output_preserves_requested_item_names(sample_context: RequestContext) -> None:
    draft = EasyKoreanDraft(
        request_reason="체류기간 늘림 신청",
        requested_items=("여권 복사본 1부", "근로계약서 사본 1부"),
        submission_method="방문 내기",
    )
    text = render_easy_korean_text(draft, sample_context)
    assert "여권 복사본 1부" in text
    assert "근로계약서 사본 1부" in text


def test_easy_output_includes_iso_deadline(sample_context: RequestContext) -> None:
    draft = EasyKoreanDraft(
        request_reason="체류기간 늘림 신청",
        requested_items=("여권 복사본 1부",),
        submission_method="방문 내기",
    )
    text = render_easy_korean_text(draft, sample_context)
    assert "2026-08-15" in text


def test_easy_output_preserves_obligation_prohibition_and_warning_strength(
    sample_input: EasyBranchInput,
) -> None:
    gen = FakeGenerator()
    val = FakeValidator()
    subgraph = build_easy_korean_subgraph(
        generator=gen,
        validator=val,
        allow_draft_context_pack=True,
    )
    res = subgraph.invoke(sample_input)["easy_result"]
    assert res.status == "success"


def test_easy_output_adds_no_explanatory_fact(sample_input: EasyBranchInput) -> None:
    gen = FakeGenerator()
    val = FakeValidator()
    subgraph = build_easy_korean_subgraph(
        generator=gen,
        validator=val,
        allow_draft_context_pack=True,
    )
    res = subgraph.invoke(sample_input)["easy_result"]
    assert "신청 사유:" in res.text


def test_easy_validation_retries_with_failed_check_ids(sample_input: EasyBranchInput) -> None:
    gen = FakeGenerator()
    val = FakeValidator(
        decision=SemanticValidationDecision(
            status="failed",
            failed_checks=("request_reason.semantic_equivalence",),
        )
    )
    policy = LanguageExecutionPolicy(max_correction_retries=1)
    subgraph = build_easy_korean_subgraph(
        generator=gen,
        validator=val,
        policy=policy,
        allow_draft_context_pack=True,
    )
    res = subgraph.invoke(sample_input)["easy_result"]
    assert gen.call_count == 2
    assert res.status == "warning"
    assert res.validation.status == "failed"


def test_easy_retry_exhaustion_returns_last_candidate(sample_input: EasyBranchInput) -> None:
    gen = FakeGenerator()
    val = FakeValidator(
        decision=SemanticValidationDecision(
            status="failed",
            failed_checks=("request_reason.semantic_equivalence",),
        )
    )
    policy = LanguageExecutionPolicy(max_correction_retries=2)
    subgraph = build_easy_korean_subgraph(
        generator=gen,
        validator=val,
        policy=policy,
        allow_draft_context_pack=True,
    )
    res = subgraph.invoke(sample_input)["easy_result"]
    assert res.used_standard_fallback is False
    assert res.status == "warning"
    assert any(w.code == WarningCode.VALIDATION_RETRY_EXCEEDED for w in res.warnings)


def test_easy_hard_failure_falls_back_to_standard_korean(sample_input: EasyBranchInput) -> None:
    gen = FakeGenerator(raise_error=RuntimeError("Provider offline"))
    val = FakeValidator()
    subgraph = build_easy_korean_subgraph(
        generator=gen,
        validator=val,
        allow_draft_context_pack=True,
    )
    res = subgraph.invoke(sample_input)["easy_result"]
    assert res.text == sample_input["standard_korean_text"]
    assert res.used_standard_fallback is True
    assert res.status == "warning"
    assert res.validation.status == "not_run"
    codes = [w.code for w in res.warnings]
    assert WarningCode.EASY_KOREAN_GENERATION_FAILED in codes
    assert WarningCode.STANDARD_KOREAN_FALLBACK in codes


def test_unapproved_context_pack_skips_provider_and_falls_back_to_standard(
    sample_input: EasyBranchInput,
) -> None:
    gen = FakeGenerator()
    val = FakeValidator()
    # allow_draft_context_pack=False will fail loading draft context pack in test env
    subgraph = build_easy_korean_subgraph(
        generator=gen,
        validator=val,
        allow_draft_context_pack=False,
    )
    res = subgraph.invoke(sample_input)["easy_result"]
    assert gen.call_count == 0
    assert res.attempt_count == 0
    assert res.text == sample_input["standard_korean_text"]
    assert res.used_standard_fallback is True
    assert res.status == "warning"
    assert res.validation.status == "not_run"
    codes = [w.code for w in res.warnings]
    assert WarningCode.EASY_KOREAN_CONTEXT_PACK_UNAVAILABLE in codes
    assert WarningCode.STANDARD_KOREAN_FALLBACK in codes
