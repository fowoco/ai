# Language Assistant Control Tower Ledger

## Authority

- Integration branch: `feat/language-assistant`
- Execution protocol: `docs/engineering/specs/2026-08-02-language-assistant-control-tower-design.md`
- Current wave: `W1`
- Current gate: `User Gate`
- State: `active`
- Maximum concurrent builders: `2`

## T0 Record

- Docs commit: `c2a6a716d05e5d420b95b3f580973c15a497986e`
- Evidence Pack commit: `d670faf7cb7c32178223b52d119f9990f1e9bf8a`
- Luna Verifier: `unverified`
- Sol Gate: `not applicable in W0`
- User decision: `proceed to T1`
- Unverified: independent T0 replay, T1 implementation/evidence/replay, external G1-G7 evidence

## Tasks

| Task | Title | Status | Dependencies | Base | Branch | Packet | Implementation | Evidence | Merge | Integrated | Luna | Sol | User | Unverified |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 | Domain contracts | integrated | T0 | `cd3fabbfbf6e996f3ef1d068804e04cc9f85e07a` | `task/la-t01-domain-contracts` | `536dc6a36c66bdfe6346482748672b0882cb7c41` | `42f429cd67fbecaf5cff41eef22e2389f8d8ad60` | `cb3fd9812aff1bd299d6e498e23ebc44315aa453` | `ffc229fe2c87298074f94a5c3acd59c3a243db36` | `63e2262d81eea8cd414f2ca57c392d9e5eee0832` | Hume / `019fc0ed-3801-7061-9d76-34cfc22f5e5f` | S1 | proceed | S1 review, user Gate, T02/T03, HTTP/LangGraph/provider/Qdrant/model production behavior, merge-after behavior, G1-G7 |
| T02 | Language normalization | integrated | T01 | `bbba26e67fa392b0691f397df162ce07292c7932` | `task/la-t02-language-normalization` | `e41f66dbee21d6c9bb63d685882b1645de7a730b` | `5acaecb961ffbcaa56db80f21fa4571061f6c158` | `e91bb957ba347ad507009659caf5682842c900ef` | `550fc47c329f2d049985df9ec552d981cbf53aaf` | `550fc47c329f2d049985df9ec552d981cbf53aaf` | Lorentz / `019fc15d-d0ff-76f0-bec3-d315d78f2497` | S1 | proceed | S1 review, user Gate, T04 onward, HTTP/LangGraph/provider/Qdrant/model production behavior, G1-G7 |
| T03 | Facts and queries | integrated | T01 | `13d088a7924f837b3c7caf476f62153bee903f2b` | `task/la-t03-facts-and-queries` | `6ac7477701a01b02dcbd0cfe0320dd92bce7f8e7` | `c18490c52830627ef8d126e84689f74e01c48a54` | `ae836ab2cd0c9ba4b4aabe1816c63fe5a6826d5f` | `2ddb84cc3600fe2b7cd03577e5fa364174f19133` | `2ddb84cc3600fe2b7cd03577e5fa364174f19133` | Mill / `019fc180-ff45-76c0-ba48-813dee29f5d9` | S1 | proceed | S1 review, user Gate, T04 onward, HTTP/LangGraph/provider/Qdrant/model production behavior, G1-G7 |
| T04 | Retrieval domain | pending | T02,T03 | — | `task/la-t04-retrieval-domain` | — | — | — | — | — | — | S2 | — | — |
| T05 | EPS index plan | pending | T02,T04 | — | `task/la-t05-eps-index-plan` | — | — | — | — | — | — | S2 | — | — |
| T06 | Hybrid retrieval | pending | T04,T05 | — | `task/la-t06-hybrid-retrieval` | — | — | — | — | — | — | S2 | — | — |
| T07 | Generation resources | pending | T01,T04,S2 | — | `task/la-t07-generation-resources` | — | — | — | — | — | — | S3 | — | — |
| T08 | Validation retry | pending | T03,T07 | — | `task/la-t08-validation-retry` | — | — | — | — | — | — | S3 | — | — |
| T09 | Easy Korean | pending | T07,T08 | — | `task/la-t09-easy-korean` | — | — | — | — | — | — | S3 | — | — |
| T10 | Native translation | pending | T06,T07,T08 | — | `task/la-t10-native-translation` | — | — | — | — | — | — | S3 | — | — |
| T11 | Graph assembly | pending | T09,T10 | — | `task/la-t11-graph-assembly` | — | — | — | — | — | — | S3 | — | — |
| T12 | Internal API | pending | T11,G1 | — | `task/la-t12-internal-api` | — | — | — | — | — | — | S3 | — | — |
| T13 | Runtime and Qdrant | pending | T06,T12,S3 | — | `task/la-t13-runtime-qdrant` | — | — | — | — | — | — | S4 | — | — |
| T14 | Privacy and resilience | pending | T11,T13 | — | `task/la-t14-privacy-resilience` | — | — | — | — | — | — | S4 | — | — |
| T15 | Evaluation | pending | T14,S4 | — | `task/la-t15-evaluation` | — | — | — | — | — | — | S5 | — | — |
| T16 | Verification handoff | pending | T14,T15 | — | `task/la-t16-verification-handoff` | — | — | — | — | — | — | S5 | — | — |

