# Dynamic Field Mapping Foundation — final fix report

Date: 2026-08-11

Base commit: `d788f6e`

Scope: the single user-authorized final fix wave. Existing registered-template/editing/HWP/HWPX/workflow behavior was left unchanged. The repository-wide baseline's 57 unrelated Language/Qdrant/Compose failures were not changed.

All model-backed tests below used protocol-complete deterministic fakes. No Qwen weights were downloaded or executed.

## 1. Mandatory Qwen execution evidence

**Root cause.** `scripts/evaluate_dynamic_mapping.py` read undocumented `FOWOCO_QWEN3_*` variables, discarded mapper evidence, and certified precision alone. Lazy backend failures were converted to expected `AMBIGUOUS` mappings, so exact-rule cases plus an expected ambiguous case could produce a false-green Qwen report with no successful inference.

**RED.** A direct CLI reproduction using only documented `FOWOCO_DYNAMIC_AUTOMATION_*` settings exited 1 without a report because the evaluator still required the alternate variables. Supplying the alternate variables while replacing `SentenceTransformer` with a constructor that raised reproduced the false green: exit 0, `gate.passed=true`, precision 1.0, coverage 0.5, and zero successful model inference. The focused regression command was:

```text
python -m pytest tests/documents/dynamic_automation/test_evaluation.py::test_qwen_cli_fails_closed_when_lazy_model_inference_never_succeeds tests/documents/dynamic_automation/test_evaluation.py::test_qwen_cli_uses_documented_settings_and_records_fake_backend_execution -q
```

Before the fix the missing-model assertion observed exit 0 instead of 2, and the documented-settings case could not construct the Qwen mapper.

**Minimal fix.** The evaluator now builds `Settings`, honors the documented enable flag, model paths, score threshold, and margin, and wraps both ports with successful-call counters. The JSON report records embedding/reranker execution counts and semantic case counts. Qwen certification requires both ports to execute successfully and every explicitly semantic expected-match case to pass. The fixture now contains `semantic-company-contact`, which cannot exact-rule match. Fake injection is limited to complete backend contracts on the Python entry point.

**GREEN.** The focused command above reports `2 passed`. The final rule CLI still exits 0 with six cases, precision 1.0, sensitive precision 1.0, and coverage 0.4.

**Files changed.** `scripts/evaluate_dynamic_mapping.py`; `tests/documents/dynamic_automation/test_evaluation.py`; `tests/fixtures/dynamic_automation/mapping_cases.jsonl`; `tests/integration/dynamic_automation/test_qwen_mapping_smoke.py`.

## 2. Repeated labels and structural containers

**Root cause.** Registry rows, nearby labels, and repeated-label counts were keyed without a table/container identity. Equal coordinates from different tables contaminated one another. Candidate filtering also treated `repeat_index > 0` as ineligible for non-repeatable canonical definitions. Field IDs were truncated to 200 characters and duplicate IDs were accepted.

**RED.** The focused container/repeat/identity regressions produced three failures: there was no preserved `container_id`, equal table coordinates shared row/nearby context, a repeated phone context lost candidates, and duplicate/oversized identities were not rejected.

```text
python -m pytest tests/documents/dynamic_automation/test_field_context.py::test_equal_coordinates_in_different_tables_are_container_local tests/documents/dynamic_automation/test_field_context.py::test_repeated_worker_and_company_phone_contexts_keep_compatible_candidates tests/documents/dynamic_automation/test_field_context.py::test_registry_rejects_duplicate_and_oversized_field_identities -q
```

**Minimal fix.** The registry adapter validates bounded `field_id` and real `target_id`, derives the table container from MCP target paths, rejects duplicate IDs, and never truncates identity fields. Row grouping, nearby-label search, section inference inputs, and repeated-label counters are container-local. Candidate compatibility no longer filters on repeat index; global mapping validation remains the repeatability enforcement layer. Fixtures use all fields emitted by `RegistryField.model_dump()`.

**GREEN.** `python -m pytest tests/documents/dynamic_automation/test_field_context.py tests/documents/dynamic_automation/test_catalog.py -q` reports `13 passed`.

**Files changed.** `app/documents/dynamic_automation/field_context.py`; `app/documents/dynamic_automation/models.py`; `app/documents/dynamic_automation/catalog.py`; `tests/documents/dynamic_automation/test_field_context.py`; `tests/documents/dynamic_automation/test_catalog.py`; `tests/fixtures/dynamic_automation/integrated_application_registry.json`; `tests/fixtures/dynamic_automation/extension_application_registry.json`.

