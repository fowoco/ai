from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hwp_mcp.hwpx import DocumentError
from hwp_mcp.integrity import EnvSigningKeyProvider
from hwp_mcp.plans import sha256_file
from hwp_mcp.vision import (
    HostReviewer,
    VisionDecision,
    VisionImage,
    VisionView,
    build_vision_review_request,
    create_vision_delivery,
    compute_review_id,
    validate_host_vision_submission,
    validate_vision_delivery,
    validate_vision_review_request,
)


def _image(tmp_path: Path, name: str) -> VisionImage:
    path = tmp_path / name
    path.write_bytes(name.encode())
    return VisionImage(path=str(path), sha256=sha256_file(path))


def _request(tmp_path: Path):
    original = tmp_path / "original.hwpx"
    modified = tmp_path / "modified.hwpx"
    report = tmp_path / "verification-report.json"
    original.write_bytes(b"original")
    modified.write_bytes(b"modified")
    report.write_text('{"status":"PENDING_VISION_REVIEW"}', encoding="utf-8")
    full = VisionView(
        view_id="page-001-full",
        page=1,
        kind="full",
        bbox=None,
        field_ids=["field-1"],
        original=_image(tmp_path, "full-original.png"),
        modified=_image(tmp_path, "full-modified.png"),
        diff=_image(tmp_path, "full-diff.png"),
    )
    detail = VisionView(
        view_id="page-001-band-001",
        page=1,
        kind="detail",
        bbox=[0, 0, 100, 100],
        field_ids=["field-1"],
        original=_image(tmp_path, "detail-original.png"),
        modified=_image(tmp_path, "detail-modified.png"),
        diff=_image(tmp_path, "detail-diff.png"),
    )
    request = build_vision_review_request(
        plan_id="a" * 64,
        original_path=original,
        modified_path=modified,
        verification_path=report,
        views=[full, detail],
        expected_field_ids=["field-1"],
        prompt="이미지 검토",
    )
    return request


def test_review_request_binds_artifacts_and_images(tmp_path: Path) -> None:
    request = _request(tmp_path)

    assert request.review_id == compute_review_id(request)
    assert request.original_sha256 == sha256_file(tmp_path / "original.hwpx")
    assert request.modified_sha256 == sha256_file(tmp_path / "modified.hwpx")
    assert request.verification_report_sha256 == sha256_file(
        tmp_path / "verification-report.json"
    )
    validate_vision_review_request(request, tmp_path)


def test_review_request_rejects_tampered_image(tmp_path: Path) -> None:
    request = _request(tmp_path)
    Path(request.views[0].modified.path).write_bytes(b"tampered")

    with pytest.raises(DocumentError, match="이미지 무결성"):
        validate_vision_review_request(request, tmp_path)


@pytest.mark.parametrize("model", ["gemini-test", "gpt-test", "claude-test"])
def test_host_review_is_model_agnostic(tmp_path: Path, model: str) -> None:
    request = _request(tmp_path)
    decision = VisionDecision.model_validate(
        {
            "verdict": "PASS",
            "summary": "원본과 비교해 올바른 입력란에 배치됨",
            "fields": [
                {
                    "field_id": "field-1",
                    "verdict": "PASS",
                    "reason": "업체명 라벨 오른쪽 셀 안에 중첩 없이 배치됨",
                    "evidence_view_ids": [
                        "page-001-full",
                        "page-001-band-001",
                    ],
                }
            ],
        }
    )
    reviewer = HostReviewer(
        provider="test",
        model=model,
        capabilities=["image_input"],
    )

    validated = validate_host_vision_submission(request, reviewer, decision)

    assert validated.verdict == "PASS"


def test_host_review_rejects_text_only_model(tmp_path: Path) -> None:
    request = _request(tmp_path)
    decision = VisionDecision.model_validate(
        {
            "verdict": "PASS",
            "summary": "검토 완료",
            "fields": [
                {
                    "field_id": "field-1",
                    "verdict": "PASS",
                    "reason": "입력란에 배치됨",
                    "evidence_view_ids": ["page-001-full"],
                }
            ],
        }
    )

    with pytest.raises(DocumentError, match="image_input"):
        validate_host_vision_submission(
            request,
            HostReviewer(provider="test", model="text", capabilities=[]),
            decision,
        )


def test_host_review_requires_mapped_detail_evidence(tmp_path: Path) -> None:
    request = _request(tmp_path)
    decision = VisionDecision.model_validate(
        {
            "verdict": "PASS",
            "summary": "검토 완료",
            "fields": [
                {
                    "field_id": "field-1",
                    "verdict": "PASS",
                    "reason": "전체 페이지에서 입력란에 배치됨",
                    "evidence_view_ids": ["page-001-full"],
                }
            ],
        }
    )

    with pytest.raises(DocumentError, match="detail"):
        validate_host_vision_submission(
            request,
            HostReviewer(
                provider="test",
                model="vision",
                capabilities=["image_input"],
            ),
            decision,
        )


def test_vision_delivery_is_signed_and_bound_to_image_manifest(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    signer = EnvSigningKeyProvider("v1", {"v1": b"a" * 32})
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    delivery = create_vision_delivery(
        request,
        signer=signer,
        expires_at=expires_at,
    )

    validate_vision_delivery(
        request,
        delivery,
        signer=EnvSigningKeyProvider("v1", {"v1": b"a" * 32}),
        now=datetime.now(timezone.utc),
    )
    changed = request.model_copy(
        update={"review_id": "b" * 64},
    )
    with pytest.raises(DocumentError, match="delivery"):
        validate_vision_delivery(
            changed,
            delivery,
            signer=signer,
            now=datetime.now(timezone.utc),
        )


def test_vision_delivery_rejects_expired_or_forged_signature(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    signer = EnvSigningKeyProvider("v1", {"v1": b"a" * 32})
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    delivery = create_vision_delivery(
        request,
        signer=signer,
        expires_at=expires_at,
    )

    with pytest.raises(DocumentError, match="만료"):
        validate_vision_delivery(
            request,
            delivery,
            signer=signer,
            now=expires_at + timedelta(seconds=1),
        )

    forged = delivery.model_copy(
        update={
            "signature": delivery.signature.model_copy(
                update={"value": "A" * 44}
            )
        }
    )
    with pytest.raises(DocumentError, match="서명"):
        validate_vision_delivery(
            request,
            forged,
            signer=signer,
            now=datetime.now(timezone.utc),
        )
