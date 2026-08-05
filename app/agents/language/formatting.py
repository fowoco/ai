from .contracts import ComponentValidation, RequestContext
from .protected_facts import ProtectedFacts


def format_standard_korean(
    context: RequestContext,
    protected_facts: ProtectedFacts,
) -> str:
    if (
        protected_facts.request_reason,
        protected_facts.requested_items,
        protected_facts.deadline,
        protected_facts.submission_method,
    ) != (
        context.request_reason,
        context.requested_items,
        context.deadline,
        context.submission_method,
    ):
        raise ValueError("protected facts do not match request context")
    lines = [
        "다음 요청 내용을 확인해 주세요.",
        "",
        f"요청 목적: {protected_facts.request_reason}",
        "준비할 자료:",
    ]
    lines.extend(
        f"{index}. {item}"
        for index, item in enumerate(protected_facts.requested_items, start=1)
    )
    lines.extend(
        (
            f"제출 기한: {protected_facts.deadline.isoformat()}",
            f"제출 방법: {protected_facts.submission_method}",
        )
    )
    return "\n".join(lines)


def assert_standard_formatter_invariants(
    request_context: RequestContext,
    rendered_text: str,
    protected_facts: ProtectedFacts,
) -> ComponentValidation:
    expected = format_standard_korean(request_context, protected_facts)
    if rendered_text != expected:
        raise ValueError("standard Korean formatter invariant violated")
    if rendered_text.count(f"제출 방법: {protected_facts.submission_method}") != 1:
        raise ValueError("submission method must appear exactly once")
    for token in protected_facts.machine_tokens:
        if rendered_text.count(token.surface) < 1:
            raise ValueError(f"protected token missing: {token.surface}")
    return ComponentValidation(status="passed", retry_count=0)
