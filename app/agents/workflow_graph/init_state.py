# Server worker·company·task 일괄 JSON → 단일 RenewalState 초기화

from __future__ import annotations

import json
from typing import Any

from .state import RenewalState, empty_renewal_state


# worker/company/task dict에서 slots·레코드 선채움
def slots_from_server_bundle(
    *,
    worker: dict[str, Any] | None = None,
    company: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
    slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(slots or {})
    if worker:
        for key in (
            "worker_id",
            "stay_expiry_date",
            "contract_end_date",
            "contract_start_date",
            "nationality_code",
            "preferred_language",
            "work_status",
            "display_name",
        ):
            if worker.get(key) and key not in merged:
                merged[key] = worker[key]
        if worker.get("display_name") and "full_name" not in merged:
            merged["full_name"] = worker["display_name"]
        if worker.get("nationality_code") and "nationality" not in merged:
            merged["nationality"] = worker["nationality_code"]
        if worker.get("worker_id") and "worker_id" not in merged:
            merged["worker_id"] = worker["worker_id"]
    if company:
        if company.get("company_id") and "company_id" not in merged:
            merged["company_id"] = company["company_id"]
        if company.get("name") and "enterprise_name" not in merged:
            merged["enterprise_name"] = company["name"]
    if task:
        raw = task.get("business_data_json") or task.get("businessDataJson")
        if isinstance(raw, str) and raw.strip():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
            if isinstance(data, dict):
                for k, v in data.items():
                    if k not in merged and v not in (None, ""):
                        merged[k] = v
        elif isinstance(raw, dict):
            for k, v in raw.items():
                if k not in merged and v not in (None, ""):
                    merged[k] = v
    return merged


# Server 일괄 페이로드로 Shared State 초깃값 생성
def init_renewal_state_from_bundle(
    *,
    request_id: str,
    instruction: str,
    task_id: str | None = None,
    worker_id: str | None = None,
    company_id: str | None = None,
    slots: dict[str, Any] | None = None,
    documents: list[dict[str, Any]] | None = None,
    worker: dict[str, Any] | None = None,
    company: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
) -> RenewalState:
    worker = dict(worker or {})
    company = dict(company or {})
    task = dict(task or {})
    resolved_task_id = task_id or task.get("task_id") or task.get("taskId") or ""
    resolved_worker = worker_id or worker.get("worker_id") or worker.get("workerId")
    resolved_company = company_id or company.get("company_id") or company.get("companyId")
    if resolved_worker and "worker_id" not in worker:
        worker["worker_id"] = resolved_worker
    if resolved_company and "company_id" not in company:
        company["company_id"] = resolved_company

    merged_slots = slots_from_server_bundle(
        worker=worker or None,
        company=company or None,
        task=task or None,
        slots=slots,
    )
    state = empty_renewal_state(
        task_id=str(resolved_task_id),
        request_id=request_id,
        instruction=instruction,
        worker_id=resolved_worker,
        company_id=resolved_company,
        slots=merged_slots,
        documents=documents,
    )
    if worker:
        state["worker_record"] = worker
    if company:
        state["company_record"] = company
    wf = task.get("workflow_id") or task.get("workflowId")
    if wf:
        state["workflow_id"] = str(wf)
    return state
