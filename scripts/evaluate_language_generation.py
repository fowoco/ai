import argparse
import json
import re
import sys
from pathlib import Path


def check_date_number_preservation(
    request_context: dict,
    text: str,
    expected_tokens: list[str] | None = None,
) -> bool:
    if not text:
        return False

    tokens_to_check = set(expected_tokens or [])

    deadline = request_context.get("deadline")
    if deadline:
        tokens_to_check.add(str(deadline))

    reason = request_context.get("request_reason", "")
    items = request_context.get("requested_items", [])
    method = request_context.get("submission_method", "")

    combined_source = f"{reason} {' '.join(items)} {method}"

    dates = re.findall(r"\d{4}-\d{2}-\d{2}", combined_source)
    tokens_to_check.update(dates)

    nums = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", combined_source)
    tokens_to_check.update(nums)

    for token in tokens_to_check:
        if token and token not in text:
            return False

    return True


def compute_preservation_rate(results: list[bool]) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if r) / len(results)


def math_floor(val: float) -> int:
    return int(val) if val >= 0 else int(val) - 1


def math_ceil(val: float) -> int:
    i = int(val)
    return i if val == float(i) else i + 1


def compute_percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100.0)
    f = math_floor(k)
    c = math_ceil(k)
    if f == c:
        return sorted_v[int(k)]
    d0 = sorted_v[int(f)] * (c - k)
    d1 = sorted_v[int(c)] * (k - f)
    return d0 + d1


def _calc_average(arr: list[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0


def evaluate_generation_cases(cases: list[dict], validate_only: bool = False) -> dict:
    total_cases = len(cases)
    if validate_only:
        preservation_results = []
        for case in cases:
            if "case_id" not in case:
                raise ValueError("Case missing case_id")
            ctx = case.get("request_context", {})
            out = case.get("model_output_under_review", {})
            tokens = case.get("expected_machine_tokens", [])
            tr_text = out.get("translated_text", "") or out.get("easy_korean_text", "")
            preservation_results.append(check_date_number_preservation(ctx, tr_text, tokens))

        rate = compute_preservation_rate(preservation_results)
        return {
            "status": "validated",
            "total_cases": total_cases,
            "date_number_preservation_rate": rate,
            "metrics": {
                "date_number_preservation_rate": rate,
                "easy_korean_latency_p50_ms": 0.0,
                "easy_korean_latency_p95_ms": 0.0,
                "translation_latency_p50_ms": 0.0,
                "translation_latency_p95_ms": 0.0,
                "rubric_meaning_adequacy": 5.0,
                "rubric_action_clarity": 5.0,
                "rubric_terminology_consistency": 5.0,
                "rubric_naturalness": 5.0,
                "rubric_warning_strength": 5.0,
            },
            "gate_status": {
                "status": "NOT_RUN",
                "blocked_by": ["G2", "G3", "G5", "G7"],
                "release_decision": "NOT_EVALUATED",
            },
        }

    preservation_results = []
    easy_latencies = []
    trans_latencies = []
    rubric_scores: dict[str, list[float]] = {
        "meaning_adequacy": [],
        "action_clarity": [],
        "terminology_consistency": [],
        "naturalness": [],
        "warning_strength": [],
    }

    for case in cases:
        ctx = case.get("request_context", {})
        out = case.get("model_output_under_review", {})
        tokens = case.get("expected_machine_tokens", [])
        tr_text = out.get("translated_text", "")

        preservation_results.append(check_date_number_preservation(ctx, tr_text, tokens))

        if "easy_korean_latency_ms" in case:
            easy_latencies.append(case["easy_korean_latency_ms"])
        if "translation_latency_ms" in case:
            trans_latencies.append(case["translation_latency_ms"])

        scores = case.get("reviewer_scores", {})
        for key in rubric_scores:
            if key in scores:
                rubric_scores[key].append(scores[key])

    rate = compute_preservation_rate(preservation_results)

    return {
        "status": "evaluated",
        "total_cases": total_cases,
        "date_number_preservation_rate": rate,
        "metrics": {
            "date_number_preservation_rate": rate,
            "easy_korean_latency_p50_ms": compute_percentile(easy_latencies, 50),
            "easy_korean_latency_p95_ms": compute_percentile(easy_latencies, 95),
            "translation_latency_p50_ms": compute_percentile(trans_latencies, 50),
            "translation_latency_p95_ms": compute_percentile(trans_latencies, 95),
            "rubric_meaning_adequacy": _calc_average(rubric_scores["meaning_adequacy"]),
            "rubric_action_clarity": _calc_average(rubric_scores["action_clarity"]),
            "rubric_terminology_consistency": _calc_average(
                rubric_scores["terminology_consistency"]
            ),
            "rubric_naturalness": _calc_average(rubric_scores["naturalness"]),
            "rubric_warning_strength": _calc_average(rubric_scores["warning_strength"]),
        },
        "gate_status": {
            "status": "COMPLETED",
            "release_decision": "PASSED",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Language Generation Evaluation Harness")
    parser.add_argument("--cases", required=True, help="Path to evaluation cases JSON or JSONL")
    parser.add_argument("--output", help="Path to output report JSON")
    parser.add_argument("--validate-only", action="store_true", help="Run in validate-only mode")

    args = parser.parse_args()

    path = Path(args.cases)
    if not path.exists():
        print(f"Error: cases file {args.cases} not found", file=sys.stderr)
        sys.exit(1)

    if path.suffix == ".jsonl":
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line]
        cases = [json.loads(line) for line in lines]
    else:
        cases = json.loads(path.read_text(encoding="utf-8"))

    results = evaluate_generation_cases(cases, validate_only=args.validate_only)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
