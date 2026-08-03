"""Knowledge 패키지 → Analyses 규칙 변환 테스트."""

from pathlib import Path

import pytest

from app.agents.knowledge_support import (
    load_ambiguity_patterns,
    load_required_slots,
    load_workflow_catalog,
    try_get_repository,
)

KNOWLEDGE_ROOT = (
    Path(__file__).resolve().parents[3] / "knowledge" / "fowoco-knowledge"
)


# knowledge 패키지·루트가 없으면 해당 테스트를 건너뛴다.
pytest.importorskip("fowoco_knowledge")


@pytest.fixture
def repository():
    """테스트용 KnowledgeRepository (없으면 skip)."""
    if not (KNOWLEDGE_ROOT / "knowledge" / "manifest.yaml").is_file():
        pytest.skip("local knowledge root not found")
    repo = try_get_repository(str(KNOWLEDGE_ROOT))
    if repo is None:
        pytest.skip("KnowledgeRepository unavailable")
    return repo


def test_load_required_slots_contains_stay_workflow(repository) -> None:
    """체류연장 워크플로 필수 slot이 knowledge에서 로드된다."""
    slots = load_required_slots(repository)
    assert "WF-STY-001" in slots
    assert "worker_id" in slots["WF-STY-001"]


def test_load_workflow_catalog_has_eight_workflows(repository) -> None:
    """표준 워크플로 8개가 카탈로그에 포함된다."""
    catalog = load_workflow_catalog(repository)
    assert len(catalog) >= 8
    assert catalog["WF-STY-001"]["intent"] == "EXPIRY_RENEWAL"


def test_load_ambiguity_patterns_flattens_terms(repository) -> None:
    """모호표현 terms가 단건 패턴 리스트로 펼쳐진다."""
    patterns = load_ambiguity_patterns(repository)
    assert len(patterns) > 0
    assert {"pattern_id", "category", "term", "question"} <= set(patterns[0])
