import json
from pathlib import Path

import pytest

from scripts.evaluate_language_generation import (
    check_date_number_preservation,
    compute_percentile,
    evaluate_generation_cases,
)
from scripts.evaluate_language_retrieval import (
    compute_mrr_at_k,
    compute_ndcg_at_k,
    compute_recall_at_k,
    evaluate_retrieval_cases,
)


def test_recall_at_k():
    retrieved = ["p1", "p2", "p3", "p4", "p5"]
    relevant = {"p3", "p6"}
    assert compute_recall_at_k(retrieved, relevant, 5) == 0.5
    assert compute_recall_at_k(retrieved, relevant, 2) == 0.0


def test_mrr_at_k():
    retrieved = ["p1", "p2", "p3", "p4"]
    relevant = {"p3"}
    assert pytest.approx(compute_mrr_at_k(retrieved, relevant, 10), rel=1e-3) == 1 / 3.0


def test_ndcg_at_k():
    retrieved = ["p1", "p2"]
    graded = {"p1": 2, "p2": 1}
    assert compute_ndcg_at_k(retrieved, graded, 10) == 1.0


def test_date_number_preservation():
    context = {
        "deadline": "2026-08-15",
        "requested_items": ["3 copies of form A", "100 USD fee"],
    }
    valid_text = "Please submit by 2026-08-15. 3 copies of form A and 100 USD fee required."
    invalid_text = "Please submit by tomorrow. copies of form A required."

    assert check_date_number_preservation(context, valid_text) is True
    assert check_date_number_preservation(context, invalid_text) is False


def test_percentile_computation():
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert compute_percentile(latencies, 50) in (50.0, 55.0)
    assert compute_percentile(latencies, 95) >= 90.0


def test_fixtures_schema_and_integrity():
    fixtures_dir = Path("tests/fixtures/language")

    ctx_file = fixtures_dir / "request_context_cases.json"
    ret_file = fixtures_dir / "retrieval_cases.jsonl"
    gen_file = fixtures_dir / "generation_cases.jsonl"

    assert ctx_file.exists()
    assert ret_file.exists()
    assert gen_file.exists()

    with open(ctx_file, encoding="utf-8") as f:
        ctx_cases = json.load(f)
    assert len(ctx_cases) == 60

    ret_lines = [line for line in ret_file.read_text(encoding="utf-8").splitlines() if line]
    ret_cases = [json.loads(line) for line in ret_lines]
    assert len(ret_cases) == 60

    gen_lines = [line for line in gen_file.read_text(encoding="utf-8").splitlines() if line]
    gen_cases = [json.loads(line) for line in gen_lines]
    assert len(gen_cases) == 60

    expected_langs = {
        "en", "zh-Hans", "vi", "th", "fil", "id", "mn", "si",
        "ru", "uz", "ky", "bn", "ur", "km", "tet",
    }
    ret_langs = {c["target_language"] for c in ret_cases}
    assert ret_langs == expected_langs


def test_evaluator_validate_only_mode():
    ret_cases = [
        {
            "case_id": "test_ret_1",
            "target_language": "en",
            "relevant_point_ids": ["p1"],
            "graded_relevance": {"p1": 2},
        }
    ]
    ret_res = evaluate_retrieval_cases(ret_cases, validate_only=True)
    assert ret_res["status"] == "validated"
    assert ret_res["total_cases"] == 1

    gen_cases = [
        {
            "case_id": "test_gen_1",
            "target_language": "en",
            "request_context": {"deadline": "2026-08-15", "requested_items": ["1 item"]},
            "model_output_under_review": {
                "translated_text": "2026-08-15 1 item"
            },
        }
    ]
    gen_res = evaluate_generation_cases(gen_cases, validate_only=True)
    assert gen_res["status"] == "validated"
    assert gen_res["date_number_preservation_rate"] == 1.0
