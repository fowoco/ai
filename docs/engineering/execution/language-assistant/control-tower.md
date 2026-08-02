# Language Assistant Control Tower Ledger

## Authority

- Integration branch: `feat/language-assistant`
- Execution protocol: `docs/engineering/specs/2026-08-02-language-assistant-control-tower-design.md`
- Current wave: `W1`
- Current gate: `none`
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
| T02 | Language normalization | verifying | T01 | `bbba26e67fa392b0691f397df162ce07292c7932` | `task/la-t02-language-normalization` | `e41f66dbee21d6c9bb63d685882b1645de7a730b` | `5acaecb961ffbcaa56db80f21fa4571061f6c158` | `e91bb957ba347ad507009659caf5682842c900ef` | — | — | Lorentz / `019fc15d-d0ff-76f0-bec3-d315d78f2497` | S1 | proceed | independent replay, S1 review, user Gate, T3 onward, HTTP/LangGraph/provider/Qdrant/model production behavior, G1-G7 |
| T03 | Facts and queries | pending | T01 | — | `task/la-t03-facts-and-queries` | — | — | — | — | — | — | S1 | — | — |
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

## T01 Verification Attempts

- Hypatia / `019fc0e9-0364-7a10-b467-5c01c51672d6`: C01-C04 passed; C05 exact schema-export replay was blocked by `PermissionError` because the verifier checkout was read-only. No repository files were modified.
- Hume / `019fc0ed-3801-7061-9d76-34cfc22f5e5f`: approved C01-C05 from disposable detached checkout `/private/tmp/la-t01-verifier-cb3fd98` at the same `evidence_sha`; focused `27 passed`, full `88 passed`, Ruff passed, two schema exports were byte-stable, and final worktree was clean. The disposable checkout initially lacked `.venv`; a temporary symlink to the existing environment was used only for replay and removed afterward.

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