## 3. Actual MCP field-type compatibility

**Root cause.** The canonical catalog declared invented transport types such as `business_number`, `alien_registration_number`, `name`, and `textarea`, while MCP serializes exactly nine registry types. A real serialized `number` business/alien-registration field therefore produced only the unrelated wage candidate or no identifier candidate.

**RED.** Loading an actual-shape integrated registry and calling `catalog.compatible()` for its two `number` identifiers showed `company.business_number` and `identity.alien_registration_number` missing. The focused contract test failed on both assertions.

```text
python -m pytest tests/documents/dynamic_automation/test_field_context.py::test_actual_mcp_number_fields_keep_identifier_candidates tests/documents/dynamic_automation/test_field_context.py::test_registry_fixture_and_type_union_match_actual_mcp_contract -q
```

**Minimal fix.** A constrained local `RegistryFieldType` mirrors MCP's `amount`, `checkbox`, `checkbox_group`, `date`, `number`, `phone`, `placeholder`, `signature`, and `text` union. Catalog `compatible_field_types` uses that type; semantic concepts remain in `value_type`. The YAML uses only real transport types and includes `number` for both registration identifiers. The contract fixture validates through the actual `hwp_mcp.fields.RegistryField` model and asserts union parity.

**GREEN.** The focused command reports `2 passed`; it is also covered by the 13-pass field-context/catalog run.

**Files changed.** `app/documents/dynamic_automation/models.py`; `app/documents/dynamic_automation/field_context.py`; `app/documents/dynamic_automation/resources/canonical_fields.v1.yaml`; `tests/documents/dynamic_automation/test_field_context.py`; integrated/extension registry and mapping-case fixtures.

## 4. Definition-based reranking

**Root cause.** `Qwen3CandidateReranker` sent `(context, canonical_field_id)` to the backend. The model never saw entity, aliases, value type, or description, and unknown IDs were never resolved.

**RED.** The two new adapter regressions failed against the old constructor/behavior: the resolver keyword was unsupported, and the backend would have accepted a bare unknown ID.

```text
python -m pytest tests/documents/dynamic_automation/test_qwen_adapters.py::test_reranker_backend_receives_full_resolved_canonical_definitions tests/documents/dynamic_automation/test_qwen_adapters.py::test_reranker_rejects_unknown_candidate_before_backend_execution -q
```

**Minimal fix.** The Qwen adapter accepts a definition resolver without changing the generic mapper port. It resolves the complete candidate batch before backend execution, verifies resolver identity, formats full definitions, and raises a clear fail-closed error for unknown/mismatched candidates. Evaluator, runtime loader, and conditional smoke constructors pass `catalog.get`.

**GREEN.** The focused command reports `2 passed`. Assertions prove the backend document contains canonical ID, entity, value type, aliases, and description, and that an unknown candidate leaves `backend.pairs == []`.

**Files changed.** `app/documents/dynamic_automation/qwen.py`; `app/documents/dynamic_automation/domain_adapters.py`; `scripts/evaluate_dynamic_mapping.py`; `scripts/train_dynamic_mapping_models.py`; `tests/documents/dynamic_automation/test_qwen_adapters.py`; `tests/integration/dynamic_automation/test_qwen_mapping_smoke.py`.

## 5. Conservative promotion trade-off

**Root cause.** The promotion predicate used coverage improvement **or** latency improvement. It promoted catastrophic loss on one axis when the other improved slightly.

**RED.** Two direct regressions both observed `promote=True`: coverage `0.80 -> 0.01` with latency `200 -> 199`, and coverage `0.80 -> 0.81` with latency `200 -> 999`.

```text
python -m pytest tests/documents/dynamic_automation/test_model_promotion.py::test_model_is_not_promoted_for_catastrophic_coverage_loss_with_latency_gain tests/documents/dynamic_automation/test_model_promotion.py::test_model_is_not_promoted_for_latency_regression_with_coverage_gain -q
```

**Minimal fix.** Promotion now requires coverage `>=` baseline, p95 latency `<=` baseline, and at least one strict improvement. Failures receive separate `coverage`, `p95_latency_ms`, or no-strict-improvement reasons.

