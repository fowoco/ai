import logging
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.agents.language.contracts import (
    LanguageExecutionPolicy,
    RequestContext,
    SupportedLanguage,
    ValidationCheckId,
    WarningCode,
)
from app.agents.language.generation.models import (
    EasyKoreanDraft,
    SemanticValidationDraft,
    StructuredGenerator,
    TranslationDraft,
)
from app.agents.language.ports import (
    SemanticValidationDecision,
    SemanticValidationPort,
)

logger = logging.getLogger(__name__)


def normalize_date_string(value: str) -> date | None:
    """Normalize surface date expressions into a canonical datetime.date object."""
    if not value or not isinstance(value, str):
        return None

    # Match YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD
    match_iso = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", value)
    if match_iso:
        y, m, d = int(match_iso.group(1)), int(match_iso.group(2)), int(match_iso.group(3))
        try:
            return date(y, m, d)
        except ValueError:
            return None

    # Match YYYY년 M월 D일
    match_ko = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?", value)
    if match_ko:
        y, m, d = int(match_ko.group(1)), int(match_ko.group(2)), int(match_ko.group(3))
        try:
            return date(y, m, d)
        except ValueError:
            return None

    return None


def _extract_machine_tokens(text: str) -> list[str]:
    """Extract machine-checkable tokens (numbers, currencies, URLs, emails, phones)."""
    tokens: list[str] = []
    if not text:
        return tokens

    current_text = text

    # URLs
    urls = re.findall(r"https?://\S+", current_text)
    tokens.extend(urls)
    current_text = re.sub(r"https?://\S+", "", current_text)

    # Emails
    emails = re.findall(r"[\w.-]+@[\w.-]+\.\w+", current_text)
    tokens.extend(emails)
    current_text = re.sub(r"[\w.-]+@[\w.-]+\.\w+", "", current_text)

    # Phone numbers
    phones = re.findall(r"\b\d{2,4}-\d{3,4}-\d{4}\b", current_text)
    tokens.extend(phones)
    current_text = re.sub(r"\b\d{2,4}-\d{3,4}-\d{4}\b", "", current_text)

    # Full dates (ISO or Korean)
    current_text = re.sub(r"\d{4}[-./년]\s*\d{1,2}[-./월]?\s*\d{1,2}일?", "", current_text)

    # Currencies with numbers (e.g., 100,000원, $500, 50,000 원)
    currencies = re.findall(r"\d{1,3}(?:,\d{3})*\s*(?:원|\$|USD|EUR|JPY)", current_text)
    for curr in currencies:
        tokens.append(curr.replace(" ", ""))
    current_text = re.sub(r"\d{1,3}(?:,\d{3})*\s*(?:원|\$|USD|EUR|JPY)", "", current_text)

    # Standalone numbers
    numbers = re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", current_text)
    for num in numbers:
        tokens.append(num.replace(",", ""))

    return tokens


def validate_deterministic(
    *,
    request_context: RequestContext,
    candidate: EasyKoreanDraft | TranslationDraft | str,
    candidate_items: Sequence[str] | None = None,
) -> tuple[ValidationCheckId, ...]:
    """Perform deterministic machine checks comparing candidate against request_context."""
    failed_checks: list[ValidationCheckId] = []

    # Extract text representation
    cand_reason = ""
    cand_sub_method = ""
    cand_items: Sequence[str] = ()

    if isinstance(candidate, EasyKoreanDraft):
        cand_reason = candidate.request_reason
        cand_items = candidate.requested_items
        cand_sub_method = candidate.submission_method
    elif isinstance(candidate, TranslationDraft):
        cand_reason = candidate.translated_reason
        cand_items = candidate.translated_items
        cand_sub_method = candidate.translated_submission_method
    elif isinstance(candidate, str):
        cand_reason = candidate
        if candidate_items is not None:
            cand_items = candidate_items
    else:
        cand_reason = str(candidate)

    # Check reason present
    if not cand_reason or not cand_reason.strip():
        failed_checks.append("request_reason.present")

    # Check submission method present (if draft model)
    if isinstance(candidate, (EasyKoreanDraft, TranslationDraft)) and (
        not cand_sub_method or not cand_sub_method.strip()
    ):
        failed_checks.append("submission_method.present")

    # Check item cardinality
    if isinstance(candidate, (EasyKoreanDraft, TranslationDraft)) or candidate_items is not None:
        if len(cand_items) != len(request_context.requested_items):
            failed_checks.append("requested_items.cardinality")

    # Check canonical deadline date
    full_cand_text = f"{cand_reason} {' '.join(cand_items)} {cand_sub_method}"
    cand_date = normalize_date_string(full_cand_text)
    if cand_date is not None and cand_date != request_context.deadline:
        failed_checks.append("deadline.canonical_value")

    # Check machine tokens multiset
    src_text = (
        f"{request_context.request_reason} "
        f"{' '.join(request_context.requested_items)} "
        f"{request_context.submission_method}"
    )
    src_tokens = _extract_machine_tokens(src_text)
    cand_tokens = _extract_machine_tokens(full_cand_text)

    src_counts = Counter(src_tokens)
    cand_counts = Counter(cand_tokens)

    # Check missing required tokens
    missing_token = False
    for tok, count in src_counts.items():
        if cand_counts[tok] < count:
            missing_token = True
            break

    if missing_token:
        failed_checks.append("machine_tokens.multiset")

    # Check extra unapproved tokens added
    extra_token = False
    for tok, count in cand_counts.items():
        if count > src_counts[tok]:
            extra_token = True
            break

    if extra_token:
        failed_checks.append("facts.no_addition")

    return tuple(failed_checks)


