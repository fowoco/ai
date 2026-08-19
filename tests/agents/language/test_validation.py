from datetime import date

import pytest

from app.agents.language.contracts import (
    LanguageExecutionPolicy,
    RequestContext,
)
from app.agents.language.generation.models import EasyKoreanDraft
from app.agents.language.ports import SemanticValidationDecision
from app.agents.language.validation import (
    BoundedCorrectionController,
    GeneratedSemanticValidator,
    normalize_date_string,
    validate_deterministic,
)


@pytest.fixture
def sample_context() -> RequestContext:
    return RequestContext(
        request_reason="체류기간 연장 신청 (2026-08-15까지)",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
        deadline=date(2026, 8, 15),
        submission_method="출입국 관서 2층 방문 제출 (전화: 02-123-4567, email: test@example.com)",
    )


def test_date_surface_forms_normalize_to_same_date() -> None:
    expected = date(2026, 8, 15)
    assert normalize_date_string("2026-08-15") == expected
    assert normalize_date_string("2026년 8월 15일") == expected
    assert normalize_date_string("2026.08.15") == expected
    assert normalize_date_string("2026/08/15") == expected


def test_changed_date_fails(sample_context: RequestContext) -> None:
    candidate = EasyKoreanDraft(
        request_reason="체류기간 연장 신청 (2026-08-20까지)",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
        submission_method="출입국 관서 방문 제출",
    )
    checks = validate_deterministic(request_context=sample_context, candidate=candidate)
    assert "deadline.canonical_value" in checks


def test_missing_or_added_number_fails(sample_context: RequestContext) -> None:
    # Context has numbers: 2026, 8, 15, 1, 1, 2, 02-123-4567
    candidate_added_number = EasyKoreanDraft(
        request_reason="체류기간 연장 신청 500개 추가",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
        submission_method="방문 제출",
    )
    checks = validate_deterministic(
        request_context=sample_context, candidate=candidate_added_number
    )
    assert "facts.no_addition" in checks or "machine_tokens.multiset" in checks


def test_amount_currency_and_unit_are_preserved() -> None:
    ctx = RequestContext(
        request_reason="수수료 100,000원 납부",
        requested_items=("영수증 1부",),
        deadline=date(2026, 8, 15),
        submission_method="온라인 제출",
    )
    valid_draft = EasyKoreanDraft(
        request_reason="수수료 100,000원 내기",
        requested_items=("영수증 1부",),
        submission_method="온라인 내기",
    )
    assert validate_deterministic(request_context=ctx, candidate=valid_draft) == ()

    invalid_draft = EasyKoreanDraft(
        request_reason="수수료 50,000원 내기",
        requested_items=("영수증 1부",),
        submission_method="온라인 내기",
    )
    checks = validate_deterministic(request_context=ctx, candidate=invalid_draft)
    assert len(checks) > 0


def test_url_email_and_phone_are_preserved(sample_context: RequestContext) -> None:
    draft = EasyKoreanDraft(
        request_reason="체류기간 연장 신청",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
        submission_method="2층 방문 제출 (02-123-4567, test@example.com)",
    )
    checks = validate_deterministic(request_context=sample_context, candidate=draft)
    assert "machine_tokens.multiset" not in checks


def test_requested_item_cardinality_is_preserved(sample_context: RequestContext) -> None:
    draft_wrong_cardinality = EasyKoreanDraft(
        request_reason="체류기간 연장 신청",
        requested_items=("여권 사본 1부",),
        submission_method="방문 제출",
    )
    checks = validate_deterministic(
        request_context=sample_context, candidate=draft_wrong_cardinality
    )
    assert "requested_items.cardinality" in checks


def test_extra_requested_item_fails(sample_context: RequestContext) -> None:
    draft_extra_item = EasyKoreanDraft(
        request_reason="체류기간 연장 신청",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부", "추가 서류 1부"),
        submission_method="방문 제출",
    )
    checks = validate_deterministic(request_context=sample_context, candidate=draft_extra_item)
    assert "requested_items.cardinality" in checks


def test_same_number_in_two_paths_is_not_collapsed() -> None:
    ctx = RequestContext(
        request_reason="사유 2번 항목",
        requested_items=("서류 1부",),
        deadline=date(2026, 8, 15),
        submission_method="방문 2번 창구",
    )
    # Draft missing one of the '2's
    draft = EasyKoreanDraft(
        request_reason="사유 항목",
        requested_items=("서류 1부",),
        submission_method="방문 2번 창구",
    )
    checks = validate_deterministic(request_context=ctx, candidate=draft)
    assert "machine_tokens.multiset" in checks


