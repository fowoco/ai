"""Coordinator 오케스트레이션 프로토타입.

역할 (AI):
  - 복합 요청을 Workflow별 카드 초안으로 분리 (split_and_confirm)
  - knowledge 9상태 전이 가능 여부 검증·추천
  - LLM 호출 없음

역할이 아닌 것 (server):
  - WorkItem 영속 저장, HR 승인 게이트, 인증·알림
  - client용 `/api/work-items` 공개 API

인메모리 저장소는 로컬 검증용이며, server 연동 후 제거하거나
server Internal 호출로 대체한다.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from .models import TaskCard, TaskCardCreate
from .transitions import TaskStatus, allowed_targets, can_transition


class CoordinatorService:
    """전이 규칙·복합 분리를 검증하는 프로토타입 서비스."""

    def __init__(self) -> None:
        self._cards: dict[UUID, TaskCard] = {}

    def propose_split(
        self,
        requests: list[TaskCardCreate],
        *,
        source_request_id: str | None = None,
    ) -> list[TaskCard]:
        """복합 요청을 Workflow별 초안 카드로 분리한다. 영속화하지 않는다."""
        group_id = uuid4()
        shared_worker_id = _extract_shared_worker_id(requests)
        cards: list[TaskCard] = []
        for req in requests:
            cards.append(
                TaskCard(
                    workflow_id=req.workflow_id,
                    title=req.title,
                    slots=req.slots,
                    source_request_id=source_request_id or req.source_request_id,
                    worker_id=req.worker_id or shared_worker_id,
                    group_id=group_id,
                )
            )
        return cards

    def validate_transition(
        self, current: TaskStatus, target: TaskStatus
    ) -> dict[str, object]:
        """상태 전이 가능 여부를 반환한다. 카드 저장과 무관하다."""
        return {
            "current": current,
            "target": target,
            "allowed": can_transition(current, target),
            "allowed_targets": allowed_targets(current),
        }

    # --- 아래는 로컬 프로토타입 저장소 (server 이전 전 임시) ---

    def create_card(self, request: TaskCardCreate) -> TaskCard:
        card = TaskCard(
            workflow_id=request.workflow_id,
            title=request.title,
            slots=request.slots,
            source_request_id=request.source_request_id,
            worker_id=request.worker_id,
        )
        self._cards[card.id] = card
        return card

    def create_composite(
        self,
        requests: list[TaskCardCreate],
        *,
        source_request_id: str | None = None,
    ) -> list[TaskCard]:
        cards = self.propose_split(requests, source_request_id=source_request_id)
        for card in cards:
            self._cards[card.id] = card
        return cards

    def get_card(self, card_id: UUID) -> TaskCard | None:
        return self._cards.get(card_id)

    def list_cards(
        self,
        *,
        status: TaskStatus | None = None,
        workflow_id: str | None = None,
        worker_id: str | None = None,
        group_id: UUID | None = None,
    ) -> list[TaskCard]:
        cards = list(self._cards.values())
        if status is not None:
            cards = [c for c in cards if c.status == status]
        if workflow_id is not None:
            cards = [c for c in cards if c.workflow_id == workflow_id]
        if worker_id is not None:
            cards = [c for c in cards if c.worker_id == worker_id]
        if group_id is not None:
            cards = [c for c in cards if c.group_id == group_id]
        return sorted(cards, key=lambda c: c.created_at)

    def transition(
        self, card_id: UUID, target: TaskStatus, *, reason: str = ""
    ) -> TaskCard:
        card = self._cards.get(card_id)
        if card is None:
            raise KeyError(f"TaskCard not found: {card_id}")
        card.transition_to(target, reason=reason)
        return card

    def get_allowed_transitions(self, card_id: UUID) -> list[TaskStatus]:
        card = self._cards.get(card_id)
        if card is None:
            raise KeyError(f"TaskCard not found: {card_id}")
        return allowed_targets(card.status)

    def add_evidence(self, card_id: UUID, key: str, value: object) -> TaskCard:
        card = self._cards.get(card_id)
        if card is None:
            raise KeyError(f"TaskCard not found: {card_id}")
        card.evidence[key] = value
        return card


def _extract_shared_worker_id(requests: list[TaskCardCreate]) -> str | None:
    ids = {
        r.worker_id or r.slots.get("worker_id")
        for r in requests
        if r.worker_id or r.slots.get("worker_id")
    }
    if len(ids) == 1:
        return ids.pop()
    return None