class GeneratedSemanticValidator(SemanticValidationPort):
    """Semantic validator adapter backed by StructuredGenerator."""

    def __init__(self, generator: StructuredGenerator) -> None:
        self.generator = generator

    def validate(
        self,
        *,
        component: Literal["easy_korean", "translation"],
        request_context: RequestContext,
        target_language: SupportedLanguage | None,
        candidate: str,
    ) -> SemanticValidationDecision:
        # Build narrow payload without parent context or retrieval truth
        payload = {
            "request_context": {
                "request_reason": request_context.request_reason,
                "requested_items": list(request_context.requested_items),
                "deadline": request_context.deadline.isoformat(),
                "submission_method": request_context.submission_method,
            },
            "component": component,
            "target_language": target_language,
            "candidate": candidate,
        }

        try:
            draft = self.generator.generate(
                operation="semantic_validation",
                payload=payload,
                response_model=SemanticValidationDraft,
            )
            if draft.status == "passed":
                return SemanticValidationDecision(status="passed")
            if draft.status == "failed":
                return SemanticValidationDecision(
                    status="failed",
                    failed_checks=draft.failed_checks,
                )
            return SemanticValidationDecision(
                status="inconclusive",
                inconclusive_checks=draft.inconclusive_checks,
            )
        except Exception:
            # LLM provider / schema failure becomes typed unavailable / inconclusive
            return SemanticValidationDecision(
                status="inconclusive",
                unavailable=True,
                inconclusive_checks=("facts.no_semantic_addition",),
            )


@dataclass(frozen=True)
class CorrectionResult:
    draft: BaseModel | None
    status: Literal["passed", "failed", "inconclusive"]
    retry_count: int
    failed_checks: tuple[ValidationCheckId, ...]
    inconclusive_checks: tuple[ValidationCheckId, ...]
    warnings: tuple[WarningCode, ...]
    requires_human_review: bool
    time_budget_exceeded: bool
    generation_error_code: str | None = None


