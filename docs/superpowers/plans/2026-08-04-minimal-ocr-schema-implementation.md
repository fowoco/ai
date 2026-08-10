# Minimal OCR Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the AI OCR integration with the approved 16-column `worker_document` migration contract.

**Architecture:** Keep transport, template routing, normalization status, and tenant-safe concurrency unchanged. Reduce the persistence allowlist and schema verifier to five OCR metadata columns and eleven structured fields; ignore all other CLOVA template fields instead of storing them.

**Tech Stack:** Python 3.12, FastAPI, psycopg 3, pytest, Ruff

## Global Constraints

- Modify only the `fowoco/ai` repository.
- Store only the approved 16 new columns.
- Never persist raw CLOVA responses or unapproved template fields.
- Preserve request ownership checks using `ocr_request_id`.
- Keep response-time template ID and confidence-based review decisions in memory.

---

### Task 1: Enforce the minimal schema contract

**Files:**
- Modify: `tests/ocr/test_repository.py`
- Modify: `tests/ocr/test_normalizer.py`
- Modify: `app/ocr/repository.py`
- Modify: `app/ocr/normalizer.py`

**Interfaces:**
- Consumes: `NormalizedOcrResult` from `app.ocr.models`.
- Produces: `REQUIRED_SCHEMA_COLUMNS` containing scope columns plus exactly 16 OCR columns, and normalized results containing only the eleven approved structured fields.

- [ ] **Step 1: Write failing contract tests**

Assert that `OCR_METADATA_COLUMNS` is exactly `ocr_status`, `ocr_request_id`, `ocr_document_side`, `ocr_error_code`, and `ocr_processed_at`. Assert that `STRUCTURED_OCR_COLUMNS` contains only the eleven approved data fields. Assert that removed CLOVA fields such as `nationality`, `full_name`, and `stay_permit_date` are ignored.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/ocr/test_repository.py tests/ocr/test_normalizer.py -v`

Expected: failures show the old metadata and structured field allowlists are still present.

- [ ] **Step 3: Implement the minimal contract**

Remove `ocr_template_id` and `ocr_field_confidences` from repository schema verification and SQL assignments. Reduce the structured column tuple and normalizer allowlists. Require only persisted fields: five passport fields, one ARC-front identifier, and one of the two ARC-back values.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `python -m pytest tests/ocr/test_repository.py tests/ocr/test_normalizer.py tests/ocr/test_service.py -v`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

Run: `git add app/ocr/repository.py app/ocr/normalizer.py tests/ocr/test_repository.py tests/ocr/test_normalizer.py && git commit -m "refactor: minimize OCR persistence schema"`

### Task 2: Align integration documentation and verify the branch

**Files:**
- Modify: `docs/clova-ocr-integration.md`
- Modify: `docs/superpowers/specs/2026-08-04-clova-template-ocr-design.md`

**Interfaces:**
- Consumes: the approved 16-column Server migration contract.
- Produces: an exact handoff contract for Server, DB, and AI deployments.

- [ ] **Step 1: Update schema, grants, and normalization documentation**

Document exactly five metadata and eleven structured columns. Explain that template IDs and confidence values remain response/in-memory data and that existing `worker` values supply general name and nationality.

- [ ] **Step 2: Run full verification**

Run tests from the parent directory with `FOWOCO_CLOVA_OCR_ENABLED=false` so the developer `.env` does not affect settings tests: `python -m pytest ai\\tests`.

Run changed-file lint: `python -m ruff check <changed Python files>`.

Run whitespace validation: `git diff --check develop`.

- [ ] **Step 3: Run privacy-safe CLOVA smoke validation**

Send the ignored runtime sample directly to CLOVA and print only provider status, normalized status, template ID, field names, confidences, review reasons, and error code. Never print field values or raw response data.

- [ ] **Step 4: Review, commit, push, and create PR**

Request an independent review of the diff. Resolve Critical and Important findings, commit documentation, push `feat/ocr_node`, and create a PR targeting `develop` when GitHub authentication is available.
