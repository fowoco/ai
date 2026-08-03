import unicodedata
from collections import Counter
from datetime import date

from app.agents.language.contracts import RequestContext
from app.agents.language.protected_facts import ProtectedFacts


def make_context() -> RequestContext:
    return RequestContext(
        request_reason=(
            "체류기간 2026-08-10 09:30, 숫자 42, 금액 1,234.50 USD, "
            "10kg, https://example.com/doc/ABC-123, user@example.com, "
            "+82-10-1234-5678, 문서 ABC-123 v2.1"
        ),
        requested_items=(
            "여권 사본 42 문서번호 DOC-2026-v2.1",
            "신청서 2026-08-10",
        ),
        deadline=date(2026, 8, 10),
        submission_method="email user@example.com으로 42 제출",
    )


def test_protected_facts_copy_request_fields_without_generated_text():
    context = make_context()

    facts = ProtectedFacts.from_request_context(context)

    assert facts.request_reason == context.request_reason
    assert facts.requested_items == context.requested_items
    assert facts.deadline == context.deadline
    assert facts.submission_method == context.submission_method
    assert not hasattr(facts, "standard_korean_text")


def test_protected_facts_extract_all_machine_token_kinds():
    facts = ProtectedFacts.from_request_context(make_context())

    kinds = {token.kind for token in facts.machine_tokens}

    assert {
        "date",
        "time",
        "number",
        "amount",
        "currency",
        "unit",
        "url",
        "email",
        "phone",
        "document_identifier",
        "version",
    } <= kinds
    assert all(token.surface for token in facts.machine_tokens)
    assert all(token.canonical_value for token in facts.machine_tokens)


def test_protected_token_paths_distinguish_repeated_values_by_source_field():
    facts = ProtectedFacts.from_request_context(make_context())

    repeated_number_paths = {
        token.source_path
        for token in facts.machine_tokens
        if token.surface == "42"
    }

    assert {"request_reason", "requested_items[0]", "submission_method"} <= repeated_number_paths


def test_protected_facts_normalize_unicode_to_nfc():
    decomposed = "안녕"
    context = RequestContext(
        request_reason=decomposed,
        requested_items=("여권",),
        deadline=date(2026, 8, 10),
        submission_method="이메일",
    )

    facts = ProtectedFacts.from_request_context(context)

    assert facts.request_reason == unicodedata.normalize("NFC", decomposed)
    assert facts.request_reason == "안녕"


def test_protected_tokens_preserve_signed_amount_currency_and_units():
    context = RequestContext(
        request_reason="금액 -1,234.50 USD, ₩-10,000, 100만원, 비율 -3.5%",
        requested_items=("수량 42개", "무게 10kg"),
        deadline=date(2026, 8, 10),
        submission_method="KRW로 42개 제출",
    )

    facts = ProtectedFacts.from_request_context(context)
    token_values = {
        (token.kind, token.surface, token.canonical_value)
        for token in facts.machine_tokens
    }

    assert ("amount", "-1,234.50", "-1234.50") in token_values
    assert ("amount", "-10,000", "-10000") in token_values
    assert ("currency", "USD", "USD") in token_values
    assert ("currency", "KRW", "KRW") in token_values
    assert ("currency", "₩", "₩") in token_values
    assert ("currency", "만원", "만원") in token_values
    assert ("unit", "-3.5%", "-3.5%") in token_values
    assert ("unit", "42개", "42개") in token_values
    assert ("unit", "10kg", "10kg") in token_values


def test_protected_tokens_canonicalize_korean_dates():
    context = RequestContext(
        request_reason="방문일은 2026년 8월 10일입니다.",
        requested_items=("여권",),
        deadline=date(2026, 8, 10),
        submission_method="이메일",
    )

    facts = ProtectedFacts.from_request_context(context)

    assert any(
        token.kind == "date"
        and token.surface == "2026년 8월 10일"
        and token.canonical_value == "2026-08-10"
        for token in facts.machine_tokens
    )


def test_protected_token_multiset_includes_source_paths():
    context = RequestContext(
        request_reason="수량 42개",
        requested_items=("수량 42개",),
        deadline=date(2026, 8, 10),
        submission_method="수량 42개 제출",
    )

    facts = ProtectedFacts.from_request_context(context)
    unit_paths = {
        token.source_path
        for token in facts.machine_tokens
        if token.kind == "unit" and token.surface == "42개"
    }

    assert unit_paths == {"request_reason", "requested_items[0]", "submission_method"}


def test_protected_tokens_match_exact_counter_with_duplicate_occurrences():
    context = RequestContext(
        request_reason="금액 -1,234.50 USD와 -1,234.50 USD",
        requested_items=("수량 42개와 42개", "비율 -3.5%"),
        deadline=date(2026, 8, 10),
        submission_method="₩-10,000을 10kg",
    )

    facts = ProtectedFacts.from_request_context(context)
    expected = Counter(
        {
            ("amount", "request_reason", "-1,234.50", "-1234.50"): 2,
            ("currency", "request_reason", "USD", "USD"): 2,
            ("number", "requested_items[0]", "42", "42"): 2,
            ("unit", "requested_items[0]", "42개", "42개"): 2,
            ("unit", "requested_items[1]", "-3.5%", "-3.5%"): 1,
            ("date", "deadline", "2026-08-10", "2026-08-10"): 1,
            ("currency", "submission_method", "₩", "₩"): 1,
            ("amount", "submission_method", "-10,000", "-10000"): 1,
            ("number", "submission_method", "10", "10"): 1,
            ("unit", "submission_method", "10kg", "10kg"): 1,
        }
    )
    observed = Counter(
        (
            token.kind,
            token.source_path,
            token.surface,
            token.canonical_value,
        )
        for token in facts.machine_tokens
    )

    assert observed == expected
