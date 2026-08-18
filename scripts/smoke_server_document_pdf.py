"""Render the Server demo HWP/HWPX fixtures and verify their PDF page counts."""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader

from app.documents.conversion import HwpToPdfConverter, HwpxToPdfConverter

FIXTURES = {
    "employment-contract-template.hwp": 2,
    "employment-contract-template.hwpx": 2,
    "employment-extension-template.hwpx": 2,
    "integrated-application-template.hwpx": 1,
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rhwp-path", default="rhwp")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for filename, expected_pages in FIXTURES.items():
        source = args.fixture_dir / filename
        if not source.is_file():
            failures.append(f"{filename}: source fixture is missing")
            continue
        destination = args.output_dir / f"{source.stem}-{source.suffix[1:]}.pdf"
        converter = (
            HwpToPdfConverter(args.rhwp_path)
            if source.suffix.casefold() == ".hwp"
            else HwpxToPdfConverter(args.rhwp_path)
        )
        converter.convert(source, destination)
        pages = len(PdfReader(destination, strict=True).pages)
        size = destination.stat().st_size
        print(f"{filename}: pages={pages}, bytes={size}, output={destination}")
        if pages != expected_pages:
            failures.append(
                f"{filename}: expected {expected_pages} pages but rendered {pages}"
            )
        if size <= 10_000:
            failures.append(f"{filename}: PDF output is unexpectedly small ({size} bytes)")
    if failures:
        for failure in failures:
            print(f"FAILED: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
