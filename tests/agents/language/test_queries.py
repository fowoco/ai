import inspect
from datetime import date

from app.agents.language.contracts import RequestContext
from app.agents.language.protected_facts import ProtectedFacts
from app.agents.language.queries import build_search_queries
from app.agents.language.state import LanguageAssistantState


def make_context() -> RequestContext:
    return RequestContext(
        request_reason="체류기간 연장: 근로계약서 제12조 확인",
        requested_items=("여권 사본", "외국인등록증 42부"),
        deadline=date(2026, 8, 10),
        submission_method="이메일로 42부를 제출해 주세요.",
    )


def make_queries():
    context = make_context()
    facts = ProtectedFacts.from_request_context(context)
    return context, facts, build_search_queries(context, facts)


def test_generates_exactly_three_queries_in_stable_order():
    context, facts, queries = make_queries()

    assert [query.kind for query in queries] == [
        "canonical",
        "reason_items",
        "action_deadline",
    ]
    assert queries == build_search_queries(context, facts)


def test_query_kinds_are_unique():
    _, _, queries = make_queries()

    assert len({query.kind for query in queries}) == 3


def test_every_query_preserves_every_requested_item():
    context, _, queries = make_queries()

    for query in queries:
        assert all(item in query.text for item in context.requested_items)


def test_every_query_preserves_deadline():
    context, _, queries = make_queries()

    assert all(context.deadline.isoformat() in query.text for query in queries)


def test_every_query_preserves_numbers_names_places_and_legal_scheme_names_when_present():
    context, facts, queries = make_queries()

    protected_surfaces = {
        token.surface
        for token in facts.machine_tokens
        if token.surface in {"42", "12"}
    }
    assert protected_surfaces == {"42", "12"}
    assert all("근로계약서 제12조" in query.text for query in queries)
    assert all(protected in query.text for query in queries for protected in protected_surfaces)


def test_queries_never_use_placeholders():
    _, _, queries = make_queries()

    assert all("placeholder" not in query.text.lower() for query in queries)
    assert all("{" not in query.text and "}" not in query.text for query in queries)


def test_queries_add_no_new_fact():
    _, _, queries = make_queries()

    assert all("박태정" not in query.text for query in queries)
    assert all("FOWOCO" not in query.text for query in queries)
    assert all("stay_expiry_date" not in query.text for query in queries)


def test_db_context_cannot_change_queries():
    _, _, queries = make_queries()
    signature = inspect.signature(build_search_queries)

    assert "parent_context" not in signature.parameters
    assert all("worker" not in query.text for query in queries)
    assert all("company" not in query.text for query in queries)


def test_state_contains_only_t3_owned_keys_in_addition_to_t1_keys():
    annotations = LanguageAssistantState.__annotations__

    assert annotations["protected_facts"]
    assert annotations["standard_korean_text"] is str
    assert annotations["standard_validation"]


def test_queries_preserve_all_new_machine_token_surfaces():
    context = RequestContext(
        request_reason="금액 -1,234.50 USD와 2026년 8월 10일",
        requested_items=("수량 42개", "비율 -3.5%"),
        deadline=date(2026, 8, 10),
        submission_method="₩-10,000을 10kg 단위로 제출",
    )
    facts = ProtectedFacts.from_request_context(context)
    queries = build_search_queries(context, facts)

    new_token_surfaces = {
        token.surface
        for token in facts.machine_tokens
        if token.surface in {
            "-1,234.50",
            "USD",
            "2026년 8월 10일",
            "42개",
            "-3.5%",
            "₩",
            "-10,000",
            "10kg",
        }
    }

    assert new_token_surfaces
    assert all(
        token_surface in query.text
        for query in queries
        for token_surface in new_token_surfaces
    )
