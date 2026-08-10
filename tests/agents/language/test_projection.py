from copy import deepcopy

from app.agents.language.projection import project_language_input


def test_projection_keeps_only_approved_fields() -> None:
    parent = {
        "worker_id": "worker-1",
        "preferred_language": "vi",
        "nationality_code": "VN",
        "request_context": {
            "request_reason": "체류기간 연장 신청",
            "requested_items": ["여권 사본"],
            "deadline": "2026-08-10",
            "submission_method": "이메일로 보내 주세요.",
        },
        "source_text": "이 값을 사용하지 말 것",
        "worker": {"stay_expiry_date": "2099-01-01"},
        "worker_documents": [{"name": "private.pdf"}],
        "company": {"name": "private-company"},
    }
    before = deepcopy(parent)

    projected = project_language_input(parent)

    assert projected.model_dump(mode="json") == {
        "worker_id": "worker-1",
        "preferred_language": "vi",
        "nationality_code": "VN",
        "request_context": {
            "request_reason": "체류기간 연장 신청",
            "requested_items": ["여권 사본"],
            "deadline": "2026-08-10",
            "submission_method": "이메일로 보내 주세요.",
        },
    }
    assert parent == before
    assert "worker" not in projected.model_dump()
    assert "worker_documents" not in projected.model_dump()
    assert "company" not in projected.model_dump()


def test_projection_is_metamorphic_over_parent_database_context() -> None:
    approved = {
        "worker_id": 1,
        "preferred_language": None,
        "nationality_code": "VN",
        "request_context": {
            "request_reason": "서류 제출",
            "requested_items": ["여권"],
            "deadline": "2026-08-10",
            "submission_method": "이메일",
        },
    }
    first = {
        **approved,
        "source_text": "first",
        "worker": {"stay_expiry_date": "2026-01-01"},
        "worker_documents": ["a"],
        "company": {"name": "A"},
    }
    second = {
        **approved,
        "source_text": "second",
        "worker": {"stay_expiry_date": "2030-01-01"},
        "worker_documents": ["b", "c"],
        "company": {"name": "B"},
    }

    assert project_language_input(first) == project_language_input(second)
    assert first["source_text"] != second["source_text"]


def test_projection_rejects_missing_approved_input() -> None:
    parent = {
        "worker_id": "worker-1",
        "preferred_language": "vi",
        "nationality_code": "VN",
    }

    try:
        project_language_input(parent)
    except Exception as exc:
        assert exc.__class__.__name__ == "ValidationError"
    else:
        raise AssertionError("missing request_context must fail")
