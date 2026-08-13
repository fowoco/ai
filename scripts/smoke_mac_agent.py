from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROMPT_VERSION = "knowledge-25e778ad"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test a running Mac AI Agent without printing secrets."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--env-file", type=Path, default=Path(".env.mac"))
    parser.add_argument("--timeout", type=float, default=90.0)
    return parser.parse_args()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    args = _arguments()
    load_dotenv(args.env_file, override=False)
    token = os.environ.get("FOWOCO_INTERNAL_API_TOKEN")
    _require(bool(token), "FOWOCO_INTERNAL_API_TOKEN is required for smoke test")

    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(
        base_url=args.base_url.rstrip("/"),
        headers=headers,
        timeout=args.timeout,
    ) as client:
        live = client.get("/health/live")
        _require(live.status_code == 200, "liveness failed")

        ready = client.get("/internal/v1/health/ready")
        _require(ready.status_code == 200, "readiness failed")
        ready_body = ready.json()
        _require(ready_body.get("ready") is True, "Agent is not ready")
        _require(ready_body.get("intentModelEnabled") is True, "Intent model is disabled")
        _require(ready_body.get("axEnabled") is True, "A.X is disabled")
        _require(ready_body.get("axAvailable") is True, "A.X is unavailable")
        _require(
            ready_body.get("promptVersion") == PROMPT_VERSION,
            "Knowledge prompt version mismatch",
        )

        plan = client.post(
            "/internal/v1/analyses",
            json={
                "requestId": "mac-smoke-plan",
                "phase": "PLAN",
                "analysisInput": {"instruction": "여권 사본을 요청해줘"},
            },
        )
        _require(plan.status_code == 200, "PLAN failed")
        plan_body = plan.json()
        _require(plan_body.get("outcome") == "CONTEXT_REQUIRED", "PLAN outcome mismatch")
        _require(plan_body.get("versions", {}).get("modelVersion") == "AX", "A.X was not used")
        _require(
            plan_body.get("versions", {}).get("promptVersion") == PROMPT_VERSION,
            "PLAN prompt version mismatch",
        )

        context = plan_body.get("contextRequirement") or {}
        requested_keys = context.get("requiredFieldKeys") or []
        requested_fields = {key: "smoke-value" for key in requested_keys}
        analyze = client.post(
            "/internal/v1/analyses",
            json={
                "requestId": "mac-smoke-analyze",
                "phase": "ANALYZE",
                "analysisInput": {
                    "instruction": "여권 사본을 요청해줘",
                    "plannedIntent": context.get("detectedIntent"),
                    "plannedWorkflowId": context.get("workflowId"),
                    "requestedFieldKeys": requested_keys,
                    "workers": [
                        {
                            "workerRef": "mac-smoke-worker",
                            "requestedFields": requested_fields,
                        }
                    ],
                },
            },
        )
        _require(analyze.status_code == 200, "ANALYZE failed")
        analyze_body = analyze.json()
        _require(
            analyze_body.get("providerAttemptCount") == 0,
            "ANALYZE called an Intent provider",
        )
        candidates = analyze_body.get("candidates") or []
        _require(bool(candidates), "ANALYZE did not return a candidate")
        _require(
            candidates[0].get("workflowId") == context.get("workflowId"),
            "ANALYZE workflow differs from PLAN",
        )

    print(
        "Mac Agent smoke passed: liveness, readiness, A.X PLAN, "
        "and zero-provider ANALYZE"
    )


if __name__ == "__main__":
    main()
