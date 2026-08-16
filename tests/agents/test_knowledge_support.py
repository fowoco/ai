"""Knowledge 패키지 → Analyses 규칙 변환 테스트."""

import os
from pathlib import Path

import pytest

from app.agents.knowledge_support import (
    load_ambiguity_patterns,
    load_context_slots,
    load_knowledge_version,
    load_required_slots,
    load_workflow_catalog,
    try_get_repository,
)

KNOWLEDGE_ROOT = Path(
    os.getenv(
        "FOWOCO_KNOWLEDGE_ROOT",
        Path(__file__).resolve().parents[3] / "knowledge" / "fowoco-knowledge",
    )
)


@pytest.fixture
def repository():
    """테스트용 KnowledgeRepository (없으면 skip)."""
    pytest.importorskip("fowoco_knowledge")
    if not (KNOWLEDGE_ROOT / "knowledge" / "manifest.yaml").is_file():
        pytest.skip("local knowledge root not found")
    repo = try_get_repository(str(KNOWLEDGE_ROOT))
    if repo is None:
        pytest.skip("KnowledgeRepository unavailable")
    return repo


class _FakeRepository:
    manifest = {"version": "0.3.0"}

    def load_yaml(self, relative_path: str) -> dict:
        if relative_path == "knowledge/required_slots.yaml":
            return {
                "workflow_requirements": {
                    "WF-STY-001": {
                        "required": ["worker_id", "due_at"],
                        "resolvable_from_context": [
                            "worker_id",
                            "due_at",
                            "stay_expiry_date",
                            "passport_status",
                            "arc_status",
                        ],
                    }
                }
            }
        raise AssertionError(f"unexpected path: {relative_path}")

    def list_workflows(self) -> list[dict]:
        return [
            {
                "id": "WF-STY-001",
                "name": "체류기간 연장 준비와 제출 추적",
                "intent": "EXPIRY_RENEWAL",
                "sensitivity": "high",
                "supported_input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
            }
        ]


def test_loads_version_and_slot_roles_from_knowledge_030() -> None:
    fake = _FakeRepository()

    assert load_knowledge_version(fake) == "0.3.0"
    assert load_required_slots(fake)["WF-STY-001"] == ["worker_id", "due_at"]
    assert load_context_slots(fake)["WF-STY-001"] == [
        "worker_id",
        "due_at",
        "stay_expiry_date",
        "passport_status",
        "arc_status",
    ]

    catalog = load_workflow_catalog(fake)
    assert catalog["WF-STY-001"]["required_slots"] == ["worker_id", "due_at"]
    assert catalog["WF-STY-001"]["context_slots"][-2:] == [
        "passport_status",
        "arc_status",
    ]


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
