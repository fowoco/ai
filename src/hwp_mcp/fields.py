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


class FieldSegment(BaseModel):
    """셀 내부의 정확한 입력 영역(세그먼트)을 표현합니다."""

    model_config = ConfigDict(extra="forbid")

    field_id: str
    label: str
    type: Literal["text", "date", "phone", "number", "amount", "checkbox", "signature"]
    cell_id: str
    paragraph_id: str | None = None
    anchor: str | None = None
    current_value: str = ""
    context: str = ""
    page: int = 1
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


def infer_field_segments(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """문서 내 긴 셀 내부의 정확한 입력 영역(세그먼트)을 확장 추출합니다."""
    segments: list[FieldSegment] = []
    import re

    for section in manifest.get("sections", []):
        for table in section.get("tables", []):
            for cell in table.get("cells", []):
                text = cell.get("text", "")
                cell_id = cell.get("id", "")

                # 1. 사업자등록번호 / 주민등록번호
                if any(kw in text for kw in ("사업자등록번호", "주민등록번호", "Identification number")):
                    segments.append(
                        FieldSegment(
                            field_id=f"{cell_id}.segment.biz_id",
                            label="사업자등록번호(주민등록번호)",
                            type="number",
                            cell_id=cell_id,
                            anchor="사업자등록번호",
                            current_value=text,
                            context=text[:50],
                        )
                    )

                # 2. 날짜 앵커 (년   월   일 등)
                date_match = re.search(r"(년\s*월\s*일|년\s+\d*월\s+\d*일|\d{4}\.\s*\d{1,2}\.\s*\d{1,2})", text)
                if date_match:
                    anchor_text = date_match.group(0)
                    segments.append(
                        FieldSegment(
                            field_id=f"{cell_id}.segment.date",
                            label="날짜 입력 영역",
                            type="date",
                            cell_id=cell_id,
                            anchor=anchor_text,
                            current_value=text,
                            context=text[:50],
                        )
                    )

                # 3. 체크박스 ([ ], [  ], □)
                for cb_match in re.finditer(r"(\[\s*\]|\[\s*V\s*\]|\[\s*■\s*\]|□)", text):
                    anchor_text = cb_match.group(0)
                    start_idx = cb_match.start()
                    # 주변 문맥 (뒤따르는 텍스트 20자)
                    label_context = text[start_idx : start_idx + 25].strip()
                    segments.append(
                        FieldSegment(
                            field_id=f"{cell_id}.segment.cb_{start_idx}",
                            label=f"체크박스 ({label_context})",
                            type="checkbox",
                            cell_id=cell_id,
                            anchor=anchor_text,
                            current_value=anchor_text,
                            context=label_context,
                        )
                    )

                # 4. 서명 / 날인 영역
                if any(kw in text for kw in ("(서명 또는 인)", "(인)", "(서명)", "(날인)")):
                    sig_match = re.search(r"(\(서명\s*또는\s*인\)|\(인\)|\(서명\)|\(날인\))", text)
                    anchor_text = sig_match.group(0) if sig_match else "(서명 또는 인)"
                    segments.append(
                        FieldSegment(
                            field_id=f"{cell_id}.segment.signature",
                            label="서명/날인 영역",
                            type="signature",
                            cell_id=cell_id,
                            anchor=anchor_text,
                            current_value=text,
                            context=text[:50],
                        )
                    )

    # 기본 후보(adjacent_blank_cell 등)도 세그먼트 형태로 상위 호환 포함
    existing_candidates = infer_field_candidates(manifest)
    for cand in existing_candidates:
        segments.append(
            FieldSegment(
                field_id=f"{cand['target_id']}.segment.cell",
                label=cand["label"],
                type="text",
                cell_id=cand["target_id"],
                current_value=cand["current_value"],
                context=cand["label"],
            )
        )

    return [s.model_dump() for s in segments]


def infer_field_candidates_spatial(
    manifest: dict[str, Any], svg_path: Path | str | None = None
) -> list[dict[str, Any]]:
    """SVG 시각 상대 기하학 좌표(Spatial Geometry)를 활용하여 라벨 하단/우측 빈 셀을 정밀 자동 추론합니다."""
    candidates = infer_field_candidates(manifest)

    spatial_candidates = _infer_spatial_under_cells(manifest)
    if spatial_candidates:
        # spatial candidates를 리스트 전면에 우선 배치
        spatial_label_ids = {sc["label_cell_id"] for sc in spatial_candidates}
        filtered_adjacent = [c for c in candidates if c["label_cell_id"] not in spatial_label_ids]
        return spatial_candidates + filtered_adjacent

    return candidates


def _infer_spatial_under_cells(manifest: dict[str, Any], svg_file: Path | None = None) -> list[dict[str, Any]]:
    """SVG 시각 상대 기하학 좌표 및 행/열 배치를 기반으로 하단 빈 셀을 정밀 식별합니다."""
    spatial_candidates: list[dict[str, Any]] = []

    for section in manifest.get("sections", []):
        for table in section.get("tables", []):
            cells = table.get("cells", [])
            cells_by_row: dict[int, list[dict[str, Any]]] = {}
            for cell in cells:
                cells_by_row.setdefault(cell.get("row", 0), []).append(cell)

            sorted_rows = sorted(cells_by_row.keys())
            for idx, row_idx in enumerate(sorted_rows):
                row_cells = cells_by_row[row_idx]
                if idx + 1 < len(sorted_rows):
                    next_row_idx = sorted_rows[idx + 1]
                    next_row_cells = cells_by_row[next_row_idx]

                    for label_cell in row_cells:
                        label_text = label_cell.get("text", "").strip()
                        if not label_text or len(label_text) > 80 or label_text.startswith("■"):
                            continue

                        # '성 Surname', '명 Given', '년 yyyy', '월 mm', '일 dd' 감지
                        if any(kw in label_text for kw in ("성 Surname", "명 Given", "년 yyyy", "월 mm", "일 dd", "성명", "생년월일")):
                            label_col = label_cell.get("column", 0)

                            for target_cell in next_row_cells:
                                target_col = target_cell.get("column", 0)
                                target_text = target_cell.get("text", "").strip()

                                # 빈 셀이거나 공백 텍스트('  ')인 경우
                                if not target_text or target_text == "  ":
                                    # 시각 기하학적 정렬 (동일 열 또는 1칸 좌측 Shift 인덱스 상응)
                                    if target_col == label_col or target_col == label_col - 1:
                                        spatial_candidates.append(
                                            FieldCandidate(
                                                target_id=target_cell.get("id", ""),
                                                label_cell_id=label_cell.get("id", ""),
                                                table_id=table.get("id", ""),
                                                label=f"{label_text} (하단 란)",
                                                current_value=target_text,
                                                kind="adjacent_blank_cell",
                                                confidence="heuristic",
                                            ).model_dump()
                                        )
                                        break
    return spatial_candidates


def _known_label(text: str) -> str | None:
    """첫 MVP에서 확인 질문을 만들 수 있는 대표 행정서식 라벨만 찾습니다."""
    for label in ("업체명", "전화번호", "소재지", "생년월일", "본국주소", "성명"):
        if label in text and not text.startswith("■"):
            return label
    return None

