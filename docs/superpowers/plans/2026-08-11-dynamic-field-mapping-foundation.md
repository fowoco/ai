# Dynamic Field Mapping Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated, versioned Rule → Qwen3 Embedding → Qwen3 Reranker pipeline that maps unknown MCP document fields to canonical fields without touching the existing registered-template path.

**Architecture:** A new `app.documents.dynamic_automation` package owns strict contracts, a YAML canonical catalog, structural field-context construction, deterministic rules, model ports, Qwen3 adapters, decision gating, and document-wide conflict validation. The deliverable is an offline mapping service and evaluation harness; it performs no DB access and no document edits.

**Tech Stack:** Python 3.11, Pydantic 2, PyYAML, transformers 4, sentence-transformers 5, PyTorch 2, pytest, existing MCP field registry JSON

**Design Reference:** `docs/superpowers/specs/2026-08-11-dynamic-document-automation-design.md`

**Prerequisite:** None. Complete this plan before the read-only query and orchestration plans.

## Global Constraints

- Do not modify `app/agents/workflow_graph/document_field_map.py` or any existing template mapper.
- Do not modify `app/documents/editing`, `app/documents/hwp5`, `app/documents/hwpx`, or `hwp-editor` behavior.
- Keep all new production code under `app/documents/dynamic_automation`.
- Treat every document label and MCP field as untrusted input.
- A missing model or reranker may reduce coverage but must never lower an automatic-match threshold.
- Persist labels and structural context only; never persist resolved DB values in mapping feedback.
- Pin Qwen model repository and revision in configuration before enabling model-backed matching.
- Run every task using red-green TDD and commit only the files listed by that task.

---

## File Structure

- `app/documents/dynamic_automation/__init__.py`: public mapping exports only.
- `app/documents/dynamic_automation/models.py`: strict immutable contracts and enums.
- `app/documents/dynamic_automation/catalog.py`: catalog loading, validation, indexing, and lookup.
- `app/documents/dynamic_automation/resources/canonical_fields.v1.yaml`: initial canonical definitions.
- `app/documents/dynamic_automation/field_context.py`: MCP registry to structural context conversion.
- `app/documents/dynamic_automation/rules.py`: exact alias and non-data rules.
- `app/documents/dynamic_automation/ports.py`: embedding, reranking, and feedback protocols.
- `app/documents/dynamic_automation/qwen.py`: lazy Qwen3 model adapters.
- `app/documents/dynamic_automation/mapper.py`: candidate filtering, decision gate, and mapping orchestration.
- `app/documents/dynamic_automation/global_validation.py`: cross-field conflicts and repeat handling.
- `app/documents/dynamic_automation/feedback.py`: JSONL feedback records without field values.
- `scripts/evaluate_dynamic_mapping.py`: reproducible offline evaluation command.
- `tests/documents/dynamic_automation/`: focused unit tests and fakes.
- `tests/fixtures/dynamic_automation/`: registry and labeled mapping fixtures.

### Task 1: Define strict mapping contracts and the versioned catalog

**Files:**
- Create: `app/documents/dynamic_automation/__init__.py`
- Create: `app/documents/dynamic_automation/models.py`
- Create: `app/documents/dynamic_automation/catalog.py`
- Create: `app/documents/dynamic_automation/resources/canonical_fields.v1.yaml`
- Modify: `pyproject.toml:52-59`
- Test: `tests/documents/dynamic_automation/test_catalog.py`

**Interfaces:**
- Produces: `MappingStatus`, `CanonicalSource`, `CanonicalFieldDefinition`, `DocumentFieldContext`, `ScoredCandidate`, `MappingEvidence`, `FieldMapping`, `CanonicalMappingPlan`.
- Produces: `CanonicalCatalog.load(path: Path) -> CanonicalCatalog`, `get(field_id: str) -> CanonicalFieldDefinition`, and `compatible(context: DocumentFieldContext) -> tuple[CanonicalFieldDefinition, ...]`.
- Consumes: no new application interfaces.

- [ ] **Step 1: Write failing catalog contract tests**