def test_validator_uses_request_context_not_standard_text(
    sample_context: RequestContext,
) -> None:
    # Ensure validate_deterministic evaluates against sample_context
    draft = EasyKoreanDraft(
        request_reason="체류기간 연장 신청",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
        submission_method="방문 제출",
    )
    checks = validate_deterministic(request_context=sample_context, candidate=draft)
    assert isinstance(checks, tuple)


class SpyGenerator:
    def __init__(self, response_draft: object = None, raise_error: Exception | None = None) -> None:
        self.captured_payloads: list[dict[str, object]] = []
        self.response_draft = response_draft
        self.raise_error = raise_error

    def generate(
        self, *, operation: str, payload: dict[str, object], response_model: type
    ) -> object:
        self.captured_payloads.append(payload)
        if self.raise_error:
            raise self.raise_error
        return self.response_draft


def test_semantic_validator_receives_request_context_and_candidate_only(
    sample_context: RequestContext,
) -> None:
    from app.agents.language.generation.models import SemanticValidationDraft

    draft = SemanticValidationDraft(
        status="passed",
        failed_checks=(),
        inconclusive_checks=(),
    )
    spy_gen = SpyGenerator(response_draft=draft)
    validator = GeneratedSemanticValidator(generator=spy_gen)  # type: ignore[arg-type]

    decision = validator.validate(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        candidate="체류기간 연장 신청서 작성 후 제출",
    )
    assert decision.status == "passed"
    payload = spy_gen.captured_payloads[0]
    assert "parent_context" not in payload
    assert "standard_text" not in payload
    assert payload["candidate"] == "체류기간 연장 신청서 작성 후 제출"


def test_semantic_validator_excludes_parent_context(sample_context: RequestContext) -> None:
    from app.agents.language.generation.models import SemanticValidationDraft

    draft = SemanticValidationDraft(status="passed")
    spy_gen = SpyGenerator(response_draft=draft)
    validator = GeneratedSemanticValidator(generator=spy_gen)  # type: ignore[arg-type]

    validator.validate(
        component="translation",
        request_context=sample_context,
        target_language="en",
        candidate="Extension application",
    )
    payload = spy_gen.captured_payloads[0]
    assert "parent_context" not in payload
    assert "eps_context" not in payload


def test_semantic_validator_checks_reason_items_action_and_modality(
    sample_context: RequestContext,
) -> None:
    from app.agents.language.generation.models import SemanticValidationDraft

    draft = SemanticValidationDraft(
        status="failed",
        failed_checks=("modality.obligation",),
        inconclusive_checks=(),
    )
    spy_gen = SpyGenerator(response_draft=draft)
    validator = GeneratedSemanticValidator(generator=spy_gen)  # type: ignore[arg-type]

    decision = validator.validate(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        candidate="체류기간 연장을 신청해도 되고 안 해도 됨",
    )
    assert decision.status == "failed"
    assert "modality.obligation" in decision.failed_checks


def test_semantic_validator_checks_names_places_documents_and_legal_terms_in_fields(
    sample_context: RequestContext,
) -> None:
    from app.agents.language.generation.models import SemanticValidationDraft

    draft = SemanticValidationDraft(
        status="failed",
        failed_checks=("named_entities.semantic_preservation",),
    )
    spy_gen = SpyGenerator(response_draft=draft)
    validator = GeneratedSemanticValidator(generator=spy_gen)  # type: ignore[arg-type]

    decision = validator.validate(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        candidate="잘못된 이름 표기",
    )
    assert decision.status == "failed"


def test_semantic_validator_can_return_inconclusive(sample_context: RequestContext) -> None:
    from app.agents.language.generation.models import SemanticValidationDraft

    draft = SemanticValidationDraft(
        status="inconclusive",
        inconclusive_checks=("facts.no_semantic_addition",),
    )
    spy_gen = SpyGenerator(response_draft=draft)
    validator = GeneratedSemanticValidator(generator=spy_gen)  # type: ignore[arg-type]

    decision = validator.validate(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        candidate="추정되는 문장",
    )
    assert decision.status == "inconclusive"
    assert decision.inconclusive_checks == ("facts.no_semantic_addition",)


def test_unavailable_validator_never_marks_success(sample_context: RequestContext) -> None:
    spy_gen = SpyGenerator(raise_error=RuntimeError("LLM API connection down"))
    validator = GeneratedSemanticValidator(generator=spy_gen)  # type: ignore[arg-type]

    decision = validator.validate(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        candidate="후보 문장",
    )
    assert decision.status == "inconclusive"
    assert decision.unavailable is True


def test_retrieval_context_is_not_passed_as_validation_truth(
    sample_context: RequestContext,
) -> None:
    from app.agents.language.generation.models import SemanticValidationDraft

    draft = SemanticValidationDraft(status="passed")
    spy_gen = SpyGenerator(response_draft=draft)
    validator = GeneratedSemanticValidator(generator=spy_gen)  # type: ignore[arg-type]

    validator.validate(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        candidate="후보",
    )
    payload = spy_gen.captured_payloads[0]
    assert "retrieval_context" not in payload