## S1 Repair Packet: T01·T03

- repair id: `S1-REPAIR-T01-T03`
- status: `approved`
- packet SHA: `9e34b592f236231bf7a574b01f84f919655cd3c1`
- base SHA: `2ce75957e1ba9bcb0af74a259eb5d959d4b57a6f`
- task branch: `repair/la-t01-t03-s1`
- worktree: `/Users/parktaejung/Desktop/workspace/ai-language-assistant-repair-t01-t03`
- Packet: `docs/engineering/execution/language-assistant/tasks/S1-REPAIR-T01-T03.md`
- scope: T01 deadline/fallback contracts and tests; T03 signed amount, currency, quantity unit, Korean-date tokenization, Query preservation, and tests
- existing implementation/evidence/verifier SHA: immutable; no prior Evidence Pack is rewritten
- `control-tower.md`: CT-only; repair branch must not modify it
- implementation SHA: `f00b9e5b6a9418488c39bf6d055860ccdab3cca4`
- evidence SHA: `a7940d01895585e627e6fdd73fc7404bfa1f179f`
- integration status: `integrated`
- Luna verifier: Schrodinger / `019fc6be-b043-7861-a282-402fad46dd3b` — `APPROVED`
- implementation commit: `fix: T01 T03 경계 보수 구현`
- evidence commit: `docs: S1 T01 T03 보수 Evidence 기록`
- verification:
  - T01 focused: `.venv/bin/python -m pytest tests/agents/language/test_contracts.py tests/agents/language/test_projection.py -q` → exit `0`, `36 passed`
  - T03 focused/token boundary: `.venv/bin/python -m pytest tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py -q` → exit `0`, `17 passed`
  - full test: `PYTEST_ADDOPTS='' .venv/bin/python -m pytest -o addopts='' --disable-warnings` → exit `0`, `183 passed`, one warning
  - changed-area Ruff: `RUFF_CACHE_DIR=/private/tmp/la-s1-repair-ruff-cache .venv/bin/ruff check app/agents/language/contracts.py app/agents/language/protected_facts.py app/agents/language/queries.py tests/agents/language/test_contracts.py tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py` → exit `0`, `All checks passed!`
  - Luna replay: repair worktree lacked `.venv`; exact relative commands returned exit `127`, equivalent commands using `/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/` returned T01 `36 passed`, T03 `17 passed`, full `183 passed`, Ruff passed
  - scope/schema: `git diff --exit-code -- docs/contracts` and `git diff --check` → exit `0`; repair worktree clean at evidence SHA
- unverified: HTTP/API, LangGraph runtime, Qdrant, EPS ingest/retrieval, external LLM/provider, production configuration, external G1–G7, S1 re-review, user Gate, and W2
- historical stop: repair Evidence Pack and independent verification were completed before the repair merge; S1 re-review and W2 opening remained closed at that point

## S1 Repair Integration Replay

- repair id: `S1-REPAIR-T01-T03`
- merge SHA: `e6eb0f463458970b6c991415ffe93595461f6477`
- integrated SHA: `f4480467d67ec4bd1c9ea51cfdef02decc744eac`
- effective implementation SHA: `f00b9e5b6a9418488c39bf6d055860ccdab3cca4`
- effective Evidence SHA: `a7940d01895585e627e6fdd73fc7404bfa1f179f`
- central HEAD at merge: `e6eb0f463458970b6c991415ffe93595461f6477`
- merge method: `--no-ff`
- repair branch: `repair/la-t01-t03-s1`
- post-merge focused T01: `36 passed`, exit `0`
- post-merge focused T03: `17 passed`, exit `0`
- post-merge full test: `183 passed`, exit `0`, one non-failing cache warning
- post-merge changed-area Ruff: `All checks passed!`, exit `0`
- post-merge whole-repository Ruff: exit `1`, existing baseline `113 errors`
- post-merge schema diff: unchanged, exit `0`
- post-merge `git diff --check`: exit `0`
- post-merge central worktree: clean
- S1 re-review: was required at this historical checkpoint; completed later in the S1 Conditional T03 Reconciliation Integration record below
- User Gate: not started at this historical checkpoint
- W2: remained blocked at this historical checkpoint; current User Gate status is recorded below

