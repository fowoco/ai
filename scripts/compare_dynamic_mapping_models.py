"""Compare dynamic mapping model manifests using fail-closed promotion gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.documents.dynamic_automation.training import (  # noqa: E402
    HeldOutEvaluationReport,
    ModelManifest,
    compare_manifests,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--baseline-artifact", required=True, type=Path)
    parser.add_argument("--baseline-report", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--candidate-artifact", required=True, type=Path)
    parser.add_argument("--candidate-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        baseline = ModelManifest.model_validate_json(
            args.baseline.read_text(encoding="utf-8")
        )
        candidate = ModelManifest.model_validate_json(
            args.candidate.read_text(encoding="utf-8")
        )
        baseline_report_bytes = args.baseline_report.read_bytes()
        candidate_report_bytes = args.candidate_report.read_bytes()
        baseline_report = HeldOutEvaluationReport.model_validate_json(
            baseline_report_bytes
        )
        candidate_report = HeldOutEvaluationReport.model_validate_json(
            candidate_report_bytes
        )
        decision = compare_manifests(
            baseline=baseline,
            candidate=candidate,
            baseline_report=baseline_report,
            candidate_report=candidate_report,
            baseline_artifact_sha256=_file_sha256(args.baseline_artifact),
            candidate_artifact_sha256=_file_sha256(args.candidate_artifact),
            baseline_report_sha256=hashlib.sha256(baseline_report_bytes).hexdigest(),
            candidate_report_sha256=hashlib.sha256(candidate_report_bytes).hexdigest(),
        )
    except (OSError, ValidationError, ValueError) as error:
        print(f"comparison failed: {error}", file=sys.stderr)
        return 1

    serialized = json.dumps(
        decision.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if decision.promote else 2


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
