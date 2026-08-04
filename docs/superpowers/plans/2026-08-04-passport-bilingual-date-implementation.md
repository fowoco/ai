# Passport Bilingual Date Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize the bilingual dates returned by the deployed Korean passport template into native Python `date` values.

**Architecture:** Extend only the provider-neutral date parser in `app/ocr/normalizer.py`. Keep the existing numeric formats, then strictly recognize `DD N월/MON YYYY`, require both month representations to match, and let the existing invalid-date review path handle malformed or contradictory input.

**Tech Stack:** Python 3.11+, `datetime`, regular expressions, pytest, Ruff.

## Global Constraints

- Modify only `fowoco/ai`.
- Never log or assert real passport values.
- Tests use synthetic dates only.
- Existing numeric date formats and invalid-date behavior must remain unchanged.

---

### Task 1: Parse Korean passport bilingual dates

**Files:**
- Modify: `tests/ocr/test_normalizer.py`
- Modify: `app/ocr/normalizer.py`

**Interfaces:**
- Consumes: CLOVA date text supplied to the existing `_parse_date(value: str)` helper.
- Produces: native `date` values through `normalize_clova_response`; malformed dates continue to produce `REVIEW_REQUIRED` with `INVALID_DATE`.

- [ ] **Step 1: Write failing normalization tests**

Add synthetic passport responses covering all three configured date fields:

```python
def test_normalizes_korean_passport_bilingual_dates() -> None:
    fields = passport_required_fields()
    fields[4] = field("date_of_birth", "17 2월/FEB 2000")
    fields[5] = field("passport_expiry_date", "24 3월/MAR 2028")
    fields.append(field("passport_issue_date", "24 3월/MAR 2023"))
    # Assert SUCCEEDED and the three hand-derived date values.
```

Add a contradictory month case such as `17 2월/MAR 2000` and assert
`REVIEW_REQUIRED`, `INVALID_DATE`, and no stored `date_of_birth`.

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest tests/ocr/test_normalizer.py -v
```

Expected: bilingual-date success test fails with `REVIEW_REQUIRED` because the current parser accepts only numeric year-first formats.

- [ ] **Step 3: Implement the strict parser**

Add a compiled regex for day, numeric Korean month, English month abbreviation, and year. Map `JAN` through `DEC` to month numbers, reject unequal numeric/English months, and construct `date(year, month, day)` so impossible calendar dates are rejected.

- [ ] **Step 4: Verify GREEN and regression behavior**

```powershell
python -m pytest tests/ocr/test_normalizer.py tests/ocr/test_service.py -v
python -m ruff check app/ocr/normalizer.py tests/ocr/test_normalizer.py
```

Expected: PASS.

- [ ] **Step 5: Run a privacy-safe live CLOVA normalization check**

Use the ignored `runtime` sample and local `.env`. Print only status, template ID,
field names, confidences, and review reasons. Expected: `SUCCEEDED`, template `43019`,
and no review reasons.

- [ ] **Step 6: Commit**

```powershell
git add app/ocr/normalizer.py tests/ocr/test_normalizer.py docs/superpowers
git commit -m "fix: parse Korean passport dates"
```