## S1 Conditional T03 Reconciliation Integration

- reconciliation id: `S1-CONDITIONAL-T03-RECONCILIATION`
- repair branch: `repair/la-s1-conditional-t03`
- repair implementation SHA: `8e90db88d0093423477840242b0e835917126fba`
- reconciliation Evidence SHA: `e63f4c793c214bcd417de1c592eca2c36aed83c1`
- independent re-review target: `e63f4c793c214bcd417de1c592eca2c36aed83c1`
- independent re-review: `APPROVED` (verifier session identifier was not included in the supplied report)
- pre-merge central HEAD: `0364d957ae508ecaecdb35de70fc268d0022e6e3`
- merge SHA: `ed9135c78661c2e9dafc8ce23abedf327a89f533`
- integrated code SHA: `ed9135c78661c2e9dafc8ce23abedf327a89f533`
- merge method: `--no-ff`
- post-merge focused T03: `19 passed`, exit `0`
- post-merge full test: `185 passed`, exit `0`, one non-failing warning
- post-merge changed-area Ruff: `All checks passed!`, exit `0`
- post-merge schema diff: unchanged, exit `0`
- post-merge `git diff --check`: exit `0`
- post-merge central worktree: clean before this CT ledger update
- fallback provenance: deferred to the T11 Graph assembly acceptance criteria; contracts/formatting were intentionally not coupled
- User Gate: pending
- W2: blocked until the user records `진행`

## T01 Verification Attempts

- Hypatia / `019fc0e9-0364-7a10-b467-5c01c51672d6`: C01-C04 passed; C05 exact schema-export replay was blocked by `PermissionError` because the verifier checkout was read-only. No repository files were modified.
- Hume / `019fc0ed-3801-7061-9d76-34cfc22f5e5f`: approved C01-C05 from disposable detached checkout `/private/tmp/la-t01-verifier-cb3fd98` at the same `evidence_sha`; focused `27 passed`, full `88 passed`, Ruff passed, two schema exports were byte-stable, and final worktree was clean. The disposable checkout initially lacked `.venv`; a temporary symlink to the existing environment was used only for replay and removed afterward.

## T03 Evidence and Verification

- Evidence Pack: `docs/engineering/execution/language-assistant/evidence/T03-EVIDENCE.md`
- Evidence SHA: `ae836ab2cd0c9ba4b4aabe1816c63fe5a6826d5f`
- Implementation SHA: `c18490c52830627ef8d126e84689f74e01c48a54`
- Packet SHA: `6ac7477701a01b02dcbd0cfe0320dd92bce7f8e7`
- Focused command: `PYTEST_ADDOPTS='' .venv/bin/python -m pytest tests/agents/language/test_protected_facts.py tests/agents/language/test_formatting.py tests/agents/language/test_queries.py -q` → exit `0`, `22 passed`.
- Full command: `PYTEST_ADDOPTS='' .venv/bin/python -m pytest -o addopts='' --disable-warnings` → exit `0`, `132 passed`, one non-failing cache warning.
- T3 Ruff command with `RUFF_CACHE_DIR=/private/tmp/la-t03-ruff-cache` → exit `0`, `All checks passed!`.
- Whole-repository Ruff → exit `1`, existing 113 violations outside T3 scope; T3 changed-file Ruff remains passed.
- `git diff --exit-code -- docs/contracts` → exit `0`; `git diff --check` → exit `0`; evidence worktree clean.
- Luna Mill independently approved C01-C09. T03 is integrated by merge commit `2ddb84cc3600fe2b7cd03577e5fa364174f19133`.

### T03 Verification Attempts

