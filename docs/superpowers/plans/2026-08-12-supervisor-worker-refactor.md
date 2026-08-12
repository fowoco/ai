# Supervisor–Worker Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the currently working Renewal workflow into explicit Supervisor–Worker agent responsibilities without changing public contracts or runtime behavior.

**Architecture:** Keep the existing `RenewalState`, rules-first Supervisor, LangGraph routes, service composition, and Tool implementations. Add only thin callable Worker boundaries around existing intent, document mapping, document execution, and review behavior; characterize public output before rewiring the graph. Unknown-document MCP/Qwen automation remains outside this plan.

**Tech Stack:** Python 3.11, LangGraph, FastAPI, Pydantic 2, pytest, existing document services

**Design Reference:** `docs/superpowers/specs/2026-08-12-supervisor-worker-refactor-design.md`

## Global Constraints

- Preserve every existing API path, request/response schema, HTTP status, and public field.
- Preserve `outcome`, `status`, `scenario`, `caseSignals`, `progressEvents`, `evidence`, and Supervisor routing semantics.
- Preserve `PLAN -> CONTEXT_REQUIRED -> ANALYZE`; AI requests canonical keys and Server owns tenant-authorized Context lookup.
- Preserve current Renewal routes: `ask_hr`, `ask_worker`, `ocr`, `generate`, `out_of_scope`.
- Preserve current behavior where the OCR route proceeds to four registered document drafts even when fields remain missing.
- Preserve the four registered template IDs, field mapping precedence, document-level `stub` fallback, and final `REVIEW_REQUIRED` outcome.
- Preserve Language Assistant projection, protected facts, Easy Korean, translation, EPS retrieval, and placeholder fallback.
- Do not add Agent retries, top-level Worker parallelism, automatic completion, direct DB access, SQL, new APIs, new dependencies, MCP calls, Qwen mapping, or unknown-document automation.
- OCR, Server Context Resolver, HWP/HWPX editing, conversion, and future MCP remain Tools; Agents only decide, route, map, or review.
- Reuse current functions and services. Do not duplicate template mappers, document editors, converters, OCR clients, or Language Assistant graphs.
- Use test-first changes and keep each commit limited to its Task files.

---

## File Structure

- `app/agents/workflow_graph/workers.py`: minimal callable Worker boundaries for business recognition, document intelligence, document automation, and review.
- `app/agents/workflow_graph/state.py`: one internal-only document plan field in existing Shared State.
- `app/agents/workflow_graph/subgraphs.py`: compose document intelligence, automation, and review in the existing document subgraph.
- `app/agents/workflow_graph/graph.py`: wire existing language/OCR Tools and the refactored document subgraph without route changes.
- `app/agents/workflow_graph/nodes/document_generator.py`: allow the existing generator to consume a precomputed registered-template value plan.
- `app/agents/workflow_graph/nodes/actions.py`: keep compatibility helper behavior while delegating review-state assembly.
- `tests/agents/test_workflow_characterization.py`: public behavior snapshots for the five existing routes.
- `tests/agents/test_workflow_workers.py`: focused Worker contract tests.
- `tests/agents/test_workflow_graph.py`: route and progress regression assertions after graph rewiring.
- `tests/agents/test_document_field_map.py`: precomputed-plan execution parity.

### Task 1: Freeze Public Renewal Behavior

**Files:**
- Create: `tests/agents/test_workflow_characterization.py`

**Interfaces:**
- Consumes: `RenewalOrchestrator.run(...) -> RenewalState` and existing fake/stub dependencies.
- Produces: `public_result(state: RenewalState) -> dict[str, object]`, a test-only projection that includes every behavior-sensitive public field except nondeterministic generated paths.

- [ ] **Step 1: Add the public projection helper and five route characterization tests**

```python
PUBLIC_KEYS = (
    "intent", "workflow_id", "confidence", "status", "outcome", "scenario",
    "phase", "step", "slots", "missing_slots", "guide_message",
    "worker_request_message", "language_assistant", "ocr_result",
    "evidence", "document_validation", "case_signals", "progress_events",
    "supervisor_reason", "supervisor_source", "active_subgraph", "errors",
)


def public_result(state):
    result = {key: state.get(key) for key in PUBLIC_KEYS}
    result["generated_documents"] = [
        {key: value for key, value in item.items() if key != "path"}
        for item in state.get("generated_documents", [])
    ]
    return result
```

Add one test for each existing route:

- `ask_worker`: no identity documents; assert `WAITING_WORKER`, existing guide fallback, document-combination evidence, and exact route order in `progress_events`.
- `ask_hr`: identity slots present, contract slots missing; assert `NEEDS_INFO` and no generated documents.
- `ocr`: document input present; use `InMemoryDb`, assert OCR persistence, then four draft results and `REVIEW_REQUIRED`.
- `generate`: all identity and contract slots present; assert the exact four template IDs and `REVIEW_REQUIRED`.
- `out_of_scope`: inject a `LanguageNode` returning `intent="OUT_OF_SCOPE"`; assert `CANCELLED` and no Tool execution.

Keep assertions on public values and event order. Do not assert object identities or temporary paths.

- [ ] **Step 2: Run the characterization tests against current code**

Run: `/opt/homebrew/bin/uv run pytest tests/agents/test_workflow_characterization.py -q`

Expected: PASS on the unrefactored implementation. If a proposed assertion does not match current behavior, change the assertion to repository truth; do not change production code in this Task.

- [ ] **Step 3: Run focused existing regression tests**

Run: `/opt/homebrew/bin/uv run pytest tests/agents/test_workflow_graph.py tests/agents/test_supervisor.py tests/api/test_workflows_endpoint.py -q`

Expected: PASS with pristine output.

- [ ] **Step 4: Commit Task 1**

```bash
git add tests/agents/test_workflow_characterization.py
git commit -m "test: characterize renewal workflow behavior"
```

### Task 2: Introduce Minimal Business and Document Worker Boundaries

**Files:**
- Create: `app/agents/workflow_graph/workers.py`
- Modify: `app/agents/workflow_graph/state.py:24-62`
- Create: `tests/agents/test_workflow_workers.py`

**Interfaces:**
- Consumes: existing `LanguageNode`, `DocumentGenerator`, `values_for_template()`, and `draft_template_ids()`.
- Produces: `BusinessRecognitionAgent(language_node: LanguageNode)` callable returning the existing language patch unchanged.
- Produces: `DocumentIntelligenceAgent()` callable returning `{"document_field_values": dict[str, dict[str, object]]}` for the existing four registered templates.
- Produces: `DocumentAutomationAgent(document_generator: DocumentGenerator)` callable returning `{"generated_documents": list[dict[str, object]]}`.
- Produces: `ValidationReviewAgent()` callable returning the current generated-document review patch.
- Produces: internal `RenewalState.document_field_values`, not exposed by API or `TaskStore`.

- [ ] **Step 1: Write failing Worker contract tests**

```python
def test_business_agent_preserves_language_patch() -> None:
    expected = {"intent": "EXPIRY_RENEWAL", "workflow_id": "WF-STY-001"}
    agent = BusinessRecognitionAgent(lambda state: expected)
    assert agent(empty_state()) == expected


def test_document_intelligence_reuses_registered_mappers() -> None:
    state = filled_state()
    patch = DocumentIntelligenceAgent()(state)
    assert tuple(patch["document_field_values"]) == RENEWAL_DRAFT_TEMPLATE_IDS
    assert patch["document_field_values"]["standard_labor_contract_v6"] == (
        values_for_template("standard_labor_contract_v6", state)
    )


def test_document_automation_passes_state_to_existing_generator() -> None:
    seen = []
    agent = DocumentAutomationAgent(lambda state: seen.append(state) or [{"status": "stub"}])
    patch = agent(empty_state())
    assert seen and patch == {"generated_documents": [{"status": "stub"}]}


def test_review_agent_preserves_review_required_patch() -> None:
    state = empty_state()
    state["generated_documents"] = [{"status": "stub"}]
    assert ValidationReviewAgent()(state) == {
        "scenario": "generate",
        "status": "READY_FOR_REVIEW",
        "outcome": "REVIEW_REQUIRED",
        "missing_slots": [],
        "guide_message": None,
        "worker_request_message": None,
        "case_signals": ["GENERATE_DRAFTS", "READY_FOR_REVIEW"],
        "phase": "PHASE_3_EXTRACTION_DOCUMENT",
        "step": "STEP_13_DOCUMENT_DRAFT",
    }
```

Use existing test helpers or minimal local helpers; do not add a generic Agent base class or Protocol for one implementation.

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/homebrew/bin/uv run pytest tests/agents/test_workflow_workers.py -q`

Expected: FAIL because `workflow_graph.workers` does not exist.

- [ ] **Step 3: Implement the four minimal callable Workers and internal State field**

```python
class BusinessRecognitionAgent:
    def __init__(self, language_node: LanguageNode) -> None:
        self._language_node = language_node

    def __call__(self, state: RenewalState) -> dict[str, Any]:
        return dict(self._language_node(state))