```python
def test_catalog_rejects_duplicate_ids_and_unapproved_identifiers(tmp_path: Path) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text(DUPLICATE_OR_UNSAFE_CATALOG, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate|identifier"):
        CanonicalCatalog.load(path)


def test_compatible_filters_wrong_type_and_non_repeatable_role() -> None:
    catalog = CanonicalCatalog.load(DEFAULT_CATALOG_PATH)
    context = DocumentFieldContext(
        field_id="f1", label="전화번호", normalized_label="전화번호",
        field_type="phone", document_title="통합신청서", section="현재 근무처",
        row_labels=("현재 근무처", "전화번호"), nearby_labels=(), options=(),
        repeat_index=0, required=True, kind="text_field",
    )
    ids = {item.field_id for item in catalog.compatible(context)}
    assert "company.phone" in ids
    assert "worker.date_of_birth" not in ids
```

- [ ] **Step 2: Run the tests and verify the expected import failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_catalog.py -q`

Expected: FAIL because `app.documents.dynamic_automation` does not exist.

- [ ] **Step 3: Implement strict Pydantic contracts and catalog validation**

```python
class MappingStatus(StrEnum):
    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    UNMAPPED = "UNMAPPED"
    NON_DATA = "NON_DATA"


class CanonicalSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    view: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    column: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    scope_keys: tuple[Literal["tenant_id", "worker_id", "company_id", "task_id"], ...]


class CanonicalFieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    field_id: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    entity: str
    value_type: str
    aliases: tuple[str, ...]
    description: str
    compatible_field_types: tuple[str, ...]
    repeatable: bool = False
    source: CanonicalSource
    sensitivity: Literal["public", "business", "personal", "sensitive"]
    formatter: str
