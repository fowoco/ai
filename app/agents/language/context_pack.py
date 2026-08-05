import hashlib
import importlib.resources
import json
import re
from dataclasses import dataclass
from typing import Self

from pydantic import BaseModel, ConfigDict


class ContextPackError(Exception):
    """Base exception for Context Pack operations."""


class ContextPackChecksumError(ContextPackError):
    """Raised when Context Pack sidecar SHA-256 checksum does not match content."""


class ContextPackUnavailableError(ContextPackError):
    """Raised when Context Pack is unavailable, unreviewed, or draft in production."""


class ContextPackSelection(BaseModel):
    model_config = ConfigDict(frozen=True)

    selected_terms: dict[str, str]
    selected_rules: tuple[dict[str, str], ...]
    selected_examples: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class ContextPack:
    pack_version: str
    review_status: str
    reviewer: str
    review_date: str
    source_title: str
    source_publisher: str
    source_url: str
    source_published_at: str
    terms: dict[str, str]
    rewrite_rules: tuple[dict[str, str], ...]
    examples: tuple[dict[str, str], ...]
    checksum: str

    def select_terms(self, text: str, max_terms: int = 10) -> dict[str, str]:
        """Deterministically select matching terms from text."""
        matched: dict[str, str] = {}
        # Sort keys deterministically by length descending then alphabetically
        sorted_keys = sorted(self.terms.keys(), key=lambda k: (-len(k), k))
        for key in sorted_keys:
            if key in text:
                matched[key] = self.terms[key]
                if len(matched) >= max_terms:
                    break
        return matched

    def select_context(self, text: str, limit: int = 5) -> ContextPackSelection:
        """Select matching terms, rules, and examples with stable size limit."""
        terms = self.select_terms(text, max_terms=limit)
        rules = self.rewrite_rules[:limit]
        examples = self.examples[:limit]
        return ContextPackSelection(
            selected_terms=terms,
            selected_rules=rules,
            selected_examples=examples,
        )

    @classmethod
    def from_dict(cls, data: dict[str, object], checksum: str) -> Self:
        return cls(
            pack_version=str(data.get("version", "")),
            review_status=str(data.get("review_status", "")),
            reviewer=str(data.get("reviewer", "")),
            review_date=str(data.get("review_date", "")),
            source_title=str(data.get("title", "")),
            source_publisher=str(data.get("publisher", "")),
            source_url=str(data.get("url", "")),
            source_published_at=str(data.get("published_at", "")),
            terms=dict(data.get("terms", {})),  # type: ignore[arg-type]
            rewrite_rules=tuple(data.get("rewrite_rules", ())),  # type: ignore[arg-type]
            examples=tuple(data.get("examples", ())),  # type: ignore[arg-type]
            checksum=checksum,
        )


def load_context_pack(*, allow_draft: bool = False) -> ContextPack:
    """Load and validate the Easy Korean Context Pack package resource."""
    resources_dir = importlib.resources.files("app.agents.language.resources")
    json_file = resources_dir.joinpath("easy_korean_rules.v1.json")
    sha256_file = resources_dir.joinpath("easy_korean_rules.v1.sha256")

    if not json_file.is_file() or not sha256_file.is_file():
        raise ContextPackUnavailableError("Context Pack resource files missing")

    json_bytes = json_file.read_bytes()
    expected_checksum = sha256_file.read_text(encoding="utf-8").strip().lower()
    actual_checksum = hashlib.sha256(json_bytes).hexdigest().lower()

    if actual_checksum != expected_checksum:
        raise ContextPackChecksumError(
            f"Checksum mismatch: expected {expected_checksum[:8]}, got {actual_checksum[:8]}"
        )

    try:
        data = json.loads(json_bytes.decode("utf-8"))
    except Exception as err:
        raise ContextPackUnavailableError(f"Failed to parse Context Pack JSON: {err}") from err

    review_status = str(data.get("review_status", ""))
    reviewer = str(data.get("reviewer", "")).strip()
    review_date = str(data.get("review_date", "")).strip()

    if not allow_draft:
        if review_status != "approved":
            raise ContextPackUnavailableError(
                f"Context Pack review_status is '{review_status}', expected 'approved'"
            )
        if not reviewer:
            raise ContextPackUnavailableError("Context Pack missing reviewer")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", review_date):
            raise ContextPackUnavailableError("Context Pack review_date must be YYYY-MM-DD")

    return ContextPack.from_dict(data, actual_checksum)


__all__ = [
    "ContextPack",
    "ContextPackChecksumError",
    "ContextPackError",
    "ContextPackSelection",
    "ContextPackUnavailableError",
    "load_context_pack",
]
