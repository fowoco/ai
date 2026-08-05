from .contracts import FrozenContract, QueryStrategy, RequestContext
from .protected_facts import ProtectedFacts


class SearchQuery(FrozenContract):
    kind: QueryStrategy
    text: str


def build_search_queries(
    context: RequestContext,
    protected_facts: ProtectedFacts,
) -> tuple[SearchQuery, ...]:
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
    items = ", ".join(protected_facts.requested_items)
    reason = protected_facts.request_reason
    deadline = protected_facts.deadline.isoformat()
    method = protected_facts.submission_method
    canonical_values = ", ".join(
        token.canonical_value
        for token in protected_facts.machine_tokens
        if token.canonical_value != token.surface
    )
    canonical_suffix = f"; 정규 보호값 {canonical_values}" if canonical_values else ""
    queries = (
        (
            "canonical",
            f"요청 목적 {reason}; 자료 {items}; 기한 {deadline}; 방법 {method}"
            f"{canonical_suffix}",
        ),
        (
            "reason_items",
            f"요청 목적 {reason}; 자료 {items}; 방법 {method}; 기한 {deadline}"
            f"{canonical_suffix}",
        ),
        (
            "action_deadline",
            f"기한 {deadline}; 방법 {method}; 요청 목적 {reason}; 자료 {items}"
            f"{canonical_suffix}",
        ),
    )
    for _, text in queries:
        if any(token.surface not in text for token in protected_facts.machine_tokens):
            raise ValueError("query omitted a protected token")
    return tuple(SearchQuery(kind=kind, text=text) for kind, text in queries)