```

Seed the catalog with the exact IDs `worker.legal_name`, `worker.nationality`, `worker.date_of_birth`, `worker.phone`, `worker.email`, `company.name`, `company.phone`, `company.address`, `company.representative_name`, `company.business_number`, `identity.passport_number`, `identity.alien_registration_number`, `contract.start_date`, `contract.end_date`, `contract.wage`, `contract.working_hours`, `contract.job_description`, `contract.work_location`, `contract.lodging`, and `application.date`.

- [ ] **Step 4: Add package data and dependencies**

Add `PyYAML>=6.0,<7` to the new `document-automation` optional dependency group and include `app.documents.dynamic_automation.resources/*.yaml` in setuptools package data. Do not add model dependencies until Task 4.

- [ ] **Step 5: Run focused and package-data tests**

Run: `python -m pytest tests/documents/dynamic_automation/test_catalog.py -q`

Expected: PASS with duplicate IDs, unsafe identifiers, unknown fields, and type filtering covered.

- [ ] **Step 6: Commit Task 1**

```bash
git add pyproject.toml app/documents/dynamic_automation tests/documents/dynamic_automation/test_catalog.py
git commit -m "feat(doc-automation): add canonical field catalog"
```

### Task 2: Build structural field context and reject obvious non-data fields

**Files:**
- Create: `app/documents/dynamic_automation/field_context.py`
- Create: `app/documents/dynamic_automation/rules.py`
- Test: `tests/documents/dynamic_automation/test_field_context.py`
- Test: `tests/documents/dynamic_automation/test_rules.py`
- Create: `tests/fixtures/dynamic_automation/integrated_application_registry.json`
- Create: `tests/fixtures/dynamic_automation/extension_application_registry.json`

**Interfaces:**
- Consumes: `DocumentFieldContext` from Task 1 and MCP `field_registry` dictionaries.
- Produces: `build_field_contexts(registry, *, document_title) -> tuple[DocumentFieldContext, ...]`.
- Produces: `classify_non_data(context) -> NonDataDecision` and `exact_alias_matches(context, catalog) -> tuple[CanonicalFieldDefinition, ...]`.

- [ ] **Step 1: Save minimized real-registry fixtures and write failing context tests**

```python
def test_context_distinguishes_company_phone_from_worker_phone(registry_fixture) -> None:
    contexts = build_field_contexts(registry_fixture, document_title="통합신청서")
    phone = next(item for item in contexts if item.field_id == "workplace-phone")
    assert phone.row_labels == ("현재 근무처", "사업자등록번호", "전화번호")
    assert phone.section == "현재 근무처"


def test_process_flow_label_is_non_data() -> None:
    decision = classify_non_data(make_context(label="확인ㆍ검토", section="처리절차"))
    assert decision.is_non_data is True
    assert decision.reason == "process_flow_label"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_field_context.py tests/documents/dynamic_automation/test_rules.py -q`

Expected: FAIL because the context builder and rules do not exist.

- [ ] **Step 3: Implement bounded context construction**

Build row groups from `row` and `column`, derive up to three row labels and four nearby labels, normalize Unicode and punctuation, cap every text field at 200 characters, and preserve `field_id`, `kind`, `required`, `type`, `options`, and repeat order. Never concatenate the full document body into model input.

```python
def build_field_contexts(
    registry: Sequence[Mapping[str, Any]], *, document_title: str
) -> tuple[DocumentFieldContext, ...]:
    validated = [_RegistryInput.model_validate(item) for item in registry]
    return tuple(_context_for(item, validated, document_title) for item in validated)
```

- [ ] **Step 4: Implement deterministic non-data and exact-alias rules**

Treat `official_region` and `signable_region` as non-data. Add exact normalized process labels `접수`, `확인검토`, `전산입력`, `신청서작성`, `고용센터`, page arrows, and official-use phrases. A substring alone must not produce `MATCHED`; exact aliases return candidates for the later decision gate.

- [ ] **Step 5: Run the fixture tests**

Run: `python -m pytest tests/documents/dynamic_automation/test_field_context.py tests/documents/dynamic_automation/test_rules.py -q`

Expected: PASS, including repeated `전화번호` contexts and process-flow rejection.

- [ ] **Step 6: Commit Task 2**

```bash
git add app/documents/dynamic_automation/field_context.py app/documents/dynamic_automation/rules.py tests/documents/dynamic_automation tests/fixtures/dynamic_automation
git commit -m "feat(doc-automation): build structural field contexts"
```

### Task 3: Implement model-independent hybrid mapping and global validation

**Files:**
- Create: `app/documents/dynamic_automation/ports.py`
- Create: `app/documents/dynamic_automation/mapper.py`
- Create: `app/documents/dynamic_automation/global_validation.py`
- Test: `tests/documents/dynamic_automation/fakes.py`
- Test: `tests/documents/dynamic_automation/test_mapper.py`
- Test: `tests/documents/dynamic_automation/test_global_validation.py`

**Interfaces:**
- Consumes: catalog, field contexts, exact/non-data rules.
- Produces: `CandidateRetriever.retrieve(context, candidates, top_k) -> tuple[ScoredCandidate, ...]`.
- Produces: `CandidateReranker.rerank(context, candidates) -> tuple[ScoredCandidate, ...]`.
- Produces: `HybridFieldMapper.map(contexts) -> CanonicalMappingPlan`.
- Produces: `validate_global_mapping(plan, catalog) -> CanonicalMappingPlan`.

- [ ] **Step 1: Write failing decision-gate tests with fake scores**

```python
def test_mapper_requires_absolute_score_and_margin(catalog, company_phone_context) -> None:
    mapper = mapper_with_scores(
        [("company.phone", 0.91), ("worker.phone", 0.88)],
        min_score=0.90,
        min_margin=0.10,
    )
    result = mapper.map((company_phone_context,)).mappings[0]
    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "insufficient_margin"


def test_reranker_failure_does_not_accept_embedding_top_one(catalog, context) -> None:
    mapper = mapper_with_reranker_error()
    assert mapper.map((context,)).mappings[0].status is MappingStatus.AMBIGUOUS
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_mapper.py tests/documents/dynamic_automation/test_global_validation.py -q`

Expected: FAIL because mapper ports and implementation do not exist.

- [ ] **Step 3: Implement candidate filters and fail-closed decision gate**

```python
class MappingThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    min_reranker_score: float = Field(ge=0, le=1)
    min_margin: float = Field(ge=0, le=1)
    exact_alias_requires_unique_entity: bool = True


class HybridFieldMapper:
    def map(self, contexts: Sequence[DocumentFieldContext]) -> CanonicalMappingPlan:
        mappings = tuple(self._map_one(context) for context in contexts)
        return validate_global_mapping(
            CanonicalMappingPlan(catalog_version=self.catalog.version, mappings=mappings),
            self.catalog,
        )
```

Record rule evidence, embedding rank, reranker score, top-2 margin, type compatibility, entity hint, catalog version, and model version in every mapping. Never emit `MATCHED` without a unique canonical ID and complete evidence.

- [ ] **Step 4: Implement document-wide conflict checks**

Downgrade conflicting non-repeatable canonical IDs, incompatible entity roles, and duplicate repeat indexes to `AMBIGUOUS`. Keep `NON_DATA` and `UNMAPPED` unchanged. Add tests where three `성명` fields cannot all become `worker.legal_name`.

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest tests/documents/dynamic_automation/test_mapper.py tests/documents/dynamic_automation/test_global_validation.py -q`

Expected: PASS with reranker outage, low margin, duplicate identity, and repeatable-field cases covered.

- [ ] **Step 6: Commit Task 3**

```bash
git add app/documents/dynamic_automation/ports.py app/documents/dynamic_automation/mapper.py app/documents/dynamic_automation/global_validation.py tests/documents/dynamic_automation
git commit -m "feat(doc-automation): add fail-closed hybrid mapper"
```

### Task 4: Add lazy Qwen3 embedding and reranker adapters

**Files:**
- Create: `app/documents/dynamic_automation/qwen.py`
- Modify: `app/core/config.py:67-83`
- Modify: `.env.example`
- Modify: `pyproject.toml:47-51`
- Modify: `scripts/download_language_models.py`
- Test: `tests/documents/dynamic_automation/test_qwen_adapters.py`
- Test: `tests/documents/dynamic_automation/test_mapping_config.py`
- Create: `tests/integration/dynamic_automation/test_qwen_mapping_smoke.py`

**Interfaces:**
- Consumes: `CandidateRetriever` and `CandidateReranker` protocols from Task 3.
- Produces: `Qwen3EmbeddingRetriever` and `Qwen3CandidateReranker`.
- Produces settings: `dynamic_automation_mapping_enabled`, `dynamic_automation_embedding_model_path`, `dynamic_automation_reranker_model_path`, `dynamic_automation_min_reranker_score`, and `dynamic_automation_min_margin`.

- [ ] **Step 1: Write adapter tests against fake tokenizers and models**

```python
def test_embedding_query_includes_instruction_and_structural_context() -> None:
    backend = RecordingEmbeddingBackend()
    retriever = Qwen3EmbeddingRetriever(backend=backend)
    retriever.retrieve(COMPANY_PHONE_CONTEXT, CANDIDATES, top_k=3)
    assert "회사 연락처 canonical field를 찾으세요" in backend.queries[0]
    assert "현재 근무처" in backend.queries[0]


def test_reranker_uses_yes_no_probability_and_returns_zero_to_one() -> None:
    reranker = Qwen3CandidateReranker(backend=FakeLogitBackend(scores=(0.8, 0.2)))
    ranked = reranker.rerank(CONTEXT, CANDIDATES)
    assert ranked[0].score == pytest.approx(0.8)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_qwen_adapters.py tests/documents/dynamic_automation/test_mapping_config.py -q`

Expected: FAIL because Qwen adapters and settings are absent.

- [ ] **Step 3: Add pinned model settings and optional dependencies**

Add `sentence-transformers>=5,<6`, `transformers>=4.51,<5`, and `torch>=2.2,<3` to `document-automation`. Default model paths must point below `FOWOCO_MODEL_CACHE_DIR`; network downloads at request time are forbidden. Define these exact manifests next to the adapter and teach the existing downloader script to fetch them only when `--include-document-automation` is supplied:

```python
QWEN3_EMBEDDING_REPO = "Qwen/Qwen3-Embedding-0.6B"
QWEN3_EMBEDDING_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QWEN3_RERANKER_REPO = "Qwen/Qwen3-Reranker-0.6B"
QWEN3_RERANKER_REVISION = "e61197ed45024b0ed8a2d74b80b4d909f1255473"
```

- [ ] **Step 4: Implement lazy local-only model adapters**

Use `SentenceTransformer(..., local_files_only=True)` for `Qwen/Qwen3-Embedding-0.6B`. Use `AutoTokenizer` and `AutoModelForCausalLM` with local-only loading for `Qwen/Qwen3-Reranker-0.6B`; compute the normalized probability of the official `yes` token against `no`. Cap mapping input at 512 tokens and batch candidates.

- [ ] **Step 5: Run adapter tests and the offline model smoke marker**

Run: `python -m pytest tests/documents/dynamic_automation/test_qwen_adapters.py tests/documents/dynamic_automation/test_mapping_config.py -q`

Expected: PASS without downloading weights.

Run when model cache is provisioned: `python -m pytest -m language_models tests/integration/dynamic_automation/test_qwen_mapping_smoke.py -q`

Expected: PASS and no outbound network request.

- [ ] **Step 6: Commit Task 4**

```bash
git add pyproject.toml .env.example app/core/config.py app/documents/dynamic_automation/qwen.py scripts/download_language_models.py tests/documents/dynamic_automation tests/integration/dynamic_automation
git commit -m "feat(doc-automation): add local Qwen3 mapping adapters"
```

### Task 5: Add privacy-safe feedback and an offline evaluation harness

**Files:**
- Create: `app/documents/dynamic_automation/feedback.py`
- Create: `scripts/evaluate_dynamic_mapping.py`
- Create: `tests/fixtures/dynamic_automation/mapping_cases.jsonl`
- Test: `tests/documents/dynamic_automation/test_feedback.py`
- Test: `tests/documents/dynamic_automation/test_evaluation.py`
- Create: `docs/evaluations/dynamic-document-mapping-baseline.md`

**Interfaces:**
- Consumes: `CanonicalMappingPlan` and reviewer decision.
- Produces: `MappingFeedbackRecord` and `JsonlMappingFeedbackStore.append(record) -> None`.
- Produces CLI metrics: extraction precision/recall, top-1, top-k recall, selective precision, coverage, ambiguous accuracy, and document zero-error rate.

- [ ] **Step 1: Write failing privacy and metric tests**

```python
def test_feedback_schema_has_no_value_field() -> None:
    schema = MappingFeedbackRecord.model_json_schema()
    serialized = json.dumps(schema)
    assert "resolved_value" not in serialized
    assert "db_value" not in serialized


def test_selective_metrics_count_wrong_auto_match() -> None:
    metrics = evaluate_cases([matched_case(correct=False), ambiguous_case(correct=True)])
    assert metrics.auto_precision == 0.0
    assert metrics.coverage == 0.5
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_feedback.py tests/documents/dynamic_automation/test_evaluation.py -q`

Expected: FAIL because feedback and evaluation modules do not exist.

- [ ] **Step 3: Implement append-only sanitized feedback**

Store layout hash, field context hash, bounded label/context, predicted and final canonical IDs, decision, candidate scores, catalog version, and model version. Reject extra keys and any key matching `value`, `passport`, `registration_number`, or `resident_number` unless it is part of a canonical field ID string.

- [ ] **Step 4: Implement deterministic evaluation and baseline output**

Make the CLI accept `--cases`, `--catalog`, `--output`, and `--mode rule|qwen`. Exit non-zero when auto precision is below `0.99` or sensitive-field precision is below `0.995`; emit a JSON report plus the checked-in Markdown baseline summary.

- [ ] **Step 5: Run the full foundation verification**

Run: `python -m pytest tests/documents/dynamic_automation -q`

Expected: PASS.

Run: `python scripts/evaluate_dynamic_mapping.py --cases tests/fixtures/dynamic_automation/mapping_cases.jsonl --catalog app/documents/dynamic_automation/resources/canonical_fields.v1.yaml --mode rule --output build/dynamic-mapping-baseline.json`

Expected: command completes and explicitly reports coverage and precision; the initial rule-only gate may remain disabled if it does not meet the automatic-match target.

- [ ] **Step 6: Commit Task 5**

```bash
git add app/documents/dynamic_automation/feedback.py scripts/evaluate_dynamic_mapping.py tests/documents/dynamic_automation tests/fixtures/dynamic_automation docs/evaluations/dynamic-document-mapping-baseline.md
git commit -m "test(doc-automation): add mapping feedback and evaluation"
```

### Task 6: Add Domain Encoder retrieval training and promotion gates

**Files:**
- Create: `app/documents/dynamic_automation/training.py`
- Create: `scripts/train_dynamic_mapping_models.py`
- Create: `scripts/compare_dynamic_mapping_models.py`
- Test: `tests/documents/dynamic_automation/test_training_dataset.py`
- Test: `tests/documents/dynamic_automation/test_model_promotion.py`
- Create: `tests/fixtures/dynamic_automation/approved_feedback.jsonl`

**Interfaces:**
- Consumes: sanitized `MappingFeedbackRecord` data from Task 5.
- Produces: `build_training_split(records) -> TrainingSplit`, `build_hard_negatives(split, catalog) -> tuple[TrainingPair, ...]`, and `ModelManifest`.
- Produces CLIs that train a domain bi-encoder/pair reranker and compare their manifests with the pinned Qwen3 baseline.

- [ ] **Step 1: Write failing leakage and promotion tests**

```python
def test_layout_hash_never_crosses_train_and_test() -> None:
    split = build_training_split(load_feedback_fixture())
    train_layouts = {item.document_layout_hash for item in split.train}
    test_layouts = {item.document_layout_hash for item in split.test}
    assert train_layouts.isdisjoint(test_layouts)


def test_model_is_not_promoted_when_precision_or_calibration_regresses() -> None:
    decision = compare_manifests(
        baseline=manifest(auto_precision=0.995, ece=0.03, p95_ms=200),
        candidate=manifest(auto_precision=0.990, ece=0.04, p95_ms=120),
    )
    assert decision.promote is False
    assert "auto_precision" in decision.reasons
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_training_dataset.py tests/documents/dynamic_automation/test_model_promotion.py -q`

Expected: FAIL because training contracts and promotion rules are absent.

- [ ] **Step 3: Implement group-safe datasets and hard negatives**

Group by layout hash, document kind/version, and source institution before splitting; reject records containing DB values. Generate hard negatives within compatible types and prioritize entity confusions such as worker/company/guarantor phone, worker/representative name, passport/registration number, and contract/application/expiry dates.

```python
class ModelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model_kind: Literal["qwen_baseline", "domain_bi_encoder", "domain_pair_reranker"]
    base_model_repo: str
    base_model_revision: str
    dataset_sha256: str
    catalog_version: str
    auto_precision: float
    sensitive_precision: float
    coverage: float
    expected_calibration_error: float
    p95_latency_ms: float
```

- [ ] **Step 4: Implement reproducible training and comparison CLIs**

`train_dynamic_mapping_models.py` accepts `--feedback`, `--catalog`, `--output-dir`, `--seed`, and `--model-kind bi-encoder|pair-reranker`; it writes weights plus `model-manifest.json`. `compare_dynamic_mapping_models.py` accepts baseline/candidate manifests and refuses promotion unless candidate auto precision and sensitive precision are no lower, coverage or p95 improves, calibration does not regress, and the candidate can retrieve a catalog field absent from its training labels.

- [ ] **Step 5: Run unit tests and the small fixture training smoke**

Run: `python -m pytest tests/documents/dynamic_automation/test_training_dataset.py tests/documents/dynamic_automation/test_model_promotion.py -q`

Expected: PASS.

Run with provisioned local model cache: `python scripts/train_dynamic_mapping_models.py --feedback tests/fixtures/dynamic_automation/approved_feedback.jsonl --catalog app/documents/dynamic_automation/resources/canonical_fields.v1.yaml --output-dir build/domain-mapping-smoke --seed 42 --model-kind bi-encoder`

Expected: writes `build/domain-mapping-smoke/model-manifest.json` with dataset and catalog hashes; production model configuration remains unchanged.

- [ ] **Step 6: Commit Task 6**

```bash
git add app/documents/dynamic_automation/training.py scripts/train_dynamic_mapping_models.py scripts/compare_dynamic_mapping_models.py tests/documents/dynamic_automation/test_training_dataset.py tests/documents/dynamic_automation/test_model_promotion.py tests/fixtures/dynamic_automation/approved_feedback.jsonl
git commit -m "feat(doc-automation): gate domain mapping model promotion"
```

## Plan 1 Completion Gate

Run:

```bash
python -m pytest tests/documents/dynamic_automation -q
python -m ruff check app/documents/dynamic_automation tests/documents/dynamic_automation scripts/evaluate_dynamic_mapping.py scripts/train_dynamic_mapping_models.py scripts/compare_dynamic_mapping_models.py
git diff --check
```

Required result: all commands exit 0; existing registered-template modules are unchanged; an MCP registry fixture can produce a versioned `CanonicalMappingPlan` without DB or MCP runtime access.
