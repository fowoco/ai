"""Coordinator Internal HTTP routes (프로토타입).

경로 prefix: /internal/coordinator
- client는 이 경로를 호출하지 않는다.
- client 공개 API는 server의 /api/work-items 이다.
- 영속·승인·권한은 server가 담당한다.

AI 쪽 핵심 엔드포인트:
  POST .../propose-split       복합 요청 분리 초안 (비영속)
  POST .../validate-transition 전이 가능 여부 검증 (저장 불필요)

아래 work-items/* 는 로컬 상태머신 검증용 임시 저장소다.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_coordinator_service
from app.api.openapi import COORDINATOR_TAG
from app.api.schemas.coordinator import (
    AllowedTransitionsResponse,
    CompositeCreateRequest,
    TaskCardCreateRequest,
    TaskCardResponse,
    TransitionRequest,
    ValidateTransitionRequest,
    ValidateTransitionResponse,
)
from app.coordinator import CoordinatorService, TaskCardCreate, TransitionError
from app.coordinator.transitions import TaskStatus

router = APIRouter(prefix="/internal/coordinator", tags=[COORDINATOR_TAG])


def _card_create(req: TaskCardCreateRequest) -> TaskCardCreate:
    return TaskCardCreate(
        workflow_id=req.workflow_id,
        title=req.title,
        slots=req.slots,
        source_request_id=req.source_request_id,
        worker_id=req.worker_id,
    )


@router.post("/propose-split", response_model=list[TaskCardResponse])
def propose_split(
    body: CompositeCreateRequest,
    service: Annotated[CoordinatorService, Depends(get_coordinator_service)],
) -> list[TaskCardResponse]:
    """복합 요청을 Workflow별 초안 카드로 분리한다. 저장하지 않는다."""
    creates = [_card_create(c) for c in body.cards]
    cards = service.propose_split(creates, source_request_id=body.source_request_id)
    return [TaskCardResponse(**c.model_dump()) for c in cards]


@router.post("/validate-transition", response_model=ValidateTransitionResponse)
def validate_transition(
    body: ValidateTransitionRequest,
    service: Annotated[CoordinatorService, Depends(get_coordinator_service)],
) -> ValidateTransitionResponse:
    """상태 전이 가능 여부를 검증한다. 카드 저장과 무관하다."""
    result = service.validate_transition(body.current, body.target)
    return ValidateTransitionResponse(**result)


# --- 프로토타입 인메모리 WorkItem 시뮬레이터 (server 이전 전 임시) ---


@router.post("/work-items", response_model=TaskCardResponse, status_code=201)
def create_work_item(
    body: TaskCardCreateRequest,
    service: Annotated[CoordinatorService, Depends(get_coordinator_service)],
) -> TaskCardResponse:
    """[프로토타입] 인메모리 업무카드 생성. 운영에서는 server /api/work-items 사용."""
    card = service.create_card(_card_create(body))
    return TaskCardResponse(**card.model_dump())


@router.post("/work-items/composite", response_model=list[TaskCardResponse], status_code=201)
def create_composite_work_items(
    body: CompositeCreateRequest,
    service: Annotated[CoordinatorService, Depends(get_coordinator_service)],
) -> list[TaskCardResponse]:
    """[프로토타입] 복합 분리 후 인메모리 저장. 운영에서는 propose-split + server 생성."""
    creates = [_card_create(c) for c in body.cards]
    cards = service.create_composite(creates, source_request_id=body.source_request_id)
    return [TaskCardResponse(**c.model_dump()) for c in cards]


@router.get("/work-items", response_model=list[TaskCardResponse])
def list_work_items(
    service: Annotated[CoordinatorService, Depends(get_coordinator_service)],
    status: str | None = None,
    workflow_id: str | None = None,
    worker_id: str | None = None,
    group_id: UUID | None = None,
) -> list[TaskCardResponse]:
    """[프로토타입] 인메모리 목록 조회."""
    status_enum = TaskStatus(status) if status else None
    cards = service.list_cards(
        status=status_enum,
        workflow_id=workflow_id,
        worker_id=worker_id,
        group_id=group_id,
    )
    return [TaskCardResponse(**c.model_dump()) for c in cards]


@router.get("/work-items/{card_id}", response_model=TaskCardResponse)
def get_work_item(
    card_id: UUID,
    service: Annotated[CoordinatorService, Depends(get_coordinator_service)],
) -> TaskCardResponse:
    """[프로토타입] 인메모리 상세 조회."""
    card = service.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"TaskCard not found: {card_id}")
    return TaskCardResponse(**card.model_dump())


@router.get("/work-items/{card_id}/transitions", response_model=AllowedTransitionsResponse)
def get_work_item_transitions(
    card_id: UUID,
    service: Annotated[CoordinatorService, Depends(get_coordinator_service)],
) -> AllowedTransitionsResponse:
    """[프로토타입] 저장된 카드 기준 허용 전이 목록."""
    try:
        allowed = service.get_allowed_transitions(card_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"TaskCard not found: {card_id}") from exc
    card = service.get_card(card_id)
    assert card is not None
    return AllowedTransitionsResponse(
        card_id=card.id,
        current=card.status,
        allowed=allowed,
    )


@router.post("/work-items/{card_id}/transition", response_model=TaskCardResponse)
def transition_work_item(
    card_id: UUID,
    body: TransitionRequest,
    service: Annotated[CoordinatorService, Depends(get_coordinator_service)],
) -> TaskCardResponse:
    """[프로토타입] 인메모리 상태 전이. 운영에서는 server가 승인 게이트와 함께 처리."""
    try:
        card = service.transition(card_id, body.target, reason=body.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"TaskCard not found: {card_id}") from exc
    except TransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TaskCardResponse(**card.model_dump())
