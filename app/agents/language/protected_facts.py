import re
import unicodedata
from datetime import date
from typing import Literal

from .contracts import FrozenContract, RequestContext

ProtectedTokenKind = Literal[
    "date",
    "time",
    "number",
    "amount",
    "currency",
    "unit",
    "url",
    "email",
    "phone",
    "document_identifier",
    "version",
]


class ProtectedToken(FrozenContract):
    kind: ProtectedTokenKind
    source_path: str
    surface: str
    canonical_value: str


class ProtectedFacts(FrozenContract):
    request_reason: str
    requested_items: tuple[str, ...]
    deadline: date
    submission_method: str
    machine_tokens: tuple[ProtectedToken, ...]

    @classmethod
    def from_request_context(cls, context: RequestContext) -> "ProtectedFacts":
        request_reason = _normalize(context.request_reason)
        requested_items = tuple(_normalize(item) for item in context.requested_items)
        submission_method = _normalize(context.submission_method)
        source_values = (
            ("request_reason", request_reason),
            *( (f"requested_items[{index}]", item) for index, item in enumerate(requested_items) ),
            ("deadline", context.deadline.isoformat()),
            ("submission_method", submission_method),
        )
        machine_tokens = tuple(
            token
            for source_path, value in source_values
            for token in _extract_tokens(source_path, value)
        )
        return cls(
            request_reason=request_reason,
            requested_items=requested_items,
            deadline=context.deadline,
            submission_method=submission_method,
            machine_tokens=machine_tokens,
        )


_TOKEN_PATTERNS: tuple[tuple[ProtectedTokenKind, re.Pattern[str]], ...] = (
    ("url", re.compile(r"https?://[^\s<>\[\]{}\"]+")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    (
        "date",
        re.compile(
            r"(?<![A-Za-z0-9])(?:\d{4}-\d{1,2}-\d{1,2}|"
            r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일?|"
            r"\d{4}[./]\s*\d{1,2}[./]\s*\d{1,2})(?![A-Za-z0-9])"
        ),
    ),
    (
        "time",
        re.compile(
            r"(?<![A-Za-z0-9])(?:\d{1,2}:\d{2}(?::\d{2})?|"
            r"\d{1,2}시(?:\s*\d{1,2}분)?)(?![A-Za-z0-9])"
        ),
    ),
    (
        "phone",
        re.compile(r"(?<![A-Za-z0-9])\+?\d{1,3}(?:[- ]\d{1,4}){3,4}(?![A-Za-z0-9])"),
    ),
    (
        "currency",
        re.compile(
            r"(?:(?<![A-Za-z0-9])(?:USD|KRW|EUR|JPY|GBP|CNY|₩)(?![A-Za-z0-9])|"
            r"(?<=\d)(?:억원|만원|천원|원)(?![A-Za-z0-9]))"
        ),
    ),
    (
        "unit",
        re.compile(
            r"(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
            r"(?:kg|g|mg|L|ml|cm|m|개|명|건|부|장|회|일|%|퍼센트)"
            r"(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "amount",
        re.compile(
            r"(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+)"
            r"(?![A-Za-z0-9])"
        ),
    ),
    (
        "document_identifier",
        re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{2,}(?:-[A-Za-z0-9]+)+(?:\.\d+)?(?![A-Za-z0-9])"),
    ),
    ("version", re.compile(r"(?<![A-Za-z0-9])v\d+(?:\.\d+)+(?![A-Za-z0-9])", re.IGNORECASE)),
    ("number", re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?![A-Za-z0-9])")),
)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def _canonicalize(kind: ProtectedTokenKind, surface: str) -> str:
    if kind == "amount":
        return surface.replace(",", "")
    if kind == "unit":
        return surface.lower()
    if kind == "date":
        date_patterns = (
            re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),
            re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일?"),
            re.compile(r"(\d{4})[./]\s*(\d{1,2})[./]\s*(\d{1,2})"),
        )
        for pattern in date_patterns:
            match = pattern.fullmatch(surface)
            if match:
                try:
                    return date(*(int(part) for part in match.groups())).isoformat()
                except ValueError:
                    return surface
    return surface


def _extract_tokens(source_path: str, value: str) -> tuple[ProtectedToken, ...]:
    matches: list[tuple[int, int, ProtectedTokenKind, str]] = []
    occupied: list[tuple[int, int]] = []
    for kind, pattern in _TOKEN_PATTERNS:
        for match in pattern.finditer(value):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            surface = match.group(0)
            if kind == "url":
                surface = surface.rstrip(".,;:!?")
            matches.append((span[0], span[1], kind, surface))
            occupied.append(span)
            if kind == "unit":
                numeric_match = re.match(
                    r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)",
                    surface,
                )
                if numeric_match and not surface[numeric_match.end() :].startswith("."):
                    number_surface = numeric_match.group(0)
                    matches.append(
                        (
                            span[0],
                            span[0] + len(number_surface),
                            "number",
                            number_surface,
                        )
                    )
    matches.sort(key=lambda item: (item[0], item[1]))
    return tuple(
        ProtectedToken(
            kind=kind,
            source_path=source_path,
            surface=surface,
            canonical_value=_canonicalize(kind, surface),
        )
        for _, _, kind, surface in matches
    )
