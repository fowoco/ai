from pathlib import Path

import pytest

from app.documents import DocumentFormat
from app.documents.editing import (
    DocumentEditingError,
    DocumentEditingNotSupportedError,
    DocumentEditingService,
    DocumentTemplateNotFoundError,
)
from app.documents.hwp5 import Hwp5BinaryDocument, Hwp5DocumentService
from app.documents.hwpx import HwpxDocumentService


def test_templates_group_hwp_and_hwpx_variants() -> None:
    templates = DocumentEditingService().templates()

    assert len(templates) == 4
    identity = next(
        template
        for template in templates
        if template.template_id == "identity_guaranty_v129"
    )
    assert identity.display_name == "신원보증서(한글)"
    assert [variant.format for variant in identity.variants] == [
        DocumentFormat.HWP,
        DocumentFormat.HWPX,
    ]
    hwp_variant = identity.variants[0]
    assert any(field.name == "foreign_name" for field in hwp_variant.fields)
    assert any(
        field.name == "guarantor_signature"
        and field.field_type == "signature"
        for field in hwp_variant.fields
    )
    assert hwp_variant.supports_assets is True
    assert identity.variants[1].supports_dynamic_labels is True


def test_inspect_identifies_registered_hwp_and_hwpx() -> None:
    service = DocumentEditingService()
    hwp = Hwp5DocumentService().registry.get("identity_guaranty_v129")
    hwpx = HwpxDocumentService().registry.get("identity_guaranty_v129")

    hwp_result = service.inspect(hwp.source_path)
    hwpx_result = service.inspect(hwpx.source_path)

    assert hwp_result.format is DocumentFormat.HWP
    assert hwp_result.template_id == "identity_guaranty_v129"
    assert hwpx_result.format is DocumentFormat.HWPX
    assert hwpx_result.template_id == "identity_guaranty_v129"


def test_edit_dispatches_registered_hwp_template(tmp_path: Path) -> None:
    source = Hwp5DocumentService().registry.get(
        "identity_guaranty_v129"
    ).source_path
    output = tmp_path / "edited.hwp"

    result = DocumentEditingService().edit(
        source,
        output,
        template_id="identity_guaranty_v129",
        values={"foreign_name": "API NAME", "foreign_male": True},
    )

    assert result.format is DocumentFormat.HWP
    assert result.changed_fields == ("foreign_name", "foreign_male")
    document = Hwp5BinaryDocument(output)
    assert "API NAME" in document.paragraphs()[8].text


def test_generate_rejects_assets_for_hwpx(tmp_path: Path) -> None:
    with pytest.raises(
        DocumentEditingNotSupportedError,
        match="HWPX structured asset insertion",
    ):
        DocumentEditingService().generate(
            "identity_guaranty_v129",
            DocumentFormat.HWPX,
            tmp_path / "generated.hwpx",
            assets={"signature": tmp_path / "signature.png"},
        )


def test_hwpx_edit_rejects_unmatched_dynamic_labels(tmp_path: Path) -> None:
    template = HwpxDocumentService().registry.get(
        "identity_guaranty_v129"
    )

    with pytest.raises(DocumentEditingError, match="not found in the HWPX"):
        DocumentEditingService().edit(
            template.source_path,
            tmp_path / "edited.hwpx",
            template_id=template.template_id,
            values={"missing label": "value"},
        )


def test_template_lookup_rejects_unknown_id() -> None:
    with pytest.raises(DocumentTemplateNotFoundError, match="unknown document"):
        DocumentEditingService().template("missing-template")
