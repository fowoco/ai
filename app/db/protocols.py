# worker/company 조회·신분 슬롯 저장 인터페이스 (실구현은 memory 또는 외부 DB)

from __future__ import annotations

from typing import Any, Protocol


# 담당자 입력용 worker/company 조회
class WorkerCompanyLookup(Protocol):

    # worker_id로 근로자 레코드 조회
    def get_worker(self, worker_id: str | None) -> dict[str, Any] | None:
        ...

    # company_id로 사업장 레코드 조회
    def get_company(self, company_id: str | None) -> dict[str, Any] | None:
        ...


# 근로자 서류 OCR 매핑 결과 저장
class IdentityStore(Protocol):

    # 신분 슬롯을 영속 저장
    def save_identity_slots(
        self,
        *,
        worker_id: str | None,
        task_id: str,
        slots: dict[str, Any],
    ) -> None:
        ...
