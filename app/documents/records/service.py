"""TXT/DB 레코드를 규칙 기반으로 HWPX 템플릿에 기입한다."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.documents.common import DocumentFormat
from app.documents.editing import (
    DocumentMutationResult,
    DocumentTemplateNotFoundError,
)
from app.documents.hwpx import HwpxDocument, HwpxError, HwpxRecordAssignment
from app.documents.hwpx.service import HwpxDocumentService

from .errors import DocumentRecordError
from .rules import TEMPLATE_RULES, XmlCellRule
from .text_reader import RecordReader, TextRecordReader


class DocumentRecordGenerationService:
    """외부 레코드를 고정 양식 규칙에 따라 HWPX로 생성한다."""

    def __init__(
        self,
        hwpx_service: HwpxDocumentService | None = None,
        reader: RecordReader | None = None,
        rules: Mapping[str, tuple[XmlCellRule, ...]] | None = None,
    ):
        self.hwpx_service = hwpx_service or HwpxDocumentService()
        self.reader = reader or TextRecordReader()
        self.rules = dict(rules or TEMPLATE_RULES)

    def generate_from_txt(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        template_id: str,
    ) -> DocumentMutationResult:
        return self.generate(
            self.reader.read(source),
            destination,
            template_id=template_id,
        )

    def generate(
        self,
        record: Mapping[str, object],
        destination: str | Path,
        *,
        template_id: str,
    ) -> DocumentMutationResult:
        try:
            template = self.hwpx_service.registry.get(template_id)
        except HwpxError as exc:
            raise DocumentTemplateNotFoundError(str(exc)) from exc
        try:
            template_rules = self.rules[template_id]
        except KeyError as exc:
            raise DocumentTemplateNotFoundError(
                f"no record mapping rules are registered for: {template_id}"
            ) from exc

        assignments = tuple(
            _assignment(rule, value)
            for rule in template_rules
            if (value := _record_value(rule, record)) is not None and value != ""
        )
        if not assignments:
            supported = sorted(rule.source_key for rule in template_rules)
            raise DocumentRecordError(
                "TXT record has no fields supported by template "
                f"{template_id!r}; supported fields: {supported}"
            )

        try:
            document = HwpxDocument(template.source_path)
            changed_fields = document.apply_record_assignments(assignments)
            output = document.save(destination)
        except (HwpxError, OSError, ValueError) as exc:
            raise DocumentRecordError(str(exc)) from exc

        return DocumentMutationResult(
            destination=output,
            format=DocumentFormat.HWPX,
            template_id=template_id,
            changed_fields=changed_fields,
        )


def _assignment(rule: XmlCellRule, value: object) -> HwpxRecordAssignment:
    rendered_value = str(value)
    if rule.digits_only:
        rendered_value = "".join(
            character for character in rendered_value if character.isdecimal()
        )
    if rule.value_index is not None:
        try:
            rendered_value = rendered_value[rule.value_index]
        except IndexError as exc:
            raise DocumentRecordError(
                f"record field {rule.source_key!r} needs at least "
                f"{rule.value_index + 1} characters"
            ) from exc
    return HwpxRecordAssignment(
        name=rule.source_key,
        table_index=rule.table_index,
        row=rule.row,
        column=rule.column,
        value=rendered_value,
        operation=rule.operation,
        marker=rule.marker,
        replacement_format=rule.replacement_format,
        text_index=rule.text_index,
    )


def _record_value(
    rule: XmlCellRule,
    record: Mapping[str, object],
) -> object | None:
    for key in (rule.source_key, *rule.record_keys):
        if key in record:
            return record[key]
    return None


__all__ = ["DocumentRecordGenerationService"]