class DocumentIntelligenceAgent:
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        return {
            "document_field_values": {
                template_id: values_for_template(template_id, state)
                for template_id in draft_template_ids(state)
            }
        }


class DocumentAutomationAgent:
    def __init__(self, document_generator: DocumentGenerator) -> None:
        self._document_generator = document_generator

    def __call__(self, state: RenewalState) -> dict[str, Any]:
        return {"generated_documents": self._document_generator(state)}


class ValidationReviewAgent:
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        del state
        return {
            "scenario": "generate",
            "status": TaskStatus.READY_FOR_REVIEW.value,
            "outcome": "REVIEW_REQUIRED",
            "missing_slots": [],
            "guide_message": None,
            "worker_request_message": None,
            "case_signals": ["GENERATE_DRAFTS", "READY_FOR_REVIEW"],
            "phase": WorkflowPhase.EXTRACTION_DOCUMENT.value,
            "step": WorkflowStep.STEP_13_DOCUMENT_DRAFT.value,
        }
```

Add `document_field_values: NotRequired[dict[str, dict[str, object]]]` to `RenewalState` and initialize it to `{}`. Do not include it in API response or `InMemoryTaskStore.save()`.

- [ ] **Step 4: Run focused tests**

Run: `/opt/homebrew/bin/uv run pytest tests/agents/test_workflow_workers.py tests/agents/test_init_state.py -q`

Expected: PASS with pristine output.

- [ ] **Step 5: Commit Task 2**

```bash
git add app/agents/workflow_graph/workers.py app/agents/workflow_graph/state.py tests/agents/test_workflow_workers.py
git commit -m "refactor: define renewal worker boundaries"
```

### Task 3: Execute Precomputed Registered-Template Plans

**Files:**
- Modify: `app/agents/workflow_graph/nodes/document_generator.py:61-114`
- Modify: `tests/agents/test_document_field_map.py`

**Interfaces:**
- Consumes: internal `RenewalState.document_field_values` from Task 2.
- Preserves: `EditingServiceDocumentGenerator.__call__(state) -> list[dict[str, Any]]` and existing document result schema.
- Produces: exact same generated or `stub` documents while avoiding a second call to `values_for_template()` when a plan exists.

- [ ] **Step 1: Write a failing precomputed-plan parity test**

```python
def test_generator_uses_precomputed_document_field_values(tmp_path: Path) -> None:
    state = filled_state()
    state["document_field_values"] = {
        "standard_labor_contract_v6": {"employee_name": "PLAN VALUE"}
    }
    generator = EditingServiceDocumentGenerator(
        output_dir=tmp_path,
        template_ids=("standard_labor_contract_v6",),
    )
    result = generator(state)
    assert result[0]["mapped_fields"] == ["employee_name"]
```

Also assert the existing no-plan path still derives values through `values_for_template()`.

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/homebrew/bin/uv run pytest tests/agents/test_document_field_map.py -q`

Expected: FAIL because the generator ignores `document_field_values`.

- [ ] **Step 3: Reuse the precomputed plan when present**

Inside the existing template loop, replace only the value selection:

```python
plans = state.get("document_field_values") or {}
values = dict(plans[tid]) if tid in plans else values_for_template(tid, state)
```

Keep destination, editing call, result fields, exception handling, and document-level `stub` fallback unchanged.

- [ ] **Step 4: Run focused document tests**

Run: `/opt/homebrew/bin/uv run pytest tests/agents/test_document_field_map.py tests/documents/test_editing_service.py -q`

Expected: PASS with pristine output.

- [ ] **Step 5: Commit Task 3**

```bash
git add app/agents/workflow_graph/nodes/document_generator.py tests/agents/test_document_field_map.py
git commit -m "refactor: execute precomputed document plans"
```

### Task 4: Rewire Existing LangGraph Through Worker Boundaries

**Files:**
- Modify: `app/agents/workflow_graph/subgraphs.py:21-135`
- Modify: `app/agents/workflow_graph/graph.py:32-102`
- Modify: `app/agents/workflow_graph/nodes/actions.py:223-242`
- Modify: `tests/agents/test_workflow_graph.py`
- Modify: `tests/agents/test_workflow_characterization.py`

**Interfaces:**
- Consumes: four Workers from Task 2 and precomputed plan support from Task 3.
- Preserves: `build_language_subgraph`, `build_ocr_subgraph`, `build_document_subgraph`, `build_renewal_graph`, and `generate_docs` call signatures.
- Produces: document subgraph node order `document_intelligence -> document_automation -> validation_review` with existing public progress event semantics.

