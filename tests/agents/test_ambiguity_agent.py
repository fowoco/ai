"""Ambiguity Agent 유닛 테스트."""

from app.agents.ambiguity import AmbiguityAgent


def test_detects_missing_slots() -> None:
    agent = AmbiguityAgent()
    result = agent.check("WF-STY-001", {"worker_id": "W-1"}, "체류 연장")
    assert "stay_expiry_date" in result.missing_slots
    assert result.has_issues


def test_no_missing_when_all_provided() -> None:
    agent = AmbiguityAgent()
    result = agent.check(
        "WF-STY-001",
        {"worker_id": "W-1", "stay_expiry_date": "2026-12-31"},
        "체류 연장",
    )
    assert result.missing_slots == []


def test_detects_ambiguous_terms() -> None:
    agent = AmbiguityAgent()
    slots = {"worker_id": "W-1", "document_type": "여권"}
    result = agent.check("WF-DOC-001", slots, "조만간 처리해줘")
    assert len(result.ambiguities) >= 2
    categories = {a.category for a in result.ambiguities}
    assert "TIME" in categories
    assert "ACTION" in categories
    assert result.has_issues


def test_no_issues() -> None:
    agent = AmbiguityAgent()
    result = agent.check("WF-INS-001", {"worker_id": "W-1"}, "내일 출근 스케줄 안내")
    assert not result.has_issues
