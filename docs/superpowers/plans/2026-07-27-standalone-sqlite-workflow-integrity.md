# Standalone SQLite Workflow Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단일 HWPX MCP 서버가 전용 SQLite와 환경변수 HMAC 키를 사용해 재시작 후에도 승인, attempt, 산출물, Vision 검토 무결성을 유지하게 한다.

**Architecture:** `HWP_MCP_ROOT/.hwp-mcp/state.sqlite3`를 workflow의 유일한 authoritative source로 사용하고 기존 `workflow-state.json`은 사람이 읽는 projection으로만 유지한다. HWPX·JSON·PNG는 기존 workspace에 저장하되 `LocalArtifactStore`가 SQLite에 URI·SHA-256·크기를 등록하고 읽을 때 다시 검증한다. FOWOCO나 외부 공유 DB 연동은 포함하지 않는다.

**Tech Stack:** Python 3.10+, stdlib `sqlite3`/`hmac`/`hashlib`, Pydantic 2, FastMCP 1.27+, pytest

## Global Constraints

- 원본 HWPX를 절대 덮어쓰지 않는다.
- `HWP_MCP_ROOT` 밖의 파일과 DB 경로를 허용하지 않는다.
- 신규 workflow·서명·artifact 로직은 실패 테스트를 먼저 실행한다.
- HMAC 키 원문은 소스, SQLite, workspace, receipt, 로그에 기록하지 않는다.
- 단일 서버 프로세스가 정식 지원 대상이며 다중 인스턴스 공유 DB는 이번 범위가 아니다.
- FOWOCO DB, 사용자 테이블, 도메인 개인정보를 추가하지 않는다.

---

### Task 1: 지속 HMAC 서명과 손실 없는 여권번호

**Files:**
- Create: `src/hwp_mcp/integrity.py`
- Modify: `src/hwp_mcp/plans.py`
- Modify: `src/hwp_mcp/fields.py`
- Test: `tests/test_integrity.py`
- Test: `tests/test_plans.py`
- Test: `tests/test_field_registry.py`

**Interfaces:**
- Produces: `Signature`, `EnvSigningKeyProvider`, `canonical_json_bytes`
- Produces: `create_approval_receipt(..., signer, approver_subject)`와 `validate_approval_receipt(..., signer)`
- Consumes: `HWP_MCP_ACTIVE_SIGNING_KEY_ID`, `HWP_MCP_SIGNING_KEYS`

- [x] **Step 1: Write failing signature and passport tests**

```python
def test_env_signer_survives_restart_and_supports_rotation(monkeypatch):
    monkeypatch.setenv("HWP_MCP_ACTIVE_SIGNING_KEY_ID", "v2")
    monkeypatch.setenv("HWP_MCP_SIGNING_KEYS", json.dumps({"v1": OLD, "v2": NEW}))
    first = EnvSigningKeyProvider.from_env()
    signature = first.sign(b"approval")
    second = EnvSigningKeyProvider.from_env()
    assert second.verify(b"approval", signature)


def test_passport_number_is_text_and_preserved():
    assert _guess_field_type("여권번호 Passport No.") == "text"
```

- [x] **Step 2: Run tests and confirm they fail because the provider and precedence are absent**

Run: `uv run pytest tests/test_integrity.py tests/test_field_registry.py -q`

- [x] **Step 3: Implement the minimal HMAC provider and signed receipt v2**

```python
class SigningKeyProvider(Protocol):
    def sign(self, payload: bytes) -> Signature: ...
    def verify(self, payload: bytes, signature: Signature) -> bool: ...


class ApprovalReceipt(BaseModel):
    version: Literal[2] = 2
    plan_id: str
    document_sha256: str
    edit_plan_sha256: str
    approver_subject: str
    source: Literal["mcp_elicitation"]
    approved_at: str
    signature: Signature
```

The provider decodes a JSON key ring of base64 values, rejects keys shorter than 32 bytes, signs with the active key, and verifies with the receipt `key_id` using `hmac.compare_digest`.

- [x] **Step 4: Put passport keywords before the generic `번호` rule**

```python
if any(kw in label_lower for kw in ("여권", "passport")):
    return "text"
```

- [x] **Step 5: Run focused tests**

Run: `uv run pytest tests/test_integrity.py tests/test_plans.py tests/test_field_registry.py -q`

### Task 2: Authoritative SQLite repository and local artifact registry

**Files:**
- Create: `src/hwp_mcp/state.py`
- Create: `src/hwp_mcp/artifacts.py`
- Test: `tests/test_state.py`
- Test: `tests/test_artifacts.py`

