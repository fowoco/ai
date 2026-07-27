# HWPX Workflow Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자 승인, typed preflight, 범용 Host Vision 검토와 hash-bound final gate를 갖춘 HWPX 작성 흐름을 구현한다.

**Architecture:** `server.py`는 MCP capability와 Tool 흐름만 조율한다. `plans.py`가 plan·승인 receipt·typed 입력을 검증하고, `vision.py`가 모델 독립적인 review request와 판정을 검증하며, `workspace.py`가 상태와 final gate를 강제한다.

**Tech Stack:** Python 3.10+, FastMCP, Pydantic, Pillow, rhwp SVG, pytest, uv

## Global Constraints

- 원본 HWPX를 덮어쓰지 않는다.
- 모든 경로는 `HWP_MCP_ROOT`와 현재 workspace 안에 둔다.
- 새 dependency, 외부 Vision SDK, API key, 모델별 adapter를 추가하지 않는다.
- 좌표 대신 field type, `visual_regions`, geometry와 field-view 관계를 검증한다.
- 각 task는 실패 테스트부터 작성하고 `uv run pytest`로 검증한다.
- 사용자 소유 `samples/` 산출물과 `uv.lock` 변경을 건드리지 않는다.

---

### Task 1: Typed plan preflight와 일관된 next action

**Files:**
- Modify: `src/hwp_mcp/plans.py`
- Modify: `src/hwp_mcp/server.py`
- Modify: `src/hwp_mcp/compare.py`
- Test: `tests/test_plans.py`
- Test: `tests/test_analysis_contract.py`

