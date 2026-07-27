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
- Authoritative workflow state: `$HWP_MCP_ROOT/.hwp-mcp/state.sqlite3`
- `workflow-state.json`은 사람이 읽는 projection이며 승인·attempt 횟수의 근거가 아닙니다.
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

- 반드시 MCP `analyze_document` Tool을 호출합니다. shell에서 `hwp_mcp.hwpx` 내부 함수를 import해 인터뷰 목록을 만들지 않습니다.
- `analyze_document` 직후 `next_action: confirm_visual_candidates`를 수행합니다.
- 확인 후 반환된 `analysis_contract.version: 2`, `stage: XML_SVG_MAPPED`, `registry_source: rhwp_svg`, `interview_ready: true`를 모두 확인한 뒤 인터뷰를 시작합니다.
- 위 계약이 없거나 `xml_field_candidates`만 보이면 구 MCP 서버·캐시 또는 내부 XML 분석 결과입니다. 인터뷰를 중단하고 MCP 서버를 재연결한 뒤 다시 분석합니다.
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
- XML 요약만 읽고 시각 검토를 완료했다고 보고하지 않습니다.

## 5. Finalization Gate

```text
ANALYZED → READY_FOR_INTERVIEW → WAITING_APPROVAL → APPROVED
→ PENDING_VISION_REVIEW → VERIFIED_FINAL
```

- `approve_edit_plan`의 MCP elicitation을 사용자가 수락해야 HMAC 서명 승인 receipt와 SQLite 승인 레코드가 생성됩니다.
- `HWP_MCP_ACTIVE_SIGNING_KEY_ID`와 `HWP_MCP_SIGNING_KEYS`가 없거나 기존 `key_id`가 key ring에 없으면 승인·적용·최종화는 중단됩니다.
- `apply_edit_plan`은 호출자가 보낸 `approved=true`나 plan 객체를 받지 않습니다.
- `apply_edit_plan`은 최종본을 만들지 않습니다.
- 원본 hash, 승인 대상 외 변경, field postcondition, 페이지 수, 신규 layout warning, SVG geometry, PNG component diff를 자동 검증합니다.
- SVG에서 승인값 누락·신규 overflow·cell 이동이 하나라도 있으면 Vision 전에 `NEEDS_HUMAN`으로 차단합니다.
- `review_document_vision`은 full-page와 편집 필드가 있는 detail band 각각의 원본·수정·diff PNG를 해시와 결합합니다.
- MCP Client가 Sampling을 지원하면 같은 이미지 묶음을 `sampling/createMessage`에 전달합니다.
- Sampling 미지원 또는 transport 실패이면 실제 full/detail PNG `ImageContent`, 서명된 1회성 `delivery_id`, `VISION_REVIEW_REQUIRED`, `next_action: submit_host_vision_review`를 함께 반환합니다. 이 경우 workflow는 `PENDING_VISION_REVIEW`를 유지합니다.
- Host의 멀티모달 LLM은 반환된 모든 full-page와 관련 detail view를 **이미지 입력으로 직접 열어** 비교합니다. Gemini, GPT, Claude, 로컬 VLM 등 모델명은 제한하지 않습니다.
- `submit_host_vision_review`은 `delivery_id`, 만료·서명·1회 사용 여부, `image_input` capability, `review_id`, 모든 artifact hash, 전체 편집 field, field별 full/detail `evidence_view_ids`, 고유 reason을 검증합니다.
- 이미지 입력을 사용할 수 없거나 이미지를 열지 못한 모델은 판정을 제출하지 말고 `NEEDS_HUMAN`으로 중단합니다.
- sampling 응답은 모든 편집 field의 `PASS | FAIL | NEEDS_HUMAN` JSON 판정을 포함해야 합니다.
- sampling 응답 누락·형식 오류는 자동 `PASS`하지 않고 `NEEDS_HUMAN`입니다.
- `finalize_document`는 서버가 검증·저장한 `mcp_sampling` 또는 `host_vision_submission` PASS에서만 final HWPX를 복사합니다.
- `attempts/<plan-id>/modified.hwpx`를 다른 경로로 직접 복사해 완료본으로 취급하지 않습니다. SQLite `documents.status: VERIFIED_FINAL`과 서버의 `final_path`가 함께 있어야 완료입니다.
- `FAIL` 또는 `NEEDS_HUMAN`은 attempt와 verification report를 보존하고 final 파일을 만들지 않습니다.
- 출력이 생성된 실패 attempt는 SQLite의 2회 제한을 소비합니다. `workflow-state.json`의 `attempts`를 지우거나 바꿔도 제한은 초기화되지 않습니다.
