# Language Assistant Retrieval and Generation Baseline Report

```yaml
evaluation_mode: HARNESS_ONLY
status: NOT_RUN
blocked_by: [G2, G3, G4, G5, G7]
release_decision: NOT_EVALUATED
date: 2026-08-04
```

---

## Executive Summary

Language Assistant W5 T15 evaluation harness infrastructure has been established and verified in deterministic `HARNESS_ONLY` mode. All evaluators, dataset fixture schemas, metric calculators, and CLI validation modes run cleanly without live external LLM or Qdrant connections.

External gates G2 (LLM Runtime), G3 (Context Pack Editorial Review), G4 (Retrieval Labels), G5 (Native-language Reviewers), and G7 (Data/Model Use Review) remain unclosed. Consequently, measured live benchmark metrics are marked `NOT_RUN` until production gate approvals are recorded.

---

## Gate Status and External Dependencies

```yaml
gates:
  G2_llm_runtime:
    status: NOT_RUN
    description: Base URL, model name, JSON output contract, credential injection
  G3_context_pack_review:
    status: NOT_RUN
    description: Legal Context Pack editorial review approval
  G4_retrieval_labels:
    status: NOT_RUN
    description: 60-case reviewed relevant Point ID relevance labels
  G5_native_language_review:
    status: NOT_RUN
    description: Fluent reviewer evaluations for 15 target languages
  G7_data_model_review:
    status: NOT_RUN
    description: EPS data use scope and BGE model license review
```

---

## Retrieval Evaluation Harness

### Metric Definitions
- **Recall@5 / Recall@10 / Recall@30**: Fraction of relevant EPS documents retrieved in top $K$ results.
- **MRR@10**: Mean Reciprocal Rank of the first relevant document in top 10 results.
- **nDCG@10**: Normalized Discounted Cumulative Gain at rank 10 using graded relevance labels (0/1/2).
- **Precision@5**: Ratio of relevant documents within top 5 candidates.

### Dataset Overview
- **Path**: `tests/fixtures/language/retrieval_cases.jsonl`
- **Cases**: 60 synthetic cases across 15 target languages (4 structural scenarios per language).
- **Languages**: `en`, `zh-Hans`, `vi`, `th`, `fil`, `id`, `mn`, `si`, `ru`, `uz`, `ky`, `bn`, `ur`, `km`, `tet`.

---

## Generation Evaluation Harness

### Metric Definitions
- **Date/Number/Token 100% Preservation Rate**: Invariant verification that all dates, numbers, currencies, and machine tokens in `request_context` are 100% preserved in generated outputs.
- **Latency (p50 / p95)**: Measured execution latency in milliseconds for Easy Korean and Translation branches separately.
- **5-Dimension Rubric Score (1–5)**:
  1. Meaning Adequacy
  2. Action Clarity
  3. Terminology Consistency
  4. Naturalness
  5. Obligation/Prohibition/Warning Strength

### Dataset Overview
- **Path**: `tests/fixtures/language/generation_cases.jsonl`
- **Cases**: 60 synthetic cases across 15 target languages.

---

## Target Languages and Scenarios Coverage

| Target Language | Language Code | Scenarios Count | Coverage |
|-----------------|---------------|-----------------|----------|
| English | `en` | 4 | 100% |
| Simplified Chinese | `zh-Hans` | 4 | 100% |
| Vietnamese | `vi` | 4 | 100% |
| Thai | `th` | 4 | 100% |
| Filipino | `fil` | 4 | 100% |
| Indonesian | `id` | 4 | 100% |
| Mongolian | `mn` | 4 | 100% |
| Sinhala | `si` | 4 | 100% |
| Russian | `ru` | 4 | 100% |
| Uzbek | `uz` | 4 | 100% |
| Kyrgyz | `ky` | 4 | 100% |
| Bengali | `bn` | 4 | 100% |
| Urdu | `ur` | 4 | 100% |
| Khmer | `km` | 4 | 100% |
| Tetum | `tet` | 4 | 100% |
| **Total** | **15 Languages** | **60 Cases** | **100%** |
