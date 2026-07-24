from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .hwpx import DocumentError
from .plans import CellEditInput, EditPlan
from .server import (
    analyze_document as analyze_mcp_document,
    apply_edit_plan as apply_mcp_edit_plan,
    create_edit_plan as create_mcp_edit_plan,
)


class DocumentRequest(BaseModel):
    """허용 작업 루트 기준 문서 경로입니다."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)


class CreatePlanRequest(DocumentRequest):
    """문서 경로와 셀 변경 요청입니다."""

    edits: list[CellEditInput] = Field(min_length=1, max_length=100)


class ApplyPlanRequest(BaseModel):
    """승인된 계획을 적용할 경로와 검토 설정입니다."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)
    output_path: str = Field(min_length=1, max_length=4096)
    plan: EditPlan
    approved: bool = False
    review_output_dir: str | None = Field(default=None, max_length=4096)


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
        return _call(create_mcp_edit_plan, request.path, request.edits)

    @app.post("/plans/apply")
    def apply_edit_plan(request: ApplyPlanRequest) -> dict[str, Any]:
        return _call(
            apply_mcp_edit_plan,
            request.path,
            request.output_path,
            request.plan,
            request.approved,
            request.review_output_dir,
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
