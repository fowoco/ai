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


# ──────────────────────────────────────────────────────────────
# XML Field Registry: 문서의 채울 수 있는 모든 필드를 기계적으로 추출
# ──────────────────────────────────────────────────────────────

_OFFICIAL_USE_KEYWORDS = ("공 용 란", "공용란", "For Official Use", "결     재", "결재", "수입인지")

RegistryFieldType = Literal[
    "checkbox", "checkbox_group", "text", "date", "phone",
    "number", "amount", "signature", "placeholder",
]


class RegistryField(BaseModel):
    """XML에서 기계적으로 추출된 단일 필드 엔트리."""

    model_config = ConfigDict(extra="forbid")

    field_id: str
    target_id: str
    label: str
    type: RegistryFieldType
    category: str  # "step1_application", "step2_personal", "step3_address", "step4_signature"
    row: int
    column: int
    current_text: str
    required: bool = True
    options: list[str] | None = None  # checkbox_group의 선택지


def infer_all_fields(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """XML manifest에서 채울 수 있는 모든 필드를 기계적으로 추출합니다 (Field Registry).

    체크박스, 빈 셀, 하단 빈 셀, 플레이스홀더를 모두 탐지하고
    공용란(관용구)은 자동 제외합니다.
    """
    import re
    from pathlib import Path

    registry: list[RegistryField] = []
    seen_ids: set[str] = set()

    # 공용란 시작 행 감지
    official_start_row: int | None = None

    for section in manifest.get("sections", []):
        for table in section.get("tables", []):
            cells = table.get("cells", [])
            cells_by_row: dict[int, list[dict[str, Any]]] = {}
            for cell in cells:
                cells_by_row.setdefault(cell.get("row", 0), []).append(cell)

            # Pass 0: 공용란 시작 행 감지
            for cell in cells:
                text = cell.get("text", "")
                if any(kw in text for kw in _OFFICIAL_USE_KEYWORDS):
                    row = cell.get("row", 9999)
                    if official_start_row is None or row < official_start_row:
                        official_start_row = row

            # Pass 1: 체크박스 필드 탐지
            for cell in cells:
                row = cell.get("row", 0)
                if official_start_row is not None and row >= official_start_row:
                    continue
                text = cell.get("text", "")
                cell_id = cell.get("id", "")
                col = cell.get("column", 0)

                # \[\s+\] 또는 \[\s*\] 패턴 감지
                brackets = re.findall(r"\[\s*\]", text)
                if brackets:
                    # 라벨 추출: 브래킷 앞 텍스트(라벨[ ])와 뒤 텍스트([ ]라벨) 모두 시도
                    before = re.findall(r"([가-힣A-Za-z][^\[\]]*?)\s*\[\s*\]", text)
                    after = re.findall(r"\[\s*\]\s*([가-힣A-Za-z][^\[\]]*)", text)
                    before_clean = [lb.strip().strip(",").strip() for lb in before if lb.strip().strip(",").strip()]
                    after_clean = [lb.strip().strip(",").strip() for lb in after if lb.strip().strip(",").strip()]
                    # 더 많은 쪽 우선 (before: 미취학[ ], after: [ ]남 M)
                    labels = before_clean if len(before_clean) >= len(after_clean) else after_clean if after_clean else before_clean

                    if len(labels) > 1:
                        # checkbox_group: [ ]남 M[ ]여 F / 미취학[ ], 초[ ], 중[ ], 고[ ]
                        registry.append(RegistryField(
                            field_id=f"{cell_id}.checkbox_group",
                            target_id=cell_id,
                            label=" / ".join(labels[:4]),
                            type="checkbox_group",
                            category=_categorize_row(row),
                            row=row, column=col,
                            current_text=text,
                            required=_is_required_field(text),
                            options=labels,
                        ))
                    elif len(labels) == 1:
                        registry.append(RegistryField(
                            field_id=f"{cell_id}.checkbox",
                            target_id=cell_id,
                            label=labels[0],
                            type="checkbox",
                            category=_categorize_row(row),
                            row=row, column=col,
                            current_text=text,
                            required=False,
                        ))
                    elif brackets:
                        # 브래킷은 있지만 라벨 추출 실패 — 텍스트 전체를 라벨로
                        clean_label = re.sub(r"\[\s*\]", "", text).strip()[:60]
                        if clean_label:
                            registry.append(RegistryField(
                                field_id=f"{cell_id}.checkbox",
                                target_id=cell_id,
                                label=clean_label,
                                type="checkbox",
                                category=_categorize_row(row),
                                row=row, column=col,
                                current_text=text,
                                required=False,
                            ))
                    seen_ids.add(cell_id)

            # Pass 2: 플레이스홀더 필드 탐지 (희망 자격 :        )
            for cell in cells:
                row = cell.get("row", 0)
                if official_start_row is not None and row >= official_start_row:
                    continue
                cell_id = cell.get("id", "")
                if cell_id in seen_ids:
                    continue
                text = cell.get("text", "")
                col = cell.get("column", 0)

                placeholder_match = re.search(r"[(\（]([^)）]+?)\s*:\s*\s{4,}[)\）]", text)
                if placeholder_match:
                    registry.append(RegistryField(
                        field_id=f"{cell_id}.placeholder",
                        target_id=cell_id,
                        label=placeholder_match.group(1).strip(),
                        type="placeholder",
                        category=_categorize_row(row),
                        row=row, column=col,
                        current_text=text,
                        required=False,
                    ))
                    seen_ids.add(cell_id)

            # Pass 3: 빈 셀 필드 탐지 (같은 행 라벨→옆 빈 셀)
            sorted_rows = sorted(cells_by_row.keys())
            for row_idx in sorted_rows:
                if official_start_row is not None and row_idx >= official_start_row:
                    continue
                row_cells = sorted(cells_by_row[row_idx], key=lambda c: c.get("column", 0))
                for label_cell, target_cell in zip(row_cells, row_cells[1:]):
                    label_text = label_cell.get("text", "").strip()
                    target_text = target_cell.get("text", "").strip()
                    target_id = target_cell.get("id", "")

                    if target_id in seen_ids:
                        continue
                    if not label_text or label_text.startswith("■") or len(label_text) > 120:
                        continue
                    if target_text:
                        continue
                    # 라벨 셀 자체가 체크박스이면 스킵
                    if re.search(r"\[\s*\]", label_text):
                        continue

                    field_type = _guess_field_type(label_text)
                    registry.append(RegistryField(
                        field_id=f"{target_id}.blank",
                        target_id=target_id,
                        label=label_text[:60],
                        type=field_type,
                        category=_categorize_row(row_idx),
                        row=row_idx, column=target_cell.get("column", 0),
                        current_text="",
                        required=_is_required_field(label_text),
                    ))
                    seen_ids.add(target_id)

            # Pass 4: 하단 빈 셀 (Spatial Geometry)
            for idx, row_idx in enumerate(sorted_rows):
                if official_start_row is not None and row_idx >= official_start_row:
                    continue
                if idx + 1 >= len(sorted_rows):
                    continue
                next_row_idx = sorted_rows[idx + 1]
                if official_start_row is not None and next_row_idx >= official_start_row:
                    continue
                next_row_cells = cells_by_row[next_row_idx]
                for label_cell in cells_by_row[row_idx]:
                    label_text = label_cell.get("text", "").strip()
                    if not label_text or len(label_text) > 80 or label_text.startswith("■"):
                        continue
                    if re.search(r"\[\s*\]", label_text):
                        continue
                    label_col = label_cell.get("column", 0)
                    for target_cell in next_row_cells:
                        target_id = target_cell.get("id", "")
                        if target_id in seen_ids:
                            continue
                        target_text = target_cell.get("text", "").strip()
                        target_col = target_cell.get("column", 0)
                        if (not target_text or target_text == "  ") and abs(target_col - label_col) <= 1:
                            registry.append(RegistryField(
                                field_id=f"{target_id}.spatial",
                                target_id=target_id,
                                label=f"{label_text[:40]} (하단 란)",
                                type=_guess_field_type(label_text),
                                category=_categorize_row(next_row_idx),
                                row=next_row_idx, column=target_col,
                                current_text="",
                                required=True,
                            ))
                            seen_ids.add(target_id)
                            break

    return [f.model_dump() for f in registry]


def _categorize_row(row: int) -> str:
    """행 번호로 인터뷰 단계를 대략 분류합니다."""
    if row <= 12:
        return "step1_application"
    if row <= 18:
        return "step2_personal"
    if row <= 27:
        return "step3_address"
    return "step4_signature"


def _guess_field_type(label: str) -> RegistryFieldType:
    """라벨 텍스트로 필드 타입을 추정합니다."""
    label_lower = label.lower()
    if any(kw in label_lower for kw in ("전화", "phone", "cell phone", "telephone")):
        return "phone"
    if any(kw in label_lower for kw in ("날짜", "일자", "date", "기간", "유효", "생년월일")):
        return "date"
    if any(kw in label_lower for kw in ("서명", "signature", "seal", "인")):
        return "signature"
    if any(kw in label_lower for kw in ("소득", "금액", "만원", "amount", "income")):
        return "amount"
    if any(kw in label_lower for kw in ("번호", "등록번호", "no.")):
        return "number"
    return "text"


def _is_required_field(text: str) -> bool:
    """해당자에 한함 등 선택적 필드인지 판단합니다."""
    optional_keywords = ("해당자", "소지자", "해당 시", "에만 기재", "에 한함")
    return not any(kw in text for kw in optional_keywords)


def _known_label(text: str) -> str | None:
    """첫 MVP에서 확인 질문을 만들 수 있는 대표 행정서식 라벨만 찾습니다."""
    for label in ("업체명", "전화번호", "소재지", "생년월일", "본국주소", "성명"):
        if label in text and not text.startswith("■"):
            return label
    return None

