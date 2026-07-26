# HWPX Form Editor MCP Instructions & Agent Protocol

## 🚨 MANDATORY AGENT CONVENTIONS & INTERVIEW PROTOCOL

All AI Agents executing commands via `hwp-editor-mcp` MUST adhere strictly to the following Core Principles and Field Registry-driven Interview Protocol.

---

## 1. Document Workspace Auto-Isolation Principle

- NEVER save generated files directly under `samples/` root or arbitrary paths.
- All safe workflow operations MUST use `<source-parent>/<safe-stem>-<sha256-prefix>/`.
  - Copy original into workspace: `original.hwpx` (never move the source)
  - Modified File: `attempts/<plan-id>/modified.hwpx`
  - Render Outputs: `attempts/<plan-id>/{original,modified,diffs}/`
  - Final File: `final/<safe-stem>_verified.hwpx`, created only after Vision `PASS`
- File naming convention: `page_001.svg`, `page_001.png`, `page_001_diff.png` (3-digit 1-indexed).

---

## 2. Checkbox Substitution Rules

- HWPX checkboxes use `[  ]` (double-space) or `[ ]` (single-space) brackets in `<t>` text nodes.
- To check a box: replace `[  ]` or `[ ]` with `[V]` **in-place within the existing `<t>` node**.
- NEVER append a new `<run><t>` element for checkbox values. This causes duplicate text rendering.
- For sex/gender fields with `[ ]남 M` and `[ ]여 F` in separate `<t>` nodes: replace only the specific `<t>` node that matches the selected option.
- Use the `anchor` field when targeting a specific checkbox within a cell containing multiple checkboxes.

---

## 3. XML Field Registry — 필수 체크리스트 기반 인터뷰

### 🔑 핵심 원칙

`analyze_document` 결과에 `field_registry`가 포함됩니다. 이것은 XML 후보를 `rhwp` SVG의 `cell-clip` 좌표와 결합한 **채울 수 있는 필드의 목록**입니다.

- XML cell 수와 SVG cell clip 수가 다르면 `svg_analysis.status: NEEDS_HUMAN`이며 인터뷰로 진행하지 않습니다.
- 라벨 아래 칸은 SVG 수평 겹침과 수직 인접 관계를 우선하고, 아래 칸이 없을 때만 오른쪽 인접 칸을 사용합니다.
- 각 field의 `visual_regions`와 `constraints.visual_source: rhwp_svg`가 실제 페이지 bbox 근거입니다.

**CRITICAL RULE: LLM은 `field_registry`의 모든 필드를 인터뷰에서 빠짐없이 소화해야 합니다.**
- `field_registry`에 있는 필드를 건너뛰면 안 됩니다.
- `field_registry`에 없는 필드를 임의로 추가하면 안 됩니다.
- `required: false`인 필드도 "해당사항이 있으시면 알려주세요" 형태로 반드시 물어봐야 합니다.
- 계획 생성 전 모든 field에 `provided | not_applicable | intentionally_blank | manual_after_export` 중 하나를 지정해야 합니다.
- `signable_region`은 현재 `manual_after_export`만 허용합니다.

### 📋 Field Registry 구조

```json
{
  "field_id": "section0.table0.row15.cell5.checkbox_group",
  "target_id": "section0.table0.row15.cell5",
  "label": "남 M / 여 F",
  "type": "checkbox_group",
  "category": "step2_personal",  // step1~step4
  "row": 15,
  "column": 5,
  "current_text": "[ ]남 M[ ]여 F",
  "required": true,
  "options": ["남 M", "여 F"]  // checkbox_group만
}
```

**Primitive kind**: `text_field`, `character_grid`, `checkbox`, `checkbox_group`, `placeholder`, `date_segments`, `signable_region`

### 📝 4단계 순차 인터뷰 (Field Registry 기반)

1. **Step 1** (`category: step1_application`): `field_registry`에서 추출된 **모든 체크박스와 플레이스홀더** 제시
2. **Step 2** (`category: step2_personal`): 인적사항 — 성명, 생년월일, 성별, 국적, 여권정보 등
3. **Step 3** (`category: step3_address`): 주소·연락처·근무처·학력·재입국·이메일 등
4. **Step 4** (`category: step4_signature`): 계좌·서명·신청일

각 단계에서:
1. `field_registry`를 `category`로 필터링
2. 해당 카테고리의 **모든 필드**를 가독성 좋은 표 또는 번호 목록으로 제시
3. `required: true`는 필수, `required: false`는 "(해당 시)" 표기
4. `checkbox_group`은 `options` 중에서 선택하도록 안내
5. 사용자 답변 수집 후 다음 단계로 진행

### ⚠️ 공용란

공용란 내부 입력 후보는 제외되고 하나의 `official_region`으로 보존됩니다. 질문하거나 편집하지 말고 `intentionally_blank`로 처리하세요. 공동이용 동의서의 서명란은 공용란 앞의 `signable_region`으로 유지됩니다.

---

## 4. SVG Visual Verification Checklist (더블 체크)

`analyze_document` → SVG 렌더링 후, **`field_registry`를 필수 체크리스트로 사용하여** 시각 더블체크를 수행합니다:

1. `field_registry`의 각 필드가 `visual_regions`로 SVG cell에 매핑됐는지 확인
2. registry에 있는데 SVG에서 안 보이면 → 경고 발생
3. SVG에서 보이는데 registry에 없으면 → 추가 검토

### 적용 후 Visual Diff

- `compare_document_versions`로 원본 vs 수정본 SVG 렌더링 비교
- 원본/수정 SVG에서 승인값 렌더 여부, 신규 text overflow, cell bbox 이동을 확인
- `attempts/<plan-id>/diffs/page_001_diff.png` 생성 및 사용자에게 제공
- Agent가 diff 이미지를 직접 검사하고 이상 징후를 사전 탐지

## 5. Finalization Gate

```text
ANALYZED → READY_FOR_INTERVIEW → WAITING_APPROVAL
→ PENDING_VISION_REVIEW → VERIFIED_FINAL
```

- `apply_edit_plan`은 최종본을 만들지 않습니다.
- 원본 hash, 승인 대상 외 변경, field postcondition, 페이지 수, 신규 layout warning, SVG geometry, PNG component diff를 자동 검증합니다.
- SVG에서 승인값 누락·신규 overflow·cell 이동이 하나라도 있으면 Vision 전에 `NEEDS_HUMAN`으로 차단합니다.
- `review_document_vision`은 파싱된 SVG geometry 근거와 원본·수정·diff PNG를 MCP client의 멀티모달 sampling에 전달합니다.
- sampling 응답은 모든 편집 field의 `PASS | FAIL | NEEDS_HUMAN` JSON 판정을 포함해야 합니다.
- sampling 미지원·응답 누락·형식 오류는 자동 `PASS`하지 않고 `NEEDS_HUMAN`입니다.
- `finalize_document`는 호출자가 제출한 판정을 받지 않으며, 서버가 저장한 Vision `PASS`에서만 final HWPX를 복사합니다.
- `FAIL` 또는 `NEEDS_HUMAN`은 attempt와 verification report를 보존하고 final 파일을 만들지 않습니다.
