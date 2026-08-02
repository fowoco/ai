import unicodedata
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
