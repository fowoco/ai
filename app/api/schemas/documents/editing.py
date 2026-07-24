"""Request and response schemas for document templates and editing."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.documents import DocumentFormat

EditValue = str | int | float | bool


class DocumentEditPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str | None = Field(default=None, min_length=1)
    values: dict[str, EditValue] = Field(default_factory=dict)
    application_options: dict[str, EditValue] = Field(default_factory=dict)
    assets: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_mutation(self) -> DocumentEditPayload:
        if not (self.values or self.application_options or self.assets):
            raise ValueError(
                "payload needs at least one value, application option, or asset"
            )
        return self


class DocumentGeneratePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(min_length=1)
    format: DocumentFormat
    values: dict[str, EditValue] = Field(default_factory=dict)
    application_options: dict[str, EditValue] = Field(default_factory=dict)
    assets: dict[str, str] = Field(default_factory=dict)


class EditableFieldResponse(BaseModel):
    name: str
    type: str
    width_mm: float | None = None
    height_mm: float | None = None


class DocumentTemplateVariantResponse(BaseModel):
    format: DocumentFormat
    field_count: int
    fields: tuple[EditableFieldResponse, ...]
    supports_dynamic_labels: bool
    supports_assets: bool


class DocumentTemplateResponse(BaseModel):
    template_id: str
    display_name: str
    variants: tuple[DocumentTemplateVariantResponse, ...]


class DocumentInspectionResponse(BaseModel):
    format: DocumentFormat
    editable: bool
    template_id: str | None


__all__ = [
    "DocumentEditPayload",
    "DocumentGeneratePayload",
    "DocumentInspectionResponse",
    "DocumentTemplateResponse",
    "DocumentTemplateVariantResponse",
    "EditableFieldResponse",
]
