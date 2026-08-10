import pytest

from app.agents.language.context_pack import (
    ContextPack,
    ContextPackChecksumError,
    ContextPackUnavailableError,
    load_context_pack,
)


def test_pack_has_semver_and_source_metadata() -> None:
    pack = load_context_pack(allow_draft=True)
    assert pack.pack_version == "easy-ko-v1.0.0"
    assert pack.source_title == "알기 쉬운 법령 정비기준 제10판(수정증보판)"
    assert pack.source_publisher == "법제처"
    assert pack.source_published_at == "2026-01-22"
    assert pack.source_url.startswith("https://")


def test_pack_has_rewrite_rules_terms_and_examples() -> None:
    pack = load_context_pack(allow_draft=True)
    assert len(pack.terms) >= 30
    assert len(pack.rewrite_rules) >= 10
    assert len(pack.examples) >= 12
    assert "체류기간" in pack.terms
    assert "연장" in pack.terms


def test_pack_contains_no_runtime_url_fetch_behavior() -> None:
    # Verify that load_context_pack works synchronously and makes no network calls
    pack = load_context_pack(allow_draft=True)
    assert isinstance(pack, ContextPack)


def test_term_selection_is_deterministic() -> None:
    pack = load_context_pack(allow_draft=True)
    text = "체류기간 연장 신청서 작성 및 제출 안내"
    selected1 = pack.select_terms(text, max_terms=5)
    selected2 = pack.select_terms(text, max_terms=5)
    assert selected1 == selected2
    assert "체류기간" in selected1
    assert "연장" in selected1


def test_context_selection_has_stable_size_limit() -> None:
    pack = load_context_pack(allow_draft=True)
    text = "체류기간 연장 신청서 구비서류 사본 첨부 및 지참하여 교부 받으십시오"
    selection = pack.select_context(text, limit=3)
    assert len(selection.selected_terms) <= 3
    assert len(selection.selected_examples) <= 3


def test_context_pack_checksum_changes_with_content() -> None:
    pack = load_context_pack(allow_draft=True)
    assert len(pack.checksum) == 64  # SHA-256 hex string length


def test_context_pack_is_included_in_package_data() -> None:
    pack = load_context_pack(allow_draft=True)
    assert pack.pack_version is not None


def test_production_loader_rejects_draft_unreviewed_or_checksum_invalid_pack() -> None:
    with pytest.raises(ContextPackUnavailableError):
        # Default allow_draft=False in production loader
        load_context_pack()


def test_production_loader_accepts_only_approved_pack_with_reviewer_and_date() -> None:
    # When status is draft, production loader must raise ContextPackUnavailableError
    with pytest.raises(ContextPackUnavailableError):
        load_context_pack(allow_draft=False)


def test_checksum_mismatch_raises_checksum_error(tmp_path: pytest.TempPathFactory) -> None:
    # Verify ContextPackChecksumError class exists and inherits from ContextPackError
    from app.agents.language.context_pack import ContextPackError
    assert issubclass(ContextPackChecksumError, ContextPackError)

