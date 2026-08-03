# Knowledge 패키지 선택 로드 — 없으면 builtin 규칙 유지

from __future__ import annotations

from typing import Any


# Knowledge 미설치·미설정 시 None → builtin 규칙 폴백
# fowoco_knowledge.KnowledgeRepository 로드 실패 시 None
def try_get_repository(root: str | None = None) -> Any | None:
    try:
        from fowoco_knowledge import KnowledgeRepository
        from fowoco_knowledge.repository import KnowledgeNotFoundError
    except ImportError:
        return None
    try:
        return KnowledgeRepository(root=root) if root else KnowledgeRepository()
    except KnowledgeNotFoundError:
        return None
    except Exception:
        return None


# workflow_requirements.required 목록을 AmbiguityAgent용 dict로 변환
# Knowledge required_slots.yaml에서 워크플로별 필수 slot 로드
def load_required_slots(repository: Any) -> dict[str, list[str]]:
    data = repository.load_yaml("knowledge/required_slots.yaml")
    requirements = data.get("workflow_requirements", {})
    result: dict[str, list[str]] = {}
    for workflow_id, cfg in requirements.items():
        required = cfg.get("required", [])
        if isinstance(required, list):
            result[str(workflow_id)] = [str(s) for s in required]
    return result


# ambiguity_patterns.yaml terms → 에이전트 단건 패턴 리스트
# Knowledge 모호표현을 AmbiguityAgent가 쓰는 단건 패턴으로 변환
def load_ambiguity_patterns(repository: Any) -> list[dict[str, str]]:
    data = repository.load_yaml("knowledge/ambiguity_patterns.yaml")
    patterns: list[dict[str, str]] = []
    for entry in data.get("patterns", []):
        terms = entry.get("terms", [])
        question = str(entry.get("question_template", "추가 정보를 입력해 주세요."))
        pattern_id = str(entry.get("id", "AMB-UNKNOWN"))
        category = str(entry.get("category", "OBJECT"))
        for term in terms:
            patterns.append(
                {
                    "pattern_id": pattern_id,
                    "category": category,
                    "term": str(term),
                    "question": question,
                }
            )
    return patterns


# workflow_catalog.yaml을 WorkflowAgent builtin 형태로 변환
# Knowledge Workflow 목록을 내부 카탈로그 dict로 변환
def load_workflow_catalog(repository: Any) -> dict[str, dict[str, object]]:
    catalog: dict[str, dict[str, object]] = {}
    for workflow in repository.list_workflows():
        workflow_id = str(workflow["id"])
        catalog[workflow_id] = {
            "name": str(workflow.get("name", "")),
            "intent": str(workflow.get("intent", "")),
            "sensitivity": str(workflow.get("sensitivity", "medium")),
            "required_slots": [],
            "input_modes": list(workflow.get("supported_input_modes", [])),
        }
    # required_slots_ref가 있으면 required_slots.yaml에서 채움
    required_map = load_required_slots(repository)
    for workflow_id, entry in catalog.items():
        entry["required_slots"] = required_map.get(workflow_id, [])
    return catalog
