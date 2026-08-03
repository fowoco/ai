# S1 Repair Packet — T01·T03 계약·보호 사실 보수

```yaml
packet_version: 1
repair_id: S1-REPAIR-T01-T03
wave: W1
gate: S1
status: sealed
tasks: [T01, T03]
```

## Claim

- T01은 공백이 포함된 deadline 입력을 안전하게 정규화하면서 datetime, 잘못된 구분자, 실제 존재하지 않는 날짜를 거부한다.
- T01의 Easy Korean 후보 부재는 Standard Korean fallback으로 명시되고, 마지막 후보가 남은 warning과 혼동되지 않는다.
- T03은 부호·통화·수량 단위·한국어 날짜를 부분 일치 없이 보호하고, canonical value와 source path를 결정적으로 보존한다.
- T03의 세 Query는 새 machine token을 포함한 모든 request fact를 그대로 보존한다.
- 기존 T01/T03 implementation, Evidence Pack, verifier SHA는 변경·재작성하지 않는다.

## Source authority

- design: `docs/engineering/specs/2026-08-02-language-assistant-graph-design.md`
- plan: `docs/engineering/plans/2026-08-02-language-assistant-graph.md`
- control tower protocol: `docs/engineering/specs/2026-08-02-language-assistant-control-tower-design.md`
- ledger: `docs/engineering/execution/language-assistant/control-tower.md`

## Git

- integration branch: `feat/language-assistant`
- base SHA: `2ce75957e1ba9bcb0af74a259eb5d959d4b57a6f`
- task branch: `repair/la-t01-t03-s1`
- worktree: `/Users/parktaejung/Desktop/workspace/ai-language-assistant-repair-t01-t03`
- packet SHA: Control Tower ledger에 사후 기록
- rollback SHA: `2ce75957e1ba9bcb0af74a259eb5d959d4b57a6f`

## Dependencies

- T01 integrated SHA: `63e2262d81eea8cd414f2ca57c392d9e5eee0832`
- T03 integrated SHA: `2ddb84cc3600fe2b7cd03577e5fa364174f19133`
- S1 review findings are the repair authority supplied by the user; no W2 work is opened.

## Allowed files

- `app/agents/language/contracts.py`
- `tests/agents/language/test_contracts.py`
- `app/agents/language/protected_facts.py`
- `app/agents/language/queries.py`
- `tests/agents/language/test_protected_facts.py`
- `tests/agents/language/test_queries.py`
- `docs/engineering/execution/language-assistant/tasks/S1-REPAIR-T01-T03.md`
- `docs/engineering/execution/language-assistant/evidence/S1-REPAIR-T01-T03-EVIDENCE.md`

## Forbidden files and behavior

- `docs/engineering/execution/language-assistant/control-tower.md` — CT only
- all existing T01/T03 Packet, implementation, Evidence Pack, and verifier records
- `app/agents/language/codes.py`, `projection.py`, `state.py`, `formatting.py`
- all graph, API, runtime, Qdrant, EPS, provider, LLM, HWPX, and unrelated test files
- cherry-pick, squash, rebase, amend, force-push, or rewriting any existing SHA
- HTTP, LangGraph runtime, Qdrant, EPS, external LLM, production configuration, or W2 implementation

## T01 acceptance

- Strip surrounding whitespace from string deadline input before checking `YYYY-MM-DD`.
- Continue rejecting datetime objects, datetime strings, wrong separators, and impossible calendar dates.
- Define no-candidate Easy fallback as the exact state:
  - `easy_korean_text == standard_korean_text`
  - Easy component status is `warning`
  - Easy validation status is `not_run`
  - a `STANDARD_KOREAN_FALLBACK` warning exists
  - `generation_status` and `requires_human_review` remain contract-consistent
- Reject an output that claims fallback while changing the fallback text.
- Accept and distinguish a warning state retaining a final Easy candidate from a no-candidate Standard fallback.

## T03 acceptance

- Preserve signs in numeric and amount tokens: `-1,234.50`, `-3.5%`, `₩-10,000`.
- Preserve currency forms: `USD`, `KRW`, `₩`, `100만원`.
- Preserve quantity units as complete tokens: `42개`, `10kg`, `3.5%`.
- Recognize `2026년 8월 10일` and canonicalize it to `2026-08-10`.
- Preserve token `kind`, `source_path`, `surface`, and `canonical_value` in a deterministic multiset.
- Make token matching precedence prevent partial loss of signs, currency, and units.
- Prove all three Query strings preserve every new machine-token surface and canonical request field.

## Token format and canonicalization contract

| kind | supported surface examples | canonicalization |
|---|---|---|
| `date` | `2026-08-10`, `2026년 8월 10일` | ISO `YYYY-MM-DD`; invalid calendar text is not converted |
| `time` | `09:30`, `9시 30분` | normalized surface |
| `number` | `42`, `제12조` | normalized numeric surface without sign loss |
| `amount` | `-1,234.50`, `-10,000` | remove grouping commas, preserve sign and decimal scale |
| `currency` | `USD`, `KRW`, `₩`, `만원` | normalized surface; no exchange-rate or unit-scale inference |
| `unit` | `42개`, `10kg`, `3.5%` | normalized complete quantity-plus-unit surface |
| `url`, `email`, `phone` | URL, email, phone examples | normalized surface without surrounding punctuation |
| `document_identifier`, `version` | `ABC-123`, `v2.1` | normalized surface |

## Required failing tests before implementation

```text
test_accepts_deadline_with_surrounding_whitespace
test_rejects_datetime_objects_and_datetime_strings
test_rejects_invalid_calendar_dates
test_easy_standard_fallback_rejects_changed_text
test_easy_standard_fallback_requires_fallback_warning
test_easy_warning_with_last_candidate_is_not_fallback
test_fallback_generation_status_requires_human_review
test_protected_tokens_preserve_signed_amount_currency_and_units
test_protected_tokens_canonicalize_korean_dates
test_protected_token_multiset_includes_source_paths
test_queries_preserve_all_new_machine_token_surfaces
```

## Required verification commands

```bash
.venv/bin/python -m pytest tests/agents/language/test_contracts.py tests/agents/language/test_projection.py -q
.venv/bin/python -m pytest tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py -q
PYTEST_ADDOPTS='' .venv/bin/python -m pytest -o addopts='' --disable-warnings
RUFF_CACHE_DIR=/private/tmp/la-s1-repair-ruff-cache .venv/bin/ruff check app/agents/language/contracts.py app/agents/language/protected_facts.py app/agents/language/queries.py tests/agents/language/test_contracts.py tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py
git diff --exit-code -- docs/contracts
git diff --check
```

The Evidence Pack must include exact exit codes, test counts, changed-file scope, RED output, implementation SHA, evidence SHA, and the still-unverified HTTP, LangGraph runtime, Qdrant, EPS, and LLM boundaries.

## Stop conditions

- Any required file outside this Packet must change.
- Existing SHA or Evidence content would need rewriting.
- A test passes before the new regression is proven RED.
- A shared state, graph, API, runtime, or Control Tower ledger file needs implementation edits.
- Verification fails or an external integration is required.
- After Evidence Pack and independent verifier result are recorded, stop. Do not re-run S1 review, open W2, or merge this repair in this session.