**GREEN.** `python -m pytest tests/documents/dynamic_automation/test_model_promotion.py -o addopts='' -q` reports `19 passed` after the final evidence-byte hardening.

**Files changed.** `app/documents/dynamic_automation/training.py`; `tests/documents/dynamic_automation/test_model_promotion.py`.

## 6. Evidence-bound, loadable domain adapters

**Root cause.** Training wrote an unused bias/calibration JSON and a hand-filled manifest. No checked-in runtime loader applied the weights. Manifests had no exact artifact/report hashes or code/count bindings; comparison trusted manifest metrics and an editable unseen-field boolean. Pair calibration also discarded score orientation, so a reversed base ranker could not be corrected.

**RED.** The initial end-to-end test failed at collection with `ModuleNotFoundError: app.documents.dynamic_automation.domain_adapters`; after introducing the interface, the old train entry point rejected injected complete backends. A comparison regression also showed that omitting all four exact artifact/report byte hashes still returned `PromotionDecision(promote=True)`. A separate final calibration RED reproduced the orientation defect:

```text
python -m pytest tests/documents/dynamic_automation/test_domain_adapters.py::test_trained_reranker_calibration_can_reverse_a_wrong_base_ranking -q
```

It failed with `assert 1.25 < 0`, proving the learned head remained monotonic in the wrong direction.

**Minimal fix.** `domain_adapters.py` provides strict typed v2 artifact loaders through the existing retriever/reranker ports. Query projection is applied to fresh base query vectors; reranker scale/bias is applied to fresh base scores. Loaders validate exact SHA-256, artifact kind/format, pinned repo/revision, dimensions, finiteness, and score contracts. Training exports the artifact first, reloads it through the public loader, evaluates held-out and generated unseen cases, hashes exact report bytes, and emits a manifest bound to artifact/report/dataset/catalog hashes, schema/code versions, pinned base, sample/cohort counts, and structured unseen candidate/rank evidence. Comparison requires all four actual artifact/report byte hashes, validates report cross-links, and derives gates from the report; omitted hashes fail closed. The calibration scale now preserves learned score orientation.

**GREEN.** `python -m pytest tests/documents/dynamic_automation/test_domain_adapters.py -q` reports `4 passed`. The cache-independent CLI boundary command selecting the fake train/export/load/evaluate/compare test and the reversed-ranker test reports `2 passed`. Report or artifact tampering fails closed.

**Files changed.** `app/documents/dynamic_automation/domain_adapters.py`; `app/documents/dynamic_automation/training.py`; `scripts/train_dynamic_mapping_models.py`; `scripts/compare_dynamic_mapping_models.py`; `tests/documents/dynamic_automation/test_domain_adapters.py`; `tests/documents/dynamic_automation/test_model_promotion.py`; `tests/documents/dynamic_automation/test_training_dataset.py`.

## 7. Complete group-safe metadata

**Root cause.** Sanitized feedback carried only `layout_hash`, and splitting grouped only that value. Forms sharing kind, version, or institution could cross train/test; pairwise grouping alone also missed transitive bridges.

**RED.** Full v2 records with the required structural fields were rejected as an invalid schema/extra inputs, and a bridge `A(kind)=B; B(institution)=C` could cross partitions.

```text
python -m pytest tests/documents/dynamic_automation/test_feedback.py::test_feedback_requires_bounded_group_metadata tests/documents/dynamic_automation/test_training_dataset.py::test_all_required_group_identities_are_disjoint_across_split tests/documents/dynamic_automation/test_training_dataset.py::test_training_split_keeps_transitively_connected_groups_together -q
```

The parametrized focused run produced five failing cases before the fix.

**Minimal fix.** Feedback schema v2 requires bounded, nonempty `document_kind`, `document_version`, and `source_institution`; `from_review`, fixtures, ingestion, training examples, and dataset hashes carry them as value-free structural metadata. Deterministic union-find builds connected components sharing any required identity and splits whole components, so transitive relationships cannot leak.

**GREEN.** The focused command reports `5 passed`; reversed input produces the identical split, and every required identity set is disjoint across train/test.

**Files changed.** `app/documents/dynamic_automation/feedback.py`; `app/documents/dynamic_automation/training.py`; `scripts/train_dynamic_mapping_models.py`; `tests/documents/dynamic_automation/test_feedback.py`; `tests/documents/dynamic_automation/test_training_dataset.py`; `tests/fixtures/dynamic_automation/approved_feedback.jsonl`; `tests/documents/dynamic_automation/test_domain_adapters.py`.