**Interfaces:**
- Produces: `CellEditInput.value_origin: Literal["user", "example"]`
- Produces: `validate_operation_input(field: dict[str, Any], edit: CellEditInput) -> None`
- Produces: workflow 응답의 `status`, `next_action`, `interview_ready`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_plan_rejects_unit_inside_prefix_unit_amount(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    manifest = make_grounded_manifest(source)
    field = manifest["field_registry"][0]
    field["type"] = "amount"
    field["constraints"].update({"mode": "prefix_unit", "anchor": "만원"})
    with pytest.raises(EditPlanError, match="단위를 제외한 숫자"):
        create_edit_plan(
            source,
            manifest,
            [CellEditInput(
                field_id=field["field_id"],
                target_id=field["target_id"],
                expected_text="",
                value="4000만원",
            )],
            dispositions={field["field_id"]: "provided"},
        )


def test_invalid_date_does_not_create_attempt(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    manifest = make_grounded_manifest(source)
    field = manifest["field_registry"][0]
    field["type"] = "date"
    field["kind"] = "date_segments"
    with pytest.raises(EditPlanError, match="날짜"):
        create_edit_plan(
            source,
            manifest,
            [CellEditInput(
                field_id=field["field_id"],
                target_id=field["target_id"],
                expected_text="",
                value="2026-99-99",
            )],
            dispositions={field["field_id"]: "provided"},
        )
```

- [ ] **Step 2: 실패 확인**

Run: `UV_CACHE_DIR=/private/tmp/hwp-editor-uv-cache uv run --offline pytest tests/test_plans.py tests/test_analysis_contract.py -q`

Expected: unit/date preflight와 `next_action` assertion 실패

- [ ] **Step 3: 최소 구현**

```python
ValueOrigin = Literal["user", "example"]

class CellEditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_id: str | None = Field(default=None, min_length=1, max_length=240)
    target_id: str = Field(min_length=1, max_length=200)
    expected_text: str = Field(max_length=10_000)
    value: str = Field(min_length=1, max_length=10_000)
    value_origin: ValueOrigin = "user"
    label: str | None = Field(default=None, max_length=200)
    anchor: str | None = Field(default=None, min_length=1, max_length=10_000)
    expected_match_count: Literal[1] = 1
    value_origin: ValueOrigin = "user"


def _validate_operation_input(field: dict[str, Any], edit: CellEditInput) -> None:
    constraints = field.get("constraints", {})
    if field.get("type") == "amount" and constraints.get("mode") == "prefix_unit":
        if not re.fullmatch(r"\d[\d,]*", edit.value):
            raise EditPlanError("prefix_unit 금액은 단위를 제외한 숫자만 입력하세요.")
```

날짜·checkbox·character grid도 실제 apply 함수와 같은 제약으로 plan 생성 전에
검증한다. `value_origin`은 `EditOperation`과 plan hash payload에 포함한다.

- [ ] **Step 4: 통과 확인**

Run: `UV_CACHE_DIR=/private/tmp/hwp-editor-uv-cache uv run --offline pytest tests/test_plans.py tests/test_analysis_contract.py tests/test_compare.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/hwp_mcp/plans.py src/hwp_mcp/server.py src/hwp_mcp/compare.py tests/test_plans.py tests/test_analysis_contract.py
git commit -m "fix: validate typed edits before apply"
```

### Task 2: 서버 저장 승인 receipt

**Files:**
- Modify: `src/hwp_mcp/plans.py`
- Modify: `src/hwp_mcp/server.py`
- Modify: `src/hwp_mcp/workspace.py`
- Modify: `src/hwp_mcp/api.py`
- Test: `tests/test_v2_workflow.py`
- Test: `tests/test_protocol.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: stored `attempts/<plan_id>/edit-plan.json`
- Produces: `ApprovalReceipt`
- Produces: `approve_edit_plan(path: str, plan_id: str, ctx: Context) -> dict`
- Changes: `apply_edit_plan(path: str, plan_id: str) -> dict`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_apply_requires_matching_approval_receipt(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    workspace = prepare_workspace(source)
    manifest = make_grounded_manifest(workspace["original_path"])
    field = manifest["field_registry"][0]
    plan = create_edit_plan(
        workspace["original_path"],
        manifest,
        [CellEditInput(
            field_id=field["field_id"],
            target_id=field["target_id"],
            expected_text="",
            value="ABC",
        )],
        dispositions={field["field_id"]: "provided"},
    )
    attempt = workspace["attempts_dir"] / plan.plan_id
    attempt.mkdir()
    plan_path = attempt / "edit-plan.json"
    write_json(plan_path, plan.model_dump())
    with pytest.raises(DocumentError, match="승인 receipt"):
        load_approved_plan(workspace["workspace_dir"], plan.plan_id)


async def approve(_context, params):
    assert plan.plan_id in params.message
    return ElicitResult(action="accept", content={"approved": True})
```

Protocol test는 elicitation callback이 없는 Client에서 approval tool이 receipt를 만들지
않는 것과, callback이 수락한 Client에서만 apply가 진행되는 것을 검증한다.

- [ ] **Step 2: 실패 확인**

Run: `UV_CACHE_DIR=/private/tmp/hwp-editor-uv-cache uv run --offline pytest tests/test_v2_workflow.py tests/test_protocol.py tests/test_api.py -q`

Expected: approval Tool/receipt 부재와 기존 boolean apply 계약 때문에 FAIL

- [ ] **Step 3: 최소 구현**

```python
class ApprovalReceipt(BaseModel):
    version: Literal[1] = 1
    plan_id: str
    document_sha256: str
    edit_plan_sha256: str
    source: Literal["mcp_elicitation"] = "mcp_elicitation"
    approved_at: str


class ApprovalAnswer(BaseModel):
    approved: bool
```

`approve_edit_plan`은 client elicitation capability를 먼저 확인한다. 수락 응답만
`approval-receipt.json`으로 저장하고 state를 `APPROVED`로 바꾼다.
`apply_edit_plan`은 호출자 boolean과 plan 객체를 받지 않고 저장 파일과 receipt
hash를 다시 검증한다. FastAPI apply는 승인 receipt가 이미 존재할 때만 같은
application 함수를 호출한다.

- [ ] **Step 4: 통과 확인**

Run: `UV_CACHE_DIR=/private/tmp/hwp-editor-uv-cache uv run --offline pytest tests/test_v2_workflow.py tests/test_protocol.py tests/test_api.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/hwp_mcp/plans.py src/hwp_mcp/server.py src/hwp_mcp/workspace.py src/hwp_mcp/api.py tests/test_v2_workflow.py tests/test_protocol.py tests/test_api.py
git commit -m "feat: require server approval receipt"
```

### Task 3: Hash-bound Vision review request

**Files:**
- Modify: `src/hwp_mcp/vision.py`
- Modify: `src/hwp_mcp/server.py`
- Test: `tests/test_vision.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Produces: `build_vision_review_request(plan_id: str, original_path: Path, modified_path: Path, verification_path: Path, views: list[VisionView], expected_field_ids: list[str], prompt: str) -> VisionReviewRequest`
- Produces: `compute_review_id(request: VisionReviewRequest) -> str`
- Produces: `validate_review_request(request, attempt_dir) -> None`
- Produces: `FieldVisionDecision.evidence_view_ids: list[str]`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_review_request_binds_every_artifact_and_field(tmp_path: Path) -> None:
    original = tmp_path / "original.hwpx"
    modified = tmp_path / "modified.hwpx"
    verification = tmp_path / "verification-report.json"
    original.write_bytes(b"original")
    modified.write_bytes(b"modified")
    verification.write_text('{"status":"PENDING_VISION_REVIEW"}')
    images = {}
    for kind in ("original", "modified", "diff"):
        path = tmp_path / f"{kind}.png"
        path.write_bytes(kind.encode())
        images[kind] = VisionImage(path=str(path), sha256=sha256_file(path))
    view = VisionView(
        view_id="page-001-full",
        page=1,
        kind="full",
        bbox=None,
        field_ids=["field-1"],
        original=images["original"],
        modified=images["modified"],
        diff=images["diff"],
    )
    request = build_vision_review_request(
        plan_id="a" * 64,
        original_path=original,
        modified_path=modified,
        verification_path=verification,
        views=[view],
        expected_field_ids=["field-1"],
        prompt="review",
    )
    assert request.review_id == compute_review_id(request)
    assert request.modified_sha256 == sha256_file(modified)
    assert request.views[0].kind == "full"
    assert request.views[0].original.sha256 == sha256_file(tmp_path / "original.png")
    assert request.views[0].modified.sha256 == sha256_file(tmp_path / "modified.png")
    assert request.views[0].diff.sha256 == sha256_file(tmp_path / "diff.png")
    assert "field-1" in request.views[0].field_ids
```

- [ ] **Step 2: 실패 확인**

Run: `UV_CACHE_DIR=/private/tmp/hwp-editor-uv-cache uv run --offline pytest tests/test_vision.py -q`

Expected: review request models/functions 미정의로 FAIL

- [ ] **Step 3: 최소 구현**

`VisionImage`, `VisionView`, `VisionReviewRequest` Pydantic model을 `vision.py`에
추가한다. request는 plan, 원본, 수정본, verification report와 PNG SHA-256을
포함한다. detail view의 `field_ids`는 field `visual_regions`와 crop bbox 교차로
계산한다. canonical JSON으로 `review_id`를 만든다.

- [ ] **Step 4: 통과 확인**

Run: `UV_CACHE_DIR=/private/tmp/hwp-editor-uv-cache uv run --offline pytest tests/test_vision.py tests/test_protocol.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/hwp_mcp/vision.py src/hwp_mcp/server.py tests/test_vision.py tests/test_protocol.py
git commit -m "feat: bind vision review artifacts"
```

### Task 4: Sampling capability 분기와 범용 Host 제출

**Files:**
- Modify: `src/hwp_mcp/vision.py`
- Modify: `src/hwp_mcp/server.py`
- Modify: `src/hwp_mcp/workspace.py`
- Test: `tests/test_vision.py`
- Test: `tests/test_protocol.py`
- Test: `tests/test_v2_workflow.py`

**Interfaces:**
- Consumes: `VisionReviewRequest`
- Produces: `HostReviewer`, `HostVisionSubmission`
- Produces: `validate_host_submission(request: VisionReviewRequest, reviewer: HostReviewer, decision: VisionDecision) -> dict[str, Any]`
- Produces: `submit_host_vision_review(path, plan_id, review_id, reviewer, decision)`
- Changes: final source allowlist to `mcp_sampling | host_vision_submission`

- [ ] **Step 1: 실패 테스트 작성**

```python
@pytest.mark.parametrize("model", ["gemini-test", "gpt-test", "claude-test"])
def test_host_review_is_model_agnostic(model: str) -> None:
    review = validate_host_submission(
        request,
        reviewer={"provider": "test", "model": model, "capabilities": ["image_input"]},
        decision={
            "verdict": "PASS",
            "summary": "필드가 원래 입력란 경계 안에 배치됨",
            "fields": [{
                "field_id": "field-1",
                "verdict": "PASS",
                "reason": "업체명 라벨 오른쪽 셀 안에 중첩 없이 배치됨",
                "evidence_view_ids": ["page-001-full", "page-001-band-001"],
            }],
        },
    )
    assert review.source == "host_vision_submission"


def test_host_review_rejects_tampered_or_missing_evidence() -> None:
    reviewer = {"provider": "test", "model": "text-only", "capabilities": []}
    decision = {
        "verdict": "PASS",
        "summary": "검토 완료",
        "fields": [{
            "field_id": "field-1",
            "verdict": "PASS",
            "reason": "입력란에 배치됨",
            "evidence_view_ids": ["page-001-full"],
        }],
    }
    with pytest.raises(DocumentError, match="image_input"):
        validate_host_submission(request, reviewer=reviewer, decision=decision)
```

Protocol test의 unsupported Client에서는 `create_message`가 호출되지 않고
`VISION_REVIEW_REQUIRED`, request path와
`next_action=submit_host_vision_review`가 반환되어야 한다.

- [ ] **Step 2: 실패 확인**

Run: `UV_CACHE_DIR=/private/tmp/hwp-editor-uv-cache uv run --offline pytest tests/test_vision.py tests/test_protocol.py tests/test_v2_workflow.py -q`

Expected: Host 제출 Tool과 capability 분기 부재로 FAIL

- [ ] **Step 3: 최소 구현**

`review_document_vision`은 `ClientCapabilities(sampling=SamplingCapability())`를
호출 전에 확인한다. 미지원이면 state를 `PENDING_VISION_REVIEW`로 유지한다.

`submit_host_vision_review`은 다음을 재검증한다.

- 현재 plan/review ID와 모든 artifact hash
- `image_input` capability
- 편집 field 정확한 집합
- field에 매핑된 full view
- detail view가 있으면 해당 detail evidence
- unique reason과 aggregate verdict

유효한 Sampling 실패 판정은 Host PASS로 덮어쓰지 못한다. finalizer는 두 source
모두 같은 request/artifact hash를 요구한다.

- [ ] **Step 4: 통과 확인**

Run: `UV_CACHE_DIR=/private/tmp/hwp-editor-uv-cache uv run --offline pytest tests/test_vision.py tests/test_protocol.py tests/test_v2_workflow.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/hwp_mcp/vision.py src/hwp_mcp/server.py src/hwp_mcp/workspace.py tests/test_vision.py tests/test_protocol.py tests/test_v2_workflow.py
git commit -m "feat: support host vision review"
```

### Task 5: 안내문과 전체 회귀 검증

**Files:**
- Modify: `src/hwp_mcp/instructions.md`
- Modify: `README.md`
- Test: `tests/`

**Interfaces:**
- Documents: approval → apply → Sampling/Host Vision → finalize

- [ ] **Step 1: 안내문 계약 테스트 갱신**

```python
assert "submit_host_vision_review" in initialize_result.instructions
assert "VERIFIED_FINAL" in initialize_result.instructions
```

- [ ] **Step 2: 문서 갱신**

Sampling 미지원 Host는 full-page PNG와 모든 관련 detail band를 이미지 입력으로
직접 열고 판정해야 한다. XML/SVG 요약만 읽거나 이미지 입력이 없는 모델은
`NEEDS_HUMAN`으로 중단한다고 명시한다.

- [ ] **Step 3: 전체 테스트**

Run: `UV_CACHE_DIR=/private/tmp/hwp-editor-uv-cache uv run --offline pytest -q`

Expected: 전체 PASS

- [ ] **Step 4: 정적 검증**

Run: `git diff --check`

Expected: 출력 없음

- [ ] **Step 5: 커밋**

```bash
git add README.md src/hwp_mcp/instructions.md tests
git commit -m "docs: explain host vision finalization"
```
