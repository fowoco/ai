# 인메모리 DB — 로컬·테스트용. 프로세스 종료 시 내용 소멸

from __future__ import annotations

from typing import Any


# 조회·저장을 프로세스 메모리에 유지
class InMemoryDb:

    # 시드 데이터와 저장소 초기화
    def __init__(
        self,
        *,
        workers: dict[str, dict[str, Any]] | None = None,
        companies: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._workers = workers or {
            "worker-001": {
                "worker_id": "worker-001",
                "stay_expiry_date": "2026-12-31",
                "contract_end_date": "2026-11-30",
                "display_name": "Demo Worker",
            }
        }
        self._companies = companies or {
            "company-001": {"name": "FOWOCO Demo Co.", "business_number": "000-00-00000"}
        }
        self.identity_saves: list[dict[str, Any]] = []

    # worker_id로 레코드 조회
    def get_worker(self, worker_id: str | None) -> dict[str, Any] | None:
        if not worker_id:
            return None
        return self._workers.get(worker_id)

    # company_id로 레코드 조회
    def get_company(self, company_id: str | None) -> dict[str, Any] | None:
        if not company_id:
            return None
        return self._companies.get(company_id)

    # OCR 신분 슬롯을 메모리에 기록
    def save_identity_slots(
        self,
        *,
        worker_id: str | None,
        task_id: str,
        slots: dict[str, Any],
    ) -> None:
        self.identity_saves.append(
            {"worker_id": worker_id, "task_id": task_id, "slots": dict(slots)}
        )
        if worker_id and worker_id in self._workers:
            self._workers[worker_id] = {**self._workers[worker_id], **slots}