## 8. Reproducible dependency lock

**Root cause.** `uv` was absent from the development interpreter and the committed lock did not represent the `document-automation` extra in `pyproject.toml`.

**RED.** After installing `uv` only into the development environment, `python -m uv lock --check` exited nonzero and reported that `uv.lock` needed an update.

**Minimal fix.** `python -m uv lock` regenerated only `uv.lock`; no unrelated dependency was added to `pyproject.toml`.

**GREEN.** Both commands exit 0:

```text
python -m uv lock --check
python -m uv sync --frozen --extra document-automation --dry-run
```

The frozen dry run resolves 136 packages and would install 74 packages. Because it was a dry run, it created no environment and downloaded neither packages nor model weights. The only environmental message was the existing Windows `SSL_CERT_DIR` certificate warning.

**Files changed.** `uv.lock`.

## 9. Immutable public catalog iteration

**Root cause.** The frozen catalog dataclass held a mutable private dictionary. `catalog._fields_by_id.clear()` succeeded, and new training code reached into that private lookup; there was no stable public iteration contract.

**RED.** The new catalog regression failed because `definitions` did not exist; the direct mutation reproduction removed all definitions from the supposedly frozen catalog.

```text
python -m pytest tests/documents/dynamic_automation/test_catalog.py::test_catalog_definitions_are_immutable_and_stably_iterable -q
```

**Minimal fix.** The catalog's canonical public storage is a lexically sorted tuple of frozen definitions, `__iter__` exposes the same deterministic order, and the private ID lookup is a `MappingProxyType`. Training consumes `catalog.definitions`; production private-lookup references remain only inside `catalog.py`.

**GREEN.** The focused command reports `1 passed`; tuple/definition/lookup mutation attempts fail and iteration order is stable.

**Files changed.** `app/documents/dynamic_automation/catalog.py`; `app/documents/dynamic_automation/training.py`; `scripts/train_dynamic_mapping_models.py`; `tests/documents/dynamic_automation/test_catalog.py`.

## Final verification

```text
PYTHONUTF8=1 python -m pytest tests/documents/dynamic_automation -o addopts='' -q
134 passed in 11.24s

python -m pytest tests/documents/dynamic_automation/test_model_promotion.py -o addopts='' -q
19 passed in 1.62s (run after the final exact-byte-hash hardening)

PYTHONUTF8=1 python -m pytest tests/agents/test_document_field_map.py tests/agents/language/test_model_cache.py tests/documents/dynamic_automation/test_mapping_config.py tests/integration/language/test_compose_config.py -o addopts='' -q
36 passed in 6.65s

python scripts/evaluate_dynamic_mapping.py --cases tests/fixtures/dynamic_automation/mapping_cases.jsonl --catalog app/documents/dynamic_automation/resources/canonical_fields.v1.yaml --mode rule --output <temporary-report>
exit 0; 6 cases; precision 1.0; sensitive precision 1.0; coverage 0.4; gate passed

PYTHONUTF8=1 python -m pytest tests/documents/dynamic_automation/test_domain_adapters.py::test_fake_backend_train_export_load_evaluate_and_compare_cli tests/documents/dynamic_automation/test_domain_adapters.py::test_trained_reranker_calibration_can_reverse_a_wrong_base_ranking -o addopts='' -q
2 passed in 0.54s

python -m ruff check app/documents/dynamic_automation tests/documents/dynamic_automation scripts/evaluate_dynamic_mapping.py scripts/train_dynamic_mapping_models.py scripts/compare_dynamic_mapping_models.py
All checks passed!

python -m uv lock --check
exit 0; resolved 136 packages

python -m uv sync --frozen --extra document-automation --dry-run
exit 0; frozen resolution valid; would install 74 packages; no download performed

git diff --check
exit 0
```

Conditional real-model smoke:

```text
PYTHONUTF8=1 python -m pytest tests/integration/dynamic_automation/test_qwen_mapping_smoke.py -o addopts='' -q
1 skipped in 0.16s
```

The skip is expected because both pinned Qwen caches are absent. No real model weights were downloaded. No additional concerns remain inside this fix wave; the known 57 unrelated Language/Qdrant/Compose baseline failures remain outside scope.
