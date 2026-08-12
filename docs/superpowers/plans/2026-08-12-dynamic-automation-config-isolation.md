# Dynamic Automation Configuration Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove dynamic document-mapping configuration from the FastAPI server's shared settings path while preserving the existing opt-in environment interface for dynamic evaluation commands.

**Architecture:** A package-owned `DynamicAutomationSettings` model reads and validates the existing environment variables only when the Qwen evaluation path constructs it. `app.core.config.Settings` returns to its prior server-only contract, so malformed dynamic-only environment values cannot affect `app.main.create_app()`.

**Tech Stack:** Python 3.12, Pydantic v2, pydantic-settings, pytest, Ruff

## Global Constraints

- Preserve all existing `FOWOCO_DYNAMIC_AUTOMATION_*` environment variable names and defaults.
- Keep Qwen model paths pinned below `FOWOCO_MODEL_CACHE_DIR`.
- Do not import, load, or download model weights while reading configuration.
- Do not change API routes, schemas, workflow graphs, document editors, MCP behavior, or database access.
- Use strict TDD: observe each new regression test fail before production edits.

---

### Task 1: Isolate dynamic automation settings from server startup

**Files:**
- Create: `app/documents/dynamic_automation/config.py`
- Modify: `app/core/config.py:1-162`
- Modify: `scripts/evaluate_dynamic_mapping.py:320-356`
- Modify: `tests/documents/dynamic_automation/test_mapping_config.py`

**Interfaces:**
- Consumes: `QWEN3_EMBEDDING_CACHE_NAME`, `QWEN3_EMBEDDING_REVISION`, `QWEN3_RERANKER_CACHE_NAME`, and `QWEN3_RERANKER_REVISION` from `app.documents.dynamic_automation.qwen`.
- Produces: `DynamicAutomationSettings(BaseSettings)` with `model_cache_dir: Path`, `dynamic_automation_mapping_enabled: bool`, `dynamic_automation_embedding_model_path: Path | None`, `dynamic_automation_reranker_model_path: Path | None`, `dynamic_automation_min_reranker_score: float`, and `dynamic_automation_min_margin: float`.
- Produces: unchanged Qwen evaluation behavior through `_make_mapper(...)`; rule mode does not construct dynamic settings.

- [ ] **Step 1: Write server-isolation and package-settings tests**

Update imports and add literal behavioral assertions in `test_mapping_config.py`:

```python
import os

from app.core.config import Settings
from app.documents.dynamic_automation.config import DynamicAutomationSettings


def test_invalid_dynamic_environment_cannot_break_server_startup() -> None:
    environment = {
        **os.environ,
        "FOWOCO_DYNAMIC_AUTOMATION_MIN_MARGIN": "not-a-number",
        "FOWOCO_DYNAMIC_AUTOMATION_EMBEDDING_MODEL_PATH": "outside-cache/model",
    }
    completed = subprocess.run(
        [sys.executable, "-c", "from app.main import create_app; create_app()"],
        cwd=Path(__file__).parents[3],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_shared_settings_do_not_expose_dynamic_automation_fields() -> None:
    settings = Settings(_env_file=None)
    assert not hasattr(settings, "dynamic_automation_mapping_enabled")
    assert not hasattr(settings, "dynamic_automation_embedding_model_path")
```

Change the existing defaults, explicit-environment, managed-cache, pinned
revision, and probability-bound tests to instantiate
`DynamicAutomationSettings` instead of shared `Settings`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```text
python -m pytest tests/documents/dynamic_automation/test_mapping_config.py -o addopts='' -q
```

Expected: collection fails because `app.documents.dynamic_automation.config`
does not exist. Do not edit production code until this exact missing-module
failure is observed.

- [ ] **Step 3: Add the package-owned settings model**

Create `app/documents/dynamic_automation/config.py` with this public shape:

```python
from pathlib import Path
import tempfile
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .qwen import (
    QWEN3_EMBEDDING_CACHE_NAME,
    QWEN3_EMBEDDING_REVISION,
    QWEN3_RERANKER_CACHE_NAME,
    QWEN3_RERANKER_REVISION,
)

_EMBEDDING_PATH = Path(QWEN3_EMBEDDING_CACHE_NAME) / QWEN3_EMBEDDING_REVISION
_RERANKER_PATH = Path(QWEN3_RERANKER_CACHE_NAME) / QWEN3_RERANKER_REVISION


class DynamicAutomationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="FOWOCO_",
        extra="ignore",
    )

    model_cache_dir: Path = Field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "fowoco-model-cache"
    )
    dynamic_automation_mapping_enabled: bool = False
    dynamic_automation_embedding_model_path: Path | None = None
    dynamic_automation_reranker_model_path: Path | None = None
    dynamic_automation_min_reranker_score: float = Field(default=0.90, ge=0, le=1)
    dynamic_automation_min_margin: float = Field(default=0.10, ge=0, le=1)

    @model_validator(mode="after")
    def derive_model_paths(self) -> Self:
        embedding_path = self.dynamic_automation_embedding_model_path or (
            self.model_cache_dir / _EMBEDDING_PATH
        )
        reranker_path = self.dynamic_automation_reranker_model_path or (
            self.model_cache_dir / _RERANKER_PATH
        )
        self.dynamic_automation_embedding_model_path = _managed_model_path(
            embedding_path,
            model_cache_dir=self.model_cache_dir,
            pinned_suffix=_EMBEDDING_PATH,
            setting_name="dynamic_automation_embedding_model_path",
        )
        self.dynamic_automation_reranker_model_path = _managed_model_path(
            reranker_path,
            model_cache_dir=self.model_cache_dir,
            pinned_suffix=_RERANKER_PATH,
            setting_name="dynamic_automation_reranker_model_path",
        )
        return self


def _managed_model_path(
    path: Path,
    *,
    model_cache_dir: Path,
    pinned_suffix: Path,
    setting_name: str,
) -> Path:
    resolved_cache = model_cache_dir.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    try:
        relative_path = resolved_path.relative_to(resolved_cache)
    except ValueError as err:
        raise ValueError(f"{setting_name} must be below model_cache_dir") from err
    if relative_path.parts[-2:] != pinned_suffix.parts:
        raise ValueError(
            f"{setting_name} must end in the pinned revision directory "
            f"{pinned_suffix.as_posix()}"
        )
    return resolved_path
```

