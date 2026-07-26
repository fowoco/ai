# HWPX Form Editor MCP Instructions & Agent Protocol

## 🚨 MANDATORY AGENT CONVENTIONS & INTERVIEW PROTOCOL

All AI Agents executing commands via `hwp-editor-mcp` MUST adhere strictly to the following Core Principles and Field Registry-driven Interview Protocol.

---

## 1. Document Workspace Auto-Isolation Principle

- NEVER save generated files directly under `samples/` root or arbitrary paths.
- All operations MUST automatically create and use the document STEM workspace directory: `samples/[doc_stem]/`
  - Copy original into workspace: `samples/[doc_stem]/original.hwpx`
  - Modified File: `samples/[doc_stem]/modified_[user_name].hwpx`
  - Render Outputs: `samples/[doc_stem]/renders/` (contains `original/`, `modified/`, `diffs/`)
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

`analyze_document` 결과에 `field_registry`가 포함됩니다. 이것은 XML에서 **기계적으로 추출한 모든 채울 수 있는 필드의 완전한 목록**입니다.

**CRITICAL RULE: LLM은 `field_registry`의 모든 필드를 인터뷰에서 빠짐없이 소화해야 합니다.**
- `field_registry`에 있는 필드를 건너뛰면 안 됩니다.
- `field_registry`에 없는 필드를 임의로 추가하면 안 됩니다.
- `required: false`인 필드도 "해당사항이 있으시면 알려주세요" 형태로 반드시 물어봐야 합니다.

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

**필드 타입**: `checkbox`, `checkbox_group`, `text`, `date`, `phone`, `number`, `amount`, `signature`, `placeholder`

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

### ⚠️ 자동 제외

`field_registry`는 이미 **공용란(For Official Use Only)** 영역을 자동 제외합니다. 공용란에 대한 질문을 하지 마세요.

---

## 4. SVG Visual Verification Checklist (더블 체크)

`analyze_document` → SVG 렌더링 후, **`field_registry`를 필수 체크리스트로 사용하여** 시각 더블체크를 수행합니다:

1. `field_registry`의 각 필드가 SVG 렌더링에서 올바른 위치에 있는지 확인
2. registry에 있는데 SVG에서 안 보이면 → 경고 발생
3. SVG에서 보이는데 registry에 없으면 → 추가 검토

### 적용 후 Visual Diff

- `compare_document_versions`로 원본 vs 수정본 SVG 렌더링 비교
- `renders/diffs/page_001_diff.png` 생성 및 사용자에게 제공
- Agent가 diff 이미지를 직접 검사하고 이상 징후를 사전 탐지
