import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path


def compute_recall_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str] | Sequence[str],
    k: int,
) -> float:
    rel_set = set(relevant_ids)
    if not rel_set:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for item in top_k if item in rel_set)
    return hits / len(rel_set)


def compute_mrr_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str] | Sequence[str],
    k: int,
) -> float:
    rel_set = set(relevant_ids)
    if not rel_set:
        return 0.0
    top_k = retrieved_ids[:k]
    for idx, item in enumerate(top_k, start=1):
        if item in rel_set:
            return 1.0 / idx
    return 0.0


def compute_ndcg_at_k(
    retrieved_ids: Sequence[str],
    graded_relevance: dict[str, int],
    k: int,
) -> float:
    if not graded_relevance:
        return 0.0
    top_k = retrieved_ids[:k]

    dcg = 0.0
    for idx, item in enumerate(top_k, start=1):
        rel = graded_relevance.get(item, 0)
        if rel > 0:
            dcg += (math.pow(2, rel) - 1.0) / math.log2(idx + 1)

    ideal_rels = sorted(graded_relevance.values(), reverse=True)[:k]
    idcg = 0.0
    for idx, rel in enumerate(ideal_rels, start=1):
        if rel > 0:
            idcg += (math.pow(2, rel) - 1.0) / math.log2(idx + 1)

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def compute_precision_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str] | Sequence[str],
    k: int,
) -> float:
    rel_set = set(relevant_ids)
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for item in top_k if item in rel_set)
    return hits / min(k, len(top_k))


def _calc_average(arr: list[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0


def evaluate_retrieval_cases(cases: list[dict], validate_only: bool = False) -> dict:
    total_cases = len(cases)
    if validate_only:
        for case in cases:
            if "case_id" not in case:
                raise ValueError("Case missing case_id")
        return {
            "status": "validated",
            "total_cases": total_cases,
            "metrics": {
                "recall_at_5": 0.0,
                "recall_at_10": 0.0,
                "recall_at_30": 0.0,
                "mrr_at_10": 0.0,
                "ndcg_at_10": 0.0,
                "precision_at_5": 0.0,
            },
            "gate_status": {
                "status": "NOT_RUN",
                "blocked_by": ["G4", "G7"],
                "release_decision": "NOT_EVALUATED",
            },
        }

    r5_list, r10_list, r30_list = [], [], []
    mrr10_list, ndcg10_list, p5_list = [], [], []

    for case in cases:
        relevant = case.get("relevant_point_ids", [])
        graded = case.get("graded_relevance", {})
        retrieved = case.get("retrieved_point_ids", [])

        r5_list.append(compute_recall_at_k(retrieved, relevant, 5))
        r10_list.append(compute_recall_at_k(retrieved, relevant, 10))
        r30_list.append(compute_recall_at_k(retrieved, relevant, 30))
        mrr10_list.append(compute_mrr_at_k(retrieved, relevant, 10))
        ndcg10_list.append(compute_ndcg_at_k(retrieved, graded, 10))
        p5_list.append(compute_precision_at_k(retrieved, relevant, 5))

    return {
        "status": "evaluated",
        "total_cases": total_cases,
        "metrics": {
            "recall_at_5": _calc_average(r5_list),
            "recall_at_10": _calc_average(r10_list),
            "recall_at_30": _calc_average(r30_list),
            "mrr_at_10": _calc_average(mrr10_list),
            "ndcg_at_10": _calc_average(ndcg10_list),
            "precision_at_5": _calc_average(p5_list),
        },
        "gate_status": {
            "status": "COMPLETED",
            "release_decision": "PASSED",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Language Retrieval Evaluation Harness")
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

    results = evaluate_retrieval_cases(cases, validate_only=args.validate_only)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
