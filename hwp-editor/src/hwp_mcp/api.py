from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .fields import Disposition
from .hwpx import DocumentError
from .plans import CellEditInput
from .server import (
    analyze_document as analyze_mcp_document,
    apply_edit_plan as apply_mcp_edit_plan,
    compare_document_versions as compare_mcp_versions,
    confirm_visual_candidates as confirm_mcp_visual_candidates,
    create_edit_plan as create_mcp_edit_plan,
    finalize_document as finalize_mcp_document,
)


class DocumentRequest(BaseModel):
    """허용 작업 루트 기준 문서 경로입니다."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)


class CreatePlanRequest(DocumentRequest):
    """문서 경로와 셀 변경 요청입니다."""

    edits: list[CellEditInput] = Field(min_length=1, max_length=100)
    dispositions: dict[str, Disposition]


class ApplyPlanRequest(BaseModel):
    """서버 승인 receipt가 있는 계획을 적용합니다."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)
    plan_id: str = Field(min_length=64, max_length=64)


class CompareRequest(BaseModel):
    """두 문서의 시각/구조 비교 요청입니다."""

    model_config = ConfigDict(extra="forbid")

    original_path: str = Field(min_length=1, max_length=4096)
    modified_path: str = Field(min_length=1, max_length=4096)
    output_dir: str = Field(min_length=1, max_length=4096)
    debug_overlay: bool = True


class VisualCandidatesRequest(DocumentRequest):
    """Vision이 제안하고 사람이 판정한 시각 후보입니다."""

    candidates: list[dict[str, Any]] = Field(max_length=500)


class FinalizeRequest(DocumentRequest):
    """서버 Vision PASS를 받은 attempt 최종화 요청입니다."""

    plan_id: str = Field(min_length=64, max_length=64)


def create_app() -> FastAPI:
    """MCP와 같은 로컬 기능을 HTTP로 노출하는 얇은 Control Plane을 만듭니다."""
    app = FastAPI(title="HWPX Editor Control Plane", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "transport": "http"}

    @app.post("/documents/analyze")
    def analyze_document(request: DocumentRequest) -> dict[str, Any]:
        return _call(analyze_mcp_document, request.path)

    @app.post("/plans/create")
    def create_edit_plan(request: CreatePlanRequest) -> dict[str, Any]:
        return _call(
            create_mcp_edit_plan,
            request.path,
            request.edits,
            request.dispositions,
        )

    @app.post("/plans/apply")
    def apply_edit_plan(request: ApplyPlanRequest) -> dict[str, Any]:
        return _call(
            apply_mcp_edit_plan,
            request.path,
            request.plan_id,
        )

    @app.post("/documents/visual-candidates/confirm")
    def confirm_visual_candidates(request: VisualCandidatesRequest) -> dict[str, Any]:
        return _call(
            confirm_mcp_visual_candidates,
            request.path,
            request.candidates,
        )

    @app.post("/documents/finalize")
    def finalize_document(request: FinalizeRequest) -> dict[str, Any]:
        return _call(
            finalize_mcp_document,
            request.path,
            request.plan_id,
        )

    @app.post("/compare/versions")
    def compare_versions(request: CompareRequest) -> dict[str, Any]:
        return _call(
            compare_mcp_versions,
            request.original_path,
            request.modified_path,
            request.output_dir,
            request.debug_overlay,
        )

    return app


def _call(function: Any, *args: Any) -> dict[str, Any]:
    try:
        return function(*args)
    except DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("hwp_mcp.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