- Hubble / `019fc176-6a27-7473-aaa4-4f06c846352c`: REJECTED C01-C07/C09 passed, but C08 found `113` whole-repository Ruff errors while the first Evidence Pack recorded `114`. No repository files were modified.
- Noether / `019fc179-fe9c-74b2-bed7-3ef9a59f6272`: APPROVED C01-C09 for Evidence SHA `6ac1f7dcd98eb3f3ac0c217ab0e8bff8b5d51f6f`; later identified and corrected one stale `114` count in the Evidence Pack footer.
- Cicero / `019fc17d-1335-7812-9d4b-7657a912012d`: REJECTED C02-C09 passed, but the verifier prompt carried a one-character Packet SHA typo; repository Evidence Pack itself was correct. No repository files were modified.
- Mill / `019fc180-ff45-76c0-ba48-813dee29f5d9`: APPROVED C01-C09 for final Evidence SHA `ae836ab2cd0c9ba4b4aabe1816c63fe5a6826d5f`; focused `22 passed`, full `132 passed`, T3 Ruff passed, whole Ruff `113 errors` matched the recorded baseline, and the task worktree was clean.

## T02/T03 Integration Replay

- T02 `merge_sha`: `550fc47c329f2d049985df9ec552d981cbf53aaf`; T02 `integrated_sha`: same merge commit.
- T03 `merge_sha`: `2ddb84cc3600fe2b7cd03577e5fa364174f19133`; T03 `integrated_sha`: same merge commit.
- T02 post-merge command: `PYTEST_ADDOPTS='' .venv/bin/python -m pytest -o addopts='' --disable-warnings` → exit `0`, `148 passed`, one non-failing cache warning.
- Final focused command: `PYTEST_ADDOPTS='' .venv/bin/python -m pytest -o addopts='' --disable-warnings tests/agents/language/test_codes.py tests/agents/language/test_protected_facts.py tests/agents/language/test_formatting.py tests/agents/language/test_queries.py` → exit `0`, `60 passed`, one non-failing cache warning.
- Final full command: `PYTEST_ADDOPTS='' .venv/bin/python -m pytest -o addopts='' --disable-warnings` → exit `0`, `170 passed`, one non-failing cache warning.
- Changed-area Ruff: `RUFF_CACHE_DIR=/private/tmp/la-merge-ruff-cache .venv/bin/ruff check app/agents/language tests/agents/language` → exit `0`, `All checks passed!`.
- Whole-repository Ruff: `RUFF_CACHE_DIR=/private/tmp/la-merge-ruff-cache .venv/bin/ruff check .` → exit `1`, existing `113 errors`; no out-of-scope cleanup was performed.
- `git diff --exit-code -- docs/contracts` and `git diff --check` → exit `0`.
- Central `feat/language-assistant` is clean after the replay. Original `develop` remains untouched with its pre-existing untracked HWPX/image changes preserved.
- T2 and T3 were integrated only with `--no-ff`; no cherry-pick, squash, rebase, or amend was used.

## T01 Integration Replay

- `merge_sha`: `ffc229fe2c87298074f94a5c3acd59c3a243db36`
- Focused command: `.venv/bin/python -m pytest tests/agents/language/test_contracts.py tests/agents/language/test_projection.py -q` → exit `0`; diagnostic summary `27 passed`; one non-failing pytest cache write warning.
- Full command: `.venv/bin/python -m pytest -q` → exit `0`; diagnostic replay with `-o addopts='' -ra` collected and passed `110` tests; one non-failing pytest cache write warning.
- Ruff command: `.venv/bin/python -m ruff check app tests scripts/export_language_schemas.py` first returned exit `2` because `.ruff_cache` could not create a temporary file; the same check with `RUFF_CACHE_DIR=/private/tmp/la-t01-ruff-cache` returned exit `0`, `All checks passed!`.
- The earlier T01 Evidence Pack recorded `88 passed`; the post-merge replay observed `110 passed`. Existing evidence and implementation SHAs were not rewritten; `110 passed` is the integrated-branch result recorded here.
- Worktree remained clean after the replay.

## Commit Language Policy

- From this ledger entry onward, newly created commit subjects and bodies must be written in Korean.
- Only the Conventional Commits `type` remains English; the description and body are Korean.
- Existing English commit messages and their SHAs are immutable. Do not amend, cherry-pick, squash, or rebase them.
- Examples: `feat: Language Assistant 도메인 계약 정의`, `test: 도메인 계약 경계값 테스트 추가`, `docs: T1 독립 검증 결과 기록`, `fix: 요청 항목 빈 배열 검증 수정`.
