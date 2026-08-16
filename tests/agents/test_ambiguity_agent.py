# Ambiguity Agent 유닛 테스트

from app.agents.ambiguity import AmbiguityAgent


def test_detects_missing_slots() -> None:
    agent = AmbiguityAgent()
    result = agent.check("WF-STY-001", {"worker_id": "W-1"}, "체류 연장")
    assert result.missing_slots == ["due_at"]
    assert result.has_issues


def test_no_missing_when_all_provided() -> None:
    agent = AmbiguityAgent()
    result = agent.check(
        "WF-STY-001",
        {"worker_id": "W-1", "due_at": "2026-10-01T09:00:00+09:00"},
        "체류 연장",
    )
    assert result.missing_slots == []


def test_builtin_has_no_ungrounded_ambiguity_patterns() -> None:
    agent = AmbiguityAgent()
    result = agent.check(
        "WF-DOC-001",
        {"worker_id": "W-1", "document_type": "여권"},
        "조만간 처리해줘",
    )
    assert result.ambiguities == []


def test_detects_ambiguous_terms_when_knowledge_patterns_injected() -> None:
    # Knowledge ambiguity_patterns.yaml 형태를 주입했을 때만 탐지
    agent = AmbiguityAgent(
        ambiguity_patterns=[
            {
                "pattern_id": "AMB-OBJECT-001",
                "category": "OBJECT",
                "term": "그거",
                "question": "정확한 서류명 또는 대상 번호를 입력해 주세요.",
            },
            {
                "pattern_id": "AMB-ACTION-001",
                "category": "ACTION",
                "term": "처리해줘",
                "question": "확인, 안내, 서류 작성 중 어떤 결과가 필요한지 선택해 주세요.",
            },
        ]
    )
    slots = {"worker_id": "W-1", "document_type": "여권"}
    result = agent.check("WF-DOC-001", slots, "그거 처리해줘")
    assert len(result.ambiguities) == 2
    categories = {a.category for a in result.ambiguities}
    assert "OBJECT" in categories
    assert "ACTION" in categories
    assert result.has_issues


def test_no_issues() -> None:
    agent = AmbiguityAgent()
    result = agent.check(
        "WF-INS-001",
        {
            "worker_id": "W-1",
            "effective_at": "2026-08-17T07:00:00+09:00",
            "work_action": "2공장으로 출근",
        },
        "내일 출근 스케줄 안내",
    )
    assert not result.has_issues