**Interfaces:**
- Produces: `SqliteWorkflowRepository`
- Produces: `ArtifactRecord`, `LocalArtifactStore`
- Repository methods:
  - `ensure_document(document_id, original_sha256, workspace_uri)`
  - `set_analysis_status(document_id, status)`
  - `create_plan(document_id, plan_id, plan_sha256)`
  - `approve_plan(document_id, plan_id, receipt_sha256, approved_at)`
  - `reserve_attempt(document_id, plan_id) -> int`
  - `complete_attempt(plan_id, status, modified_sha256, report_sha256)`
  - `record_vision_delivery(...)`
  - `require_vision_delivery(...)`
  - `record_vision_review(...)`
  - `finalize(document_id, plan_id)`
- Artifact methods:
  - `put(owner_id, kind, source) -> ArtifactRecord`
  - `open_verified(owner_id, kind) -> BinaryIO`

- [x] **Step 1: Write failing repository transaction tests**

```python
def test_sqlite_state_survives_new_repository_instance(tmp_path):
    first = SqliteWorkflowRepository(tmp_path / "state.sqlite3")
    first.ensure_document("doc", "a" * 64, "workspace")
    first.create_plan("doc", "p1", "b" * 64)
    second = SqliteWorkflowRepository(tmp_path / "state.sqlite3")
    assert second.get_document("doc").current_plan_id == "p1"


def test_projection_edit_cannot_reset_attempt_limit(tmp_path):
    repo = prepared_repo(tmp_path)
    repo.reserve_attempt("doc", "p1")
    repo.complete_attempt("p1", "FAILED", "c" * 64, "d" * 64)
    repo.create_plan("doc", "p2", "e" * 64)
    repo.reserve_attempt("doc", "p2")
    repo.complete_attempt("p2", "FAILED", "f" * 64, "0" * 64)
    repo.create_plan("doc", "p3", "1" * 64)
    with pytest.raises(DocumentError, match="2회"):
        repo.reserve_attempt("doc", "p3")
```

- [x] **Step 2: Run repository tests and confirm missing-module failures**

Run: `uv run pytest tests/test_state.py -q`

- [x] **Step 3: Implement schema creation and `BEGIN IMMEDIATE` transitions**

Use tables `documents`, `plans`, `approvals`, `attempts`, `vision_deliveries`, `vision_reviews`, and `artifacts`. Enable foreign keys, WAL, a busy timeout, unique plan IDs, and a unique `(document_id, sequence)` attempt index. Count `RESERVED`, `PENDING_VISION_REVIEW`, `FAILED`, and `VERIFIED_FINAL` toward the two-attempt limit; `ABORTED_NO_OUTPUT` releases its slot.

- [x] **Step 4: Write failing artifact tamper tests**

```python
def test_local_artifact_store_rejects_changed_bytes(tmp_path):
    store = LocalArtifactStore(repo)
    artifact = store.put("p1", "edit_plan", source)
    source.write_bytes(b"tampered")
    with pytest.raises(DocumentError, match="ARTIFACT_TAMPERED"):
        store.open_verified("p1", "edit_plan")
```

- [x] **Step 5: Implement artifact registration and byte verification**

The store resolves every path below `HWP_MCP_ROOT`, records URI/hash/size in SQLite, and verifies all three values before opening.

- [x] **Step 6: Run focused state/artifact tests**

Run: `uv run pytest tests/test_state.py tests/test_artifacts.py -q`

### Task 3: Integrate SQLite into edit workflow

**Files:**
- Modify: `src/hwp_mcp/server.py`
- Modify: `src/hwp_mcp/workspace.py`
- Test: `tests/test_v2_workflow.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Consumes: Task 1 signer and Task 2 repository/store
- Produces: `_workflow_services()` based only on `HWP_MCP_ROOT` and signing env
- Produces: DB-backed analyze → plan → approval → attempt → finalization transitions

- [x] **Step 1: Write failing restart and projection-tamper integration tests**

```python
def test_signed_approval_remains_valid_after_service_restart(...):
    approve_with_first_repository()
    apply_with_new_repository_and_same_env()
    assert result["status"] == "PENDING_VISION_REVIEW"


def test_workflow_json_cannot_forge_approval_or_reset_attempts(...):
    write_json(state_path, forged_projection)
    with pytest.raises(DocumentError):
        apply_edit_plan("form.hwpx", plan_id)
