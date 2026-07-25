# HWPX Form Editor MCP Instructions & Agent Protocol

## 🚨 MANDATORY AGENT CONVENTIONS & INTERVIEW PROTOCOL

All AI Agents executing commands via `hwp-editor-mcp` MUST adhere strictly to the following Core Principles and 4-Step Interactive Interview Template.

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

## 3. Mandatory 4-Step Sequential Complete Interview Template

When assisting a user with filling out an HWPX form, use the following 4-step sequence.
**CRITICAL: You MUST ask about ALL fields detected by `analyze_document`, not just common ones.
Run `analyze_document` first, then cross-reference ALL detected empty cells against this template.**

### 📝 [Step 1] 신청/신고 종류 선택 (Application Type Checkboxes)

Present ALL available checkboxes from the document. For `통합신청서`:
1. `[ ] 외국인 등록` (Foreign Resident Registration)
2. `[ ] 체류자격 외 활동허가` (희망 자격: ___)
3. `[ ] 등록증 재발급` (Reissuance of Registration Card)
4. `[ ] 근무처 변경·추가허가 / 신고` (Change/Addition of Workplace)
5. `[ ] 체류기간 연장허가` (Extension of Sojourn Period)
6. `[ ] 재입국허가 (단수/복수)` (Reentry Permit)
7. `[ ] 체류자격 변경허가` (희망 자격: ___)
8. `[ ] 체류지 변경신고` (Alteration of Residence)
9. `[ ] 체류자격 부여` (희망 자격: ___)
10. `[ ] 등록사항 변경신고` (Change of Information on Registration)

### 👤 [Step 2] 인적사항 및 여권정보 (Personal & Passport Details)

Ask for ALL of:
1. **성명** (Name): 성(Surname) / 명(Given Names)
2. **생년월일** (DOB): YYYY.MM.DD
3. **성별** (Sex): 남(M) 또는 여(F)
4. **국적** (Nationality)
5. **외국인등록번호** (Foreign Reg. No.) — 소지자만
6. **여권번호** (Passport No.)
7. **여권 발급일자** (Passport Issue Date)
8. **여권 유효기간** (Passport Expiry Date)

### 🏠 [Step 3] 주소·연락처·근무처·학력·체류 (Address, Contact, Work, School, Stay)

Ask for ALL of:
1. **대한민국 내 주소** (Address in Korea)
2. **전화번호** (Telephone No.)
3. **휴대전화** (Cell Phone No.)
4. **본국 주소** (Home Country Address)
5. **본국 전화번호** (Home Country Phone)
6. **재학 여부** (School Status): 미취학 / 초 / 중 / 고
7. **학교 이름** (Name of School) — 해당자
8. **학교 종류** (Type of School): 교육청 인가 / 비인가·대안학교
9. **원 근무처** (Current Workplace) / 사업자등록번호 / 전화번호
10. **예정 근무처** (New Workplace) / 사업자등록번호 / 전화번호 — 해당자
11. **연 소득금액** (Annual Income, 만원)
12. **직업** (Occupation)
13. **재입국 신청 기간** (Intended Period of Reentry) — 재입국 신청자만
14. **전자우편** (E-Mail)

### 🖋️ [Step 4] 계좌·서명·신청일 (Account, Signature, Date)

Ask for:
1. **반환용 계좌번호** (Refund Bank Account) — 외국인등록/재발급 신청자만
2. **신청일** (Date of Application)
3. **신청인 서명 동의** (Signature Consent)

**NOTE**: `공용란 (For Official Use Only)` (row35~42) is for government officials only. Do NOT ask the user about these fields.

---

## 4. Visual Verification Protocol

- After applying the approved EditPlan, always run `compare_document_versions` with the official Rust `rhwp` engine.
- Provide the generated visual highlight diff PNG (`renders/diffs/page_001_diff.png`) to the user for visual confirmation.
- Agent MUST visually inspect the diff image and flag any anomalies before presenting to the user.
