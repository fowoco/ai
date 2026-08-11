# Dynamic Document Mapping Baseline

```yaml
date: 2026-08-11
mode: rule
catalog_version: v1
fixture_cases: 5
gate: PASSED
```

This deterministic offline baseline uses
`tests/fixtures/dynamic_automation/mapping_cases.jsonl`. Rule mode exercises exact aliases,
fail-closed ambiguity, non-data classification, and unsupported fields without importing or
requiring model packages. The fixture contains labels and bounded structural context only; it
contains no document values or resolved database values.

## Results

| Metric | Rule baseline |
| --- | ---: |
| Extraction precision | 1.000000 |
| Extraction recall | 1.000000 |
| Top-1 accuracy | 1.000000 |
| Top-5 recall | 1.000000 |
| Automatic-match precision | 1.000000 |
| Coverage | 0.500000 |
| Ambiguous accuracy | 1.000000 |
| Sensitive-field precision | 1.000000 |
| Document zero-error rate | 1.000000 |

The release gate requires automatic-match precision of at least `0.99` and sensitive-field
precision of at least `0.995`. This five-case rule baseline passes both gates. Coverage is lower by
design: uncertain fields are deferred instead of being accepted automatically.

## Metric definitions

- Extraction precision and recall treat every status other than `NON_DATA` as an extracted data
  field.
- Top-1 accuracy and top-k recall compare literal expected canonical IDs with the ranked candidate
  IDs.
- Automatic-match precision measures correct `MATCHED` outcomes among automatic matches; coverage
  measures automatic matches among expected data fields.
- Ambiguous accuracy measures correct deferral for cases labeled `AMBIGUOUS`.
- Sensitive-field precision restricts automatic-match precision to catalog fields marked
  `sensitive`.
- Document zero-error rate requires every evaluated field in a document to have the expected status
  and, for a match, the expected canonical ID.

Reproduce the JSON report with:

```powershell
python scripts/evaluate_dynamic_mapping.py --cases tests/fixtures/dynamic_automation/mapping_cases.jsonl --catalog app/documents/dynamic_automation/resources/canonical_fields.v1.yaml --mode rule --output build/dynamic-mapping-baseline.json
```