```

- [x] **Step 2: Run integration tests and confirm the current JSON-authoritative behavior fails**

Run: `uv run pytest tests/test_v2_workflow.py -q`

- [x] **Step 3: Register documents and analysis state in SQLite**

`prepare_workspace` continues to create directories and projection JSON. `analyze_document` and `confirm_visual_candidates` write the authoritative status through the repository before updating the projection.

- [x] **Step 4: Register plan and signed approval artifacts**

`create_edit_plan` registers the stored plan and revokes any prior active approval. `approve_edit_plan` signs the canonical receipt, records it in SQLite, registers the receipt artifact, then updates the projection.

- [x] **Step 5: Reserve and complete attempts transactionally**

`apply_edit_plan` reserves before creating `modified.hwpx`. If no modified output exists after failure it records `ABORTED_NO_OUTPUT`; if output exists it records a consumed `FAILED` attempt with registered output/report hashes. A successful automatic verification records `PENDING_VISION_REVIEW`.

- [x] **Step 6: Make finalization verify DB state and artifacts**

`finalize_document` requires the current DB plan, signed approval, verified modified/report/request/review artifacts, and a DB-recorded PASS review before copying to `final/`. It records the final artifact and `VERIFIED_FINAL` transition.

- [x] **Step 7: Run edit workflow and protocol tests**

Run: `uv run pytest tests/test_v2_workflow.py tests/test_protocol.py -q`

### Task 4: Signed Host Vision delivery with actual image content

**Files:**
- Modify: `src/hwp_mcp/vision.py`
- Modify: `src/hwp_mcp/server.py`
- Test: `tests/test_vision.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Produces: `VisionDelivery`, canonical image manifest hash, expiry validation
- `review_document_vision` returns `CallToolResult` for Host fallback with `structuredContent` plus actual PNG `ImageContent`
- `submit_host_vision_review` requires `delivery_id`

- [x] **Step 1: Write failing delivery tests**

```python
def test_host_fallback_contains_png_bytes_and_signed_delivery(...):
    result = await review_document_vision(...)
    assert result.structuredContent["delivery_id"]
    assert any(isinstance(item, ImageContent) for item in result.content)


def test_host_pass_without_active_delivery_is_rejected(...):
    with pytest.raises(DocumentError, match="delivery"):
        submit_host_vision_review(..., delivery_id="missing")
```

- [x] **Step 2: Run tests and confirm fallback currently returns paths only**

Run: `uv run pytest tests/test_vision.py tests/test_protocol.py -q`

- [x] **Step 3: Create, sign, and persist a bounded delivery**

Build a canonical manifest from every view/image SHA-256, sign it with the configured key, store delivery ID/review ID/plan ID/manifest/expiry in SQLite, and register each image artifact. Refuse delivery creation above 30 MiB and move the workflow to `NEEDS_HUMAN`.

- [x] **Step 4: Return `CallToolResult` with text and image blocks**

```python
return CallToolResult(
    structuredContent=payload,
    content=[
        TextContent(type="text", text=request.prompt),
        *image_blocks,
    ],
)
```

- [x] **Step 5: Validate delivery, signature, expiry, current plan, and current bytes on submission**

Only a PASS/FAIL/NEEDS_HUMAN submission tied to the active delivery is recorded. A reused, expired, modified, or other-review delivery fails closed.

- [x] **Step 6: Run Vision and protocol tests**

Run: `uv run pytest tests/test_vision.py tests/test_protocol.py -q`

### Task 5: Standalone operation contract and full verification

**Files:**
- Modify: `docs/superpowers/specs/2026-07-27-deployment-workflow-integrity-design.md`
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `src/hwp_mcp/instructions.md`
- Test: all tests

**Interfaces:**
- Documents the permanent standalone topology and startup variables
- Removes FOWOCO/shared-DB/KMS work from the accepted target; those remain optional future adapters

- [x] **Step 1: Update the design status and supported topology**

State that one MCP server, one dedicated SQLite file, one persistent environment key ring, and local artifact storage are the supported standalone deployment. Multiple simultaneous server instances remain unsupported.

- [x] **Step 2: Document key generation and startup**

```bash
export HWP_MCP_ROOT=/absolute/private/workspace
export HWP_MCP_ACTIVE_SIGNING_KEY_ID=v1
export HWP_MCP_SIGNING_KEYS='{"v1":"<base64-32-byte-or-longer-key>"}'
uv run hwp-editor-mcp
```

Document that the key ring and `.hwp-mcp/state.sqlite3` must both be backed up; losing either prevents prior approval validation.

- [x] **Step 3: Run the full suite**

Run: `uv run pytest -q`

- [x] **Step 4: Check source and config diffs**

Run: `git diff --check`

- [x] **Step 5: Commit only feature files, excluding unrelated root samples and pre-existing `uv.lock` changes**

```bash
git add src tests README.md .env.example docs/superpowers
git commit -m "feat: persist standalone workflow integrity"
```
