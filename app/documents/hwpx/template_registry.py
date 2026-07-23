"""Bundled HWPX template lookup and content-hash identification."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .errors import HwpxError

TEMPLATE_FILES = {
    "employment_extension_application_v12_3": "취업활동기간연장신청서.hwpx",
    "identity_guaranty_v129": "신원보증서.hwpx",
    "immigration_integrated_application_v34": "통합신청서.hwpx",
    "standard_labor_contract_v6": "표준근로계약서.hwpx",
}


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class HwpxTemplate:
    template_id: str
    source_path: Path
    sha256: str


class HwpxTemplateRegistry:
    def __init__(self, template_dir: str | Path | None = None):
        self.template_dir = (
            Path(template_dir).resolve()
            if template_dir is not None
            else Path(__file__).resolve().parent / "templates"
        )
        self._by_id: dict[str, HwpxTemplate] = {}
        self._by_hash: dict[str, HwpxTemplate] = {}
        for template_id, filename in TEMPLATE_FILES.items():
            source_path = self.template_dir / filename
            if not source_path.is_file():
                raise HwpxError(f"missing bundled HWPX template: {source_path}")
            digest = file_sha256(source_path)
            template = HwpxTemplate(template_id, source_path, digest)
            self._by_id[template_id] = template
            self._by_hash[digest] = template

    def list(self) -> tuple[HwpxTemplate, ...]:
        return tuple(self._by_id[key] for key in sorted(self._by_id))

    def get(self, template_id: str) -> HwpxTemplate:
        try:
            return self._by_id[template_id]
        except KeyError as exc:
            raise HwpxError(f"unknown HWPX template_id: {template_id}") from exc

    def identify(self, source: str | Path) -> HwpxTemplate:
        digest = file_sha256(source)
        try:
            return self._by_hash[digest]
        except KeyError as exc:
            raise HwpxError(f"no HWPX template matches source SHA-256: {digest}") from exc


__all__ = ["HwpxTemplate", "HwpxTemplateRegistry"]