class BoundedCorrectionController:
    """Controller enforcing max 2 retries and LanguageExecutionPolicy time budget."""

    def __init__(self, policy: LanguageExecutionPolicy | None = None) -> None:
        self.policy = policy or LanguageExecutionPolicy()

    def run(
        self,
        *,
        component: Literal["easy_korean", "translation"],
        request_context: RequestContext,
        target_language: SupportedLanguage | None,
        generate_fn: object,
        validator: SemanticValidationPort,
        draft_model: type[BaseModel],
    ) -> CorrectionResult:
        start_time = self.policy.monotonic()
        deadline = start_time + self.policy.branch_time_budget_seconds

        retries_remaining = self.policy.max_correction_retries
        attempts = 0
        last_draft: BaseModel | None = None
        last_failed_checks: tuple[ValidationCheckId, ...] = ()
        last_inconclusive_checks: tuple[ValidationCheckId, ...] = ()
        warnings: list[WarningCode] = []
        time_budget_exceeded = False
        generation_error_code: str | None = None

        while True:
            # Check remaining time budget before scheduling generation/correction call
            current_time = self.policy.monotonic()
            if current_time >= deadline:
                time_budget_exceeded = True
                warnings.append(WarningCode.GENERATION_TIME_BUDGET_EXCEEDED)
                break

            # Execute generation call
            is_correction = attempts > 0
            correction_payload = {}
            if is_correction and last_draft is not None:
                correction_payload = {
                    "request_context": {
                        "request_reason": request_context.request_reason,
                        "requested_items": list(request_context.requested_items),
                        "deadline": request_context.deadline.isoformat(),
                        "submission_method": request_context.submission_method,
                    },
                    "component": component,
                    "target_language": target_language,
                    "last_draft": last_draft.model_dump(),
                    "failed_checks": list(last_failed_checks),
                    "inconclusive_checks": list(last_inconclusive_checks),
                }

            try:
                if callable(generate_fn):
                    current_draft = generate_fn(is_correction, correction_payload)
                else:
                    break
                last_draft = current_draft
            except Exception as exc:
                error_code = getattr(exc, "code", "GENERATION_FAILED")
                if not isinstance(error_code, str):
                    error_code = "GENERATION_FAILED"
                request_id = getattr(exc, "request_id", None)
                if not isinstance(request_id, str):
                    request_id = "unavailable"
                logger.warning(
                    "language_generation_failed component=%s error_code=%s "
                    "error_type=%s provider_request_id=%s correction=%s",
                    component,
                    error_code,
                    type(exc).__name__,
                    request_id,
                    is_correction,
                )
                generation_error_code = error_code
                if attempts == 0:
                    # Hard generation failure on initial attempt
                    return CorrectionResult(
                        draft=None,
                        status="failed",
                        retry_count=0,
                        failed_checks=(),
                        inconclusive_checks=(),
                        warnings=(),
                        requires_human_review=True,
                        time_budget_exceeded=False,
                        generation_error_code=generation_error_code,
                    )
                break

            # Hard deterministic validation
            hard_checks = validate_deterministic(
                request_context=request_context,
                candidate=current_draft,  # type: ignore[arg-type]
            )

            # Candidate text for semantic validator
            cand_text = ""
            if isinstance(current_draft, EasyKoreanDraft):
                cand_text = (
                    f"{current_draft.request_reason} "
                    f"{' '.join(current_draft.requested_items)} "
                    f"{current_draft.submission_method}"
                )
            elif isinstance(current_draft, TranslationDraft):
                cand_text = (
                    f"{current_draft.translated_reason} "
                    f"{' '.join(current_draft.translated_items)} "
                    f"{current_draft.translated_submission_method}"
                )
            else:
                cand_text = str(current_draft)

            # Semantic validation
            sem_decision = validator.validate(
                component=component,
                request_context=request_context,
                target_language=target_language,
                candidate=cand_text,
            )

            # Combine checks
            combined_failed = tuple(dict.fromkeys(hard_checks + sem_decision.failed_checks))
            combined_inconclusive = sem_decision.inconclusive_checks

            last_failed_checks = combined_failed
            last_inconclusive_checks = combined_inconclusive

            if sem_decision.unavailable:
                warnings.append(WarningCode.SEMANTIC_VALIDATION_INCONCLUSIVE)
                return CorrectionResult(
                    draft=last_draft,
                    status="inconclusive",
                    retry_count=attempts,
                    failed_checks=combined_failed,
                    inconclusive_checks=combined_inconclusive,
                    warnings=tuple(warnings),
                    requires_human_review=True,
                    time_budget_exceeded=time_budget_exceeded,
                )

            if not combined_failed and not combined_inconclusive:
                return CorrectionResult(
                    draft=last_draft,
                    status="passed",
                    retry_count=attempts,
                    failed_checks=(),
                    inconclusive_checks=(),
                    warnings=tuple(warnings),
                    requires_human_review=False,
                    time_budget_exceeded=time_budget_exceeded,
                )

            # Need correction retry
            if retries_remaining > 0:
                retries_remaining -= 1
                attempts += 1
            else:
                warnings.append(WarningCode.VALIDATION_RETRY_EXCEEDED)
                break

        # Max retries exhausted, budget expired, or error occurred
        final_status: Literal["passed", "failed", "inconclusive"] = "failed"
        if last_inconclusive_checks and not last_failed_checks:
            final_status = "inconclusive"

        return CorrectionResult(
            draft=last_draft,
            status=final_status,
            retry_count=attempts,
            failed_checks=last_failed_checks,
            inconclusive_checks=last_inconclusive_checks,
            warnings=tuple(warnings),
            requires_human_review=True,
            time_budget_exceeded=time_budget_exceeded,
            generation_error_code=generation_error_code,
        )


__all__ = [
    "BoundedCorrectionController",
    "CorrectionResult",
    "GeneratedSemanticValidator",
    "normalize_date_string",
    "validate_deterministic",
]