- [ ] **Step 1: Add failing graph-structure and behavior assertions**

Update focused tests to require:

```python
assert [
    event["message"] for event in state["progress_events"]
    if event.get("subgraph") == "document"
] == [
    "Document 서브그래프: 초안 생성",
]
assert state["outcome"] == "REVIEW_REQUIRED"
assert len(state["generated_documents"]) == 4
```

Add an injected generator spy test proving document automation receives a state containing `document_field_values` for all four template IDs. Do not expose internal node names or the plan field through the HTTP response.

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/homebrew/bin/uv run pytest tests/agents/test_workflow_graph.py tests/agents/test_workflow_characterization.py -q`

Expected: the new generator-spy assertion FAILS because mapping and execution are not separated.

- [ ] **Step 3: Rewire the current subgraphs minimally**

In `build_language_subgraph()`, wrap the injected or stub language node with `BusinessRecognitionAgent`; keep event messages and State patches unchanged.

In `build_document_subgraph()`:

1. `document_intelligence` calls `DocumentIntelligenceAgent`.
2. `document_automation` calls `DocumentAutomationAgent` and appends the one existing document progress event.
3. `validation_review` calls `ValidationReviewAgent`.
4. Edges are `START -> document_intelligence -> document_automation -> validation_review -> END`.

Keep `build_renewal_graph()` route edges unchanged, including `ocr -> generate`.

Make `generate_docs()` a compatibility wrapper that invokes `DocumentAutomationAgent`, then `ValidationReviewAgent`, merging their patches. Existing direct callers must receive the same result.

- [ ] **Step 4: Run characterization and workflow tests**

Run: `/opt/homebrew/bin/uv run pytest tests/agents/test_workflow_workers.py tests/agents/test_workflow_graph.py tests/agents/test_workflow_characterization.py tests/agents/test_workflow_adapters.py tests/api/test_workflows_endpoint.py -q`

Expected: PASS; all public characterization values remain unchanged.

- [ ] **Step 5: Commit Task 4**

```bash
git add app/agents/workflow_graph/subgraphs.py app/agents/workflow_graph/graph.py app/agents/workflow_graph/nodes/actions.py tests/agents/test_workflow_graph.py tests/agents/test_workflow_characterization.py
git commit -m "refactor: route renewal work through agents"
```

### Task 5: Verify External Contract and Regression Safety

**Files:**
- Modify only if a behavior-preservation test reveals an actual regression in Task 2-4 files.

**Interfaces:**
- Consumes: complete refactor from Tasks 1-4.
- Produces: verification evidence only; no new product capability.

- [ ] **Step 1: Verify no external schema or route change**

Run:

```bash
git diff --name-only origin/feat/mcp_mapping...HEAD
git diff origin/feat/mcp_mapping...HEAD -- app/api app/ocr app/agents/language app/documents docs/contracts
```

Expected: no production diff under `app/api`, `app/ocr`, `app/agents/language`, `app/documents`, or `docs/contracts`; only planned workflow-graph production files, tests, and design/plan documents changed.

- [ ] **Step 2: Run the complete relevant test suite**

Run:

```bash
/opt/homebrew/bin/uv run pytest tests/agents tests/api/test_workflows_endpoint.py tests/api/test_analyses_endpoint.py tests/api/test_ocr_endpoint.py tests/api/test_language_endpoint.py tests/documents -q
```

Expected: PASS with pristine output.

- [ ] **Step 3: Run lint and diff checks**

Run:

```bash
/opt/homebrew/bin/uv run ruff check app/agents/workflow_graph tests/agents
git diff --check origin/feat/mcp_mapping...HEAD
git status --short
```

Expected: all commands exit 0 and worktree is clean.

- [ ] **Step 4: Commit only if verification required a regression fix**

If Step 2 or 3 required a code correction, commit only that correction and its covering test:

```bash
git add <corrected-task-files-and-covering-tests>
git commit -m "fix: preserve renewal refactor behavior"
```

If no correction was required, create no empty commit.

## Completion Gate

Required result:

- All five existing routes preserve their characterized public behavior.
- Existing API and Pydantic contracts remain unchanged.
- Registered templates still produce the same four document result records.
- Document mapping, execution, and review are separate Worker steps built from current functions.
- OCR, DB Context, document editing, conversion, and MCP remain Tools.
- No new retry, top-level parallelism, automatic completion, dependency, API, MCP/Qwen, or unknown-document feature is present.
- Relevant tests, Ruff, and `git diff --check` pass with a clean worktree.
