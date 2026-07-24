from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class FieldCandidate(BaseModel):
    """사용자 확인 전 단계의 입력 후보입니다."""

    model_config = ConfigDict(extra="forbid")

    target_id: str
    label_cell_id: str
    table_id: str
    label: str
    current_value: str
    kind: Literal["adjacent_blank_cell", "label_cell"]
    confidence: Literal["heuristic"]
    requires_user_confirmation: bool = True


def infer_field_candidates(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """표에서 라벨 다음의 빈 셀을 입력 후보로 추려 반환합니다."""
    candidates: list[FieldCandidate] = []
    used_label_cells: set[str] = set()
    for section in manifest["sections"]:
        for table in section["tables"]:
            cells_by_row: dict[int, list[dict[str, Any]]] = {}
            for cell in table["cells"]:
                cells_by_row.setdefault(cell["row"], []).append(cell)
            for row_cells in cells_by_row.values():
                ordered = sorted(row_cells, key=lambda cell: cell["column"])
                for label_cell, target_cell in zip(ordered, ordered[1:]):
                    label = label_cell["text"].strip()
                    if (
                        not label
                        or label.startswith("■")
                        or len(label) > 100
                        or target_cell["text"].strip()
                    ):
                        continue
                    candidates.append(
                        FieldCandidate(
                            target_id=target_cell["id"],
                            label_cell_id=label_cell["id"],
                            table_id=table["id"],
                            label=label,
                            current_value=target_cell["text"],
                            kind="adjacent_blank_cell",
                            confidence="heuristic",
                        )
                    )
                    used_label_cells.add(label_cell["id"])
                    used_label_cells.add(target_cell["id"])
            for cell in table["cells"]:
                text = cell["text"].strip()
                if cell["id"] in used_label_cells:
                    continue
                label = _known_label(text)
                if label is None:
                    continue
                candidates.append(
                    FieldCandidate(
                        target_id=cell["id"],
                        label_cell_id=cell["id"],
                        table_id=table["id"],
                        label=label,
                        current_value=cell["text"],
                        kind="label_cell",
                        confidence="heuristic",
                    )
                )
    return [candidate.model_dump() for candidate in candidates]


def _known_label(text: str) -> str | None:
    """첫 MVP에서 확인 질문을 만들 수 있는 대표 행정서식 라벨만 찾습니다."""
    for label in ("업체명", "전화번호", "소재지", "생년월일", "본국주소", "성명"):
        if label in text and not text.startswith("■"):
            return label
    return None
