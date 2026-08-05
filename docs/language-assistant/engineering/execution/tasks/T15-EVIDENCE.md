# T15 Evidence Pack — Build Retrieval and Generation Evaluation Harnesses and Calibrate Release Gates

```yaml
wave: W5
task: T15
title: Build Retrieval and Generation Evaluation Harnesses and Calibrate Release Gates
implementation_sha: c6026c736b415fe4fd624ca6a8d294dd42cfdf5b
base_sha: a0650d2becbe77191b5825a41f3bc86f0ad40a29
branch: task/la-evaluations
builder: Language Assistant W5 T15 Builder
date: 2026-08-04
```

---

## 클레임 검증

| # | 클레임 | 검증 방법 | 결과 |
|---|--------|----------|------|
| C1 | Evaluation harness schemas, metric formulas, and deterministic CLI report generation run cleanly in `HARNESS_ONLY` mode without live external LLMs or Qdrant connections | `evaluate_language_retrieval.py`, `evaluate_language_generation.py` CLI `--validate-only` 실행 및 `test_evaluator_validate_only_mode` 통과 | ✅ |
| C2 | Offline synthetic test fixtures cover 15 target languages and validate deterministic date, number, cardinality, and warning code invariants | `request_context_cases.json` (60건), `retrieval_cases.jsonl` (60건), `generation_cases.jsonl` (60건) 검증 및 `test_fixtures_schema_and_integrity` 통과 | ✅ |
| C3 | Evaluators output structured Markdown baseline reports (`docs/evaluations/language-assistant-baseline.md`) with explicit gate status (`status: NOT_RUN` for unclosed external gates) | `docs/evaluations/language-assistant-baseline.md` 생성 및 G2/G3/G4/G5/G7 미해결 게이트에 대해 `status: NOT_RUN` 명시 기록 | ✅ |

---

## 테스트 결과

```
전체: 453 passed, 1 skipped (T01~T14 포함)
T15 신규: 9 tests (test_evaluation_harness.py: 7, test_model_offline_smoke.py: 2)
CLI 검증: evaluate_language_retrieval.py 및 evaluate_language_generation.py --validate-only 통과
Ruff: 0 errors (허용 산출물 한정)
git diff --check: clean
```

---

## 변경 파일 목록 (9개 허용 범위 100% 준수)

### 신규 파일 (8개)
- `scripts/evaluate_language_retrieval.py` — 검색 평가 스크립트 (Recall@5/10/30, MRR@10, nDCG@10, Precision@5, --validate-only 모드)
- `scripts/evaluate_language_generation.py` — 생성 평가 스크립트 (날짜/수량 100% 보존율, Latency p50/p95, 5차원 루브릭 점수, --validate-only 모드)
- `tests/agents/language/test_evaluation_harness.py` — 평가 Harness 단위 테스트 7종
- `tests/fixtures/language/request_context_cases.json` — 15개 언어 60개 Request Context 시나리오 픽스처
- `tests/fixtures/language/retrieval_cases.jsonl` — 15개 언어 60개 검색 평가 시나리오 픽스처
- `tests/fixtures/language/generation_cases.jsonl` — 15개 언어 60개 생성 평가 시나리오 픽스처
- `docs/evaluations/language-assistant-baseline.md` — 구조화 Baseline 보고서 (`status: NOT_RUN` 명시)
- `tests/integration/language/test_model_offline_smoke.py` — 오프라인 모델 및 Qdrant 계약 연동 스모크 테스트

### 수정 파일 (1개)
- `pyproject.toml` — pytest `qdrant_integration` 및 `language_models` 마커 추가

---

## 핵심 설계 결정

1. **Harness-Only Deterministic Execution**
   - 외부 LLM/Qdrant 연동 없이 독립 실행 가능한 `--validate-only` 모드 구축.
   - 지표 계산 알고리즘 (Recall, MRR, nDCG, Preservation Rate, Percentile Latency) 검증 완료.

2. **60-Case 15-Language Synthetic Fixtures**
   - 15개 지원 언어(`en`, `zh-Hans`, `vi`, `th`, `fil`, `id`, `mn`, `si`, `ru`, `uz`, `ky`, `bn`, `ur`, `km`, `tet`) 각 4개 구조적 시나리오(서류 요청, 기한/숫자 보존, 금액/단위, 금지/의무/경고).
   - 총 60개 완전 무결성 픽스처 구축.

3. **Baseline Report Gate Mapping**
   - 미해결 외부 게이트(G2, G3, G4, G5, G7)에 대해 추정치나 가짜 점수를 입력하지 않고 `status: NOT_RUN`으로 명시적 격리.

---

## 금지 사항 준수

- ✅ 허용 목록(9개) 외 코드 수정 없음 (T16 원장, control tower 등 미수정)
- ✅ --validate-only 및 단위 테스트 중 라이브 LLM/Qdrant 호출 없음
- ✅ 기존 T01~T14 계약 및 테스트 약화 없음 (444 passed -> 453 passed)
- ✅ 중앙 feature 브랜치 병합 또는 push 없음