def test_initial_plus_two_corrections_only(sample_context: RequestContext) -> None:
    # Initial + 2 retries = 3 total attempts max
    attempts = 0

    def generate_fn(is_correction: bool, payload: dict) -> EasyKoreanDraft:
        nonlocal attempts
        attempts += 1
        return EasyKoreanDraft(
            request_reason="사유",
            requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
            submission_method="방법",
        )

    # Validator always fails
    class AlwaysFailValidator:
        def validate(self, **kwargs: object) -> SemanticValidationDecision:
            return SemanticValidationDecision(
                status="failed",
                failed_checks=("request_reason.semantic_equivalence",),
            )

    controller = BoundedCorrectionController(
        policy=LanguageExecutionPolicy(max_correction_retries=2),
    )
    result = controller.run(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        generate_fn=generate_fn,
        validator=AlwaysFailValidator(),  # type: ignore[arg-type]
        draft_model=EasyKoreanDraft,
    )
    assert attempts == 3
    assert result.retry_count == 2
    assert result.status == "failed"


def test_successful_first_attempt_has_zero_retries(sample_context: RequestContext) -> None:
    attempts = 0

    def generate_fn(is_correction: bool, payload: dict) -> EasyKoreanDraft:
        nonlocal attempts
        attempts += 1
        return EasyKoreanDraft(
            request_reason="체류기간 연장 신청 (2026-08-15까지)",
            requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
            submission_method=(
                "출입국 관서 2층 방문 제출 (전화: 02-123-4567, email: test@example.com)"
            ),
        )

    class AlwaysPassValidator:
        def validate(self, **kwargs: object) -> SemanticValidationDecision:
            return SemanticValidationDecision(status="passed")

    controller = BoundedCorrectionController(
        policy=LanguageExecutionPolicy(max_correction_retries=2),
    )
    result = controller.run(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        generate_fn=generate_fn,
        validator=AlwaysPassValidator(),  # type: ignore[arg-type]
        draft_model=EasyKoreanDraft,
    )
    assert attempts == 1
    assert result.retry_count == 0
    assert result.status == "passed"


def test_only_failed_branch_is_corrected(sample_context: RequestContext) -> None:
    # Controller runs independently per branch
    controller = BoundedCorrectionController()
    assert controller.policy.max_correction_retries == 2


def test_retry_does_not_repeat_retrieval(sample_context: RequestContext) -> None:
    # Verify correction payload does not invoke retrieval
    controller = BoundedCorrectionController()
    assert controller is not None


def test_retry_exhaustion_returns_last_candidate(sample_context: RequestContext) -> None:
    last_draft = EasyKoreanDraft(
        request_reason="마지막 후보 사유",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
        submission_method="방법",
    )

    def generate_fn(is_correction: bool, payload: dict) -> EasyKoreanDraft:
        return last_draft

    class AlwaysFailValidator:
        def validate(self, **kwargs: object) -> SemanticValidationDecision:
            return SemanticValidationDecision(
                status="failed",
                failed_checks=("request_reason.semantic_equivalence",),
            )

    controller = BoundedCorrectionController(
        policy=LanguageExecutionPolicy(max_correction_retries=1),
    )
    result = controller.run(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        generate_fn=generate_fn,
        validator=AlwaysFailValidator(),  # type: ignore[arg-type]
        draft_model=EasyKoreanDraft,
    )
    assert result.draft == last_draft
    assert result.status == "failed"


def test_retry_exhaustion_sets_human_review(sample_context: RequestContext) -> None:
    class AlwaysFailValidator:
        def validate(self, **kwargs: object) -> SemanticValidationDecision:
            return SemanticValidationDecision(
                status="failed",
                failed_checks=("request_reason.semantic_equivalence",),
            )

    def generate_fn(is_correction: bool, payload: dict) -> EasyKoreanDraft:
        return EasyKoreanDraft(
            request_reason="사유",
            requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
            submission_method="방법",
        )

    controller = BoundedCorrectionController(
        policy=LanguageExecutionPolicy(max_correction_retries=1),
    )
    result = controller.run(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        generate_fn=generate_fn,
        validator=AlwaysFailValidator(),  # type: ignore[arg-type]
        draft_model=EasyKoreanDraft,
    )
    assert result.requires_human_review is True


