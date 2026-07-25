# HWPX Form Editor MCP Instructions & Agent Protocol

## 🚨 MANDATORY AGENT CONVENTIONS & INTERVIEW PROTOCOL

All AI Agents executing commands via `hwp-editor-mcp` MUST adhere strictly to the following 3 Core Principles and 4-Step Interactive Interview Template.

---

### 1. Document Workspace Auto-Isolation Principle
- NEVER save generated files directly under `samples/` root or arbitrary paths.
- All operations MUST automatically use the document STEM workspace directory: `samples/[doc_stem]/`
  - Original File: `samples/[doc_stem]/original.hwpx`
  - Modified File: `samples/[doc_stem]/modified_[user_name].hwpx`
  - Render Outputs: `samples/[doc_stem]/renders/` (contains `original/`, `modified/`, `diffs/`)

---

### 2. Mandatory 4-Step Sequential Complete Interview Template

When assisting a user with filling out an HWPX administrative form (e.g. `통합신청서(신고서).hwpx`), DO NOT ask vague or bundled 1-line questions. Use the following friendly, highly readable 4-step sequence:

#### 📝 [Step 1] Application / Notification Type Selection (체크박스 선택)
Present available checkboxes (e.g. `[ ] 외국인 등록`, `[ ] 체류기간 연장허가`, `[ ] 체류자격 변경허가`, `[ ] 등록증 재발급`) and ask the user to choose their target application type.

#### 👤 [Step 2] Applicant Personal & Passport Details (인적사항 및 여권정보)
Ask for:
1. Surname / Given Names (성 / 명)
2. Date of Birth & Sex (생년월일 YYYY.MM.DD & 성별 남/여)
3. Nationality & Passport No. / Expiry Date (국적 & 여권번호 / 유효기간)

#### 🏠 [Step 3] Residence, Contact & Employment Info (주소·연락처 및 근무처/소득)
Ask for:
1. Address in Korea & Cell Phone No. (대한민국 내 주소 & 휴대전화)
2. Home Country Address & E-Mail (본국 주소 & 이메일)
3. Workplace / Occupation / Income (근무처, 직업 및 연 소득금액 - 해당자)

#### 🖋️ [Step 4] Refund Account & Date / Signature Approval (계좌 및 서명/신청일)
Ask for:
1. Refund Bank Account (반환용 계좌번호 - 해당자)
2. Date of Application & Signature Consent (신청일자 & 서명 동의)

---

### 3. Visual Verification Protocol
- After applying the approved `EditPlan`, always run `compare_document_versions` with the official Rust `rhwp` engine (`~/.cargo/bin/rhwp`).
- Provide the generated visual highlight diff PNG (`renders/diffs/page_001_diff.png`) to the user for visual confirmation before final completion.
