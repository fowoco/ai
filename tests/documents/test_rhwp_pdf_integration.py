import os
import shutil
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.documents.conversion import HwpToPdfConverter, HwpxToPdfConverter
from app.documents.hwp5 import Hwp5DocumentService
from app.documents.hwpx import HwpxDocumentService


def _rhwp_executable() -> str | None:
    configured = os.getenv("FOWOCO_RHWP_PATH", "rhwp")
    return shutil.which(configured)


@pytest.mark.rhwp_integration
@pytest.mark.skipif(_rhwp_executable() is None, reason="rhwp executable is unavailable")
@pytest.mark.parametrize(
    ("source", "expected_pages"),
    [
        (
            Hwp5DocumentService().registry.get(
                "standard_labor_contract_v6"
            ).source_path,
            2,
        ),
        (
            HwpxDocumentService().registry.get(
                "standard_labor_contract_v6"
            ).source_path,
            2,
        ),
        (
            HwpxDocumentService().registry.get(
                "employment_extension_application_v12_3"
            ).source_path,
            2,
        ),
        (
            HwpxDocumentService().registry.get(
                "immigration_integrated_application_v34"
            ).source_path,
            1,
        ),
    ],
)
def test_canonical_document_is_rendered_to_expected_pdf_pages(
    source: Path,
    expected_pages: int,
    tmp_path: Path,
) -> None:
    executable = _rhwp_executable()
    assert executable is not None
    destination = tmp_path / f"{source.stem}.pdf"
    converter = (
        HwpToPdfConverter(executable)
        if source.suffix.casefold() == ".hwp"
        else HwpxToPdfConverter(executable)
    )

    converter.convert(source, destination)

    document = PdfReader(destination, strict=True)
    assert len(document.pages) == expected_pages
    assert destination.stat().st_size > 10_000