This preserves the existing deterministic path derivation and managed-cache
validation while making the Qwen constants the single source of truth. Keep
`_managed_model_path(...)` private to this new module.

- [ ] **Step 4: Remove dynamic behavior from shared settings**

Delete only the two dynamic pinned-path constants, the five dynamic fields,
`derive_dynamic_automation_model_paths`, and `_managed_model_path` from
`app/core/config.py`. Preserve `model_cache_dir` because existing language model
composition and download behavior use it. Remove `Self` from imports only if no
remaining validator needs it; the OCR validator still returns `Self`, so retain
it.

- [ ] **Step 5: Rewire only the Qwen evaluation path**

In the non-rule branch of `_make_mapper` replace:

```python
from app.core.config import Settings
settings = Settings()
```

with:

```python
from app.documents.dynamic_automation.config import DynamicAutomationSettings
settings = DynamicAutomationSettings()
```

Do not import this module at script top level. Keeping the import inside the
Qwen branch ensures rule evaluation and FastAPI startup do not construct the
dynamic settings model.

- [ ] **Step 6: Run focused tests to verify GREEN**

Run:

```text
python -m pytest tests/documents/dynamic_automation/test_mapping_config.py tests/documents/dynamic_automation/test_evaluation.py -o addopts='' -q
```

Expected: all selected tests pass, including the subprocess server-startup
regression and existing fail-closed Qwen CLI cases.

- [ ] **Step 7: Run scoped regression and quality gates**

Run:

```text
python -m pytest tests/documents/dynamic_automation -o addopts='' -q
python -m pytest tests/api/test_analyses_endpoint.py tests/api/test_internal_handshake.py tests/contracts/test_analyses_fixtures.py -o addopts='' -q
python -m ruff check app/core/config.py app/documents/dynamic_automation scripts/evaluate_dynamic_mapping.py tests/documents/dynamic_automation/test_mapping_config.py
git diff --check
```

Expected: dynamic automation and Server↔AI contract suites pass; Ruff and diff
checks exit 0.

- [ ] **Step 8: Record the repository-wide baseline**

Run:

```text
python -m pytest -q --tb=no
```

Expected on the current base: 57 known failures in Language context checksum,
LangGraph compatibility, Qdrant, Compose, and runtime composition. Confirm no
new failure appears outside that recorded set. This result must be disclosed in
the Draft PR; it is not a success gate for making the feature merge-ready.

- [ ] **Step 9: Commit the isolated implementation**

```text
git add app/core/config.py app/documents/dynamic_automation/config.py scripts/evaluate_dynamic_mapping.py tests/documents/dynamic_automation/test_mapping_config.py
git commit -m "fix(doc-automation): isolate mapping configuration"
```

The commit must contain only these four files.

---

### Task 2: Publish a Draft pull request with explicit boundaries

**Files:**
- Inspect: `.github/PULL_REQUEST_TEMPLATE.md` or repository PR templates if present
- No repository file changes are required.

**Interfaces:**
- Consumes: branch `feat/dynamic-field-mapping-foundation` and its verified commit history.
- Produces: a Draft GitHub pull request against the confirmed fork base `feat/mcp_mapping`.

- [ ] **Step 1: Confirm branch provenance and remote base**

Run:

```text
git merge-base --is-ancestor feat/mcp_mapping HEAD
git ls-remote --heads origin feat/mcp_mapping feat/dynamic-field-mapping-foundation
git status --short
```

Expected: the local feature contains `feat/mcp_mapping`, the worktree is clean,
and the remote base exists. If the remote base does not exist, stop and ask for
the intended GitHub base rather than targeting `develop` or `main` by guess.

- [ ] **Step 2: Push without force**

```text
git push -u origin feat/dynamic-field-mapping-foundation
```

Expected: push succeeds without rewriting any remote history.

- [ ] **Step 3: Create the Draft PR**

Use GitHub CLI against `fowoco/ai` with base `feat/mcp_mapping`. The PR body must
state:

- additive dynamic mapping package; existing template path is unchanged;
- MCP registry is consumed but MCP extraction itself is not replaced;
- no DB access, SQL generation, or Server runtime wiring is included;
- dynamic configuration is isolated from FastAPI shared settings;
- scoped test counts and Server↔AI contract test count;
- the repository-wide 57-failure pre-existing baseline;
- real Qwen smoke was skipped when the pinned cache was unavailable and no
  weights were downloaded.

Create it as Draft, retain the linked worktree for review fixes, and report the
PR URL.