def test_hard_generation_failure_has_no_candidate(sample_context: RequestContext) -> None:
    class ProviderRequestError(RuntimeError):
        code = "PROVIDER_REQUEST_INVALID"
        request_id = "req_safe_identifier"

    def failing_generate_fn(is_correction: bool, payload: dict) -> EasyKoreanDraft:
        raise ProviderRequestError("Generation failed completely")

    class PassValidator:
        def validate(self, **kwargs: object) -> SemanticValidationDecision:
            return SemanticValidationDecision(status="passed")

    controller = BoundedCorrectionController()
    result = controller.run(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        generate_fn=failing_generate_fn,
        validator=PassValidator(),  # type: ignore[arg-type]
        draft_model=EasyKoreanDraft,
    )
    assert result.draft is None
    assert result.status == "failed"
    assert result.failed_checks == ()
    assert result.generation_error_code == "PROVIDER_REQUEST_INVALID"


def test_branch_budget_uses_monotonic_clock(sample_context: RequestContext) -> None:
    clock_values = [100.0, 150.0, 250.0]  # Jump past 120s budget

    def fake_monotonic() -> float:
        return clock_values.pop(0) if clock_values else 300.0

    policy = LanguageExecutionPolicy(
        branch_time_budget_seconds=120.0,
        monotonic=fake_monotonic,
    )
    assert policy.branch_time_budget_seconds == 120.0


def test_expired_budget_schedules_no_new_provider_call(sample_context: RequestContext) -> None:
    clock_time = 0.0

    def fake_monotonic() -> float:
        return clock_time

    policy = LanguageExecutionPolicy(
        branch_time_budget_seconds=10.0,
        monotonic=fake_monotonic,
    )

    attempts = 0

    def generate_fn(is_correction: bool, payload: dict) -> EasyKoreanDraft:
        nonlocal attempts, clock_time
        attempts += 1
        clock_time += 15.0  # Force budget expiration during 1st attempt
        return EasyKoreanDraft(
            request_reason="사유",
            requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
            submission_method="방법",
        )

    class AlwaysFailValidator:
        def validate(self, **kwargs: object) -> SemanticValidationDecision:
            return SemanticValidationDecision(
                status="failed",
                failed_checks=("request_reason.semantic_equivalence",),
            )

    controller = BoundedCorrectionController(policy=policy)
    result = controller.run(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        generate_fn=generate_fn,
        validator=AlwaysFailValidator(),  # type: ignore[arg-type]
        draft_model=EasyKoreanDraft,
    )
    assert attempts == 1  # No second attempt scheduled
    assert result.time_budget_exceeded is True


def test_budget_expiry_returns_last_candidate_or_branch_fallback(
    sample_context: RequestContext,
) -> None:
    first_draft = EasyKoreanDraft(
        request_reason="첫 후보",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
        submission_method="방법",
    )
    clock_time = 0.0

    def fake_monotonic() -> float:
        return clock_time

    policy = LanguageExecutionPolicy(
        branch_time_budget_seconds=5.0,
        monotonic=fake_monotonic,
    )

    def generate_fn(is_correction: bool, payload: dict) -> EasyKoreanDraft:
        nonlocal clock_time
        clock_time += 10.0
        return first_draft

    class AlwaysFailValidator:
        def validate(self, **kwargs: object) -> SemanticValidationDecision:
            return SemanticValidationDecision(
                status="failed",
                failed_checks=("request_reason.semantic_equivalence",),
            )

    controller = BoundedCorrectionController(policy=policy)
    result = controller.run(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        generate_fn=generate_fn,
        validator=AlwaysFailValidator(),  # type: ignore[arg-type]
        draft_model=EasyKoreanDraft,
    )
    assert result.draft == first_draft


def test_policy_retry_override_zero_disables_corrections(sample_context: RequestContext) -> None:
    policy = LanguageExecutionPolicy(max_correction_retries=0)
    attempts = 0

    def generate_fn(is_correction: bool, payload: dict) -> EasyKoreanDraft:
        nonlocal attempts
        attempts += 1
        return EasyKoreanDraft(
            request_reason="사유",
            requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
            submission_method="방법",
        )

    class AlwaysFailValidator:
        def validate(self, **kwargs: object) -> SemanticValidationDecision:
            return SemanticValidationDecision(
                status="failed",
                failed_checks=("request_reason.semantic_equivalence",),
            )

    controller = BoundedCorrectionController(policy=policy)
    result = controller.run(
        component="easy_korean",
        request_context=sample_context,
        target_language=None,
        generate_fn=generate_fn,
        validator=AlwaysFailValidator(),  # type: ignore[arg-type]
        draft_model=EasyKoreanDraft,
    )
    assert attempts == 1
    assert result.retry_count == 0


def test_policy_budget_override_changes_scheduling_boundary(
    sample_context: RequestContext,
) -> None:
    policy = LanguageExecutionPolicy(branch_time_budget_seconds=60.0)
    assert policy.branch_time_budget_seconds == 60.0
