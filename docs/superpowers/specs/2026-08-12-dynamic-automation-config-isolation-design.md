# Dynamic Automation Configuration Isolation Design

## Goal

Keep the dynamic document-mapping feature opt-in without changing the shared
configuration path used when the FastAPI server starts. Existing
`FOWOCO_DYNAMIC_AUTOMATION_*` environment variable names remain stable, but
only dynamic-automation commands read them.

## Alternatives considered

1. **Package-owned settings (selected).** Move all dynamic mapping fields,
   pinned-path derivation, and validation into
   `app.documents.dynamic_automation.config`. This provides a hard import and
   validation boundary while retaining environment-based operations.
2. **Lazy fields on the shared `Settings`.** Skip validation while disabled.
   This reduces startup risk but still changes the server configuration model
   and leaves accidental coupling possible.
3. **CLI arguments only.** Remove environment variables and require every
   command to receive paths and thresholds explicitly. This isolates the
   server but makes repeatable deployment and evaluation unnecessarily harder.

## Architecture

`app.core.config.Settings` returns to its pre-feature contract: it contains no
dynamic-automation fields, constants, path derivation, or validators. Because
`app.main.create_app()` only constructs this shared object, server startup does
not import, validate, load, or resolve anything from dynamic automation.

A new `DynamicAutomationSettings` class belongs to the dynamic-automation
package. It reads:

- `FOWOCO_MODEL_CACHE_DIR`
- `FOWOCO_DYNAMIC_AUTOMATION_MAPPING_ENABLED`
- `FOWOCO_DYNAMIC_AUTOMATION_EMBEDDING_MODEL_PATH`
- `FOWOCO_DYNAMIC_AUTOMATION_RERANKER_MODEL_PATH`
- `FOWOCO_DYNAMIC_AUTOMATION_MIN_RERANKER_SCORE`
- `FOWOCO_DYNAMIC_AUTOMATION_MIN_MARGIN`

The package-owned class retains the existing pinned-revision and managed-cache
validation. It performs no model import, load, download, or network access.

Only `scripts/evaluate_dynamic_mapping.py` constructs this settings object,
and only for a Qwen-backed evaluation mode. Rule-only evaluation does not need
model paths. The opt-in model downloader remains independently controlled by
`--include-document-automation` and keeps its existing default behavior.

## Data and error flow

When the FastAPI application starts, dynamic environment variables are ignored
by shared settings. Invalid dynamic-only paths therefore cannot prevent the
existing server from starting.

When a dynamic Qwen evaluation starts, the package-owned settings class derives
default pinned paths below `FOWOCO_MODEL_CACHE_DIR` or validates explicitly
provided paths. Invalid, unpinned, or out-of-cache paths fail before any model
backend is imported. A disabled mapping setting continues to fail closed for a
Qwen evaluation request.

## Compatibility boundaries

- No API route, request/response schema, workflow graph, document editor, HWP,
  HWPX, or server composition code changes.
- Existing dynamic environment variable names and defaults remain unchanged.
- `.env.example` retains the opt-in documentation.
- The dynamic catalog and mapping behavior remain unchanged.
- No database access or Server canonical-slot integration is added.

## Verification

Tests will prove:

1. Shared `Settings` has no dynamic-automation fields.
2. Invalid `FOWOCO_DYNAMIC_AUTOMATION_*` values cannot break shared `Settings`
   construction or FastAPI server startup.
3. Package-owned settings preserve the current defaults, environment parsing,
   thresholds, pinned revisions, and managed-cache rejection behavior.
4. The evaluation CLI reads package-owned settings and preserves fail-closed
   Qwen behavior.
5. Dynamic-automation tests and the existing analyses contract tests pass.

The implementation is limited to the shared config rollback, the new package
settings module, the evaluation CLI import, focused tests, and any necessary
documentation adjustments.
